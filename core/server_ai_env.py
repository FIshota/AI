"""
サーバーAI環境 (Server AI Environment)
Sprint J: Ubuntuサーバー上のアイ専用Docker環境を管理する。

機能:
- アイ専用コンテナのライフサイクル管理
- 知識ベースの同期（Mac ↔ Server）
- サーバーメトリクス取得（Prometheus連携）
- サーバー側バッチ学習ジョブ
"""
from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.server_home import ServerHome

# アイ専用コンテナの設定
AICHAN_CONTAINER = "ai-chan-ml"
AICHAN_IMAGE = "python:3.11-slim"
AICHAN_REMOTE_DIR = "/home/{user}/ai-chan"


class ServerAIEnv:
    """
    サーバー上のアイ専用AI環境を管理する。

    使い方:
      env = ServerAIEnv(server_home)
      env.ensure_container_running()
      env.run_ml_job("train.py", ["--epochs", "10"])
    """

    def __init__(self, server_home: ServerHome):
        self._server = server_home
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._server.enabled

    def container_status(self) -> dict:
        """コンテナの状態を取得する"""
        if not self.enabled:
            return {"status": "disabled"}

        result = self._server.run_command(
            f"docker inspect --format '{{{{.State.Status}}}}' {AICHAN_CONTAINER}"
        )
        if result.get("ok"):
            return {
                "status": result["stdout"].strip(),
                "container": AICHAN_CONTAINER,
            }
        return {"status": "not_found"}

    def ensure_container_running(self) -> dict:
        """コンテナが稼働中でなければ起動する"""
        if not self.enabled:
            return {"ok": False, "error": "サーバー無効"}

        status = self.container_status()

        if status["status"] == "running":
            return {"ok": True, "action": "already_running"}

        if status["status"] == "not_found":
            # コンテナ作成
            user = self._server._settings.get("username", "admin")
            remote_dir = AICHAN_REMOTE_DIR.format(user=user)
            create_cmd = (
                f"docker run -d --name {AICHAN_CONTAINER} "
                f"-v {remote_dir}:/workspace "
                f"--restart unless-stopped "
                f"{AICHAN_IMAGE} "
                f"tail -f /dev/null"
            )
            result = self._server.run_command(create_cmd)
            return {"ok": result.get("ok", False), "action": "created"}

        # 停止中なら再起動
        result = self._server.docker_control(AICHAN_CONTAINER, "start")
        return {"ok": result.get("ok", False), "action": "started"}

    def run_ml_job(self, script: str, args: list[str] | None = None) -> dict:
        """コンテナ内でスクリプトを実行する"""
        if not self.enabled:
            return {"ok": False, "error": "サーバー無効"}

        args_str = " ".join(args) if args else ""
        cmd = f"docker exec {AICHAN_CONTAINER} python /workspace/{script} {args_str}"
        return self._server.run_command(cmd)

    def get_status_text(self) -> str:
        """コンテナ状態のテキスト"""
        status = self.container_status()
        s = status["status"]
        if s == "disabled":
            return "🤖 AI環境: 未設定"
        if s == "running":
            return f"🤖 AI環境: ✅ 稼働中 ({AICHAN_CONTAINER})"
        if s == "not_found":
            return "🤖 AI環境: 未作成（「サーバーAI環境セットアップ」で作成）"
        return f"🤖 AI環境: {s}"


# ─── 知識同期 ────────────────────────────────────────────

class KnowledgeSync:
    """Mac ↔ Server 間の知識ベース同期"""

    def __init__(self, base_dir: Path, server_home: ServerHome):
        self._base = base_dir
        self._server = server_home
        self._state_path = base_dir / "data" / ".sync_state.json"
        self._lock = threading.Lock()

    def push_knowledge(self) -> dict:
        """ローカルの学習データをサーバーに転送する"""
        if not self._server.enabled:
            return {"ok": False, "error": "サーバー無効"}

        learning_dir = self._base / "data" / "learning"
        if not learning_dir.exists():
            return {"ok": False, "error": "学習データなし"}

        # ディレクトリハッシュで変更チェック
        current_hash = self._dir_hash(learning_dir)
        state = self._load_state()
        if state.get("last_push_hash") == current_hash:
            return {"ok": True, "action": "no_changes"}

        try:
            # tar.gz にまとめる
            tmp = tempfile.NamedTemporaryFile(
                suffix=".tar.gz", prefix="aichan_knowledge_", delete=False
            )
            tmp.close()
            with tarfile.open(tmp.name, "w:gz") as tar:
                tar.add(str(learning_dir), arcname="learning")

            # サーバーに転送
            user = self._server._settings.get("username", "admin")
            remote_dir = f"/home/{user}/ai-chan/knowledge"
            self._server.run_command(f"mkdir -p {remote_dir}")
            result = self._server.push_file(
                Path(tmp.name),
                f"{remote_dir}/knowledge_sync.tar.gz",
            )

            if result.get("ok"):
                # サーバー側で展開
                self._server.run_command(
                    f"cd {remote_dir} && tar xzf knowledge_sync.tar.gz"
                )
                state["last_push_hash"] = current_hash
                state["last_push_at"] = datetime.now(timezone.utc).isoformat()
                self._save_state(state)

            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    def pull_knowledge(self) -> dict:
        """サーバーから新しい知識をダウンロードする"""
        if not self._server.enabled:
            return {"ok": False, "error": "サーバー無効"}

        try:
            user = self._server._settings.get("username", "admin")
            remote_dir = f"/home/{user}/ai-chan/knowledge"

            # サーバー上の新しいファイルを確認
            result = self._server.run_command(
                f"ls -1 {remote_dir}/server_output/ 2>/dev/null"
            )
            if not result.get("ok") or not result.get("stdout", "").strip():
                return {"ok": True, "action": "nothing_to_pull"}

            # ダウンロード先
            sync_dir = self._base / "data" / "learning" / "server_sync"
            sync_dir.mkdir(parents=True, exist_ok=True)

            files = result["stdout"].strip().splitlines()
            pulled = 0
            for fname in files[:10]:  # 最大10ファイル
                fname = fname.strip()
                if not fname.endswith((".json", ".jsonl", ".txt")):
                    continue
                pull_result = self._server.pull_file(
                    f"{remote_dir}/server_output/{fname}",
                    sync_dir / fname,
                )
                if pull_result.get("ok"):
                    pulled += 1

            return {"ok": True, "pulled": pulled}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_sync_status(self) -> str:
        """同期状態のテキスト"""
        state = self._load_state()
        last = state.get("last_push_at", "")
        if last:
            return f"📡 最終同期: {last[:19]}"
        return "📡 同期: 未実行"

    @staticmethod
    def _dir_hash(directory: Path) -> str:
        """ディレクトリ内容のハッシュ（変更検出用）"""
        h = hashlib.sha256()
        for p in sorted(directory.rglob("*")):
            if p.is_file():
                h.update(p.name.encode())
                h.update(str(p.stat().st_mtime).encode())
        return h.hexdigest()[:16]

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self, state: dict) -> None:
        with self._lock:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)


# ─── Prometheus連携 ──────────────────────────────────────

class PrometheusReader:
    """サーバーのPrometheusからメトリクスを取得する"""

    def __init__(self, server_home: ServerHome):
        self._server = server_home

    def get_server_health_summary(self) -> dict:
        """サーバーの健全性サマリーを返す"""
        if not self._server.enabled:
            return {"status": "disabled"}

        result: dict = {"status": "ok"}

        # CPU使用率
        cpu_result = self._server.run_command(
            "curl -s 'localhost:9090/api/v1/query?query=100-(avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m]))*100)' 2>/dev/null"
        )
        if cpu_result.get("ok"):
            try:
                data = json.loads(cpu_result["stdout"])
                val = data["data"]["result"][0]["value"][1]
                result["cpu_percent"] = round(float(val), 1)
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                pass

        # メモリ使用率
        mem_result = self._server.run_command(
            "curl -s 'localhost:9090/api/v1/query?query=100*(1-node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes)' 2>/dev/null"
        )
        if mem_result.get("ok"):
            try:
                data = json.loads(mem_result["stdout"])
                val = data["data"]["result"][0]["value"][1]
                result["memory_percent"] = round(float(val), 1)
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                pass

        # ディスク使用率
        disk_result = self._server.run_command(
            "curl -s 'localhost:9090/api/v1/query?query=100*(1-node_filesystem_free_bytes{mountpoint=\"/\"}/node_filesystem_size_bytes{mountpoint=\"/\"})' 2>/dev/null"
        )
        if disk_result.get("ok"):
            try:
                data = json.loads(disk_result["stdout"])
                val = data["data"]["result"][0]["value"][1]
                result["disk_percent"] = round(float(val), 1)
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                pass

        return result

    def get_summary_text(self) -> str:
        """Prometheus メトリクスの日本語サマリー"""
        health = self.get_server_health_summary()
        if health.get("status") == "disabled":
            return "📊 サーバーメトリクス: 未接続"

        parts: list[str] = ["📊 サーバーメトリクス:"]
        if "cpu_percent" in health:
            parts.append(f"  CPU: {health['cpu_percent']}%")
        if "memory_percent" in health:
            parts.append(f"  メモリ: {health['memory_percent']}%")
        if "disk_percent" in health:
            parts.append(f"  ディスク: {health['disk_percent']}%")

        if len(parts) == 1:
            parts.append("  データ取得できず")

        return "\n".join(parts)


# ─── 自律エンジン用ジョブファクトリ ──────────────────────

def build_sync_job(knowledge_sync: KnowledgeSync):
    """6時間ごとの知識同期ジョブを返す"""
    def _job() -> dict:
        push = knowledge_sync.push_knowledge()
        pull = knowledge_sync.pull_knowledge()
        return {
            "action": "knowledge_sync",
            "push": push.get("ok", False),
            "pull": pull.get("ok", False),
        }
    return _job


def build_server_health_job(prometheus: PrometheusReader):
    """毎時のサーバーヘルスチェックジョブを返す"""
    def _job() -> dict:
        return {
            "action": "server_metrics",
            **prometheus.get_server_health_summary(),
        }
    return _job

"""
サーバーホーム (Server Home)
Sprint J: アイの「家」としてUbuntuサーバーに接続・管理する。

機能:
- SSH接続管理（認証情報は暗号化保存）
- リモートコマンド実行（許可リスト制御）
- ファイル転送（SFTP）
- Docker コンテナ管理
- サーバーヘルスチェック

倫理規定: 許可リスト外のコマンドは絶対に実行しない。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import paramiko
    PARAMIKO_OK = True
except (ImportError, OSError):
    # cffi アーキテクチャ不整合など、ImportError 以外の OSError も捕捉
    PARAMIKO_OK = False

try:
    from cryptography.fernet import Fernet
    FERNET_OK = True
except (ImportError, OSError):
    FERNET_OK = False

# ─── コマンド許可リスト (defense-in-depth) ──────────────────────────────
#
# 歴史: 2026-04-21 以前、この allowlist は以下の致命的問題を持っていた:
#   1. "rm -rf /home" が含まれており、startswith マッチで
#      "rm -rf /home/../.." のような path traversal が全て通過していた
#   2. 単体の "cat", "ls", "pwd", "mkdir" が含まれており
#      "cat /etc/shadow", "ls /root/.ssh/" 等が全て通過していた
#
# 現在の方針:
#   - rm 系は完全禁止 (ファイル削除は allowlist しない)
#   - 曖昧な単語プレフィックスを排除し、具体的な形で列挙
#   - ファイル操作は /home/ 配下に限定
#   - _is_allowed() で path traversal / command substitution を追加拒否
#
# 注意: これは「完全な sandbox」ではなく defense-in-depth のみ。
#       run_command() への呼び出し元が信頼できる内部コードであることが大前提。
DEFAULT_ALLOWED_PREFIXES = [
    # Docker operations (container lifecycle + inspect only)
    "docker inspect ", "docker exec ", "docker ps", "docker logs ",
    "docker stats", "docker images", "docker create ",
    "docker start ", "docker stop ", "docker restart ",
    # Metrics over localhost only (Prometheus / health checks)
    "curl -s 'localhost:", "curl -s \"localhost:",
    "curl -s 'http://localhost:", "curl -s http://localhost:",
    "curl -s 'http://127.0.0.1:", "curl -s http://127.0.0.1:",
    "curl localhost:",
    # File operations — /home/ 配下に限定
    "mkdir -p /home/", "ls -1 /home/", "ls /home/", "cd /home/",
    # Read-only system info (literal or literal+args)
    "uptime", "whoami", "hostname", "uname",
    "df -h", "free -h", "top -bn1", "ps aux",
    "systemctl status ",
]

# コンテナ名のバリデーション
_SAFE_NAME = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$')

# _is_allowed() で拒否する危険パターン (defense-in-depth)
_DANGEROUS_PATTERNS = re.compile(
    r"(\.\.(?:/|\\|$))"          # path traversal
    r"|(\$\()"                   # command substitution $(...)
    r"|(`)"                      # command substitution backticks
    r"|(\x00)"                   # null byte
    r"|(\n|\r)"                  # newline-based chaining
    r"|(\brm\s+-?r)"             # rm -r / rm -rf (allowlist を通過しても禁止)
    r"|(/etc/shadow|/etc/passwd|/etc/sudoers)"  # 機密ファイル名 (明示)
)


@dataclass
class ServerCredentials:
    """サーバー認証情報"""
    host: str
    port: int
    username: str
    password: str = ""
    key_path: str = ""


class CredentialStore:
    """認証情報の暗号化保存・読み込み"""

    def __init__(self, base_dir: Path, key_file: Path | None = None):
        self._cred_path = base_dir / "data" / ".server_cred"
        self._key_file = key_file or (base_dir / "data" / ".key")

    def save(self, creds: ServerCredentials) -> bool:
        """認証情報を暗号化して保存する"""
        if not FERNET_OK:
            return False
        try:
            key = self._derive_key()
            fernet = Fernet(key)
            data = json.dumps({
                "host": creds.host,
                "port": creds.port,
                "username": creds.username,
                "password": creds.password,
                "key_path": creds.key_path,
            }).encode()
            encrypted = fernet.encrypt(data)
            self._cred_path.parent.mkdir(parents=True, exist_ok=True)
            self._cred_path.write_bytes(encrypted)
            return True
        except Exception:
            return False

    def load(self) -> ServerCredentials | None:
        """保存された認証情報を復号する"""
        if not FERNET_OK or not self._cred_path.exists():
            return None
        try:
            key = self._derive_key()
            fernet = Fernet(key)
            encrypted = self._cred_path.read_bytes()
            data = json.loads(fernet.decrypt(encrypted))
            return ServerCredentials(**data)
        except Exception:
            return None

    def _derive_key(self) -> bytes:
        """既存の.keyファイルからFernet鍵を導出する"""
        if self._key_file.exists():
            raw = self._key_file.read_bytes()[:32]
        else:
            raw = b"ai-chan-default-server-key-seed!"
        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)


class ServerHome:
    """
    アイのサーバーホーム接続管理。

    使い方:
      server = ServerHome(base_dir, settings)
      if server.is_reachable():
          health = server.health_check()
    """

    def __init__(self, base_dir: str | Path, settings: dict | None = None):
        self._base = Path(base_dir)
        self._settings = (settings or {}).get("server_home", {})
        self._enabled = self._settings.get("enabled", False)
        self._timeout = self._settings.get("connect_timeout_sec", 10)
        self._allowed = self._settings.get(
            "allowed_commands", DEFAULT_ALLOWED_PREFIXES
        )
        self._cred_store = CredentialStore(
            self._base,
            key_file=self._base / (settings or {}).get("security", {}).get("key_file", "data/.key"),
        )
        self._lock = threading.Lock()
        self._state_path = self._base / "data" / ".server_state.json"

        # Security migration: if settings.json still holds a plaintext password,
        # move it into the encrypted CredentialStore and wipe the plaintext.
        self._migrate_plaintext_credentials(settings)

    def _migrate_plaintext_credentials(self, settings: dict | None) -> None:
        """Move any plaintext password from settings.json into the encrypted store."""
        if not settings or not FERNET_OK:
            return
        sh = settings.get("server_home", {})
        pwd = sh.get("password", "")
        if not pwd or pwd in ("", "***", "REDACTED"):
            return
        try:
            creds = ServerCredentials(
                host=sh.get("host", ""),
                port=sh.get("port", 22),
                username=sh.get("username", ""),
                password=pwd,
                key_path=sh.get("key_path", ""),
            )
            if self._cred_store.save(creds):
                # Wipe plaintext from on-disk settings.json
                settings_path = self._base / "config" / "settings.json"
                try:
                    data = json.loads(settings_path.read_text(encoding="utf-8"))
                    if data.get("server_home", {}).get("password"):
                        data["server_home"]["password"] = ""
                        settings_path.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        logger.warning(
                            "[server_home] plaintext password migrated to encrypted store; "
                            "settings.json scrubbed"
                        )
                except OSError as e:
                    logger.warning("[server_home] could not scrub settings.json: %s", e)
        except Exception as e:
            logger.warning("[server_home] credential migration failed: %s", e)

    @property
    def enabled(self) -> bool:
        return self._enabled and PARAMIKO_OK

    # ─── 認証情報管理 ────────────────────────────────────────

    def setup_credentials(
        self, host: str, port: int, username: str, password: str
    ) -> bool:
        """サーバー認証情報を暗号化保存する"""
        creds = ServerCredentials(
            host=host, port=port, username=username, password=password
        )
        return self._cred_store.save(creds)

    # ─── 接続チェック ────────────────────────────────────────

    def is_reachable(self) -> bool:
        """サーバーにSSH接続できるか確認する"""
        if not self.enabled:
            return False
        try:
            with self._connect() as client:
                client.exec_command("echo ok", timeout=5)
                return True
        except Exception:
            return False

    # ─── リモートコマンド ────────────────────────────────────

    def run_command(self, cmd: str) -> dict:
        """
        許可リスト内のコマンドをリモート実行する。
        戻り値: {"ok": bool, "stdout": str, "stderr": str, "exit_code": int}
        """
        if not self.enabled:
            return {"ok": False, "error": "サーバー接続が無効です"}

        # 許可リストチェック
        if not self._is_allowed(cmd):
            return {
                "ok": False,
                "error": f"許可されていないコマンドです: {cmd[:50]}",
            }

        try:
            with self._connect() as client:
                stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
                exit_code = stdout.channel.recv_exit_status()
                return {
                    "ok": exit_code == 0,
                    "stdout": stdout.read().decode("utf-8", errors="replace")[:5000],
                    "stderr": stderr.read().decode("utf-8", errors="replace")[:2000],
                    "exit_code": exit_code,
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── ヘルスチェック ──────────────────────────────────────

    def health_check(self) -> dict:
        """サーバーの状態を総合チェックする"""
        result = {
            "reachable": False,
            "uptime": "",
            "disk_usage": "",
            "memory": "",
            "docker_running": 0,
        }

        if not self.enabled:
            result["error"] = "サーバー接続が無効です"
            return result

        try:
            with self._connect() as client:
                result["reachable"] = True
                result["ok"] = True

                # uptime
                _, out, _ = client.exec_command("uptime -p", timeout=5)
                result["uptime"] = out.read().decode().strip()

                # disk
                _, out, _ = client.exec_command("df -h / | tail -1", timeout=5)
                result["disk_usage"] = out.read().decode().strip()

                # memory
                _, out, _ = client.exec_command(
                    "free -h | grep Mem | awk '{print $3\"/\"$2}'", timeout=5
                )
                result["memory"] = out.read().decode().strip()

                # docker
                _, out, _ = client.exec_command(
                    "docker ps --format '{{.Names}}' | wc -l", timeout=5
                )
                try:
                    result["docker_running"] = int(out.read().decode().strip())
                except ValueError:
                    pass

        except Exception as e:
            result["error"] = str(e)

        # 状態を保存
        self._save_state(result)
        return result

    # ─── Docker 管理 ─────────────────────────────────────────

    def docker_ps(self) -> list[dict]:
        """実行中のDockerコンテナ一覧"""
        result = self.run_command(
            "docker ps --format '{{.Names}}\\t{{.Status}}\\t{{.Image}}'"
        )
        if not result.get("ok"):
            return []
        containers: list[dict] = []
        for line in result["stdout"].strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                containers.append({
                    "name": parts[0],
                    "status": parts[1],
                    "image": parts[2],
                })
        return containers

    def docker_control(self, container: str, action: str) -> dict:
        """コンテナの start/stop/restart"""
        if action not in ("start", "stop", "restart"):
            return {"ok": False, "error": f"不正なアクション: {action}"}
        if not _SAFE_NAME.match(container):
            return {"ok": False, "error": f"不正なコンテナ名: {container}"}
        return self.run_command(f"docker {action} {container}")

    # ─── ファイル転送 ────────────────────────────────────────

    def push_file(self, local_path: Path, remote_path: str) -> dict:
        """ローカルファイルをサーバーに転送する"""
        if not self.enabled:
            return {"ok": False, "error": "サーバー接続が無効です"}
        try:
            with self._connect() as client:
                sftp = client.open_sftp()
                sftp.put(str(local_path), remote_path)
                sftp.close()
                return {"ok": True, "remote_path": remote_path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pull_file(self, remote_path: str, local_path: Path) -> dict:
        """サーバーからファイルをダウンロードする"""
        if not self.enabled:
            return {"ok": False, "error": "サーバー接続が無効です"}
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as client:
                sftp = client.open_sftp()
                sftp.get(remote_path, str(local_path))
                sftp.close()
                return {"ok": True, "local_path": str(local_path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── サマリー ────────────────────────────────────────────

    def get_status_text(self) -> str:
        """サーバー状態の日本語サマリー"""
        if not self.enabled:
            return "🏠 サーバーホーム: 未設定\nサーバー接続を有効にするには「サーバー接続設定」と話しかけてね。"

        health = self.health_check()

        if not health.get("reachable"):
            error = health.get("error", "不明")
            return f"🏠 サーバーホーム: ❌ 接続不可\n  原因: {error}"

        lines: list[str] = ["🏠 サーバーホーム: ✅ 接続中"]
        if health["uptime"]:
            lines.append(f"  ⏱ 稼働時間: {health['uptime']}")
        if health["memory"]:
            lines.append(f"  💾 メモリ: {health['memory']}")
        if health["disk_usage"]:
            lines.append(f"  💿 ディスク: {health['disk_usage']}")
        lines.append(f"  🐳 Docker: {health['docker_running']} コンテナ稼働中")

        return "\n".join(lines)

    # ─── 自律エンジン用 ──────────────────────────────────────

    def hourly_job(self) -> dict:
        """毎時のサーバーヘルスチェック"""
        if not self.enabled:
            return {"action": "server_health", "status": "disabled"}
        health = self.health_check()
        return {
            "action": "server_health",
            "reachable": health.get("reachable", False),
            "docker_running": health.get("docker_running", 0),
        }

    # ─── private ─────────────────────────────────────────────

    def _connect(self):
        """SSHクライアントを生成して接続する（コンテキストマネージャ用）"""
        if not PARAMIKO_OK:
            raise RuntimeError("paramiko がインストールされていません")

        creds = self._cred_store.load()
        if creds is None:
            # settings.json からフォールバック
            creds = ServerCredentials(
                host=self._settings.get("host", "192.168.3.86"),
                port=self._settings.get("port", 22),
                username=self._settings.get("username", ""),
                password=self._settings.get("password", ""),
            )

        if not creds.host or not creds.username:
            raise RuntimeError("サーバー認証情報が設定されていません")

        client = paramiko.SSHClient()
        # Security: load known_hosts first (default ~/.ssh/known_hosts).
        # Reject unknown hosts unless the user explicitly opts into TOFU mode
        # via settings.ssh_trust_on_first_use = true. This closes B507.
        try:
            client.load_system_host_keys()
        except Exception as e:
            logger.warning("load_system_host_keys failed: %s", e)
        tofu = bool(self._settings.get("ssh_trust_on_first_use", False))
        if tofu:
            # TOFU: add on first connect, but still verify on subsequent ones.
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507 — opt-in TOFU
        else:
            # Default: refuse unknown host keys
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            hostname=creds.host,
            port=creds.port,
            username=creds.username,
            password=creds.password if creds.password else None,
            key_filename=creds.key_path if creds.key_path else None,
            timeout=self._timeout,
            banner_timeout=self._timeout,
        )
        return client

    def _is_allowed(self, cmd: str) -> bool:
        """コマンドが許可リストに含まれるか確認する.

        多層検査:
          1. 危険パターン (path traversal / command substitution / rm 系) を拒否
          2. allowlist の prefix にマッチするか確認
        """
        cmd_stripped = cmd.strip()
        if not cmd_stripped:
            return False
        # 1. 危険パターンは allowlist に関わらず拒否
        if _DANGEROUS_PATTERNS.search(cmd_stripped):
            logger.warning(
                "server_home: rejected dangerous pattern in command: %r",
                cmd_stripped[:100],
            )
            return False
        # 2. allowlist prefix マッチ
        for prefix in self._allowed:
            if cmd_stripped.startswith(prefix):
                return True
        return False

    def _save_state(self, state: dict) -> None:
        with self._lock:
            state["checked_at"] = datetime.now(timezone.utc).isoformat()
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

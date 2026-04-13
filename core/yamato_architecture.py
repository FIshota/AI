"""
7層アーキテクチャ基盤 (Yamato 7-Layer Architecture)
ヤマト計画 A3: AIシステム全体を7層で管理・可視化する基盤。

層構造:
  L1. インフラ層        — ハードウェア/OS/ストレージ監視
  L2. 分散処理層        — マルチモデル管理・ルーティング (MoE連携)
  L3. データ管理層      — 記憶・知識グラフ・学習データ
  L4. モデル層          — LLM推論・パラメータ管理
  L5. 学習制御層        — 継続学習・蒸留・カリキュラム
  L6. 推論最適化層      — キャッシュ・バッチ・品質評価
  L7. API/サービス層    — UI・外部連携・コマンド処理

機能:
- 各層のヘルスチェック
- 層間依存関係の可視化
- ボトルネック検出
- アーキテクチャダッシュボード
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass
class LayerStatus:
    """各層のステータス"""
    layer_id: int               # 1-7
    name: str
    name_en: str
    status: str = "ok"          # ok, warn, error, offline
    message: str = ""
    metrics: dict = field(default_factory=dict)
    last_checked: str = ""

    def to_dict(self) -> dict:
        return {
            "layer_id": self.layer_id,
            "name": self.name,
            "name_en": self.name_en,
            "status": self.status,
            "message": self.message,
            "metrics": self.metrics,
            "last_checked": self.last_checked,
        }


# ─── 層定義 ──────────────────────────────────────────────────

_LAYER_DEFINITIONS = [
    (1, "インフラ層", "Infrastructure"),
    (2, "分散処理層", "Distributed Processing"),
    (3, "データ管理層", "Data Management"),
    (4, "モデル層", "Model"),
    (5, "学習制御層", "Learning Control"),
    (6, "推論最適化層", "Inference Optimization"),
    (7, "API/サービス層", "API/Service"),
]

_STATUS_ICONS = {
    "ok": "✅",
    "warn": "⚠️",
    "error": "❌",
    "offline": "💤",
}


class YamatoArchitecture:
    """
    7層アーキテクチャの監視・管理基盤。
    各層のヘルスチェックを実行し、システム全体の状態を可視化する。
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._layers: dict[int, LayerStatus] = {}
        self._health_checks: dict[int, Callable[[], dict]] = {}
        self._lock = threading.Lock()
        self._init_layers()

    def _init_layers(self) -> None:
        """層を初期化する"""
        for layer_id, name, name_en in _LAYER_DEFINITIONS:
            self._layers[layer_id] = LayerStatus(
                layer_id=layer_id,
                name=name,
                name_en=name_en,
            )

    # ─── ヘルスチェック登録 ──────────────────────────────────

    def register_health_check(
        self, layer_id: int, check_fn: Callable[[], dict]
    ) -> None:
        """
        層にヘルスチェック関数を登録する。
        check_fn は {"status": "ok"|"warn"|"error", "message": str, ...} を返すこと。
        """
        if layer_id < 1 or layer_id > 7:
            return
        self._health_checks[layer_id] = check_fn

    # ─── ヘルスチェック実行 ──────────────────────────────────

    def check_layer(self, layer_id: int) -> LayerStatus:
        """特定の層のヘルスチェックを実行する"""
        if layer_id not in self._layers:
            return LayerStatus(layer_id=layer_id, name="unknown", name_en="unknown", status="error")

        layer = self._layers[layer_id]
        now = datetime.now().isoformat()[:19]

        check_fn = self._health_checks.get(layer_id)
        if check_fn is None:
            # デフォルトチェック
            result = self._default_check(layer_id)
        else:
            try:
                result = check_fn()
            except Exception as e:
                result = {"status": "error", "message": f"チェック例外: {e}"}

        with self._lock:
            layer.status = result.get("status", "ok")
            layer.message = result.get("message", "")
            layer.metrics = {
                k: v for k, v in result.items()
                if k not in ("status", "message")
            }
            layer.last_checked = now

        return layer

    def check_all(self) -> list[LayerStatus]:
        """全層のヘルスチェックを実行する"""
        results = []
        for layer_id in sorted(self._layers.keys()):
            results.append(self.check_layer(layer_id))
        return results

    def _default_check(self, layer_id: int) -> dict:
        """デフォルトのヘルスチェック（登録がない層用）"""
        if layer_id == 1:
            return self._check_infrastructure()
        return {"status": "ok", "message": "チェック未登録（デフォルトOK）"}

    def _check_infrastructure(self) -> dict:
        """L1: インフラ層のデフォルトチェック"""
        metrics: dict[str, Any] = {}

        # ディスク使用率
        try:
            import shutil
            usage = shutil.disk_usage(str(self._base))
            used_pct = usage.used / usage.total * 100
            metrics["disk_used_pct"] = round(used_pct, 1)
            metrics["disk_free_gb"] = round(usage.free / (1024**3), 1)
        except Exception:
            pass

        # メモリ（Pythonプロセス）
        try:
            import resource
            mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
            metrics["process_mem_mb"] = round(mem_mb, 1)
        except Exception:
            pass

        # データディレクトリサイズ
        data_dir = self._base / "data"
        if data_dir.exists():
            total_size = sum(
                f.stat().st_size for f in data_dir.rglob("*") if f.is_file()
            )
            metrics["data_dir_mb"] = round(total_size / (1024 * 1024), 1)

        # モデルディレクトリ
        models_dir = self._base / "models"
        if models_dir.exists():
            model_files = list(models_dir.glob("*.gguf"))
            metrics["gguf_models"] = len(model_files)

        status = "ok"
        message = "インフラ正常"
        if metrics.get("disk_used_pct", 0) > 90:
            status = "warn"
            message = "ディスク使用率が90%超過"

        return {"status": status, "message": message, **metrics}

    # ─── 可視化 ──────────────────────────────────────────────

    def get_dashboard(self) -> str:
        """アーキテクチャダッシュボードをテキストで返す"""
        self.check_all()

        lines = ["🏗️ ヤマト7層アーキテクチャ ダッシュボード", "=" * 45]

        for layer_id in sorted(self._layers.keys()):
            layer = self._layers[layer_id]
            icon = _STATUS_ICONS.get(layer.status, "❓")
            lines.append(
                f"  L{layer.layer_id} {icon} {layer.name} ({layer.name_en})"
            )
            if layer.message:
                lines.append(f"      └─ {layer.message}")
            if layer.metrics:
                metric_parts = []
                for k, v in list(layer.metrics.items())[:4]:
                    metric_parts.append(f"{k}={v}")
                if metric_parts:
                    lines.append(f"      └─ {', '.join(metric_parts)}")

        # 全体スコア
        statuses = [l.status for l in self._layers.values()]
        ok_count = statuses.count("ok")
        total = len(statuses)
        health_pct = round(ok_count / total * 100) if total else 0
        lines.append(f"\n  🏥 総合ヘルス: {health_pct}% ({ok_count}/{total}層 正常)")

        return "\n".join(lines)

    def get_layer_status(self, layer_id: int) -> dict | None:
        """特定の層のステータスを返す"""
        layer = self._layers.get(layer_id)
        if layer is None:
            return None
        return layer.to_dict()

    def get_all_status(self) -> list[dict]:
        """全層のステータスを返す"""
        return [l.to_dict() for l in sorted(
            self._layers.values(), key=lambda l: l.layer_id
        )]

    def get_bottlenecks(self) -> list[dict]:
        """問題のある層（ボトルネック）を検出する"""
        self.check_all()
        issues = []
        for layer in self._layers.values():
            if layer.status in ("warn", "error"):
                issues.append({
                    "layer_id": layer.layer_id,
                    "name": layer.name,
                    "status": layer.status,
                    "message": layer.message,
                })
        return issues

    @property
    def layer_count(self) -> int:
        return len(self._layers)

    @property
    def healthy_count(self) -> int:
        return sum(1 for l in self._layers.values() if l.status == "ok")

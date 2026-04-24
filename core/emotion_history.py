"""
感情履歴管理
会話ごとの感情スナップショットを記録し、グラフ表示用データを提供します
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from core.tenant import SELF_TENANT, TenantId, tenant_dir
from utils.secure_store import load_json as _load_json_enc, save_json as _save_json_enc

logger = logging.getLogger(__name__)


EMOTION_KEYS = ["happiness", "curiosity", "affection", "energy", "anxiety"]


class EmotionHistory:
    def __init__(
        self,
        data_dir: Path,
        key: Optional[bytes] = None,
        tenant: TenantId | None = None,
        tenant_context: "object | None" = None,
    ):
        """B2 fix (2026-04-21): key を渡すと履歴が暗号化される。
        H2 fix (2026-04-21): tenant ごとに data/tenants/{tenant}/emotion_history.json に書き込む。
        旧パス `data/emotion_history.json` は後方互換で読み込みのみ対応。
        MT fix (2026-04-24): ``tenant_context`` (core.tenant_context.TenantContext) を
        渡すとファイルはその memory_dir 配下に格納される (完全物理分離)。
        """
        self._tenant = tenant or SELF_TENANT
        self._tenant_context = tenant_context
        if tenant_context is not None:
            try:
                tc_mem = tenant_context.memory_dir  # type: ignore[attr-defined]
                self._path = tenant_context.guard_path(
                    tc_mem / "emotion_history.json"
                )
            except AttributeError:  # pragma: no cover
                self._path = tenant_dir(Path(data_dir), self._tenant) / "emotion_history.json"
        else:
            self._path = tenant_dir(Path(data_dir), self._tenant) / "emotion_history.json"
        self._legacy_path = Path(data_dir) / "emotion_history.json"
        self._key = key
        self._records: list[dict] = []
        self._load()

    def _load(self):
        loaded = _load_json_enc(self._path, self._key, default=None)
        if loaded is None and self._legacy_path.exists():
            # H2 fix: 旧パス fallback
            loaded = _load_json_enc(self._legacy_path, self._key, default=[])
        self._records = loaded if isinstance(loaded, list) else []

    def _save(self):
        # 最大1000件まで保持
        self._records = self._records[-1000:]
        _save_json_enc(self._path, self._records, self._key)

    def record(self, emotion_state: dict):
        """現在の感情状態を記録"""
        entry = {
            "ts": datetime.now().isoformat()[:16],
            **{k: round(emotion_state.get(k, 0.5), 3) for k in EMOTION_KEYS},
        }
        self._records.append(entry)
        self._save()

    def get_recent(self, n: int = 50) -> list[dict]:
        """最新N件の記録を返す"""
        return self._records[-n:]

    def get_daily_averages(self, days: int = 14) -> list[dict]:
        """日別平均を返す（グラフ描画用）"""
        daily: dict[str, list] = defaultdict(list)
        for r in self._records:
            day = r["ts"][:10]
            daily[day].append(r)

        result = []
        for day in sorted(daily.keys())[-days:]:
            recs = daily[day]
            avg = {"date": day}
            for k in EMOTION_KEYS:
                avg[k] = round(sum(r.get(k, 0.5) for r in recs) / len(recs), 3)
            result.append(avg)
        return result

    def compress_old_entries(self, days_threshold: int = 30) -> dict:
        """
        古いエントリを日別サマリーに圧縮する (#24)。

        days_threshold 日より古いエントリを日別平均に集約し、
        個別エントリを削除してストレージを節約する。

        Returns:
            圧縮結果レポート
        """
        cutoff = (datetime.now() - timedelta(days=days_threshold)).isoformat()[:10]

        old_entries: list[dict] = []
        recent_entries: list[dict] = []

        for r in self._records:
            day = r["ts"][:10]
            if day < cutoff:
                old_entries.append(r)
            else:
                recent_entries.append(r)

        if not old_entries:
            return {"compressed": 0, "summaries_created": 0}

        # 日別にグループ化して平均を計算
        daily: dict[str, list[dict]] = defaultdict(list)
        for r in old_entries:
            daily[r["ts"][:10]].append(r)

        summaries: list[dict] = []
        for day in sorted(daily.keys()):
            recs = daily[day]
            summary = {"ts": f"{day}T00:00", "is_summary": True}
            for k in EMOTION_KEYS:
                vals = [r.get(k, 0.5) for r in recs]
                summary[k] = round(sum(vals) / len(vals), 3)
            summary["original_count"] = len(recs)
            summaries.append(summary)

        # サマリー + 最近のエントリで置換
        self._records = summaries + recent_entries
        self._save()

        result = {
            "compressed": len(old_entries),
            "summaries_created": len(summaries),
            "remaining": len(self._records),
        }
        logger.info(
            "感情履歴圧縮: %d エントリ → %d サマリー",
            len(old_entries),
            len(summaries),
        )
        return result

    def stats(self) -> dict:
        if not self._records:
            return {}
        last = self._records[-1]
        first = self._records[0]
        return {
            "total_records": len(self._records),
            "since": first["ts"][:10],
            "latest": last["ts"][:10],
        }

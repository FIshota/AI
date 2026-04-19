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

logger = logging.getLogger(__name__)


EMOTION_KEYS = ["happiness", "curiosity", "affection", "energy", "anxiety"]


class EmotionHistory:
    def __init__(self, data_dir: Path):
        self._path = Path(data_dir) / "emotion_history.json"
        self._records: list[dict] = []
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._records = json.loads(self._path.read_text("utf-8"))
            except Exception:
                self._records = []

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 最大1000件まで保持
        self._records = self._records[-1000:]
        self._path.write_text(
            json.dumps(self._records, ensure_ascii=False), "utf-8"
        )

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

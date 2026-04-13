"""
感情履歴管理
会話ごとの感情スナップショットを記録し、グラフ表示用データを提供します
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict


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

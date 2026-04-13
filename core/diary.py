"""
アイの日記システム
その日の会話を自動でまとめて保存し、振り返りができます。
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import datetime, date
from typing import Optional

from core.memory import MemoryManager


class DiaryManager:
    def __init__(self, data_dir: Path, memory: MemoryManager):
        self.data_dir = Path(data_dir)
        self.diary_dir = self.data_dir / "diary"
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        self.memory = memory

    # ─── 書き込み ──────────────────────────────────────────────────

    def write_today(self, emotion_snapshot: Optional[dict] = None) -> dict:
        """今日の会話記憶をまとめて日記エントリを作成・保存します"""
        today_str = date.today().isoformat()
        mems = self.memory.get_recent(limit=100, memory_type="mid")

        # 今日の記憶だけ抽出
        today_mems = [
            m for m in mems
            if m.created_at.startswith(today_str)
               and "conversation" in m.tags
        ]

        if not today_mems:
            return {}

        # 会話ペアを復元
        exchanges = []
        for m in today_mems:
            parsed = self._parse_memory_content(m.content)
            if parsed:
                exchanges.append(parsed)

        # ハイライトを抽出（重要度0.6以上）
        highlights = [
            self._parse_memory_content(m.content) or m.content[:60]
            for m in today_mems
            if m.importance >= 0.6
        ][:5]

        # サマリー文生成（テンプレートベース）
        count = len(exchanges)
        if count == 0:
            summary = "今日はあまり話せなかった日だったね。"
        elif count <= 3:
            summary = f"今日は少しだけ話した日だったよ。{count}回やりとりしたね。"
        elif count <= 10:
            summary = f"今日はよく話した日だったよ。{count}回のやりとりがあったね。"
        else:
            summary = f"今日はたくさん話した日だったよ！{count}回もやりとりしたね。"

        entry = {
            "date": today_str,
            "summary": summary,
            "exchange_count": count,
            "highlights": [
                h if isinstance(h, str) else f"{h.get('user', '')}"
                for h in highlights
            ],
            "emotion_snapshot": emotion_snapshot or {},
            "exchanges": [
                {"user": e["user"][:80], "ai": e["ai"][:80]}
                for e in exchanges[:20]
            ],
            "generated_at": datetime.now().isoformat(),
        }

        path = self.diary_dir / f"{today_str}.json"
        path.write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), "utf-8"
        )
        return entry

    def _parse_memory_content(self, content: str) -> Optional[dict]:
        """'[timestamp] ユーザー:「...」→ アイ:「...」' を解析"""
        m = re.search(
            r'ユーザー[：:][「"](.+?)[」"]\s*[→→]\s*アイ[：:][「"](.+?)[」"]',
            content, re.DOTALL
        )
        if m:
            return {"user": m.group(1).strip(), "ai": m.group(2).strip()}
        return None

    # ─── 読み込み ──────────────────────────────────────────────────

    def get_entry(self, date_str: Optional[str] = None) -> Optional[dict]:
        """指定日（省略時=今日）の日記を返します"""
        if date_str is None:
            date_str = date.today().isoformat()
        path = self.diary_dir / f"{date_str}.json"
        if path.exists():
            try:
                return json.loads(path.read_text("utf-8"))
            except Exception:
                pass
        return None

    def list_entries(self) -> list[str]:
        """日記がある日付の一覧を返します（新しい順）"""
        dates = [p.stem for p in sorted(self.diary_dir.glob("*.json"), reverse=True)]
        return dates

    def format_for_display(self, entry: dict) -> str:
        """日記エントリを表示用テキストに変換"""
        lines = [
            f"📔 {entry['date']} の日記",
            entry["summary"],
        ]
        if entry.get("highlights"):
            lines.append("\n✨ 印象に残ったこと:")
            for h in entry["highlights"][:3]:
                if h:
                    lines.append(f"  ・{h[:50]}")
        lines.append(f"\n話した回数: {entry.get('exchange_count', 0)}回")
        return "\n".join(lines)

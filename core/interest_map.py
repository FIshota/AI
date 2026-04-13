"""
好み・関心マップ
ユーザーの発言からキーワードを抽出し、関心度マップを構築します
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import datetime


CATEGORIES: dict[str, list[str]] = {
    "食べ物・飲み物": ["ご飯", "食べ", "料理", "美味し", "ランチ", "ディナー", "コーヒー",
                      "お菓子", "甘い", "お茶", "ラーメン", "カフェ", "スイーツ", "外食"],
    "仕事・勉強": ["仕事", "勉強", "学校", "会社", "プロジェクト", "締め切り", "資格",
                   "試験", "研究", "授業", "課題", "レポート", "面接", "就活"],
    "趣味・娯楽": ["映画", "音楽", "ゲーム", "読書", "スポーツ", "旅行", "写真", "絵",
                   "歌", "アニメ", "マンガ", "ドラマ", "ライブ", "散歩", "料理"],
    "健康・体調": ["運動", "ジム", "ダイエット", "健康", "睡眠", "疲れ", "病院",
                   "体調", "頭痛", "風邪", "ストレッチ", "ヨガ", "ランニング"],
    "人間関係": ["友達", "家族", "恋人", "職場", "先輩", "後輩", "彼氏", "彼女",
                 "同僚", "上司", "親", "兄弟", "姉妹"],
    "技術・IT": ["プログラミング", "AI", "コード", "アプリ", "スマホ", "パソコン",
                 "ゲーム開発", "データ", "エンジニア", "ソフトウェア", "Python"],
    "感情・気持ち": ["嬉しい", "楽しい", "悲しい", "疲れた", "不安", "ワクワク",
                    "幸せ", "つらい", "がんばる", "達成"],
}


class InterestMap:
    def __init__(self, data_dir: Path):
        self._path = Path(data_dir) / "interest_map.json"
        # {keyword: {count, last_seen, category}}
        self._interests: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._interests = json.loads(self._path.read_text("utf-8"))
            except Exception:
                self._interests = {}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._interests, ensure_ascii=False, indent=2), "utf-8"
        )

    def update(self, text: str) -> list[str]:
        """テキストからキーワードを検出して更新。新規発見したキーワードのリストを返す"""
        now = datetime.now().isoformat()[:16]
        new_keywords = []
        for category, keywords in CATEGORIES.items():
            for kw in keywords:
                if kw in text:
                    is_new = kw not in self._interests
                    if is_new:
                        self._interests[kw] = {
                            "count": 0,
                            "last_seen": now,
                            "category": category,
                        }
                        new_keywords.append(kw)
                    self._interests[kw]["count"] += 1
                    self._interests[kw]["last_seen"] = now
        if self._interests:
            self._save()
        return new_keywords

    def get_top(self, n: int = 15) -> list[dict]:
        """関心度の高い順にトップNを返す"""
        items = [
            {"keyword": kw, **data}
            for kw, data in self._interests.items()
        ]
        items.sort(key=lambda x: x["count"], reverse=True)
        return items[:n]

    def get_by_category(self) -> dict[str, list[dict]]:
        """カテゴリ別に整理して返す"""
        result: dict[str, list] = {}
        for kw, data in self._interests.items():
            cat = data.get("category", "その他")
            if cat not in result:
                result[cat] = []
            result[cat].append({"keyword": kw, "count": data["count"]})
        for cat in result:
            result[cat].sort(key=lambda x: x["count"], reverse=True)
        return result

    def build_context_hint(self) -> str:
        """LLMへの関心ヒント文（最大3キーワード）"""
        top = self.get_top(5)
        if not top:
            return ""
        kws = "、".join(item["keyword"] for item in top[:3])
        return f"よく話す話題：{kws}"

    def stats(self) -> dict:
        return {
            "total_keywords": len(self._interests),
            "top_keyword": self._interests and max(
                self._interests, key=lambda k: self._interests[k]["count"]
            ) or "",
        }

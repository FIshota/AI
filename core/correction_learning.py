"""
ユーザー訂正学習モジュール

ユーザーが「違う」「そうじゃなくて」「そういう意味じゃない」等の
訂正フレーズを使った場合、直前のAI応答の品質を下げ、
訂正内容を学習データとして蓄積する。

蓄積された訂正データは:
1. 直後のLLM応答に「前回の訂正」としてコンテキスト注入
2. 長期的にlearningデータとして保存（将来の応答品質向上）
3. 筋肉記憶の精度向上に寄与（十分蓄積されたら）
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── 訂正検出パターン ──
_CORRECTION_PATTERNS = [
    # 明示的な否定・訂正（文頭 + 文中両対応）
    re.compile(r'(違う|ちがう|ちゃう)[よって！!。、 ]'),
    re.compile(r'^(違う|ちがう|ちゃう)$'),
    re.compile(r'(違くない|違うって|違うってば)'),
    re.compile(r'^(そうじゃ|そーじゃ)(ない|なくて|ないよ|ないって)'),
    re.compile(r'^(そういう)(意味|こと)(じゃ|では)(ない|なくて)'),
    re.compile(r'^(そうじゃなくて|そうじゃないよ|そうじゃないって)'),
    re.compile(r'(いや|いやいや)[、。 ]'),
    re.compile(r'^いやいや$'),
    re.compile(r'(ちょっと|なんか|それ)(違う|ずれてる|合ってない)'),
    re.compile(r'(それ|そこ)(は|が)(違う|間違い|間違ってる|おかしい|変)'),
    re.compile(r'(間違い|間違えてる|間違ってる|間違ってない[？?])'),

    # やり直し要求
    re.compile(r'(もう一回|もう1回|やり直し|もう一度|言い直して)'),

    # 訂正を伴う言い換え（「〜じゃなくて〜」パターン）
    re.compile(r'.+じゃなくて.+'),
    re.compile(r'.+ではなくて?.+'),
    re.compile(r'.+じゃない[よ。、].+'),

    # 繰り返しへの不満・修正指示
    re.compile(r'(同じ(こと|話)|おなじこと|おんなじこと)(言う|言わないで|繰り返|ばっかり|ばかり)'),
    re.compile(r'(さっき|前)(と|も|に)(同じ|おなじ|一緒|言った)'),
    re.compile(r'(繰り返|くりかえ)し(てる|すぎ|ないで|やめて)'),
    re.compile(r'(それ|それって|それは)(さっき|前に)(も|聞いた|言った)'),
    re.compile(r'(ワンパターン|マンネリ|飽きた|また同じ|また一緒)'),
    re.compile(r'(何回|なんかい)(も|言わせる|同じ)'),
    re.compile(r'もう聞いた[よ。]?$'),

    # フラストレーション系
    re.compile(r'(話|会話)(聞いて|が通じ|にならない|が成り立|を聞いて)'),
    re.compile(r'(ちゃんと|よく)(聞いて|読んで|見て|理解して)'),
]

# 訂正の後に正しい情報が続くパターン（幅広く拾う）
_CORRECTION_WITH_ANSWER = re.compile(
    r'(?:違う|ちがう|そうじゃなくて|そうじゃないよ|いや|いやいや)[、。 ]*(.+)',
    re.DOTALL,
)


@dataclass
class CorrectionEntry:
    """訂正記録"""
    timestamp: float
    user_original: str       # ユーザーの元発言
    ai_wrong_response: str   # AIの間違った応答
    correction_input: str    # ユーザーの訂正フレーズ
    correct_info: str        # 正しい情報（抽出できた場合）


@dataclass
class CorrectionLearning:
    """ユーザー訂正に基づく学習エンジン"""

    data_dir: Path
    corrections: list[CorrectionEntry] = field(default_factory=list)
    _last_user_input: str = ""
    _last_ai_response: str = ""
    _correction_count: int = 0
    _max_corrections: int = 500  # 保持する最大訂正数

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        """保存済み訂正データを読み込む"""
        path = self.data_dir / "corrections.jsonl"
        if not path.exists():
            return
        try:
            for line in path.read_text("utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                self.corrections.append(CorrectionEntry(
                    timestamp=obj.get("ts", 0),
                    user_original=obj.get("user_original", ""),
                    ai_wrong_response=obj.get("ai_wrong", ""),
                    correction_input=obj.get("correction", ""),
                    correct_info=obj.get("correct_info", ""),
                ))
        except Exception as e:
            print(f"[CorrectionLearning] 読込エラー: {e}", flush=True)
        self._correction_count = len(self.corrections)

    def _save_entry(self, entry: CorrectionEntry) -> None:
        """訂正エントリを追記保存"""
        path = self.data_dir / "corrections.jsonl"
        obj = {
            "ts": entry.timestamp,
            "user_original": entry.user_original,
            "ai_wrong": entry.ai_wrong_response,
            "correction": entry.correction_input,
            "correct_info": entry.correct_info,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def record_turn(self, user_input: str, ai_response: str) -> None:
        """会話ターンを記録（訂正検出のために直前の会話を保持）"""
        self._last_user_input = user_input
        self._last_ai_response = ai_response

    def detect_correction(self, user_input: str) -> Optional[CorrectionEntry]:
        """
        ユーザーの入力が訂正かどうかを判定する。

        Returns:
            CorrectionEntry if correction detected, None otherwise.
        """
        if not self._last_ai_response:
            return None

        # パターンマッチで訂正を検出
        is_correction = False
        for pattern in _CORRECTION_PATTERNS:
            if pattern.search(user_input):
                is_correction = True
                break

        if not is_correction:
            return None

        # 訂正から正しい情報を抽出
        correct_info = ""
        m = _CORRECTION_WITH_ANSWER.search(user_input)
        if m:
            correct_info = m.group(1).strip()

        # correct_info が取れなかった場合、訂正フレーズ自体を記録
        # （「繰り返してる 〇〇していいからね」のような指示も保持する）
        if not correct_info and len(user_input) > 10:
            correct_info = user_input

        entry = CorrectionEntry(
            timestamp=time.time(),
            user_original=self._last_user_input,
            ai_wrong_response=self._last_ai_response,
            correction_input=user_input,
            correct_info=correct_info,
        )

        # 保存
        self.corrections.append(entry)
        self._correction_count += 1
        self._save_entry(entry)

        # 上限を超えたら古いものを切り捨て
        if len(self.corrections) > self._max_corrections:
            self.corrections = self.corrections[-self._max_corrections:]

        return entry

    def build_correction_context(self, entry: CorrectionEntry) -> str:
        """
        訂正検出時にLLMに注入するコンテキストを生成する。
        直前の応答が間違いであることを伝え、正しい方向に誘導する。
        """
        parts = [
            f"直前の応答「{entry.ai_wrong_response[:60]}」はユーザーに訂正された。"
        ]
        if entry.correct_info:
            parts.append(f"ユーザーの指示: {entry.correct_info[:80]}")
        parts.append("素直に従って。")
        return " ".join(parts)

    def get_recent_corrections_hint(self, max_entries: int = 3) -> str:
        """
        最近の訂正履歴をLLMコンテキストに追加するヒント文を返す。
        correct_info が空でも訂正フレーズ自体を表示する。
        """
        if not self.corrections:
            return ""

        recent = self.corrections[-max_entries:]
        hints = []
        for c in recent:
            if c.correct_info:
                hints.append(
                    f"・「{c.ai_wrong_response[:30]}」は誤り → {c.correct_info[:50]}"
                )
            elif c.correction_input:
                # correct_info がなくても訂正フレーズを表示
                hints.append(
                    f"・ユーザーの指摘: {c.correction_input[:50]}"
                )
        if not hints:
            return ""
        return "過去の訂正: " + " / ".join(hints)

    def generalize_corrections(self) -> dict:
        """
        訂正をカテゴリ別にグループ化し、3件以上の訂正があるカテゴリから
        メタルールを自動生成する (#79)。

        カテゴリは訂正内容のキーワードから推定する。
        結果は data/correction_rules.json に保存される。

        Returns:
            生成されたメタルールのレポート
        """
        # カテゴリ分類キーワード
        category_keywords: dict[str, list[str]] = {
            "repetition": ["同じ", "繰り返", "またさ", "ワンパターン", "おんなじ"],
            "tone": ["敬語", "です・ます", "口調", "丁寧", "タメ口"],
            "factual": ["違う", "間違", "正しく", "事実"],
            "relevance": ["関係ない", "そうじゃなくて", "意味", "ずれ"],
            "length": ["長い", "短い", "もっと", "簡潔"],
            "emotion": ["気持ち", "感情", "共感", "寄り添"],
        }

        # 訂正をカテゴリに分類
        categorized: dict[str, list[CorrectionEntry]] = {}
        for entry in self.corrections:
            text = entry.correction_input + " " + entry.correct_info
            assigned_category = "other"
            for cat, keywords in category_keywords.items():
                if any(kw in text for kw in keywords):
                    assigned_category = cat
                    break
            categorized.setdefault(assigned_category, []).append(entry)

        # 3件以上のカテゴリからメタルールを生成
        meta_rules: list[dict] = []
        for category, entries in categorized.items():
            if len(entries) < 3:
                continue

            # 代表的な訂正内容を収集
            samples = [
                e.correct_info or e.correction_input
                for e in entries[-5:]
                if e.correct_info or e.correction_input
            ]

            rule = {
                "category": category,
                "count": len(entries),
                "rule": f"カテゴリ '{category}' で{len(entries)}件の訂正あり。注意して応答すること。",
                "samples": samples[:3],
                "created_at": time.time(),
            }
            meta_rules.append(rule)

        # 保存
        rules_path = self.data_dir / "correction_rules.json"
        rules_path.write_text(
            json.dumps(meta_rules, ensure_ascii=False, indent=2), "utf-8"
        )

        return {
            "total_categories": len(categorized),
            "rules_generated": len(meta_rules),
            "categories": {cat: len(entries) for cat, entries in categorized.items()},
        }

    def stats(self) -> dict:
        return {
            "total_corrections": self._correction_count,
            "stored_corrections": len(self.corrections),
        }

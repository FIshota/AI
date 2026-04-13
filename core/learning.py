"""
擬似学習システム
会話データファイルから例文を読み込み、システムプロンプトに注入することで
アイの話し方を自然に誘導します
"""
from __future__ import annotations
import json
import random
import re
from pathlib import Path


# 自己学習で保存してはいけないパターン（Phi-3 幻覚・プロンプトリーク対策）
_BAD_LEARNING_PATTERNS = re.compile(
    r"アルベロ"
    r"|<\|[^|]*\|>"      # <|assistant|> <|system|> などテンプレートトークン
    r"|指示[：:]"          # プロンプト指示のリーク
    r"|======"
    r"|shift Register"
    r"|\bassistant\b"
    r"|\bsystem\b"
    r"|スゴテ"
    r"|私（.*?）"         # "私（アルベロ）" のような自称リーク
)


def is_safe_learning_example(user: str, ai: str) -> bool:
    """学習ファイルに保存して安全なサンプルか判定する。"""
    if not user or not ai:
        return False
    ai_stripped = ai.strip()
    # 長さガード
    if len(ai_stripped) < 2 or len(ai_stripped) > 400:
        return False
    # 禁止パターン
    blob = f"{user}\n{ai_stripped}"
    if _BAD_LEARNING_PATTERNS.search(blob):
        return False
    return True


class LearningEngine:
    def __init__(self, learning_dir: str | Path):
        self.learning_dir = Path(learning_dir)
        self.conversations: list[dict] = []
        self._load_all()

    def _load_all(self):
        """learning/ 以下の全JSONLファイルを読み込みます（毒サンプルは除外）"""
        jsonl_files = list(self.learning_dir.glob("*.jsonl"))
        for f in jsonl_files:
            try:
                for line in f.read_text("utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "user" not in obj or "ai" not in obj:
                        continue
                    # 読み込み時にも安全性チェック（毒サンプルは参照させない）
                    if not is_safe_learning_example(obj["user"], obj["ai"]):
                        continue
                    self.conversations.append(obj)
            except Exception:
                pass

    def get_few_shot_examples(self, n: int = 5, user_input: str = "") -> str:
        """
        システムプロンプトに追加するfew-shot例文を返します。
        user_inputに関連しそうな例を優先的に選びます。
        """
        if not self.conversations:
            return ""

        # キーワードで関連例を優先
        scored = []
        for conv in self.conversations:
            score = sum(1 for kw in user_input if kw in conv["user"] or kw in conv["ai"])
            scored.append((score, conv))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for _, c in scored[:max(n*2, 10)]]
        selected = random.sample(top, min(n, len(top)))

        # ペルソナの Examples スタイルに合わせて出力（ユーザー:/アイ: は使わない）
        lines = [f'{c["user"]} → {c["ai"]}' for c in selected]
        return "Examples:\n" + "\n".join(lines)

    def add_conversation(self, user: str, ai: str, save: bool = True) -> bool:
        """
        新しい会話例を追加します（継続学習）。
        毒サンプル（Phi-3 幻覚・プロンプトリーク）は自動で弾きます。
        Returns: True=保存した / False=汚染と判定して捨てた
        """
        if not is_safe_learning_example(user, ai):
            print(
                f"[Learning] ⚠ 汚染サンプルを破棄 (len={len(ai)}): {ai[:60]}...",
                flush=True,
            )
            return False
        conv = {"user": user, "ai": ai}
        self.conversations.append(conv)
        if save:
            target = self.learning_dir / "learned.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(json.dumps(conv, ensure_ascii=False) + "\n")
        return True

    def stats(self) -> dict:
        return {"total_examples": len(self.conversations)}

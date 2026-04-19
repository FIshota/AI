"""
レスポンスパイプライン
LLM 出力のクリーニング、品質推定、エラーメッセージの人格化を担当します。
"""
from __future__ import annotations

import logging
import random
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ai_chan import AiChan

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# エラーメッセージの人格化 (Item #40)
# ──────────────────────────────────────────────────────────────

ERROR_MESSAGES: dict[str, str] = {
    "generic": "ごめん、ちょっと頭がこんがらがっちゃった…もう一回言ってくれる？",
    "model_not_found": "あれ…記憶の引き出しが開かないみたい…",
    "connection": "ちょっと繋がりにくいみたい…後でまた試してみるね",
    "timeout": "ごめん、考え込んじゃった…もう一回聞いてくれる？",
    "memory": "記憶の整理中にちょっと混乱しちゃった…",
}


def get_friendly_error(error_key: str = "generic") -> str:
    """エラーキーに対応する人格化されたエラーメッセージを返す"""
    return ERROR_MESSAGES.get(error_key, ERROR_MESSAGES["generic"])


# ──────────────────────────────────────────────────────────────
# 三人称ナレーション検出パターン
# ──────────────────────────────────────────────────────────────

_NARRATION_RE = re.compile(
    r'^アイ[はが].+'
    r'(した|った|ている|てる|ていた|ます|ました'
    r'|てしまった|ちゃった|てしまいました'
    r'|思った|考えた|感じた|見た|言った|答えた|呟いた|微笑んだ'
    r'|笑った|頷いた|首を振った|目を細めた|手を振った|息を吐いた|声を出した)$'
)

# ──────────────────────────────────────────────────────────────
# 日本語文中の不自然な英語検出
# LLM が日本語文中に無意味な英語を混ぜるケースを検出・除去する。
# 固有名詞やカタカナ語として定着した英語はそのまま残す。
# ──────────────────────────────────────────────────────────────

# 日本語文脈で使われても自然な英語（除外リスト）
_NATURAL_EN = frozenset({
    "OK", "NG", "PC", "AI", "SNS", "URL", "ID", "Wi-Fi", "WiFi",
    "YouTube", "Twitter", "LINE", "Discord", "Slack", "Notion",
    "iPhone", "iPad", "Mac", "Windows", "Linux", "Python", "Java",
    "USB", "LLM", "GPU", "CPU", "RAM", "SSD", "API", "CLI",
    "BGM", "RPG", "FPS", "MMO", "DLC", "PvP", "NPC",
})

def _strip_stray_english(text: str) -> str:
    """日本語の文中に孤立して現れる不自然な英語を除去する。
    例: 「楽しみ curious だな」→「楽しみだな」
    固有名詞やカタカナ語として自然なものはそのまま残す。
    """
    def _replace(m: re.Match) -> str:
        word = m.group(0)
        # 大文字略語や固有名詞リストはそのまま
        if word.upper() in _NATURAL_EN or word in _NATURAL_EN:
            return word
        # 全大文字の略語（2-5文字）はそのまま
        if word.isupper() and len(word) <= 5:
            return word
        # 前後が日本語文字なら不自然な混入 → 除去
        start, end = m.start(), m.end()
        before = text[max(0, start - 1):start]
        after = text[end:end + 1]
        jp_around = (
            bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', before))
            or bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', after))
        )
        if jp_around:
            return ""  # 日本語に囲まれた英語 → 除去
        return word
    # 3文字以上の英語単語にマッチ（前後にスペースがある孤立した単語）
    result = re.sub(r'(?<=\s)[a-zA-Z]{3,}(?=\s|[。、！？])', _replace, text)
    # 除去で生じた連続スペースを整理
    result = re.sub(r'  +', ' ', result).strip()
    return result


# ──────────────────────────────────────────────────────────────
# 入力サニタイズ (Item #92)
# ──────────────────────────────────────────────────────────────

_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_PROMPT_INJECTION_RE = re.compile(
    r'(ignore\s+(previous|above)\s+instructions'
    r'|system\s*:\s*you\s+are'
    r'|<\|im_start\|>'
    r'|<\|endoftext\|>'
    r'|\[INST\]'
    r'|<<SYS>>)',
    re.IGNORECASE,
)


def sanitize_input(text: str) -> str:
    """
    ユーザー入力をサニタイズする。
    - 制御文字を除去
    - 長さを制限 (4096文字)
    - プロンプトインジェクションの基本パターンを無害化
    """
    # 制御文字を除去
    text = _CONTROL_CHAR_RE.sub("", text)

    # 長さ制限
    text = text[:4096]

    # プロンプトインジェクション基本パターンを無害化
    text = _PROMPT_INJECTION_RE.sub("[filtered]", text)

    return text.strip()


# ──────────────────────────────────────────────────────────────
# レスポンスパイプラインクラス
# ──────────────────────────────────────────────────────────────

class ResponsePipeline:
    """
    LLM の生テキストをクリーニングし、品質を推定する。
    """

    def __init__(self, ai: AiChan) -> None:
        self.ai = ai

    # ──────────────────────────────────────────────────────

    def clean_response(self, text: str) -> str:
        """
        Phi-3の出力を清書する:
        - 「アイ:」などのプレフィックスを除去
        - 英語のメタ注釈行を除去
        - 英語が大部分なら日本語フォールバック
        - 長すぎる応答を max_sentences に制限
        """
        # 会話シミュレーション（「ユーザー:」以降のロールプレイ）を切り捨て
        for marker in ['ユーザー:', 'ユーザー：', 'User:', 'しょうた:']:
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx].strip()

        # プレフィックス除去
        text = re.sub(r'^(アイ|AI|Assistant|アシスタント)\s*[:：]\s*', '', text).strip()
        # 括弧で始まる説明文を除去
        text = re.sub(r'^\(.*?\)\s*', '', text).strip()
        # 漏れ出たブラケット指示を除去
        text = re.sub(r'\[★[^\]]*\]', '', text).strip()
        text = re.sub(r'指示[１２３\d][^\s。]*', '', text).strip()

        # 三人称ナレーション行を除去（一人称発話は残す）
        lines = text.splitlines()
        filtered = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _NARRATION_RE.search(stripped):
                continue
            filtered.append(stripped)
        text = '\n'.join(filtered).strip() if filtered else text.strip()

        # 英語のメタ注釈行・翻訳行を除去
        lines = text.splitlines()
        cleaned_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # **...** 形式のヘッダー行を除去
            if re.match(r'^\*\*.*\*\*$', stripped):
                continue
            # # 見出し行を除去
            if re.match(r'^#+\s', stripped):
                continue
            # 英語注釈行を除去
            if re.match(
                r'^\((?:Note|Translation|Instruction|Example|Solution)[:\s]',
                stripped,
                re.IGNORECASE,
            ):
                continue
            # 日本語文字がなく英語単語がある行が来たら打ち切り
            has_japanese = bool(
                re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', stripped)
            )
            if not has_japanese and re.search(r'[a-zA-Z]{3,}', stripped):
                break
            # コード片・技術テキスト混入で打ち切り
            if re.search(
                r'(例のコード|Cookie\.js|```|import |def |class |function |var |const |let )',
                stripped,
            ):
                break
            cleaned_lines.append(stripped)
        text = '\n'.join(cleaned_lines).strip()

        # 英語が大部分（60%超）の場合のみフォールバック
        ascii_ratio = sum(1 for c in text if c.isascii() and c.isalpha()) / max(len(text), 1)
        has_japanese = bool(
            re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text)
        )
        if ascii_ratio > 0.6 and not has_japanese:
            fallbacks = [
                "ごめん、うまく言えなかった。もう一回話しかけてみて",
                "えっと…もう少し違う言い方で聞いてもいい？",
                "ちょっと考えすぎちゃった。もう一度話しかけてね",
            ]
            return random.choice(fallbacks)

        # max_sentences を超えたら打ち切り
        max_s = getattr(self.ai, '_max_sentences', 6)
        sentences = re.split(r'(?<=[。！？\n])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) > max_s:
            text = ''.join(sentences[:max_s])

        # 日本語文中の不自然な英語を除去 (Item #120)
        text = _strip_stray_english(text)

        return text if text else "うん、聞いてるよ"

    # ──────────────────────────────────────────────────────

    def estimate_response_quality(self, user_input: str, response: str) -> float:
        """
        LLM呼び出しなしで応答品質を推定する軽量ヒューリスティック。

        Returns: 0.0 ~ 1.0 の品質スコア
        """
        if not response or not response.strip():
            return 0.1

        resp = response.strip()
        resp_len = len(resp)

        if resp_len <= 3:
            return 0.3

        # 日本語文字の割合チェック
        jp_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', resp))
        if resp_len > 10 and jp_chars / resp_len < 0.2:
            return 0.25

        score = 0.65  # 基準値

        # フォールバック応答の検出
        _fallback_phrases = (
            "うまく言えなかった",
            "もう一回話しかけて",
            "ちょっと考えすぎちゃった",
            "うん、聞いてるよ",
        )
        for fb in _fallback_phrases:
            if fb in resp:
                return 0.2

        # オウム返し検出
        _strip_p = re.compile(r'[！!。、？?〜～\s…・「」]+')
        u_clean = _strip_p.sub("", user_input)
        r_clean = _strip_p.sub("", resp)
        if u_clean and r_clean and len(u_clean) >= 5 and u_clean in r_clean:
            score -= 0.15

        # ユーザー入力に対して応答が極端に短い
        if len(user_input) > 20 and resp_len < 8:
            score -= 0.1

        # 直前の応答と酷似（繰り返し検出）
        prev_responses = [
            m["content"] for m in self.ai.conversation_history[-4:]
            if m.get("role") == "assistant"
        ]
        for prev in prev_responses:
            prev_clean = _strip_p.sub("", prev)
            if r_clean and prev_clean:
                short, long_ = (
                    (r_clean, prev_clean)
                    if len(r_clean) <= len(prev_clean)
                    else (prev_clean, r_clean)
                )
                if len(short) >= 5 and short in long_:
                    score -= 0.2
                    break

        return max(0.1, min(1.0, score))


def compute_phi_quality(text: str) -> float:
    """
    アカシックΦスコアによる応答品質評価 (0.0-1.0)。
    高いΦ = 多次元統合的な応答 = 高品質。
    低いΦ = 単純/断片的な応答 = 要改善。
    既存の品質スコアの補完指標として使用。
    """
    if not text or len(text) < 5:
        return 0.0
    try:
        from core.akashic.unified_field import UnifiedField
        return round(UnifiedField().measure_phi(text), 3)
    except Exception:
        return 0.0

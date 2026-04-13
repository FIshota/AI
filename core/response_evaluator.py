"""
応答品質自己評価 (Response Evaluator)
Sprint K4: アイが自分の応答品質を評価し改善する。

機能:
- 応答の日本語自然さスコア
- 会話の一貫性チェック
- 繰り返し応答の検出・回避
- 応答多様性の管理
- 品質メトリクスの蓄積
"""
from __future__ import annotations

import json
import re
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class QualityScore:
    """応答品質スコア"""
    naturalness: float = 0.0    # 日本語の自然さ (0-1)
    relevance: float = 0.0      # 入力との関連性 (0-1)
    diversity: float = 0.0      # 多様性 (0-1)
    consistency: float = 0.0    # 一貫性 (0-1)
    overall: float = 0.0        # 総合スコア (0-1)

    def to_dict(self) -> dict:
        return {
            "naturalness": round(self.naturalness, 3),
            "relevance": round(self.relevance, 3),
            "diversity": round(self.diversity, 3),
            "consistency": round(self.consistency, 3),
            "overall": round(self.overall, 3),
        }


class ResponseEvaluator:
    """
    アイの応答品質を自己評価するシステム。
    過去の応答と比較して品質を維持・改善する。
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._metrics_path = self._base / "data" / "response_metrics.json"
        self._recent_responses: deque[str] = deque(maxlen=50)
        self._recent_scores: deque[float] = deque(maxlen=100)
        self._lock = threading.Lock()
        self._load()

    def evaluate(self, user_input: str, response: str) -> QualityScore:
        """応答品質を評価する"""
        score = QualityScore()

        # 1. 日本語の自然さ
        score.naturalness = self._eval_naturalness(response)

        # 2. 入力との関連性
        score.relevance = self._eval_relevance(user_input, response)

        # 3. 多様性（繰り返し回避）
        score.diversity = self._eval_diversity(response)

        # 4. 一貫性
        score.consistency = self._eval_consistency(response)

        # 総合スコア（重み付き平均）
        score.overall = (
            score.naturalness * 0.3
            + score.relevance * 0.3
            + score.diversity * 0.2
            + score.consistency * 0.2
        )

        # 記録
        self._recent_responses.append(response)
        self._recent_scores.append(score.overall)

        # 定期保存
        if len(self._recent_scores) % 20 == 0:
            self._save()

        return score

    def should_regenerate(self, score: QualityScore) -> bool:
        """応答を再生成すべきか判断する"""
        return score.overall < 0.3 or score.naturalness < 0.2

    def get_improvement_hint(self, score: QualityScore) -> str:
        """品質改善のためのヒントを返す"""
        hints: list[str] = []

        if score.naturalness < 0.5:
            hints.append("もっと自然な日本語で、口語的に")
        if score.relevance < 0.5:
            hints.append("ユーザーの話題に直接応答する")
        if score.diversity < 0.4:
            hints.append("前と違う表現や話し方を使う")
        if score.consistency < 0.5:
            hints.append("アイらしい一貫した口調で")

        return "。".join(hints) if hints else ""

    def get_quality_summary(self) -> str:
        """品質メトリクスのサマリー"""
        if not self._recent_scores:
            return "📈 応答品質: データ不足"

        avg = sum(self._recent_scores) / len(self._recent_scores)
        recent_10 = list(self._recent_scores)[-10:]
        recent_avg = sum(recent_10) / len(recent_10) if recent_10 else 0

        trend = "↗️" if recent_avg > avg else ("↘️" if recent_avg < avg - 0.05 else "→")

        return (
            f"📈 応答品質スコア:\n"
            f"  平均: {avg:.0%} {trend}\n"
            f"  直近10件: {recent_avg:.0%}\n"
            f"  評価数: {len(self._recent_scores)}件"
        )

    # ─── 評価関数 ────────────────────────────────────────────

    def _eval_naturalness(self, response: str) -> float:
        """日本語の自然さを評価する"""
        score = 1.0

        # 空応答
        if not response.strip():
            return 0.0

        # 英語の混入（重大）
        ascii_ratio = sum(1 for c in response if c.isascii() and c.isalpha()) / max(len(response), 1)
        if ascii_ratio > 0.3:
            score -= 0.4

        # 不自然な長さ
        if len(response) < 3:
            score -= 0.3
        elif len(response) > 500:
            score -= 0.2

        # です・ます調の混入（アイはタメ口）
        formal_count = len(re.findall(r"(です[。！？]|ます[。！？]|ございます|でしょうか)", response))
        if formal_count > 0:
            score -= 0.1 * min(formal_count, 3)

        # 括弧書き注釈（LLM artifact）
        if re.search(r"\([^)]{15,}\)", response):
            score -= 0.15

        # 箇条書き・リスト（設定違反）
        if re.search(r"^[\-\*\d]+[\.）\)]", response, re.MULTILINE):
            score -= 0.2

        # メタ注釈
        if re.search(r"\*\*[^*]+\*\*", response):
            score -= 0.2

        # 三人称（「アイは〜」）
        if re.search(r"^アイ[はがのをに]", response):
            score -= 0.3

        return max(0.0, score)

    def _eval_relevance(self, user_input: str, response: str) -> float:
        """入力との関連性を評価する"""
        score = 0.5  # ベースライン

        # キーワードの共有
        input_chars = set(user_input)
        response_chars = set(response)
        # 漢字・カタカナの共有（内容語の重複）
        content_chars_input = {
            c for c in input_chars
            if '\u4e00' <= c <= '\u9fff' or '\u30a0' <= c <= '\u30ff'
        }
        content_chars_response = {
            c for c in response_chars
            if '\u4e00' <= c <= '\u9fff' or '\u30a0' <= c <= '\u30ff'
        }

        if content_chars_input:
            overlap = len(content_chars_input & content_chars_response)
            overlap_ratio = overlap / len(content_chars_input)
            score += overlap_ratio * 0.3

        # 質問に対する応答性
        if user_input.endswith(("?", "？")):
            # 質問に対して疑問符で返すのは変（鸚鵡返し）
            if response.count("？") > 2:
                score -= 0.2
            # 何らかの回答がある
            if len(response) > 10:
                score += 0.1

        # 感情語への反応
        emotion_words = ["悲しい", "嬉しい", "辛い", "楽しい", "怒", "不安"]
        has_emotion_input = any(w in user_input for w in emotion_words)
        has_empathy = any(
            w in response
            for w in ["そうだよね", "わかる", "大丈夫", "一緒", "聞く", "いるよ", "ね"]
        )
        if has_emotion_input and has_empathy:
            score += 0.2

        return min(1.0, max(0.0, score))

    def _eval_diversity(self, response: str) -> float:
        """応答の多様性を評価する（繰り返し検出）"""
        if not self._recent_responses:
            return 1.0

        score = 1.0

        # 直近の応答との類似度チェック
        for past in list(self._recent_responses)[-10:]:
            similarity = self._text_similarity(response, past)
            if similarity > 0.8:  # 80%以上類似
                score -= 0.3
                break
            elif similarity > 0.6:
                score -= 0.1

        # 同じ語尾の繰り返し
        endings = re.findall(r"[。！？♪〜]+$", response)
        if endings and self._recent_responses:
            last_endings = [
                re.findall(r"[。！？♪〜]+$", r)
                for r in list(self._recent_responses)[-5:]
            ]
            same_ending_count = sum(
                1 for le in last_endings
                if le and endings and le[-1] == endings[-1]
            )
            if same_ending_count >= 3:
                score -= 0.15

        return max(0.0, score)

    def _eval_consistency(self, response: str) -> float:
        """アイらしさの一貫性を評価する"""
        score = 0.7  # ベースライン

        # タメ口チェック（加点）
        casual_markers = ["だよ", "だね", "かな", "よね", "だよね", "ね！", "よ！"]
        casual_count = sum(1 for m in casual_markers if m in response)
        if casual_count > 0:
            score += 0.1 * min(casual_count, 3)

        # 顔文字・絵文字の使用（加点）
        emoji_count = sum(1 for c in response if ord(c) > 0x1F600)
        if 0 < emoji_count <= 3:
            score += 0.1

        # 一人称「私」の使用（アイらしい）
        if "私" in response:
            score += 0.05

        return min(1.0, score)

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """2つのテキストの類似度（簡易版 Jaccard）"""
        if not a or not b:
            return 0.0
        # 2-gram で比較
        def ngrams(text: str, n: int = 2) -> set:
            return {text[i:i+n] for i in range(len(text) - n + 1)}

        a_grams = ngrams(a)
        b_grams = ngrams(b)
        if not a_grams or not b_grams:
            return 0.0
        intersection = len(a_grams & b_grams)
        union = len(a_grams | b_grams)
        return intersection / union if union > 0 else 0.0

    # ─── 永続化 ──────────────────────────────────────────────

    def _load(self) -> None:
        if not self._metrics_path.exists():
            return
        try:
            data = json.loads(self._metrics_path.read_text("utf-8"))
            for s in data.get("recent_scores", []):
                self._recent_scores.append(s)
            for r in data.get("recent_responses", []):
                self._recent_responses.append(r)
        except (json.JSONDecodeError, KeyError):
            pass

    def _save(self) -> None:
        with self._lock:
            self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "recent_scores": list(self._recent_scores),
                "recent_responses": list(self._recent_responses)[-20:],
                "saved_at": datetime.now().isoformat()[:19],
            }
            self._metrics_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )

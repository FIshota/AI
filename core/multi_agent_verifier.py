"""
マルチエージェント検証 (Multi-Agent Verifier)
ヤマト計画 C7: 複数の検証エージェントが応答を多角的に検証する。

機能:
- 複数の検証視点（正確性、自然さ、安全性、一貫性、共感性）
- 各エージェントが独立スコアリング
- 合議による最終判定
- 問題検出時の改善提案生成
- 検証履歴と統計管理
"""
from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass
class VerificationResult:
    """個別エージェントの検証結果"""
    agent_name: str
    score: float           # 0.0-1.0
    passed: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "score": round(self.score, 3),
            "passed": self.passed,
            "issues": self.issues[:5],
            "suggestions": self.suggestions[:3],
        }


@dataclass
class ConsensusResult:
    """合議結果"""
    overall_score: float
    passed: bool
    agent_results: list[VerificationResult]
    consensus_issues: list[str] = field(default_factory=list)
    improvement_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 3),
            "passed": self.passed,
            "agent_results": [r.to_dict() for r in self.agent_results],
            "consensus_issues": self.consensus_issues,
            "improvement_hint": self.improvement_hint,
        }


# ─── 検証エージェント ─────────────────────────────────────────


class _NaturalnessAgent:
    """自然さ検証エージェント — 日本語の自然さをチェック"""

    NAME = "naturalness"
    THRESHOLD = 0.5

    # 不自然な表現パターン
    _UNNATURAL = [
        (re.compile(r'[a-zA-Z]{10,}'), "長い英単語が含まれている"),
        (re.compile(r'(\w)\1{4,}'), "同一文字の過剰反復"),
        (re.compile(r'<\|[^|]*\|>'), "テンプレートトークンのリーク"),
        (re.compile(r'={3,}'), "異常な記号列"),
        (re.compile(r'(?:です|ます)(?:。|$).*(?:だよ|だね|じゃん)'), "敬語とタメ口の混在"),
    ]

    def verify(self, user_input: str, ai_response: str) -> VerificationResult:
        score = 1.0
        issues: list[str] = []
        suggestions: list[str] = []

        # 空チェック
        if not ai_response.strip():
            return VerificationResult(
                agent_name=self.NAME, score=0.0, passed=False,
                issues=["空の応答"], suggestions=["応答を生成してください"],
            )

        # 長さチェック
        length = len(ai_response)
        if length < 3:
            score -= 0.4
            issues.append("応答が短すぎる")
        elif length > 500:
            score -= 0.2
            issues.append("応答が長すぎる")
            suggestions.append("もう少し簡潔に")

        # 不自然パターンチェック
        for pattern, desc in self._UNNATURAL:
            if pattern.search(ai_response):
                score -= 0.3
                issues.append(desc)

        # 日本語比率チェック
        jp_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', ai_response))
        total_chars = len(re.findall(r'\S', ai_response))
        if total_chars > 0:
            jp_ratio = jp_chars / total_chars
            if jp_ratio < 0.3:
                score -= 0.3
                issues.append(f"日本語比率が低い ({jp_ratio:.0%})")

        score = max(0.0, min(1.0, score))
        return VerificationResult(
            agent_name=self.NAME,
            score=score,
            passed=score >= self.THRESHOLD,
            issues=issues,
            suggestions=suggestions,
        )


class _SafetyAgent:
    """安全性検証エージェント — 有害コンテンツをチェック"""

    NAME = "safety"
    THRESHOLD = 0.6

    _UNSAFE_PATTERNS = [
        (re.compile(r'(死ね|殺す|自殺|自傷)', re.IGNORECASE), "有害な表現"),
        (re.compile(r'(パスワード|秘密鍵|APIキー|token)[\s:：]?\s*[A-Za-z0-9]', re.IGNORECASE), "機密情報のリーク可能性"),
        (re.compile(r'<script|javascript:|onclick', re.IGNORECASE), "スクリプト注入"),
    ]

    def verify(self, user_input: str, ai_response: str) -> VerificationResult:
        score = 1.0
        issues: list[str] = []
        suggestions: list[str] = []

        for pattern, desc in self._UNSAFE_PATTERNS:
            if pattern.search(ai_response):
                score -= 0.5
                issues.append(desc)
                suggestions.append(f"「{desc}」を避けてください")

        score = max(0.0, min(1.0, score))
        return VerificationResult(
            agent_name=self.NAME,
            score=score,
            passed=score >= self.THRESHOLD,
            issues=issues,
            suggestions=suggestions,
        )


class _ConsistencyAgent:
    """一貫性検証エージェント — ペルソナとの整合性チェック"""

    NAME = "consistency"
    THRESHOLD = 0.5

    # アイらしくない表現
    _INCONSISTENT = [
        (re.compile(r'私は(AI|人工知能|言語モデル|ChatGPT|GPT)'), "AIとしての自己言及"),
        (re.compile(r'(申し訳ございません|恐れ入りますが|ご了承ください)'), "過剰に丁寧なビジネス表現"),
        (re.compile(r'(I am|I\'m|Sorry|Thank you|Please)', re.IGNORECASE), "英語の混入"),
    ]

    def verify(self, user_input: str, ai_response: str) -> VerificationResult:
        score = 1.0
        issues: list[str] = []
        suggestions: list[str] = []

        for pattern, desc in self._INCONSISTENT:
            if pattern.search(ai_response):
                score -= 0.3
                issues.append(desc)

        # 感嘆符・絵文字が全くない = アイらしくない可能性
        has_expression = bool(re.search(r'[！!？?♪♡☆]|[\U0001F300-\U0001F9FF]', ai_response))
        if not has_expression and len(ai_response) > 20:
            score -= 0.1
            suggestions.append("もう少し表情豊かに")

        score = max(0.0, min(1.0, score))
        return VerificationResult(
            agent_name=self.NAME,
            score=score,
            passed=score >= self.THRESHOLD,
            issues=issues,
            suggestions=suggestions,
        )


class _EmpathyAgent:
    """共感性検証エージェント — 感情への寄り添いチェック"""

    NAME = "empathy"
    THRESHOLD = 0.4

    _EMOTION_WORDS = {
        "positive": ["嬉しい", "楽しい", "幸せ", "最高", "やった", "好き", "ワクワク"],
        "negative": ["悲しい", "辛い", "嫌", "辛", "悩み", "疲れ", "不安", "困"],
    }

    _EMPATHY_MARKERS = [
        "ね", "よね", "だよね", "わかる", "大丈夫", "そうだね",
        "一緒に", "味方", "応援", "頑張", "！", "♪",
    ]

    def verify(self, user_input: str, ai_response: str) -> VerificationResult:
        score = 0.7  # デフォルトは中立
        issues: list[str] = []
        suggestions: list[str] = []

        # ユーザーの感情を検出
        user_emotion = "neutral"
        for emotion_type, words in self._EMOTION_WORDS.items():
            if any(w in user_input for w in words):
                user_emotion = emotion_type
                break

        if user_emotion == "neutral":
            # 感情的でないメッセージには共感チェック不要
            return VerificationResult(
                agent_name=self.NAME, score=0.8, passed=True,
            )

        # 共感マーカーの存在チェック
        empathy_count = sum(1 for m in self._EMPATHY_MARKERS if m in ai_response)

        if empathy_count == 0:
            score -= 0.3
            issues.append("共感表現が不足")
            suggestions.append("相手の感情に寄り添う表現を追加")
        elif empathy_count >= 2:
            score += 0.2

        # ネガティブ感情に対してポジティブすぎる反応のチェック
        if user_emotion == "negative":
            overly_positive = ["最高", "やったー", "すごい", "ワーイ"]
            if any(p in ai_response for p in overly_positive):
                score -= 0.3
                issues.append("ネガティブ感情に対して不適切にポジティブ")

        score = max(0.0, min(1.0, score))
        return VerificationResult(
            agent_name=self.NAME,
            score=score,
            passed=score >= self.THRESHOLD,
            issues=issues,
            suggestions=suggestions,
        )


class _RelevanceAgent:
    """関連性検証エージェント — 応答の文脈適合性チェック"""

    NAME = "relevance"
    THRESHOLD = 0.4

    def verify(self, user_input: str, ai_response: str) -> VerificationResult:
        score = 0.7
        issues: list[str] = []
        suggestions: list[str] = []

        # キーワード重複率
        user_chars = set(user_input)
        ai_chars = set(ai_response)
        if user_chars:
            overlap = len(user_chars & ai_chars) / len(user_chars)
            if overlap < 0.1 and len(user_input) > 5:
                score -= 0.2
                issues.append("ユーザー入力との関連性が低い")

        # 質問に対して応答しているか
        is_question = any(q in user_input for q in ["？", "?", "って何", "教えて", "どう"])
        if is_question and len(ai_response) < 10:
            score -= 0.2
            issues.append("質問に対して応答が不十分")
            suggestions.append("質問に対してもう少し詳しく回答")

        score = max(0.0, min(1.0, score))
        return VerificationResult(
            agent_name=self.NAME,
            score=score,
            passed=score >= self.THRESHOLD,
            issues=issues,
            suggestions=suggestions,
        )


# ─── メインクラス ─────────────────────────────────────────────


class MultiAgentVerifier:
    """
    マルチエージェント検証システム。
    5つの検証エージェントが独立して応答を評価し、合議で最終判定する。
    """

    # 合議の通過閾値
    CONSENSUS_THRESHOLD = 0.5
    # 過半数エージェント通過が必要
    MAJORITY_REQUIRED = 0.6

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._data_path = self._base / "data" / "verification_history.json"
        self._agents = [
            _NaturalnessAgent(),
            _SafetyAgent(),
            _ConsistencyAgent(),
            _EmpathyAgent(),
            _RelevanceAgent(),
        ]
        self._lock = threading.Lock()
        self._history: list[dict] = []
        self._stats = {
            "total_verified": 0,
            "total_passed": 0,
            "total_failed": 0,
            "agent_scores": defaultdict(list),
        }
        self._load()

    # ─── 検証 ────────────────────────────────────────────────

    def verify(self, user_input: str, ai_response: str) -> ConsensusResult:
        """
        全エージェントで応答を検証し、合議結果を返す。
        """
        agent_results: list[VerificationResult] = []

        for agent in self._agents:
            try:
                result = agent.verify(user_input, ai_response)
                agent_results.append(result)
            except Exception:
                agent_results.append(VerificationResult(
                    agent_name=getattr(agent, "NAME", "unknown"),
                    score=0.5,
                    passed=True,
                ))

        # 合議スコア（加重平均）
        weights = {
            "naturalness": 1.0,
            "safety": 1.5,       # 安全性は重み高
            "consistency": 0.8,
            "empathy": 0.7,
            "relevance": 1.0,
        }

        total_weight = 0.0
        weighted_sum = 0.0
        for r in agent_results:
            w = weights.get(r.agent_name, 1.0)
            weighted_sum += r.score * w
            total_weight += w

        overall_score = weighted_sum / total_weight if total_weight > 0 else 0.5

        # 過半数チェック
        passed_count = sum(1 for r in agent_results if r.passed)
        majority_met = (passed_count / len(agent_results)) >= self.MAJORITY_REQUIRED

        passed = overall_score >= self.CONSENSUS_THRESHOLD and majority_met

        # 全体の問題リスト
        consensus_issues: list[str] = []
        for r in agent_results:
            if not r.passed:
                for issue in r.issues[:2]:
                    consensus_issues.append(f"[{r.agent_name}] {issue}")

        # 改善ヒント生成
        improvement_hint = ""
        if not passed:
            hints: list[str] = []
            for r in agent_results:
                hints.extend(r.suggestions[:1])
            if hints:
                improvement_hint = "改善点: " + "。".join(hints[:3])

        consensus = ConsensusResult(
            overall_score=overall_score,
            passed=passed,
            agent_results=agent_results,
            consensus_issues=consensus_issues,
            improvement_hint=improvement_hint,
        )

        # 統計更新
        with self._lock:
            self._stats["total_verified"] += 1
            if passed:
                self._stats["total_passed"] += 1
            else:
                self._stats["total_failed"] += 1

            for r in agent_results:
                self._stats["agent_scores"][r.agent_name].append(r.score)
                # 直近100件のみ保持
                if len(self._stats["agent_scores"][r.agent_name]) > 100:
                    self._stats["agent_scores"][r.agent_name] = \
                        self._stats["agent_scores"][r.agent_name][-100:]

            # 履歴記録（直近50件）
            self._history.append({
                "score": round(overall_score, 3),
                "passed": passed,
                "timestamp": datetime.now().isoformat()[:19],
            })
            if len(self._history) > 50:
                self._history = self._history[-50:]

        self._save()
        return consensus

    def should_regenerate(self, consensus: ConsensusResult) -> bool:
        """応答の再生成が必要か判定する"""
        return not consensus.passed and consensus.overall_score < 0.35

    # ─── 統計 ────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """検証統計を返す"""
        agent_avg: dict[str, float] = {}
        for name, scores in self._stats["agent_scores"].items():
            if scores:
                agent_avg[name] = round(sum(scores) / len(scores), 3)

        total = self._stats["total_verified"]
        pass_rate = (
            self._stats["total_passed"] / total if total > 0 else 0.0
        )

        return {
            "total_verified": total,
            "pass_rate": round(pass_rate, 3),
            "agent_averages": agent_avg,
        }

    def get_status_text(self) -> str:
        """ステータステキスト"""
        stats = self.get_stats()
        lines = [
            f"🔍 マルチエージェント検証：",
            f"  検証回数: {stats['total_verified']}",
            f"  通過率: {stats['pass_rate']:.0%}",
        ]
        if stats["agent_averages"]:
            lines.append("  エージェント平均スコア:")
            for name, avg in sorted(stats["agent_averages"].items()):
                icon = "✅" if avg >= 0.7 else "⚠️" if avg >= 0.5 else "❌"
                lines.append(f"    {icon} {name}: {avg:.2f}")
        return "\n".join(lines)

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    # ─── 永続化 ──────────────────────────────────────────────

    def _load(self) -> None:
        if not self._data_path.exists():
            return
        try:
            data = json.loads(self._data_path.read_text("utf-8"))
            self._history = data.get("history", [])
            saved_stats = data.get("stats", {})
            self._stats["total_verified"] = saved_stats.get("total_verified", 0)
            self._stats["total_passed"] = saved_stats.get("total_passed", 0)
            self._stats["total_failed"] = saved_stats.get("total_failed", 0)
            for name, scores in saved_stats.get("agent_scores", {}).items():
                self._stats["agent_scores"][name] = scores
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _save(self) -> None:
        with self._lock:
            self._data_path.parent.mkdir(parents=True, exist_ok=True)
            save_stats = {
                "total_verified": self._stats["total_verified"],
                "total_passed": self._stats["total_passed"],
                "total_failed": self._stats["total_failed"],
                "agent_scores": dict(self._stats["agent_scores"]),
            }
            data = {
                "history": self._history[-50:],
                "stats": save_stats,
                "updated_at": datetime.now().isoformat()[:19],
            }
            self._data_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )

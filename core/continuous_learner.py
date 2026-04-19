"""
継続的学習エンジン (Continuous Learning Engine)
ヤマト計画 A2: 会話品質に基づく選択的学習と知識蒸留。

機能:
- 品質スコアに基づく選択的学習（高品質会話のみ蓄積）
- トピッククラスタリング（類似会話のグループ化）
- 学習カリキュラム（簡単→難しいの順序制御）
- 知識蒸留（冗長な学習データの圧縮・統合）
- 学習効果の追跡・可視化
- ユーザー語彙追跡 (#74)
- 品質スコアリングによる few-shot 最適化 (#80)
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LearningExample:
    """学習用の会話例"""
    user: str
    ai: str
    quality_score: float = 0.5
    topic: str = "general"
    difficulty: int = 1          # 1=簡単, 2=普通, 3=難しい
    created_at: str = ""
    use_count: int = 0           # few-shotで使用された回数

    def to_dict(self) -> dict:
        return {
            "user": self.user,
            "ai": self.ai,
            "quality_score": self.quality_score,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "created_at": self.created_at,
            "use_count": self.use_count,
        }


@dataclass
class TopicCluster:
    """トピッククラスター"""
    name: str
    keywords: list[str]
    example_count: int = 0
    avg_quality: float = 0.5

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "keywords": self.keywords[:10],
            "example_count": self.example_count,
            "avg_quality": round(self.avg_quality, 3),
        }


# ─── トピック分類キーワード ──────────────────────────────────

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "greeting": ["おはよう", "こんにちは", "こんばんは", "おやすみ", "ただいま", "行ってきます"],
    "emotion": ["嬉しい", "悲しい", "怒り", "不安", "楽しい", "辛い", "寂しい", "疲れ", "ストレス"],
    "daily_life": ["ご飯", "仕事", "学校", "バイト", "買い物", "掃除", "料理", "洗濯"],
    "hobby": ["ゲーム", "音楽", "映画", "アニメ", "漫画", "読書", "スポーツ", "旅行"],
    "technology": ["プログラミング", "AI", "コード", "Python", "パソコン", "アプリ"],
    "relationship": ["友達", "彼氏", "彼女", "家族", "上司", "同僚", "恋人"],
    "knowledge": ["なぜ", "どうして", "仕組み", "意味", "歴史", "科学", "理由"],
    "creative": ["物語", "詩", "歌", "絵", "デザイン", "アイデア", "想像"],
    "consultation": ["相談", "アドバイス", "どうすれば", "悩み", "困って", "助けて"],
}


def _classify_topic(text: str) -> str:
    """テキストのトピックを分類する"""
    scores: dict[str, int] = defaultdict(int)
    for topic, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[topic] += 1
    if not scores:
        return "general"
    return max(scores, key=lambda k: scores[k])


def _estimate_difficulty(user: str, ai: str) -> int:
    """会話の難易度を推定する"""
    combined = user + ai
    length = len(combined)
    # 短い→簡単, 中間→普通, 長い→難しい
    if length < 50:
        return 1
    elif length < 200:
        return 2
    else:
        return 3


class ContinuousLearner:
    """
    品質ベースの継続的学習エンジン。
    高品質な会話を選択的に蓄積し、トピック別にクラスタリングする。
    """

    # 学習に必要な最低品質スコア
    MIN_QUALITY_THRESHOLD = 0.5
    # クラスター内の最大例数（超えたら蒸留）
    MAX_EXAMPLES_PER_TOPIC = 100
    # 蒸留後に残す例数
    DISTILL_TARGET = 50

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._data_path = self._base / "data" / "continuous_learning.json"
        self._vocab_path = self._base / "data" / "user_vocabulary.json"
        self._examples: list[LearningExample] = []
        self._clusters: dict[str, TopicCluster] = {}
        self._user_vocabulary: Counter = Counter()
        self._lock = threading.Lock()
        self._stats = {
            "total_learned": 0,
            "total_rejected": 0,
            "distillations": 0,
        }
        self._load()
        self._load_vocabulary()

    # ─── 学習 ────────────────────────────────────────────────

    def learn_from_conversation(
        self, user_input: str, ai_response: str, quality_score: float = 0.5
    ) -> dict:
        """
        会話から選択的に学習する。
        品質スコアが閾値以上の場合のみ蓄積。
        """
        result = {"learned": False, "reason": "", "topic": ""}

        # 品質フィルタリング
        if quality_score < self.MIN_QUALITY_THRESHOLD:
            self._stats["total_rejected"] += 1
            result["reason"] = f"品質スコア不足 ({quality_score:.2f} < {self.MIN_QUALITY_THRESHOLD})"
            return result

        # 基本検証
        if len(user_input.strip()) < 2 or len(ai_response.strip()) < 2:
            result["reason"] = "テキストが短すぎる"
            return result

        if len(ai_response) > 500:
            result["reason"] = "応答が長すぎる"
            return result

        # トピック分類と難易度推定
        topic = _classify_topic(user_input)
        difficulty = _estimate_difficulty(user_input, ai_response)
        now = datetime.now().isoformat()[:19]

        # 重複チェック（完全一致のみ）
        for ex in self._examples:
            if ex.user == user_input and ex.ai == ai_response:
                result["reason"] = "重複"
                return result

        # 学習例を作成
        example = LearningExample(
            user=user_input[:200],
            ai=ai_response[:400],
            quality_score=quality_score,
            topic=topic,
            difficulty=difficulty,
            created_at=now,
        )

        with self._lock:
            self._examples.append(example)
            self._update_cluster(topic, quality_score)
            self._stats["total_learned"] += 1

        # クラスターが溢れたら蒸留
        topic_count = sum(1 for e in self._examples if e.topic == topic)
        if topic_count > self.MAX_EXAMPLES_PER_TOPIC:
            self._distill_topic(topic)

        self._save()

        result["learned"] = True
        result["topic"] = topic
        result["reason"] = f"品質 {quality_score:.2f}, トピック: {topic}"
        return result

    # ─── カリキュラム学習 ───────────────────────────────────────

    def get_curriculum_examples(
        self, n: int = 5, topic: str = "", difficulty: int = 0, user_input: str = ""
    ) -> list[dict]:
        """
        カリキュラムに基づいて学習例を選択する。
        - topic指定: そのトピックから優先
        - difficulty指定: そのレベルから優先
        - user_input指定: 関連度が高い例を優先
        """
        if not self._examples:
            return []

        candidates = list(self._examples)

        # トピックフィルタ
        if topic:
            topic_match = [e for e in candidates if e.topic == topic]
            if topic_match:
                candidates = topic_match

        # 難易度フィルタ
        if difficulty > 0:
            diff_match = [e for e in candidates if e.difficulty == difficulty]
            if diff_match:
                candidates = diff_match

        # スコアリング (#80: score_example で品質ソート)
        scored: list[tuple[float, LearningExample]] = []
        for ex in candidates:
            # 品質スコアリング
            example_score = self.score_example(ex.to_dict()) * 10
            # 関連度ボーナス
            if user_input:
                overlap = sum(1 for c in user_input if c in ex.user)
                example_score += min(overlap, 5)
            # 使用頻度が低いものを優先（多様性）
            example_score -= ex.use_count * 0.5
            scored.append((example_score, ex))

        scored.sort(key=lambda x: -x[0])
        selected = scored[:n]

        # 使用カウント更新
        for _, ex in selected:
            ex.use_count += 1

        return [ex.to_dict() for _, ex in selected]

    def get_few_shot_text(
        self, n: int = 5, user_input: str = "", topic: str = ""
    ) -> str:
        """カリキュラムベースのfew-shotテキストを返す"""
        examples = self.get_curriculum_examples(
            n=n, topic=topic, user_input=user_input
        )
        if not examples:
            return ""

        lines = []
        for ex in examples:
            lines.append(f'{ex["user"]} → {ex["ai"]}')
        return "Examples:\n" + "\n".join(lines)

    # ─── 蒸留 ────────────────────────────────────────────────

    def _distill_topic(self, topic: str) -> int:
        """
        トピック内の低品質・冗長な例を削減する（知識蒸留）。
        品質スコア上位を残し、残りを削除する。
        """
        with self._lock:
            topic_examples = [e for e in self._examples if e.topic == topic]
            other_examples = [e for e in self._examples if e.topic != topic]

            # 品質スコアでソート（高い順）
            topic_examples.sort(key=lambda e: -e.quality_score)

            # 上位のみ残す
            kept = topic_examples[:self.DISTILL_TARGET]
            removed = len(topic_examples) - len(kept)

            self._examples = other_examples + kept
            self._stats["distillations"] += 1

        return removed

    def distill_all(self) -> dict:
        """全トピックの蒸留を実行する"""
        total_removed = 0
        topics_distilled = []

        for topic in list(self._clusters.keys()):
            count = sum(1 for e in self._examples if e.topic == topic)
            if count > self.DISTILL_TARGET:
                removed = self._distill_topic(topic)
                total_removed += removed
                topics_distilled.append(topic)

        if total_removed > 0:
            self._save()

        return {
            "topics_distilled": topics_distilled,
            "examples_removed": total_removed,
            "remaining_total": len(self._examples),
        }

    # ─── クラスター管理 ──────────────────────────────────────

    def _update_cluster(self, topic: str, quality_score: float) -> None:
        """クラスター統計を更新する"""
        if topic not in self._clusters:
            keywords = _TOPIC_KEYWORDS.get(topic, [])
            self._clusters[topic] = TopicCluster(
                name=topic, keywords=keywords
            )
        cluster = self._clusters[topic]
        # 移動平均で品質を更新
        total = cluster.example_count
        cluster.avg_quality = (
            (cluster.avg_quality * total + quality_score) / (total + 1)
        )
        cluster.example_count += 1

    # ─── 統計・情報 ──────────────────────────────────────────

    def get_stats(self) -> dict:
        """学習統計を返す"""
        topic_dist: dict[str, int] = defaultdict(int)
        for ex in self._examples:
            topic_dist[ex.topic] += 1

        return {
            **self._stats,
            "total_examples": len(self._examples),
            "topic_distribution": dict(topic_dist),
            "clusters": len(self._clusters),
            "avg_quality": (
                sum(e.quality_score for e in self._examples) / len(self._examples)
                if self._examples else 0.0
            ),
        }

    def get_status_text(self) -> str:
        """ステータステキストを返す"""
        stats = self.get_stats()
        lines = [
            f"📚 継続的学習エンジン：",
            f"  学習済み: {stats['total_examples']}例",
            f"  平均品質: {stats['avg_quality']:.2f}",
            f"  クラスター数: {stats['clusters']}",
        ]
        if stats["topic_distribution"]:
            lines.append("  トピック分布:")
            for topic, count in sorted(
                stats["topic_distribution"].items(), key=lambda x: -x[1]
            )[:5]:
                cluster = self._clusters.get(topic)
                q = f" (品質: {cluster.avg_quality:.2f})" if cluster else ""
                lines.append(f"    {topic}: {count}例{q}")

        lines.append(f"  蒸留回数: {stats['distillations']}")
        return "\n".join(lines)

    @property
    def example_count(self) -> int:
        return len(self._examples)

    # ─── ユーザー語彙追跡 (#74) ─────────────────────────────────

    def update_vocabulary(self, user_input: str) -> None:
        """ユーザー入力から語彙を更新する"""
        # 簡易トークナイズ: 日本語文字の連続区間とASCII単語を抽出
        tokens = re.findall(
            r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+|[a-zA-Z]+',
            user_input,
        )
        # 短すぎるトークンは除外
        meaningful = [t for t in tokens if len(t) >= 2]
        with self._lock:
            self._user_vocabulary.update(meaningful)
        self._save_vocabulary()

    def get_frequent_words(self, top_n: int = 20) -> list[tuple[str, int]]:
        """頻出語彙トップ N を返す"""
        return self._user_vocabulary.most_common(top_n)

    def _load_vocabulary(self) -> None:
        """語彙データを読み込む"""
        if not self._vocab_path.exists():
            return
        try:
            data = json.loads(self._vocab_path.read_text("utf-8"))
            self._user_vocabulary = Counter(data)
        except (json.JSONDecodeError, TypeError):
            pass

    def _save_vocabulary(self) -> None:
        """語彙データを保存する"""
        self._vocab_path.parent.mkdir(parents=True, exist_ok=True)
        self._vocab_path.write_text(
            json.dumps(dict(self._user_vocabulary.most_common(500)), ensure_ascii=False, indent=2),
            "utf-8",
        )

    # ─── 品質スコアリング (#80) ────────────────────────────────

    @staticmethod
    def score_example(example: dict) -> float:
        """
        学習例の品質スコアを計算する。

        スコア基準:
        - 長さ: 短すぎず長すぎない応答が高得点
        - 日本語含有率: 日本語が多いほど高得点
        - 繰り返しなし: 同じフレーズの繰り返しがないほど高得点
        - 基本 quality_score も加味

        Returns:
            0.0-1.0 の品質スコア
        """
        ai_text = example.get("ai", "")
        user_text = example.get("user", "")
        base_quality = example.get("quality_score", 0.5)

        score = 0.0

        # 長さスコア (20-150文字が理想的)
        ai_len = len(ai_text)
        if 20 <= ai_len <= 150:
            score += 0.3
        elif 10 <= ai_len <= 200:
            score += 0.2
        elif ai_len > 0:
            score += 0.1

        # 日本語含有率
        jp_chars = sum(
            1 for c in ai_text
            if '\u3000' <= c <= '\u9fff' or '\uff00' <= c <= '\uffef'
        )
        total_chars = max(len(ai_text), 1)
        jp_ratio = jp_chars / total_chars
        score += jp_ratio * 0.3

        # 繰り返しチェック: 3文字以上のフレーズが2回以上出現しない
        has_repetition = bool(re.search(r'(.{3,})\1', ai_text))
        if not has_repetition:
            score += 0.2

        # 基本品質スコアを加味
        score += base_quality * 0.2

        return min(1.0, round(score, 3))

    # ─── 永続化 ──────────────────────────────────────────────

    def _load(self) -> None:
        """ファイルから読み込む"""
        if not self._data_path.exists():
            return
        try:
            data = json.loads(self._data_path.read_text("utf-8"))
            for e_data in data.get("examples", []):
                self._examples.append(LearningExample(**e_data))
            for c_data in data.get("clusters", []):
                cluster = TopicCluster(**c_data)
                self._clusters[cluster.name] = cluster
            self._stats.update(data.get("stats", {}))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _save(self) -> None:
        """ファイルに保存する"""
        with self._lock:
            self._data_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "examples": [e.to_dict() for e in self._examples],
                "clusters": [c.to_dict() for c in self._clusters.values()],
                "stats": self._stats,
                "updated_at": datetime.now().isoformat()[:19],
            }
            self._data_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )

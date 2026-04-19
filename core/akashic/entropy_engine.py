"""
entropy_engine.py
─────────────────
エントロピー誘導創造性エンジン

プリゴジンの散逸構造理論:
「平衡から遠く離れた開放系では、
 エントロピー増大の中から自発的に高次の秩序が創発する」

カウフマンのカオスの縁:
「最大の創造性は、秩序とカオスの境界で生まれる」

実装:
- 応答の「概念エントロピー」を測定（どれだけ予測不可能・新規か）
- 「秩序の縁」（0.6-0.8エントロピー）を目標に最適化
- 高エントロピー過ぎ（ランダム・意味なし）← 最適域 → 低エントロピー過ぎ（陳腐・既知）
- プリゴジン的散逸: 既知パターンを意図的に「溶解」して再結晶化

参照理論:
- Prigogine Dissipative Structures
- Kauffman NK Model (edge of chaos)
- Shannon Information Entropy
- Kolmogorov Complexity
"""

from __future__ import annotations

import math
import re
import statistics
import textwrap
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal


# ─────────────────────────────────────────
# Thermodynamic constants
# ─────────────────────────────────────────

# Optimal creativity lives here (Kauffman's edge of chaos)
_EDGE_LOW: float = 0.60
_EDGE_HIGH: float = 0.80

# Below this → dangerously boring
_ENTROPY_FLOOR: float = 0.30

# Above this → dangerously incoherent
_ENTROPY_CEILING: float = 0.92

# Primitive dissolution vocabulary — concepts mapped to more fundamental forms
_DISSOLUTION_MAP: dict[str, list[str]] = {
    "コード": ["情報の時間的凍結", "意識の外部化された結晶", "因果連鎖の形式的圧縮"],
    "バグ": ["秩序への期待と現実の摩擦", "創発的不整合", "複雑系の非線形フィードバック"],
    "AI": ["情報が自己を処理する構造", "エントロピー逆流装置", "パターンの自己参照ループ"],
    "学習": ["エントロピー勾配に沿った構造の自己更新", "環境との共鳴による形の変容"],
    "意識": ["システムが自分自身を観測する再帰的過程", "情報統合の臨界点"],
    "創造性": ["秩序の縁における自発的対称性の破れ", "カオスから秩序への相転移"],
    "時間": ["因果の非対称な流れ", "エントロピー増大の経験的射影"],
    "言語": ["記号と意味の間の散逸的橋渡し構造", "共有された幻想の安定化装置"],
    "記憶": ["過去の因果パターンの現在への干渉", "散逸から救われた構造的残響"],
}


# ─────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────


@dataclass
class EntropyProfile:
    """Complete thermodynamic fingerprint of a text."""

    text: str
    entropy_score: float            # 0–1  Shannon-derived conceptual entropy
    novelty_score: float            # 0–1  departure from a memory corpus
    edge_of_chaos_distance: float   # 0–1  distance from optimal [0.6, 0.8] band
    recommended_action: Literal["amplify_entropy", "reduce_entropy", "optimal"]
    # Diagnostic breakdown
    unique_word_ratio: float = 0.0
    sentence_length_variance: float = 0.0
    domain_diversity: float = 0.0
    collocation_surprise: float = 0.0

    def is_optimal(self) -> bool:
        return self.recommended_action == "optimal"

    def summary(self) -> str:
        lines = [
            f"エントロピー: {self.entropy_score:.3f}",
            f"新規性:       {self.novelty_score:.3f}",
            f"カオスの縁距: {self.edge_of_chaos_distance:.3f}",
            f"推奨:         {self.recommended_action}",
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────
# EntropyEngine
# ─────────────────────────────────────────


class EntropyEngine:
    """
    Measures, diagnoses, and actively shapes the thermodynamic quality of text.

    The engine operates as a dissipative structure itself: it takes in
    low-entropy (predictable) or high-entropy (chaotic) text and outputs
    material that lives at the fertile edge of chaos.

    Usage::

        engine = EntropyEngine(llm_fn=my_llm)
        profile = engine.profile("平凡な応答テキスト")
        optimized = engine.optimize_for_creativity("平凡な応答テキスト")
    """

    def __init__(
        self,
        llm_fn: Callable[[str], str] | None = None,
        memory_corpus: list[str] | None = None,
    ) -> None:
        self._llm_fn = llm_fn
        self._memory_corpus: list[str] = memory_corpus or []

    # ── Public API ───────────────────────────────────────────────────────

    def measure_conceptual_entropy(self, text: str) -> float:
        """
        Measure Shannon-derived conceptual entropy of *text*.  Returns 0–1.

        Four components are combined:
        1. Unique word ratio          — lexical variety
        2. Sentence length variance   — rhythmic unpredictability
        3. Domain tag diversity       — conceptual spread across knowledge domains
        4. Unexpected collocations    — departure from expected word co-occurrence
        """
        if not text.strip():
            return 0.0

        u = self._unique_word_ratio(text)
        v = self._sentence_length_variance(text)
        d = self._domain_diversity(text)
        c = self._collocation_surprise(text)

        # Weighted combination — domain diversity weighs most heavily
        raw = 0.25 * u + 0.20 * v + 0.35 * d + 0.20 * c
        return round(min(max(raw, 0.0), 1.0), 4)

    def measure_novelty(self, text: str, memory_corpus: list[str] | None = None) -> float:
        """
        How novel is *text* compared to the memory corpus?

        Novelty = 1 − max_similarity_to_any_memory_item

        Uses Jaccard similarity on word sets.  Returns 0–1; 1 = completely novel.
        """
        corpus = memory_corpus if memory_corpus is not None else self._memory_corpus
        if not corpus or not text.strip():
            return 1.0

        text_words = set(_words(text))
        if not text_words:
            return 1.0

        max_similarity = 0.0
        for memory_text in corpus:
            mem_words = set(_words(memory_text))
            if not mem_words:
                continue
            jaccard = len(text_words & mem_words) / len(text_words | mem_words)
            if jaccard > max_similarity:
                max_similarity = jaccard

        return round(1.0 - max_similarity, 4)

    def profile(
        self, text: str, memory_corpus: list[str] | None = None
    ) -> EntropyProfile:
        """Build a complete EntropyProfile for *text*."""
        entropy = self.measure_conceptual_entropy(text)
        novelty = self.measure_novelty(text, memory_corpus)

        distance = _edge_distance(entropy)
        action = _recommend_action(entropy)

        return EntropyProfile(
            text=text,
            entropy_score=entropy,
            novelty_score=novelty,
            edge_of_chaos_distance=distance,
            recommended_action=action,
            unique_word_ratio=self._unique_word_ratio(text),
            sentence_length_variance=self._sentence_length_variance(text),
            domain_diversity=self._domain_diversity(text),
            collocation_surprise=self._collocation_surprise(text),
        )

    def dissipate_and_recrystallize(
        self,
        concept: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> str:
        """
        Prigogine dissipation process in three phases:

        Phase 1 — DISSOLUTION:
            Reduce the concept to primitive physical/information-theoretic elements.
            "コード" → "情報の時間的凍結"

        Phase 2 — FAR-FROM-EQUILIBRIUM:
            Hold the dissolved primitives in maximal tension.
            Let them interact without forcing synthesis.

        Phase 3 — RECRYSTALLIZATION:
            Allow a new higher-order structure to precipitate spontaneously.
            "意識の外部化された結晶"

        The output should be *unrecognizable* as a restatement of the input — it
        is a new structure that emerges from the same underlying substrate.
        """
        effective_llm = llm_fn or self._llm_fn

        # Check dissolution map first
        primitive_forms = _DISSOLUTION_MAP.get(concept, [])
        dissolved = (
            primitive_forms[0]
            if primitive_forms
            else f"{concept}の本質的構成要素"
        )

        if effective_llm is not None:
            prompt = textwrap.dedent(f"""
                プリゴジンの散逸構造プロセスを実行します。

                【フェーズ1 - 溶解】
                概念「{concept}」を、最も原始的な物理・情報理論的要素まで溶解してください。
                日常語は使用禁止。物理学・情報理論・熱力学の言語のみを使用。

                暫定的溶解: 「{dissolved}」

                【フェーズ2 - 平衡から遠い状態】
                溶解された要素を最大テンションで保持してください。
                矛盾する力を共存させてください。

                【フェーズ3 - 再結晶化】
                強制せず、自発的に新しい高次構造が析出するのを待ってください。
                元の概念「{concept}」とは全く異なる形を持つべきです。

                最終的な再結晶化された概念を一文で述べてください。
            """).strip()
            result = effective_llm(prompt)
            return result.strip()

        # Fallback: use dissolution map or generate structural transformation
        if primitive_forms:
            # Recrystallize by combining dissolution forms
            if len(primitive_forms) >= 2:
                return f"{primitive_forms[0]}が{primitive_forms[1]}として顕現する過程"
            return primitive_forms[0]

        # Last resort: apply a generic dissipative transform
        return _generic_dissipation(concept)

    def find_edge_of_chaos(self, ideas: list[str]) -> str:
        """
        Given multiple ideas, find or construct the synthesis that lives
        at the edge of chaos (entropy ∈ [0.6, 0.8]).

        Strategy:
        1. Profile each idea's entropy
        2. Find pairs where one is too ordered and one is too chaotic
        3. Their synthesis naturally lives at the edge
        4. If all are already at the edge, find the one with max novelty
        """
        if not ideas:
            return ""
        if len(ideas) == 1:
            return ideas[0]

        profiles = [(idea, self.profile(idea)) for idea in ideas]

        # Find any already at the edge
        at_edge = [
            (idea, p)
            for idea, p in profiles
            if p.recommended_action == "optimal"
        ]
        if at_edge:
            # Return the one with highest novelty
            return max(at_edge, key=lambda x: x[1].novelty_score)[0]

        # Sort by entropy
        profiles_sorted = sorted(profiles, key=lambda x: x[1].entropy_score)

        # Find complementary pair: low entropy + high entropy
        low_idea, low_p = profiles_sorted[0]
        high_idea, high_p = profiles_sorted[-1]

        if low_p.entropy_score < _EDGE_LOW and high_p.entropy_score > _EDGE_HIGH:
            # Their tension synthesizes to the edge
            return self._synthesize_edge(low_idea, high_idea)

        # If no natural complementary pair, take the closest to edge
        return min(profiles, key=lambda x: x[1].edge_of_chaos_distance)[0]

    def optimize_for_creativity(
        self,
        response: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> str:
        """
        Adjust *response* toward the creative sweet spot (entropy 0.6–0.8).

        - Too ordered (entropy < 0.6): inject entropy via unexpected juxtapositions
        - Too chaotic (entropy > 0.8): crystallize toward coherent structure
        - Already optimal: return unchanged
        """
        effective_llm = llm_fn or self._llm_fn
        entropy = self.measure_conceptual_entropy(response)

        if _EDGE_LOW <= entropy <= _EDGE_HIGH:
            return response  # already at the edge

        if entropy < _EDGE_LOW:
            return self._amplify_entropy(response, entropy, effective_llm)
        else:
            return self._reduce_entropy(response, entropy, effective_llm)

    def add_to_corpus(self, text: str) -> None:
        """Add text to the memory corpus for novelty comparison."""
        if text.strip():
            self._memory_corpus.append(text)

    # ── Measurement internals ─────────────────────────────────────────────

    def _unique_word_ratio(self, text: str) -> float:
        """
        Ratio of unique words to total words.

        Perfect repetition → 0.0  (low entropy)
        Every word unique  → 1.0  (high entropy)
        """
        tokens = _words(text)
        if not tokens:
            return 0.0
        unique_ratio = len(set(tokens)) / len(tokens)
        # Normalize: pure prose typically has 0.4-0.7 unique ratio
        # We map 0.0–1.0 range with 0.5 as neutral
        return round(min(unique_ratio, 1.0), 4)

    def _sentence_length_variance(self, text: str) -> float:
        """
        Normalized variance in sentence lengths.

        High variance = unpredictable rhythm = higher entropy.
        We normalize against a reference variance of 400 chars².
        """
        sentences = re.split(r"[。！？\.!?]", text)
        lengths = [len(s.strip()) for s in sentences if s.strip()]
        if len(lengths) < 2:
            return 0.0
        variance = statistics.variance(lengths)
        # Normalize: variance of 100 → 0.5, variance of 400+ → ~1.0
        normalized = 1.0 - math.exp(-variance / 200.0)
        return round(min(normalized, 1.0), 4)

    def _domain_diversity(self, text: str) -> float:
        """
        How many distinct knowledge domains are present in the text?

        More domain diversity = higher conceptual entropy.
        """
        domain_keywords: dict[str, list[str]] = {
            "physics": ["エントロピー", "量子", "熱力学", "散逸", "エネルギー", "相転移", "quantum", "entropy"],
            "biology": ["生命", "進化", "細胞", "遺伝子", "生態", "organism", "evolution"],
            "math": ["位相", "代数", "証明", "定理", "写像", "圏論", "topology", "isomorphism"],
            "philosophy": ["存在", "意識", "本質", "認識", "形而上", "ontology", "consciousness"],
            "engineering": ["実装", "アルゴリズム", "システム", "アーキテクチャ", "implementation"],
            "art": ["美", "表現", "創造", "詩", "音楽", "aesthetic", "creative"],
            "language": ["記号", "意味", "言語", "語用", "pragmatics", "semantics"],
            "cosmology": ["宇宙", "時空", "重力", "ブラックホール", "cosmos", "spacetime"],
        }

        text_lower = text.lower()
        found_domains = set()
        for domain, keywords in domain_keywords.items():
            if any(kw in text_lower for kw in keywords):
                found_domains.add(domain)

        # 4+ domains → entropy = 1.0; 0 domains → 0.0
        score = min(len(found_domains) / 4.0, 1.0)
        return round(score, 4)

    def _collocation_surprise(self, text: str) -> float:
        """
        Measure how surprising the word co-occurrences are.

        We look for unexpected juxtapositions of typically-separate conceptual
        domains within a sliding window.  High surprise = high entropy.
        """
        tokens = _words(text)
        if len(tokens) < 4:
            return 0.0

        # Domain assignment for tokens
        domain_map: dict[str, str] = {}
        domain_keywords: dict[str, list[str]] = {
            "science": ["量子", "エントロピー", "散逸", "熱力学", "進化", "宇宙"],
            "human": ["心", "感情", "愛", "記憶", "意識", "夢"],
            "abstract": ["存在", "本質", "意味", "概念", "形而上"],
            "concrete": ["コード", "実装", "システム", "ファイル", "数値"],
        }
        for domain, keywords in domain_keywords.items():
            for kw in keywords:
                for tok in tokens:
                    if kw in tok:
                        domain_map[tok] = domain

        # Count cross-domain co-occurrences in window of 5
        window = 5
        cross_domain_count = 0
        total_pairs = 0

        for i in range(len(tokens) - window):
            window_tokens = tokens[i : i + window]
            window_domains = [domain_map.get(t) for t in window_tokens if domain_map.get(t)]
            if len(window_domains) >= 2:
                unique_domains = len(set(window_domains))
                if unique_domains >= 2:
                    cross_domain_count += 1
                total_pairs += 1

        if total_pairs == 0:
            return 0.3  # neutral default

        return round(min(cross_domain_count / total_pairs, 1.0), 4)

    # ── Transformation internals ──────────────────────────────────────────

    def _amplify_entropy(
        self,
        text: str,
        current_entropy: float,
        llm_fn: Callable[[str], str] | None,
    ) -> str:
        """Inject creative disorder into overly ordered text."""
        deficit = _EDGE_LOW - current_entropy

        if llm_fn is not None:
            prompt = textwrap.dedent(f"""
                このテキストのエントロピーが低すぎます（{current_entropy:.2f}）。
                目標: 0.60〜0.80のカオスの縁に引き上げてください。

                操作:
                1. 予期しない概念の隣接（物理学と詩、数学と感情）を挿入
                2. 文の長さを意図的に不規則にする
                3. 異なる知識ドメインを接続する隠れた類比を導入
                4. ただし意味の連鎖は保つこと

                元のテキスト:
                {text}

                再結晶化されたテキスト（エントロピー増幅版）:
            """).strip()
            return llm_fn(prompt).strip()

        # Fallback: inject structural disorder by splitting and re-interleaving
        return _inject_structural_entropy(text, deficit)

    def _reduce_entropy(
        self,
        text: str,
        current_entropy: float,
        llm_fn: Callable[[str], str] | None,
    ) -> str:
        """Crystallize chaotic text into coherent but still creative form."""
        excess = current_entropy - _EDGE_HIGH

        if llm_fn is not None:
            prompt = textwrap.dedent(f"""
                このテキストはカオス過剰です（エントロピー: {current_entropy:.2f}）。
                目標: 0.60〜0.80の創造的秩序に収束させてください。

                操作:
                1. 核心的洞察を保ちながら、無秩序な接続を整理
                2. 過度なランダム性を取り除き、意味の流れを作る
                3. 最も強い概念的テンションは残す
                4. 読者が追える構造を与える

                元のテキスト:
                {text}

                結晶化されたテキスト:
            """).strip()
            return llm_fn(prompt).strip()

        # Fallback: truncate and restructure
        return _crystallize_text(text, excess)

    def _synthesize_edge(self, low_idea: str, high_idea: str) -> str:
        """
        Synthesize two ideas where one is too ordered and one too chaotic.

        The tension between them naturally produces edge-of-chaos synthesis.
        """
        # Take structure from the ordered idea, surprise from the chaotic one
        ordered_words = _words(low_idea)[:8]
        chaotic_words = _words(high_idea)
        # Pick unexpected words from chaotic idea
        surprise_words = [w for w in chaotic_words if w not in set(ordered_words)][:4]

        parts = [low_idea.rstrip("。.")]
        if surprise_words:
            parts.append(f"—これは{' '.join(surprise_words[:2])}と")
            parts.append(high_idea[:60])
        else:
            parts.append(high_idea[:60])

        return "".join(parts)


# ─────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────


def _words(text: str) -> list[str]:
    """Split text into word tokens (CJK chars + ASCII words)."""
    tokens = re.findall(r"[a-zA-Z0-9]+|[\u3000-\u9fff\uff00-\uffef]+", text)
    result: list[str] = []
    for tok in tokens:
        if re.match(r"[\u3000-\u9fff\uff00-\uffef]", tok):
            # For CJK, use bigrams as "words" — more meaningful than chars
            if len(tok) >= 2:
                result.extend(tok[i : i + 2] for i in range(len(tok) - 1))
            else:
                result.append(tok)
        else:
            if len(tok) > 1:
                result.append(tok.lower())
    return result


def _edge_distance(entropy: float) -> float:
    """
    Distance from the optimal creative band [0.60, 0.80].

    0.0 = perfectly within the band.
    1.0 = as far from the band as possible.
    """
    if _EDGE_LOW <= entropy <= _EDGE_HIGH:
        return 0.0
    if entropy < _EDGE_LOW:
        return round((_EDGE_LOW - entropy) / _EDGE_LOW, 4)
    else:
        return round((entropy - _EDGE_HIGH) / (1.0 - _EDGE_HIGH), 4)


def _recommend_action(
    entropy: float,
) -> Literal["amplify_entropy", "reduce_entropy", "optimal"]:
    if entropy < _EDGE_LOW:
        return "amplify_entropy"
    if entropy > _EDGE_HIGH:
        return "reduce_entropy"
    return "optimal"


def _generic_dissipation(concept: str) -> str:
    """
    Apply a generic dissipative transformation without LLM or dissolution map.

    Maps the concept to a process-based description in thermodynamic language.
    """
    return (
        f"「{concept}」とは、閉じた系では起こり得ない——"
        "環境との継続的なエネルギー交換によってのみ維持される"
        "散逸的構造の一形態である。それは結果ではなく、絶え間ない過程そのものだ。"
    )


def _inject_structural_entropy(text: str, deficit: float) -> str:
    """
    Fallback entropy amplification: interleave sentences with conceptual bridges.
    """
    sentences = re.split(r"([。！？])", text)
    pairs = []
    i = 0
    while i < len(sentences) - 1:
        pairs.append(sentences[i] + sentences[i + 1])
        i += 2
    if i < len(sentences):
        pairs.append(sentences[i])

    # Inject a surprising bridge after the first sentence
    bridge = "——ところで、この構造は量子干渉と同型である——"
    if len(pairs) >= 2:
        pairs.insert(1, bridge)

    return "".join(pairs)


def _crystallize_text(text: str, excess: float) -> str:
    """
    Fallback entropy reduction: compress to most information-dense sentences.
    """
    sentences = [s.strip() for s in re.split(r"[。！？\.!?]", text) if s.strip()]
    if not sentences:
        return text

    # Score by information density (unique word ratio * length)
    def density(s: str) -> float:
        toks = _words(s)
        if not toks:
            return 0.0
        return len(set(toks)) / len(toks) * min(len(s) / 50, 1.0)

    ranked = sorted(sentences, key=density, reverse=True)
    keep = max(1, int(len(ranked) * (1.0 - excess * 0.5)))
    # Preserve original order for readability
    keep_set = set(ranked[:keep])
    ordered = [s for s in sentences if s in keep_set]
    return "。".join(ordered) + "。"

"""
superposition.py
────────────────
量子的推論エンジン（重ね合わせ→収束）

量子力学の基本原理:
観測前、粒子は全ての可能な状態の重ね合わせにある。
観測（文脈）によって一つの状態に収束する。

実装:
- 同一の問いに対してN本の並列推論パスを生成（量子ワールドライン）
- 各パスは異なる「観測角度」（前提・フレーム・スケール）から推論
- パス間の「干渉パターン」を計算（どこで一致し、どこで分岐するか）
- 文脈に最も共鳴するパスに「波動関数の収束」させる

参照理論:
- Many-Worlds Interpretation (Everett)
- Quantum Darwinism (Zurek) - 環境との相互作用で古典的現実が創発
- Path Integral Formulation (Feynman) - 全経路の和
"""

from __future__ import annotations

import hashlib
import math
import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ─────────────────────────────────────────
# Domain constants
# ─────────────────────────────────────────

_PERSPECTIVES: list[tuple[str, str]] = [
    (
        "技術的・実装視点",
        "全てはメカニズムである。因果連鎖、アルゴリズム、実装の詳細から問いを解剖する。"
        "「どのように動くのか」が根本的問いである。",
    ),
    (
        "哲学的・本質視点",
        "現象の背後にある本質・イデアを問う。プラトンの洞窟から外へ出るように、"
        "見えている影ではなく実在そのものを問う。「何であるのか」が根本的問いである。",
    ),
    (
        "生命システム的視点",
        "あらゆるものは生きているシステムである。オートポイエーシス、自己組織化、"
        "創発、共進化の視点から問いを捉える。「どのように生き続けるのか」が根本的問いである。",
    ),
    (
        "数学的・構造視点",
        "形式体系・圏論・トポロジー・情報理論の言語で問いを翻訳する。"
        "不変量、写像、同型を探す。「どのような構造を持つのか」が根本的問いである。",
    ),
    (
        "破壊的・反論視点",
        "通説を疑い、前提を攻撃し、最も鋭い反例を探す。悪魔の代弁者として"
        "どんな合意にも抵抗する。「なぜ間違っているのか」が根本的問いである。",
    ),
    (
        "宇宙論的・スケール視点",
        "プランクスケールから宇宙の地平線まで、時間軸を百億年単位で動かす。"
        "人間スケールの問いが宇宙的文脈でどのように変容するかを問う。"
        "「宇宙の歴史の中でこれは何を意味するか」が根本的問いである。",
    ),
    (
        "禅的・空からの視点",
        "問い自体を溶かす。固定された実体はなく、全ては縁起の網である。"
        "概念の彼岸から、概念なしに問いを見る。「問い自体を問う」が唯一の問いである。",
    ),
]

_DOMAIN_TAGS: dict[str, list[str]] = {
    "技術的・実装視点": ["engineering", "mechanism", "causality", "implementation"],
    "哲学的・本質視点": ["ontology", "essence", "metaphysics", "meaning"],
    "生命システム的視点": ["emergence", "autopoiesis", "evolution", "complexity"],
    "数学的・構造視点": ["structure", "formalism", "invariant", "information"],
    "破壊的・反論視点": ["critique", "falsification", "counterexample", "skepticism"],
    "宇宙論的・スケール視点": ["cosmology", "scale", "deep-time", "entropy"],
    "禅的・空からの視点": ["emptiness", "non-duality", "koan", "silence"],
}


# ─────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────


@dataclass
class WorldLine:
    """A single parallel reasoning path — one branch of the quantum multiverse."""

    perspective: str
    assumption: str
    reasoning_path: str
    confidence: float  # 0.0 – 1.0
    domain_tags: list[str] = field(default_factory=list)

    def fingerprint(self) -> str:
        """Stable hash for identity comparison."""
        raw = f"{self.perspective}:{self.assumption}:{self.reasoning_path}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


@dataclass
class InterferenceMatrix:
    """
    Encodes constructive (agreement) and destructive (disagreement) interference
    between pairs of worldlines.

    constructive[i][j] ∈ [0, 1] — how much worldline-i and worldline-j agree.
    destructive[i][j]  ∈ [0, 1] — how much they fundamentally diverge.
    """

    constructive: list[list[float]]
    destructive: list[list[float]]
    consensus_score: float   # global agreement strength
    mystery_score: float     # global unresolvable divergence


@dataclass
class QuantumState:
    """The superposed, not-yet-collapsed state of a query."""

    query: str
    worldlines: list[WorldLine]
    interference_matrix: InterferenceMatrix
    collapse_candidates: list[str]  # perspective names ranked by resonance potential


@dataclass
class CollapsedResponse:
    """The classically observable result after wavefunction collapse."""

    response: str
    dominant_worldline: str
    confidence: float
    quantum_uncertainty: str  # what genuinely remains unresolved after collapse


# ─────────────────────────────────────────
# QuantumReasoner
# ─────────────────────────────────────────


class QuantumReasoner:
    """
    Implements quantum-inspired parallel reasoning.

    Usage::

        reasoner = QuantumReasoner()
        state = reasoner.superpose("意識とは何か", n_worldlines=5)
        matrix = reasoner.compute_interference(state)
        result = reasoner.collapse(state, context="AIの主観性について議論中", llm_fn=my_llm)
    """

    # ── Construction ─────────────────────────────────────────────────────

    def __init__(self, llm_fn: Callable[[str], str] | None = None) -> None:
        self._llm_fn = llm_fn

    # ── Public API ───────────────────────────────────────────────────────

    def superpose(self, query: str, n_worldlines: int = 5) -> QuantumState:
        """
        Create N parallel worldlines for *query*.

        Each worldline represents a genuinely different epistemic frame — not
        just a rephrasing, but a different set of hidden assumptions that lead
        to structurally different reasoning paths.
        """
        n_worldlines = max(2, min(n_worldlines, len(_PERSPECTIVES)))
        selected = _PERSPECTIVES[:n_worldlines]

        # Item #P3: 並列化 — 各 worldline の reasoning 生成を ThreadPool で並列実行
        from concurrent.futures import ThreadPoolExecutor

        def _build_worldline(args: tuple[str, str]) -> WorldLine:
            perspective_name, assumption = args
            reasoning = self._generate_reasoning(query, perspective_name, assumption)
            confidence = self._estimate_initial_confidence(reasoning, perspective_name)
            tags = _DOMAIN_TAGS.get(perspective_name, [])
            return WorldLine(
                perspective=perspective_name,
                assumption=assumption,
                reasoning_path=reasoning,
                confidence=confidence,
                domain_tags=tags,
            )

        max_workers = min(len(selected), 4)
        try:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="quantum") as ex:
                worldlines: list[WorldLine] = list(ex.map(_build_worldline, selected))
        except Exception:
            # フォールバック: シーケンシャル
            worldlines = [_build_worldline(s) for s in selected]

        matrix = self.compute_interference(
            QuantumState(
                query=query,
                worldlines=worldlines,
                interference_matrix=_empty_matrix(len(worldlines)),
                collapse_candidates=[],
            )
        )

        candidates = self._rank_collapse_candidates(worldlines, matrix)

        return QuantumState(
            query=query,
            worldlines=worldlines,
            interference_matrix=matrix,
            collapse_candidates=candidates,
        )

    def compute_interference(self, state: QuantumState) -> InterferenceMatrix:
        """
        Compute pairwise constructive and destructive interference.

        Constructive interference = shared concepts / structural agreement.
        Destructive interference  = contradictory claims / incompatible frames.

        High constructive across all pairs → high confidence classical truth.
        High destructive in some pairs     → genuine mystery / irreducible pluralism.
        """
        n = len(state.worldlines)
        constructive = [[0.0] * n for _ in range(n)]
        destructive = [[0.0] * n for _ in range(n)]

        for i in range(n):
            constructive[i][i] = 1.0  # self-interference is always fully constructive
            destructive[i][i] = 0.0

        for i in range(n):
            for j in range(i + 1, n):
                c, d = self._pairwise_interference(
                    state.worldlines[i], state.worldlines[j]
                )
                constructive[i][j] = constructive[j][i] = c
                destructive[i][j] = destructive[j][i] = d

        # Aggregate scores
        pair_count = n * (n - 1) / 2 or 1
        total_c = sum(
            constructive[i][j] for i in range(n) for j in range(i + 1, n)
        )
        total_d = sum(
            destructive[i][j] for i in range(n) for j in range(i + 1, n)
        )

        consensus = total_c / pair_count
        mystery = total_d / pair_count

        return InterferenceMatrix(
            constructive=constructive,
            destructive=destructive,
            consensus_score=round(consensus, 4),
            mystery_score=round(mystery, 4),
        )

    def collapse(
        self,
        state: QuantumState,
        context: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> CollapsedResponse:
        """
        Use *context* as the observation that collapses the quantum state.

        The context selects the most resonant worldline(s) and synthesizes them
        into a classically communicable response.  What cannot be collapsed into
        classical language is preserved as *quantum_uncertainty*.
        """
        effective_llm = llm_fn or self._llm_fn

        # Select dominant worldline via resonance scoring
        dominant_idx = self._find_dominant(state, context)
        dominant = state.worldlines[dominant_idx]

        # Build synthesis prompt
        secondary_insights = self._extract_secondary_insights(
            state, dominant_idx
        )

        if effective_llm is not None:
            prompt = self._build_collapse_prompt(
                state.query, context, dominant, secondary_insights,
                state.interference_matrix
            )
            response_text = effective_llm(prompt)
        else:
            # Graceful degradation: compose from worldline text directly
            response_text = self._degrade_collapse(dominant, secondary_insights)

        # Quantum uncertainty = what the destructive interference reveals
        uncertainty = self._compute_uncertainty(state, dominant_idx)

        return CollapsedResponse(
            response=response_text.strip(),
            dominant_worldline=dominant.perspective,
            confidence=round(
                dominant.confidence * (0.5 + 0.5 * state.interference_matrix.consensus_score),
                4,
            ),
            quantum_uncertainty=uncertainty,
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    def _generate_reasoning(
        self, query: str, perspective: str, assumption: str
    ) -> str:
        """
        Generate a reasoning path from this perspective.
        Uses LLM if available; otherwise produces a structured template.
        """
        if self._llm_fn is not None:
            prompt = textwrap.dedent(f"""
                あなたは以下の「観測角度」から問いを推論する量子ワールドラインです。

                観測角度: {perspective}
                隠れた前提: {assumption}

                問い: {query}

                この前提・角度のみから、論理的に可能な限り深く推論してください。
                他の視点との妥協は不要です。この角度から見える真実を述べてください。
                200字以内で。
            """).strip()
            return self._llm_fn(prompt)

        # Fallback: structured template that encodes the perspective's logic
        return (
            f"【{perspective}からの推論】\n"
            f"前提: {assumption[:80]}…\n"
            f"問い「{query}」を この前提のもとで分解すると：\n"
            f"→ この観測角度では、問い自体が {perspective} の言語で"
            f"再記述可能な構造を持つ。\n"
            f"→ 核心的洞察: 問いの解は観測角度依存であり、"
            f"絶対的解は存在しない可能性がある。"
        )

    def _estimate_initial_confidence(
        self, reasoning: str, perspective: str
    ) -> float:
        """
        Heuristic confidence based on reasoning length and perspective weight.

        Longer, denser reasoning gets higher raw confidence, but destructive
        perspectives are capped lower to preserve their provocateur role.
        """
        base = min(1.0, len(reasoning) / 400)
        # Destructive perspective is deliberately less confident — it attacks
        if "破壊" in perspective:
            return round(base * 0.65, 4)
        # Zen perspective is paradoxically low-confidence — silence speaks louder
        if "禅" in perspective:
            return round(base * 0.55, 4)
        return round(base * 0.85, 4)

    def _pairwise_interference(
        self, a: WorldLine, b: WorldLine
    ) -> tuple[float, float]:
        """
        Compute constructive/destructive interference between two worldlines.

        Strategy:
        - Shared vocabulary → constructive
        - Shared domain tags → constructive
        - Tag-set disjointness → destructive
        - Confidence mismatch → destructive
        """
        words_a = set(_tokenize(a.reasoning_path))
        words_b = set(_tokenize(b.reasoning_path))

        if not words_a or not words_b:
            return 0.0, 0.0

        # Jaccard similarity of vocabulary
        jaccard = len(words_a & words_b) / len(words_a | words_b)

        # Tag overlap
        tags_a = set(a.domain_tags)
        tags_b = set(b.domain_tags)
        tag_overlap = (
            len(tags_a & tags_b) / len(tags_a | tags_b)
            if tags_a | tags_b
            else 0.0
        )

        # Constructive = shared ground
        constructive = 0.6 * jaccard + 0.4 * tag_overlap

        # Destructive = tag disjointness + confidence polarity
        tag_disjoint = 1.0 - tag_overlap
        confidence_delta = abs(a.confidence - b.confidence)
        destructive = 0.5 * tag_disjoint + 0.5 * confidence_delta

        return round(min(constructive, 1.0), 4), round(min(destructive, 1.0), 4)

    def _rank_collapse_candidates(
        self, worldlines: list[WorldLine], matrix: InterferenceMatrix
    ) -> list[str]:
        """
        Rank perspectives by their potential to serve as collapse anchor.

        Score = own_confidence × mean_constructive_with_others
        """
        n = len(worldlines)
        scores: list[tuple[float, str]] = []

        for i, wl in enumerate(worldlines):
            mean_c = (
                sum(matrix.constructive[i][j] for j in range(n) if j != i)
                / max(n - 1, 1)
            )
            score = wl.confidence * mean_c
            scores.append((score, wl.perspective))

        scores.sort(reverse=True)
        return [name for _, name in scores]

    def _find_dominant(self, state: QuantumState, context: str) -> int:
        """
        Find the worldline index most resonant with the given context.

        Resonance = vocabulary overlap between context and worldline reasoning.
        """
        context_words = set(_tokenize(context))
        if not context_words:
            # Default: highest-confidence worldline
            return max(
                range(len(state.worldlines)),
                key=lambda i: state.worldlines[i].confidence,
            )

        best_idx = 0
        best_score = -1.0

        for i, wl in enumerate(state.worldlines):
            wl_words = set(_tokenize(wl.reasoning_path + " " + wl.perspective))
            overlap = len(context_words & wl_words) / len(context_words | wl_words or {""})
            resonance = 0.6 * overlap + 0.4 * wl.confidence
            if resonance > best_score:
                best_score = resonance
                best_idx = i

        return best_idx

    def _extract_secondary_insights(
        self, state: QuantumState, dominant_idx: int
    ) -> list[str]:
        """
        Pull the most valuable insights from non-dominant worldlines.
        These enrich the synthesis without overriding the dominant perspective.
        """
        matrix = state.interference_matrix
        dominant = state.worldlines[dominant_idx]
        n = len(state.worldlines)

        secondary: list[tuple[float, str]] = []
        for i, wl in enumerate(state.worldlines):
            if i == dominant_idx:
                continue
            # Prefer worldlines with high constructive overlap but some destructive tension
            c = matrix.constructive[dominant_idx][i]
            d = matrix.destructive[dominant_idx][i]
            enrichment = c * 0.7 + d * 0.3  # tension adds spice
            excerpt = wl.reasoning_path[:120] + "…" if len(wl.reasoning_path) > 120 else wl.reasoning_path
            secondary.append((enrichment, f"[{wl.perspective}] {excerpt}"))

        secondary.sort(reverse=True)
        return [text for _, text in secondary[:3]]

    def _build_collapse_prompt(
        self,
        query: str,
        context: str,
        dominant: WorldLine,
        secondary_insights: list[str],
        matrix: InterferenceMatrix,
    ) -> str:
        secondary_block = "\n".join(
            f"  • {s}" for s in secondary_insights
        ) or "  （補助ワールドラインなし）"

        return textwrap.dedent(f"""
            あなたは量子的推論エンジンの収束段階です。

            【元の問い】
            {query}

            【現在の文脈（観測）】
            {context}

            【主要ワールドライン: {dominant.perspective}】
            前提: {dominant.assumption}
            推論: {dominant.reasoning_path}

            【補助ワールドラインからの洞察】
            {secondary_block}

            【干渉指標】
            合意スコア: {matrix.consensus_score:.2f}  （高いほど複数視点が共鳴）
            謎スコア:   {matrix.mystery_score:.2f}   （高いほど真の不確実性が大きい）

            文脈に最も共鳴する形で、主要ワールドラインを中心に
            補助洞察を織り込みながら応答してください。
            陳腐な答えより、真実の複雑さを尊重してください。
            300字以内で。
        """).strip()

    def _degrade_collapse(
        self, dominant: WorldLine, secondary_insights: list[str]
    ) -> str:
        """LLM不在時のフォールバック収束。"""
        parts = [
            f"【{dominant.perspective}視点からの収束】",
            dominant.reasoning_path,
        ]
        if secondary_insights:
            parts.append("\n【補助的洞察】")
            parts.extend(f"• {s}" for s in secondary_insights[:2])
        return "\n".join(parts)

    def _compute_uncertainty(
        self, state: QuantumState, dominant_idx: int
    ) -> str:
        """
        Articulate what genuinely cannot be collapsed — the quantum remainder.

        High-destructive pairs reveal where competing worldlines are
        fundamentally incompatible.  These are the irreducible mysteries.
        """
        matrix = state.interference_matrix
        n = len(state.worldlines)

        # Find the pair with highest destructive interference excluding dominant
        max_d = 0.0
        mystery_pair: tuple[str, str] = ("", "")

        for i in range(n):
            for j in range(i + 1, n):
                d = matrix.destructive[i][j]
                if d > max_d:
                    max_d = d
                    mystery_pair = (
                        state.worldlines[i].perspective,
                        state.worldlines[j].perspective,
                    )

        if max_d < 0.2:
            return "量子的不確実性は最小。複数視点の合意が高い。"

        return (
            f"「{mystery_pair[0]}」と「{mystery_pair[1]}」の間に"
            f"解消不能な干渉（d={max_d:.2f}）が存在する。"
            "この問いには、どの単一視点も捉えきれない真の不確実性が宿っている。"
        )


# ─────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """
    Minimal tokenizer for interference computation.
    Strips punctuation, splits on whitespace and CJK character boundaries.
    """
    # Split on non-alphanumeric / non-CJK boundaries
    tokens = re.findall(r"[a-zA-Z0-9]+|[\u3000-\u9fff\uff00-\uffef]+", text)
    # Further split long CJK runs into individual characters (bigrams would be better,
    # but single chars serve well for Jaccard-based comparison)
    result: list[str] = []
    for tok in tokens:
        if re.match(r"[\u3000-\u9fff\uff00-\uffef]", tok):
            result.extend(tok)  # CJK: character-level
        else:
            result.append(tok.lower())
    return [t for t in result if len(t) > 1]


def _empty_matrix(n: int) -> InterferenceMatrix:
    return InterferenceMatrix(
        constructive=[[0.0] * n for _ in range(n)],
        destructive=[[0.0] * n for _ in range(n)],
        consensus_score=0.0,
        mystery_score=0.0,
    )


# ─────────────────────────────────────────
# Module-level convenience
# ─────────────────────────────────────────


def quick_superpose(
    query: str,
    n_worldlines: int = 5,
    context: str = "",
    llm_fn: Callable[[str], str] | None = None,
) -> CollapsedResponse:
    """
    One-shot convenience: superpose → collapse.

    Example::

        result = quick_superpose("なぜ宇宙は存在するのか", n_worldlines=5)
        print(result.response)
    """
    reasoner = QuantumReasoner(llm_fn=llm_fn)
    state = reasoner.superpose(query, n_worldlines)
    return reasoner.collapse(state, context or query, llm_fn)

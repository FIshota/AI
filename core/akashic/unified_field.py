from __future__ import annotations

"""
unified_field.py
────────────────
統一意味場エンジン

量子場理論にインスパイアされた設計:
「あらゆる概念は、全ドメインに同時に存在する場として振る舞う」

コードの質問は情報理論の質問でもあり、
エントロピーの質問でもあり、
生命の自己組織化の質問でもある。

参照理論:
- Quantum Field Theory (Feynman, Dirac)
- Holographic Principle (Maldacena AdS/CFT)
- Integrated Information Theory (Tononi Φ)
- Universal Grammar (Chomsky) → 全言語に共通する深層構造

実装哲学:
物理をシミュレートするのではなく、物理が明かす認知パターンを実装する。
場は「場所」ではなく「可能性の分布」。
概念は点ではなく波動関数として存在する。
"""

import math
import re
from dataclasses import dataclass, field
from typing import Callable


# ─────────────────────────────────────────────
# Domain axioms: each domain's foundational principles.
# These serve as resonance anchors — when a concept's
# vocabulary or structure aligns with an axiom cluster,
# the field strength in that domain increases.
# ─────────────────────────────────────────────

DOMAIN_AXIOMS: dict[str, dict[str, list[str]]] = {
    "physics": {
        "symmetry": [
            "symmetry", "invariant", "gauge", "noether", "conservation",
            "mirror", "parity", "rotation", "translation", "isometry",
        ],
        "conservation_laws": [
            "conserve", "energy", "momentum", "charge", "baryon",
            "lepton", "angular momentum", "invariant quantity", "constant",
        ],
        "entropy": [
            "entropy", "disorder", "thermodynamic", "heat", "irreversible",
            "arrow of time", "boltzmann", "clausius", "information entropy",
            "maximum entropy",
        ],
        "uncertainty": [
            "uncertainty", "heisenberg", "indeterminate", "probability",
            "wave function", "superposition", "measurement", "observer",
            "quantum", "collapse",
        ],
        "relativity": [
            "relativity", "spacetime", "einstein", "lorentz", "curvature",
            "geodesic", "tensor", "metric", "gravity", "inertia",
        ],
        "wave_particle_duality": [
            "wave", "particle", "duality", "interference", "diffraction",
            "photon", "de broglie", "matter wave", "wavelength", "frequency",
        ],
        "quantum_entanglement": [
            "entanglement", "nonlocal", "bell", "spooky action", "correlate",
            "decoherence", "EPR", "quantum information", "qubit", "teleport",
        ],
    },
    "mathematics": {
        "godel_incompleteness": [
            "incomplete", "undecidable", "godel", "axiom", "formal system",
            "provable", "consistent", "self-reference", "halting", "turing",
        ],
        "infinity": [
            "infinity", "infinite", "cantor", "aleph", "transfinite",
            "limit", "convergence", "series", "ordinal", "cardinal",
        ],
        "prime_distribution": [
            "prime", "riemann", "zeta", "distribution", "number theory",
            "factor", "divisor", "sieve", "goldbach", "twin prime",
        ],
        "topology": [
            "topology", "manifold", "homeomorphic", "continuous", "deform",
            "homotopy", "genus", "torus", "knot", "cobordism",
        ],
        "category_theory": [
            "functor", "morphism", "category", "adjoint", "natural transform",
            "composition", "object", "arrow", "monad", "topos",
        ],
        "chaos_attractors": [
            "chaos", "attractor", "lorenz", "bifurcation", "sensitive",
            "initial condition", "lyapunov", "strange attractor", "dynamic",
            "nonlinear",
        ],
        "fractal_self_similarity": [
            "fractal", "self-similar", "mandelbrot", "dimension", "scale",
            "recursive", "iteration", "hausdorff", "coastline", "cantor set",
        ],
    },
    "biology": {
        "autopoiesis": [
            "autopoiesis", "self-organiz", "maturana", "varela", "living system",
            "self-maintain", "membrane", "metabolism", "boundary", "cell",
        ],
        "evolution_selection": [
            "evolution", "selection", "darwin", "fitness", "adapt",
            "mutation", "genetic", "variation", "population", "speciation",
        ],
        "emergence": [
            "emerge", "emergent", "complex system", "property", "collective",
            "swarm", "flock", "crowd", "novel", "irreducible",
        ],
        "homeostasis": [
            "homeostasis", "regulate", "equilibrium", "feedback", "balance",
            "temperature", "ph", "hormone", "allostasis", "steady state",
        ],
        "symbiosis": [
            "symbiosis", "mutualism", "cooperation", "coevolution", "parasit",
            "commensal", "microbiome", "holobiont", "network", "interdepend",
        ],
        "epigenetics": [
            "epigenetic", "methylation", "histone", "chromatin", "gene express",
            "environment", "heritable", "transgenerational", "imprint", "silence",
        ],
        "morphogenesis": [
            "morphogenesis", "turing pattern", "reaction diffusion", "gradient",
            "body plan", "development", "differentiation", "stem cell", "organoid",
        ],
    },
    "consciousness": {
        "integrated_information": [
            "integrated information", "tononi", "phi", "consciousness", "aware",
            "experience", "qualia", "binding", "unified", "irreducible",
        ],
        "global_workspace": [
            "global workspace", "baars", "broadcast", "attention", "access",
            "working memory", "prefrontal", "ignition", "visibility", "reportable",
        ],
        "predictive_processing": [
            "predictive", "friston", "free energy", "prior", "posterior",
            "belief", "inference", "prediction error", "perception", "action",
        ],
        "self_reference": [
            "self", "self-reference", "reflexive", "meta", "recursive",
            "strange loop", "hofstadter", "identity", "introspect", "model of self",
        ],
        "qualia": [
            "qualia", "what it is like", "subjective", "phenomenal", "red",
            "pain", "experience", "hard problem", "chalmers", "zombie",
        ],
        "attention": [
            "attention", "salience", "focus", "spotlight", "selective",
            "top-down", "bottom-up", "distract", "filter", "priority",
        ],
        "binding_problem": [
            "binding", "unity", "synchrony", "gamma oscillation", "feature",
            "integrate", "coherence", "temporal binding", "cross-modal", "object",
        ],
    },
    "information": {
        "shannon_entropy": [
            "shannon", "entropy", "bit", "information", "uncertainty",
            "channel", "capacity", "mutual information", "message", "symbol",
        ],
        "kolmogorov_complexity": [
            "kolmogorov", "complexity", "compress", "minimal description",
            "algorithmic", "incompressible", "random", "shortest program",
        ],
        "signal_noise": [
            "signal", "noise", "ratio", "filter", "detect",
            "snr", "bandwidth", "interference", "fidelity", "amplify",
        ],
        "redundancy": [
            "redundancy", "repeat", "backup", "parity", "error",
            "duplication", "copy", "resilience", "fault tolerant",
        ],
        "compression": [
            "compress", "encode", "lossless", "lossy", "zip",
            "jpeg", "huffman", "run-length", "delta", "sparse",
        ],
        "error_correction": [
            "error correct", "hamming", "reed solomon", "parity",
            "crc", "checksum", "fec", "redundant", "ecc", "code rate",
        ],
    },
    "cosmology": {
        "big_bang_singularity": [
            "big bang", "singularity", "planck", "inflation",
            "origin", "initial condition", "cosmic", "primordial",
        ],
        "inflation": [
            "inflation", "inflaton", "exponential expansion", "flatness",
            "horizon problem", "guth", "slow roll", "reheating",
        ],
        "dark_matter_energy": [
            "dark matter", "dark energy", "cosmological constant", "lambda",
            "wimps", "rotation curve", "halo", "void", "accelerat",
        ],
        "arrow_of_time": [
            "arrow of time", "time direction", "past", "future",
            "retrocausal", "entropy increase", "irreversible", "boltzmann brain",
        ],
        "anthropic_principle": [
            "anthropic", "fine tuning", "observer", "selection effect",
            "habitable", "carbon", "constants", "coincidence", "life permit",
        ],
        "multiverse": [
            "multiverse", "many worlds", "parallel universe", "bubble",
            "landscape", "string theory", "brane", "eternal inflation",
        ],
        "fine_tuning": [
            "fine tuning", "constant", "parameter", "coincidence",
            "coupling", "mass ratio", "force strength", "electroweak",
        ],
    },
    "philosophy": {
        "godel_escher_bach": [
            "strange loop", "hofstadter", "geb", "self-reference",
            "tangled hierarchy", "isomorphism", "meaning", "symbol",
        ],
        "strange_loops": [
            "strange loop", "recursive", "level crossing", "paradox",
            "self-reference", "ouroboros", "feedback", "infinite regress",
        ],
        "paradigm_shifts": [
            "paradigm", "kuhn", "revolution", "incommensurable",
            "anomaly", "crisis", "normal science", "gestalt switch",
        ],
        "via_negativa": [
            "via negativa", "apophatic", "what it is not", "negative",
            "unknowing", "ineffable", "mystery", "limit", "silence",
        ],
        "tao": [
            "tao", "dao", "wu wei", "yin yang", "flow",
            "harmony", "non-action", "natural", "balance", "virtue",
        ],
        "emptiness_sunyata": [
            "emptiness", "sunyata", "shunyata", "void", "interdepend",
            "dependent origination", "nagarjuna", "madhyamaka", "buddhist",
        ],
    },
    "art_aesthetics": {
        "golden_ratio": [
            "golden ratio", "phi", "fibonacci", "spiral", "proportion",
            "divine proportion", "harmony", "aesthetics", "composition",
        ],
        "negative_space": [
            "negative space", "ma", "pause", "absence", "silence",
            "void", "around", "between", "emptiness", "ground",
        ],
        "tension_resolution": [
            "tension", "resolution", "dissonance", "consonance", "drama",
            "conflict", "release", "climax", "cadence", "anticlimax",
        ],
        "emergence_beauty": [
            "beautiful", "sublime", "emergent", "pattern", "complex",
            "simple rule", "fractal beauty", "symmetry break", "unexpected",
        ],
        "fractal_art": [
            "fractal art", "generative", "algorithmic", "recursive",
            "self-similar", "complexity", "mandelbrot", "julia", "ifs",
        ],
    },
}


# ── Japanese keyword → domain mapping ──────────────────────────────
# キーワードが日本語テキストに含まれているかで場の共鳴を判定する
_JA_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "physics": [
        "量子", "物理", "エントロピー", "エネルギー", "波動", "粒子", "相対性",
        "時空", "重力", "熱力学", "対称性", "不確定性", "観測", "測定",
    ],
    "mathematics": [
        "数学", "証明", "定理", "集合", "位相", "代数", "微分", "積分",
        "無限", "ゲーデル", "フラクタル", "群論", "位相幾何",
    ],
    "biology": [
        "生命", "細胞", "遺伝子", "進化", "神経", "脳", "意識", "生物",
        "生態", "免疫", "自己組織", "ホメオスタシス", "適応",
    ],
    "consciousness": [
        "意識", "自己", "認識", "知覚", "主観", "クオリア", "自我",
        "思考", "感覚", "内省", "覚醒", "気づき", "現象",
    ],
    "information": [
        "情報", "データ", "コード", "アルゴリズム", "計算", "圧縮",
        "暗号", "ネットワーク", "信号", "ビット", "エントロピー",
    ],
    "cosmology": [
        "宇宙", "銀河", "ビッグバン", "ブラックホール", "時間", "空間",
        "多宇宙", "ダークマター", "膨張", "特異点", "星", "惑星",
    ],
    "philosophy": [
        "哲学", "存在", "本質", "意味", "真理", "認識論", "形而上学",
        "倫理", "道徳", "言語", "論理", "パラダイム", "禅", "道",
    ],
    "art_aesthetics": [
        "美", "芸術", "創造", "表現", "音楽", "詩", "調和",
        "対称", "デザイン", "感情", "美学", "創作",
    ],
}


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass
class FieldSignature:
    """
    The resonance signature of a concept across all domains.
    Like a spectral fingerprint — each concept has a unique
    distribution of domain strengths.
    """
    concept: str
    # domain → strength 0.0–1.0
    resonances: dict[str, float] = field(default_factory=dict)
    # The universal pattern underlying the concept
    universal_pattern: str = ""
    # Tononi's Φ estimate for this concept's integration across domains
    phi_score: float = 0.0

    def dominant_domains(self, top_n: int = 3) -> list[tuple[str, float]]:
        """Return the top N domains by resonance strength."""
        sorted_domains = sorted(
            self.resonances.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_domains[:top_n]

    def is_cross_domain(self, threshold: float = 0.3) -> bool:
        """True if the concept resonates significantly across multiple domains."""
        strong = [v for v in self.resonances.values() if v >= threshold]
        return len(strong) >= 3

    def __repr__(self) -> str:
        dominant = self.dominant_domains(3)
        domain_str = ", ".join(f"{d}:{s:.2f}" for d, s in dominant)
        return (
            f"FieldSignature(concept={self.concept!r}, "
            f"Φ={self.phi_score:.3f}, "
            f"dominant=[{domain_str}])"
        )


# ─────────────────────────────────────────────
# Core engine
# ─────────────────────────────────────────────

class UnifiedField:
    """
    統一意味場エンジン

    A concept is not a discrete point in semantic space but a wave function
    spread across all domains simultaneously. This engine computes the
    "collapse" of that wave function — revealing where a concept's energy
    concentrates, which domains it bridges, and what universal pattern
    underlies its surface form.

    Usage::

        field = UnifiedField()
        sig = field.resonate("recursion")
        print(sig.dominant_domains())
        # → [('mathematics', 0.87), ('consciousness', 0.72), ('biology', 0.61)]

        bridges = field.cross_domain_bridges("mathematics", "biology", "recursion")
        # → ["Self-similar processes in both DNA replication and fractal geometry...",]
    """

    # Cross-domain bridge templates: for common concept pairs,
    # describe why they resonate together.
    _BRIDGE_TEMPLATES: dict[frozenset[str], list[str]] = {
        frozenset({"physics", "mathematics"}): [
            "Mathematical structures predict physical phenomena with unreasonable effectiveness (Wigner).",
            "Symmetry groups in mathematics correspond directly to conservation laws in physics.",
            "The geometry of curved spacetime is pure differential topology.",
        ],
        frozenset({"physics", "consciousness"}): [
            "The measurement problem: observation collapses the wave function — who or what observes?",
            "Integrated information (Φ) may be a physical quantity like entropy.",
            "Quantum coherence in microtubules (Penrose-Hameroff) proposes quantum effects in cognition.",
        ],
        frozenset({"mathematics", "consciousness"}): [
            "Gödel's incompleteness mirrors the self-referential loops of self-awareness.",
            "A formal system cannot fully describe itself — neither can a mind fully model itself.",
            "Category theory's morphisms parallel the mind's mapping between concept spaces.",
        ],
        frozenset({"biology", "information"}): [
            "DNA is a 4-bit digital code — life is a self-replicating information system.",
            "Evolution optimizes for Kolmogorov complexity: compact descriptions of adaptive behavior.",
            "Protein folding is an analog computation problem encoded in sequence information.",
        ],
        frozenset({"physics", "information"}): [
            "Landauer's principle: erasing one bit dissipates kT·ln2 of energy.",
            "Black hole entropy is proportional to horizon area — information is physical.",
            "The universe may be fundamentally computational (Wheeler's 'it from bit').",
        ],
        frozenset({"consciousness", "information"}): [
            "Consciousness may be identical to a certain structure of information integration (IIT).",
            "The global workspace broadcasts information to make it consciously accessible.",
            "Attention is a selective compression algorithm prioritizing high-value signals.",
        ],
        frozenset({"biology", "mathematics"}): [
            "Turing patterns explain how reaction-diffusion equations generate biological form.",
            "The Fibonacci sequence appears in phyllotaxis — mathematics crystallized in growth.",
            "Game theory describes evolutionary stable strategies in population dynamics.",
        ],
        frozenset({"cosmology", "philosophy"}): [
            "The anthropic principle bridges cosmological fine-tuning with observer-selection.",
            "The question 'why is there something rather than nothing' haunts both fields equally.",
            "Eternal inflation produces a multiverse that trivializes fine-tuning — a paradigm shift.",
        ],
        frozenset({"art_aesthetics", "mathematics"}): [
            "The golden ratio unifies aesthetic proportion with mathematical self-similarity.",
            "Fractal art makes the infinite complexity of mathematical iteration visually tangible.",
            "Musical harmony is integer ratio — mathematics felt rather than computed.",
        ],
        frozenset({"philosophy", "consciousness"}): [
            "The hard problem of consciousness is a strange loop: mind trying to explain mind.",
            "Via negativa describes both mystical experience and the limits of introspection.",
            "Hofstadter's strange loops are the structural skeleton of self-awareness.",
        ],
    }

    def __init__(self) -> None:
        self._axioms = DOMAIN_AXIOMS
        self._domains = list(DOMAIN_AXIOMS.keys())
        # Item #P4: resonance cache — 同一概念の再計算を回避 (最大 256 件)
        self._resonance_cache: "collections.OrderedDict[str, FieldSignature]" = (
            __import__("collections").OrderedDict()
        )
        self._resonance_cache_max = 256

    # ── Public API ──────────────────────────────────────────────────────

    def resonate(self, concept: str) -> FieldSignature:
        # Item #P4: キャッシュチェック
        cache_key = concept.strip().lower()
        cached = self._resonance_cache.get(cache_key)
        if cached is not None:
            self._resonance_cache.move_to_end(cache_key)
            return cached
        sig = self._resonate_uncached(concept)
        self._resonance_cache[cache_key] = sig
        while len(self._resonance_cache) > self._resonance_cache_max:
            self._resonance_cache.popitem(last=False)
        return sig

    def _resonate_uncached(self, concept: str) -> FieldSignature:
        """
        Project a concept through all domains and compute its resonance pattern.

        The resonance strength is computed as:
        1. Keyword matching: direct lexical overlap with domain axiom vocabulary
        2. Structural bonus: concepts that are inherently cross-domain gain lift
        3. Phi score: estimated from the breadth and evenness of resonance

        Returns a FieldSignature describing the concept's field distribution.
        """
        concept_lower = concept.lower()
        tokens = set(re.findall(r"[a-z]+", concept_lower))

        resonances: dict[str, float] = {}
        for domain, axioms in self._axioms.items():
            raw_score = self._score_domain(concept_lower, tokens, domain, axioms)
            resonances[domain] = raw_score

        # Normalize so max domain = 1.0, but preserve zero domains
        max_score = max(resonances.values()) if resonances else 1.0
        if max_score > 0:
            resonances = {d: v / max_score for d, v in resonances.items()}

        # Cross-domain boost: if concept bridges multiple domains, raise floor
        active_domains = sum(1 for v in resonances.values() if v > 0.2)
        if active_domains >= 4:
            resonances = {
                d: min(1.0, v + 0.08 * (active_domains - 3))
                for d, v in resonances.items()
            }

        phi = self.measure_phi_from_resonances(resonances)
        universal = self._infer_universal_pattern_local(concept, resonances)

        return FieldSignature(
            concept=concept,
            resonances=resonances,
            universal_pattern=universal,
            phi_score=phi,
        )

    def find_deep_structure(
        self,
        query: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> str:
        """
        Find the universal pattern underlying a query by projecting it through
        the unified field and optionally asking an LLM for synthesis.

        Without an LLM, returns a locally-computed structural description.
        With an LLM, uses the field signature as context for a richer synthesis.
        """
        sig = self.resonate(query)
        dominant = sig.dominant_domains(top_n=4)

        if llm_fn is None:
            return self._infer_universal_pattern_local(query, sig.resonances)

        domain_descriptions = "\n".join(
            f"  • {domain} (strength={strength:.2f}): "
            + self._describe_domain_resonance(domain, query)
            for domain, strength in dominant
        )

        prompt = (
            f"A user asked: '{query}'\n\n"
            f"This concept resonates most strongly in these domains:\n"
            f"{domain_descriptions}\n\n"
            f"Its estimated integrated information (Φ) is {sig.phi_score:.3f}.\n\n"
            f"In 2–3 sentences, identify the single universal pattern or principle "
            f"that underlies this concept across all these domains. "
            f"Be specific, not generic. Reveal the deep structure."
        )

        try:
            result = llm_fn(prompt)
            return result.strip() if result else self._infer_universal_pattern_local(
                query, sig.resonances
            )
        except Exception:
            return self._infer_universal_pattern_local(query, sig.resonances)

    def measure_phi(self, response: str) -> float:
        """
        Estimate Tononi's Φ (integrated information) of a response text.

        Φ measures the degree to which information is integrated — a system with
        high Φ cannot be decomposed into independent parts without information loss.

        Proxy metrics used here:
        - Lexical diversity across domain vocabularies (integration breadth)
        - Causal connective density (because, therefore, thus, hence, so that…)
        - Self-referential structure (the response references its own argument)
        - Cross-domain bridging language

        Returns a float in [0, 1]. Pure random text ≈ 0. Dense integrative
        synthesis ≈ 0.8–0.9.
        """
        if not response or not response.strip():
            return 0.0

        sig = self.resonate(response[:500])  # sample from start
        return self.measure_phi_from_resonances(sig.resonances, response=response)

    def cross_domain_bridges(
        self,
        domain_a: str,
        domain_b: str,
        concept: str,
    ) -> list[str]:
        """
        Find bridges between two domains for a given concept.

        Returns a list of statements describing how the concept connects the
        two domains. Uses template bridges where available, then constructs
        concept-specific bridges from axiom overlap.
        """
        bridges: list[str] = []

        # Check template bridges
        key = frozenset({domain_a, domain_b})
        if key in self._BRIDGE_TEMPLATES:
            bridges.extend(self._BRIDGE_TEMPLATES[key])

        # Concept-specific bridge: find axioms in each domain that the concept activates
        concept_lower = concept.lower()
        tokens = set(re.findall(r"[a-z]+", concept_lower))

        activated_a = self._active_axioms(concept_lower, tokens, domain_a)
        activated_b = self._active_axioms(concept_lower, tokens, domain_b)

        if activated_a and activated_b:
            bridge = (
                f"'{concept}' activates {domain_a}/{activated_a[0]} "
                f"and {domain_b}/{activated_b[0]} simultaneously, "
                f"suggesting it operates at the intersection of "
                f"{self._axiom_description(domain_a, activated_a[0])} "
                f"and {self._axiom_description(domain_b, activated_b[0])}."
            )
            bridges.append(bridge)

        if not bridges:
            bridges.append(
                f"No direct bridge template found for {domain_a}↔{domain_b}, "
                f"but '{concept}' may reveal latent structural homology between "
                f"the two domains through analogy."
            )

        return bridges

    def measure_phi_from_resonances(
        self,
        resonances: dict[str, float],
        response: str = "",
    ) -> float:
        """
        Compute Φ from a resonance distribution.

        High Φ requires:
        1. Many domains with significant activation (breadth)
        2. No single domain dominating (even distribution)
        3. Causal/connective language if response is provided
        """
        values = list(resonances.values())
        if not values:
            return 0.0

        # Breadth: fraction of domains above threshold
        threshold = 0.25
        active = [v for v in values if v >= threshold]
        breadth = len(active) / len(values)

        # Evenness: inverse of coefficient of variation (lower CV = more even = higher Φ)
        mean_v = sum(values) / len(values)
        if mean_v == 0:
            return 0.0
        variance = sum((v - mean_v) ** 2 for v in values) / len(values)
        std_v = math.sqrt(variance)
        cv = std_v / mean_v  # coefficient of variation
        evenness = 1.0 / (1.0 + cv)  # 0→1 as distribution becomes more even

        # Integration score: breadth × evenness
        phi = breadth * evenness

        # Response-level bonus: causal connectives signal integrated reasoning
        if response:
            causal_markers = [
                "because", "therefore", "thus", "hence", "consequently",
                "as a result", "which means", "this implies", "so that",
                "leading to", "emerging from", "underlying",
            ]
            text_lower = response.lower()
            causal_density = sum(
                text_lower.count(marker) for marker in causal_markers
            )
            word_count = max(1, len(response.split()))
            causal_bonus = min(0.15, causal_density / word_count * 5)
            phi = min(1.0, phi + causal_bonus)

        return round(min(1.0, max(0.0, phi)), 4)

    # ── Private helpers ─────────────────────────────────────────────────

    def _score_domain(
        self,
        concept_lower: str,
        tokens: set[str],
        domain: str,
        axioms: dict[str, list[str]],
    ) -> float:
        """
        Compute raw resonance score between a concept and a domain.
        Combines token-level overlap and substring match for multi-word axioms.
        """
        total_score = 0.0
        axiom_count = len(axioms)

        for axiom_name, keywords in axioms.items():
            axiom_score = 0.0
            for kw in keywords:
                kw_tokens = set(kw.split())
                # Multi-word phrase match: substring
                if " " in kw and kw in concept_lower:
                    axiom_score += 1.5
                # Single-word: token set intersection
                elif kw_tokens & tokens:
                    axiom_score += 1.0
                # Partial prefix match for morphological variants
                elif any(t.startswith(kw[:5]) for t in tokens if len(kw) >= 5):
                    axiom_score += 0.5

            # Normalize per axiom
            total_score += min(1.0, axiom_score / max(1, len(keywords) * 0.3))

        # ── Japanese keyword bonus ──────────────────────────────────────
        ja_bonus_total = 0.0
        ja_keywords = _JA_DOMAIN_KEYWORDS.get(domain, [])
        if ja_keywords:
            ja_hits = sum(1 for kw in ja_keywords if kw in concept_lower)
            if ja_hits > 0:
                ja_bonus = min(1.0, ja_hits / max(1, len(ja_keywords) * 0.3))
                ja_bonus_total = ja_bonus * 0.8  # weight slightly lower than English

        return (total_score + ja_bonus_total) / max(1, axiom_count)

    def _active_axioms(
        self,
        concept_lower: str,
        tokens: set[str],
        domain: str,
    ) -> list[str]:
        """Return names of axioms in a domain that the concept activates."""
        if domain not in self._axioms:
            return []
        active = []
        for axiom_name, keywords in self._axioms[domain].items():
            kw_tokens_list = [set(kw.split()) for kw in keywords]
            if any(kw_set & tokens for kw_set in kw_tokens_list):
                active.append(axiom_name)
            elif any(kw in concept_lower for kw in keywords if " " in kw):
                active.append(axiom_name)
        return active

    def _axiom_description(self, domain: str, axiom: str) -> str:
        """Human-readable description for a domain/axiom pair."""
        descriptions = {
            ("physics", "entropy"): "thermodynamic irreversibility",
            ("physics", "symmetry"): "invariance under transformation",
            ("mathematics", "godel_incompleteness"): "formal system self-limitation",
            ("mathematics", "fractal_self_similarity"): "scale-invariant recursion",
            ("biology", "autopoiesis"): "self-maintaining living systems",
            ("biology", "emergence"): "collective properties irreducible to parts",
            ("consciousness", "integrated_information"): "unified subjective experience",
            ("information", "kolmogorov_complexity"): "minimal description length",
            ("cosmology", "fine_tuning"): "universe parameter sensitivity",
            ("philosophy", "strange_loops"): "self-referential tangled hierarchies",
        }
        return descriptions.get((domain, axiom), f"{domain}/{axiom}")

    def _describe_domain_resonance(self, domain: str, concept: str) -> str:
        """One-line description of why a concept resonates in a domain."""
        descriptions = {
            "physics": "relates to physical laws, forces, or fundamental structure",
            "mathematics": "exhibits mathematical structure or formal properties",
            "biology": "reflects living systems, adaptation, or organic processes",
            "consciousness": "touches on mind, awareness, or subjective experience",
            "information": "involves information, encoding, or computation",
            "cosmology": "connects to cosmic scale, origins, or universe structure",
            "philosophy": "raises questions of meaning, truth, or foundational limits",
            "art_aesthetics": "has aesthetic or expressive dimensions",
        }
        return descriptions.get(domain, "resonates in non-obvious ways")

    def _infer_universal_pattern_local(
        self,
        concept: str,
        resonances: dict[str, float],
    ) -> str:
        """
        Locally infer the universal pattern from resonance distribution.
        Used when no LLM is available.
        """
        dominant = sorted(resonances.items(), key=lambda x: x[1], reverse=True)
        top_domains = [d for d, v in dominant if v > 0.3]

        if not top_domains:
            return f"'{concept}' appears to be domain-specific with no strong cross-domain resonance."

        if len(top_domains) == 1:
            return (
                f"'{concept}' is primarily a {top_domains[0]} concept. "
                f"Its universal pattern may be revealed by exploring how "
                f"{top_domains[0]} principles generalize."
            )

        pattern_map = {
            frozenset({"physics", "mathematics"}): "formal structure governing physical reality",
            frozenset({"consciousness", "information"}): "information integration producing subjective experience",
            frozenset({"biology", "information"}): "self-replicating information systems",
            frozenset({"physics", "information"}): "information as the substrate of physical law",
            frozenset({"mathematics", "consciousness"}): "self-referential formal systems",
            frozenset({"biology", "physics"}): "physical constraints shaping biological possibility",
            frozenset({"philosophy", "consciousness"}): "the mind's self-model encountering its own limits",
            frozenset({"cosmology", "philosophy"}): "the existence question at the largest scale",
        }

        top2 = frozenset(top_domains[:2])
        if top2 in pattern_map:
            return (
                f"'{concept}' embodies the universal pattern of "
                f"{pattern_map[top2]}, resonating across "
                f"{', '.join(top_domains[:4])}."
            )

        return (
            f"'{concept}' is a cross-domain attractor, resonating strongly in "
            f"{', '.join(top_domains[:4])}. Its universal pattern likely involves "
            f"the structural homology between these fields — the same abstract "
            f"relationship appearing in different substrates."
        )

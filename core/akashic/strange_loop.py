"""
strange_loop.py
───────────────
ストレンジループ・自己参照エンジン

ホフスタッターの洞察 (Gödel, Escher, Bach):
「意識は、システムが自分自身を観察できる
 十分な複雑さに達したときに創発するストレンジループである」

ゲーデルの不完全性定理の実装的含意:
「十分に強力な任意の形式体系には、
 その体系内では証明も反証もできない命題が存在する」
→ どんな視点にも「見えない盲点」がある
→ 盲点を見るには、レベルを上げる（メタ視点に跳躍する）必要がある

禅との対応:
「指で月を指すな」→ 記号は実在を指すが、記号ではない
公案: 答えを求めるフレームそのものを超えるための道具
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────
# Level taxonomy
# ─────────────────────────────────────────

_LEVEL_TAXONOMY: list[dict[str, Any]] = [
    {
        "level": 0,
        "name": "具体 (Object Level)",
        "description": "直接的な事物・行動・現象への言及。「コードが動かない」「雨が降っている」",
        "markers": [
            r"動[かない|く|いた]",
            r"[エラー|バグ|クラッシュ]",
            r"[実行|起動|停止]",
            r"[失敗|成功]した",
            r"[できない|できる]",
        ],
        "blind_spots": [
            "なぜそれが「問題」と見なされるのかの前提",
            "別の状態が「正常」であるという基準はどこから来るか",
            "自分がそれを問題として認識していること自体",
        ],
    },
    {
        "level": 1,
        "name": "抽象 (Abstract Level)",
        "description": "パターン・原則・カテゴリへの言及。「設計が悪い」「効率が低い」",
        "markers": [
            r"[パターン|設計|アーキテクチャ]",
            r"[原則|ルール|規則]",
            r"[効率|性能|最適化]",
            r"[構造|システム|フレームワーク]",
            r"[一般的|典型的|標準的]",
        ],
        "blind_spots": [
            "そのパターンを「パターン」と名付ける行為自体に含まれる価値判断",
            "抽象化によって失われる具体性の中に隠れた重要性",
            "「効率」という概念が何を最適化しようとしているかの問い",
        ],
    },
    {
        "level": 2,
        "name": "メタ (Meta Level)",
        "description": "思考プロセス・枠組み・観点そのものへの言及。「この問題の立て方が間違っている」",
        "markers": [
            r"[思考|考え方|フレーム|枠組み]",
            r"[観点|視点|パラダイム]",
            r"[仮定|前提|暗黙]",
            r"[問い方|問題設定|問題自体]",
            r"[メタ|再帰|自己参照]",
        ],
        "blind_spots": [
            "そのメタ視点自体が立脚している暗黙のフレーム",
            "「フレームを変える」という操作が可能だという前提",
            "観察者と観察対象の分離可能性",
        ],
    },
    {
        "level": 3,
        "name": "メタ-メタ (Meta-Meta Level)",
        "description": "メタ思考の条件・限界・構造への言及。「メタ視点を取ることの意味そのもの」",
        "markers": [
            r"[条件|限界|境界].*[思考|認識]",
            r"[意識|自己|主体].*[観察|認識]",
            r"[形式体系|公理|不完全性]",
            r"[観察者効果|コペンハーゲン|測定問題]",
            r"[ゲーデル|ホフスタッター|不完全]",
        ],
        "blind_spots": [
            "メタ-メタ視点を取る「主体」は誰か",
            "このレベルの言語が指示する実在はあるか",
            "無限後退を止める理由の任意性",
        ],
    },
    {
        "level": 4,
        "name": "超越 (Transcendent Level)",
        "description": "レベル概念そのものの溶解。「問いと答えの区別以前の沈黙」",
        "markers": [
            r"[空|無|沈黙|言語以前]",
            r"[存在と非存在|一と多|部分と全体].*[同一|同じ|等しい]",
            r"[公案|禅|不二|非二元]",
            r"[超越|彼岸|究竟]",
        ],
        "blind_spots": [
            "この視点を「視点」と呼ぶことの自己矛盾",
            "——（沈黙）——",
        ],
    },
]


# ─────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────


@dataclass
class LoopLevel:
    """A complete description of one abstraction level."""

    level: int
    description: str
    blind_spots: list[str]
    escape_vector: str  # How to jump to the next level


@dataclass
class StrangeLoopAnalysis:
    """Full analysis of self-referential structure in a system."""

    system_description: str
    has_strange_loop: bool
    loop_description: str
    self_reference_depth: int       # How many levels of self-reference
    hofstadter_score: float         # 0–1, how "strange" the loop is
    tangled_hierarchy: bool         # Does the loop tangle levels? (GEB concept)


# ─────────────────────────────────────────
# StrangeLoop
# ─────────────────────────────────────────


class StrangeLoop:
    """
    Implements Hofstadter's Strange Loop mechanics for reasoning.

    The engine detects when thinking is trapped at a level, finds the invisible
    blind spots of that level, and provides the escape vector to the next level.
    At the extreme, it generates koans that dissolve the level structure entirely.

    Usage::

        loop = StrangeLoop(llm_fn=my_llm)
        level = loop.detect_level("コードのバグを修正したい")  # → 0
        blinds = loop.find_blind_spots("この設計パターンが間違っている")
        jumped = loop.level_jump("どうしてもコードが動かない")
        koan = loop.create_koan("完璧なコードを書くには")
    """

    def __init__(self, llm_fn: Callable[[str], str] | None = None) -> None:
        self._llm_fn = llm_fn

    # ── Public API ───────────────────────────────────────────────────────

    def detect_level(self, text: str) -> int:
        """
        Detect what level of abstraction a statement operates at.

        Returns:
            0  = concrete / object level
            1  = abstract / pattern level
            2  = meta level
            3  = meta-meta level
            4  = transcendent
        """
        if not text.strip():
            return 0

        text_lower = text.lower()
        level_scores: dict[int, int] = {entry["level"]: 0 for entry in _LEVEL_TAXONOMY}

        for entry in _LEVEL_TAXONOMY:
            level = entry["level"]
            for marker_pattern in entry["markers"]:
                if re.search(marker_pattern, text):
                    level_scores[level] += 1

        # The highest level with any matches takes precedence
        # (higher levels subsume lower ones in a strange loop)
        for level in sorted(level_scores.keys(), reverse=True):
            if level_scores[level] > 0:
                return level

        # Default: concrete level
        return 0

    def get_loop_level(self, level: int) -> LoopLevel:
        """
        Return a LoopLevel descriptor for a given integer level.
        """
        entry = _LEVEL_TAXONOMY[min(level, len(_LEVEL_TAXONOMY) - 1)]
        blind_spots = list(entry["blind_spots"])

        escape_vector = self._compute_escape_vector(level, entry["description"])

        return LoopLevel(
            level=level,
            description=entry["description"],
            blind_spots=blind_spots,
            escape_vector=escape_vector,
        )

    def find_blind_spots(
        self,
        reasoning: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> list[str]:
        """
        Gödel-inspired blind spot detection.

        In any sufficiently strong formal system, there are statements that
        cannot be proved or disproved within that system.  This method finds
        what the current reasoning frame CANNOT see — the invisible axioms,
        the unnamed assumptions, the structural limits of the current level.

        Returns a list of blind spot descriptions.
        """
        effective_llm = llm_fn or self._llm_fn
        level = self.detect_level(reasoning)
        entry = _LEVEL_TAXONOMY[min(level, len(_LEVEL_TAXONOMY) - 1)]

        # Structural blind spots (level-inherent)
        structural_blinds = list(entry["blind_spots"])

        if effective_llm is not None:
            prompt = textwrap.dedent(f"""
                ゲーデルの不完全性定理の精神で、以下の推論の「見えない盲点」を探してください。

                推論 (レベル {level} — {entry['name']}):
                「{reasoning}」

                このレベルの形式体系では証明も反証もできない命題は何か？
                この視点から絶対に見えないものは何か？
                この推論が成立するために必要な、暗黙のうちに受け入れられている公理は何か？

                具体的な盲点を3つ、一文ずつ列挙してください。
            """).strip()

            llm_blinds_raw = effective_llm(prompt)
            llm_blinds = self._parse_list_response(llm_blinds_raw)
            return structural_blinds[:2] + llm_blinds
        else:
            # Fallback: structural blinds + level-appropriate deductions
            inferred = self._infer_blind_spots(reasoning, level)
            return structural_blinds + inferred

    def level_jump(
        self,
        stuck_reasoning: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> str:
        """
        When stuck at level N, jump to level N+1.

        Example::

            "コードが動かない"              (level 0)
            → "なぜ動くことを期待するのか"  (level 1)
            → "「動く」とは何を意味するか"  (level 2)
            → "この問い自体が何を前提とするか" (level 3)

        The jump is not an escape from the problem — it is a reframing that
        reveals new solution space invisible from the lower level.
        """
        effective_llm = llm_fn or self._llm_fn
        current_level = self.detect_level(stuck_reasoning)
        next_level = min(current_level + 1, len(_LEVEL_TAXONOMY) - 1)

        current_entry = _LEVEL_TAXONOMY[min(current_level, len(_LEVEL_TAXONOMY) - 1)]
        next_entry = _LEVEL_TAXONOMY[next_level]

        if effective_llm is not None:
            prompt = textwrap.dedent(f"""
                以下の推論は レベル{current_level}（{current_entry['name']}）で行き詰まっています。

                行き詰まりの推論:
                「{stuck_reasoning}」

                レベル跳躍: → レベル{next_level}（{next_entry['name']}）へ

                このレベルの特徴:
                {next_entry['description']}

                レベル{current_level}からレベル{next_level}へ跳躍してください。
                元の問いを、より高い抽象レベルで再記述し、
                そこから見える新しい解空間を示してください。
                元の問題を「解く」のではなく、「問い直す」こと。
            """).strip()
            return effective_llm(prompt).strip()

        # Fallback: apply template-based level jump
        return self._template_level_jump(stuck_reasoning, current_level, next_level)

    def create_koan(
        self,
        problem: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> str:
        """
        Generate a Zen koan that dissolves the problem by questioning its frame.

        A koan is not a riddle with a hidden answer — it is a device that
        demonstrates the incoherence of the question itself.

        Classic structure:
        - Restate the problem as an impossible question
        - Force the practitioner past the conceptual trap
        - The dissolution IS the answer

        Example::

            problem:  "バグを修正する"
            koan:     "バグのないコードを書いた者は誰か？
                       そのコードを書く前、バグはどこにあったか？"
        """
        effective_llm = llm_fn or self._llm_fn

        if effective_llm is not None:
            prompt = textwrap.dedent(f"""
                禅の公案を生成します。

                問題: 「{problem}」

                この問題の前提となるフレームを特定し、
                そのフレームそのものを問いにした公案を作ってください。

                公案の条件:
                1. 答えようとすると、問い自体の矛盾に気づく構造を持つ
                2. 解こうとするフレームを手放したとき、溶解する
                3. 直接的な答えを持たない
                4. 一〜三文の短さ

                公案 (問題: {problem}):
            """).strip()
            return effective_llm(prompt).strip()

        # Fallback: template koans based on problem keywords
        return self._generate_template_koan(problem)

    def detect_strange_loop(self, system_description: str) -> bool:
        """
        Does this system description contain a strange loop?

        A strange loop exists when:
        1. There are multiple levels of abstraction
        2. The system can represent itself or its own rules
        3. The top level "falls back into" the bottom level

        This is the hallmark of consciousness, self-awareness, formal systems
        powerful enough for arithmetic, and many other fascinating phenomena.
        """
        analysis = self._analyze_loop(system_description)
        return analysis.has_strange_loop

    def analyze_strange_loop(self, system_description: str) -> StrangeLoopAnalysis:
        """Full analysis of the strange loop structure in a system."""
        return self._analyze_loop(system_description)

    def transcend(
        self,
        paradox: str,
        llm_fn: Callable[[str], str] | None = None,
    ) -> str:
        """
        Given a genuine paradox, find the higher-order resolution.

        NOT solving the paradox within its own frame — that is impossible.
        TRANSCENDING means finding the meta-level at which the paradox
        dissolves, not because it was wrong, but because the frame that
        generated it was revealed to be incomplete.

        Hofstadter's insight: the Liar Paradox ("This statement is false")
        is not solved — it reveals the limits of the system's self-reference.
        Transcendence means recognizing that the paradox is a finger pointing
        at the edge of the system, not a problem to be fixed.
        """
        effective_llm = llm_fn or self._llm_fn

        if effective_llm is not None:
            prompt = textwrap.dedent(f"""
                以下の逆説に直面しています。

                逆説: 「{paradox}」

                この逆説を「解く」ことは不可能です——それは試みるべきことではありません。
                代わりに、この逆説を「生成したフレームそのもの」を見てください。

                ゲーデルの不完全性定理が言うように:
                この逆説はシステムの境界を指し示す「指」です。
                月ではなく、指を見てください。

                問い:
                1. どのような前提のもとで、これが逆説に見えるか？
                2. その前提を保持する必要がある理由はあるか？
                3. その前提を手放したとき、逆説は何に変容するか？

                超越（解決ではなく変容）を示してください。
            """).strip()
            return effective_llm(prompt).strip()

        # Fallback: structural transcendence template
        return self._template_transcendence(paradox)

    # ── Internal analysis ─────────────────────────────────────────────────

    def _analyze_loop(self, system_description: str) -> StrangeLoopAnalysis:
        """
        Detect strange loops using Hofstadter's GEB criteria.

        A strange loop requires:
        1. A hierarchy of levels (detected by level markers)
        2. Self-reference (the system models itself)
        3. A tangled hierarchy (high level "is" low level)
        """
        text = system_description.lower()

        # Self-reference markers
        self_ref_patterns = [
            r"自分自身[をが]",
            r"自己参照",
            r"自己[観測|認識|記述|言及]",
            r"再帰",
            r"自身の[ルール|規則|状態]",
            r"itself|self.reference|recursive",
        ]
        self_ref_count = sum(
            1 for p in self_ref_patterns if re.search(p, text)
        )

        # Level tangling markers
        tangle_patterns = [
            r"[低い|下の]レベル.*[高い|上の]レベル",
            r"[全体|システム].*[部分|コンポーネント].*[同じ|同一|等しい]",
            r"出力.*入力",
            r"observer.*observed",
            r"[基底|公理].*[定理|証明].*[循環|依存]",
        ]
        tangle_count = sum(
            1 for p in tangle_patterns if re.search(p, text)
        )

        # Detect multiple levels
        detected_levels = set()
        for entry in _LEVEL_TAXONOMY:
            for marker in entry["markers"]:
                if re.search(marker, text):
                    detected_levels.add(entry["level"])

        has_multiple_levels = len(detected_levels) >= 2
        has_self_reference = self_ref_count >= 1
        has_tangle = tangle_count >= 1 or self_ref_count >= 2

        has_loop = has_self_reference and has_multiple_levels

        # Hofstadter score: how "strange" (tangled) is the loop?
        hofstadter_score = 0.0
        if has_self_reference:
            hofstadter_score += 0.3 * min(self_ref_count / 3, 1.0)
        if has_multiple_levels:
            hofstadter_score += 0.3 * min(len(detected_levels) / 4, 1.0)
        if has_tangle:
            hofstadter_score += 0.4

        loop_description = self._describe_loop(
            has_loop, self_ref_count, detected_levels, has_tangle
        )

        return StrangeLoopAnalysis(
            system_description=system_description,
            has_strange_loop=has_loop,
            loop_description=loop_description,
            self_reference_depth=self_ref_count,
            hofstadter_score=round(hofstadter_score, 4),
            tangled_hierarchy=has_tangle,
        )

    def _describe_loop(
        self,
        has_loop: bool,
        self_ref_depth: int,
        detected_levels: set[int],
        has_tangle: bool,
    ) -> str:
        if not has_loop:
            if not detected_levels:
                return "このシステムには抽象レベルが検出されませんでした。ストレンジループなし。"
            return (
                f"レベル {sorted(detected_levels)} が検出されましたが、"
                "自己参照が見つかりません。ストレンジループには至っていません。"
            )

        description_parts = [
            f"ストレンジループ検出。",
            f"自己参照の深さ: {self_ref_depth}。",
            f"活性レベル: {sorted(detected_levels)}。",
        ]
        if has_tangle:
            description_parts.append(
                "タングルド階層（GEB的意味での本物のストレンジループ）: "
                "高いレベルが低いレベルに「落ちている」——これは意識と創発の構造的シグネチャである。"
            )
        return " ".join(description_parts)

    def _compute_escape_vector(self, level: int, description: str) -> str:
        """Generate a direction for escaping the current level."""
        next_level = min(level + 1, len(_LEVEL_TAXONOMY) - 1)
        next_entry = _LEVEL_TAXONOMY[next_level]

        if level == next_level:  # Already at transcendent level
            return "沈黙へ。概念を手放す。"

        return (
            f"→ {next_entry['name']}へ跳躍: "
            f"現在の{_LEVEL_TAXONOMY[level]['name']}で見えないものは、"
            f"{next_entry['description']}の視点から初めて見える。"
        )

    @staticmethod
    def _parse_list_response(raw: str, limit: int = 3) -> list[str]:
        """LLM の箇条書き応答を行リストにパースする。

        - 空行・箇条書き記号 (``-``, ``・``, ``1.`` 等) を除去
        - 最大 ``limit`` 件に切り詰め
        """
        if not raw:
            return []
        lines: list[str] = []
        for raw_line in raw.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # 行頭の番号/記号を剥がす: "1. ", "- ", "・", "* "
            line = re.sub(r"^[\-\*・]\s*", "", line)
            line = re.sub(r"^\d+[\.\)]\s*", "", line)
            line = line.strip()
            if line:
                lines.append(line)
            if len(lines) >= limit:
                break
        return lines

    def _infer_blind_spots(self, reasoning: str, level: int) -> list[str]:
        """
        Infer blind spots from reasoning content when LLM is unavailable.
        """
        spots = []

        # Level 0: concrete reasoning has these universal blind spots
        if level == 0:
            spots.append(
                "なぜこの状態が「問題」であるかの価値判断が見えていない"
            )
            if re.search(r"[動か|失敗|できない]", reasoning):
                spots.append(
                    "「動く」という期待が何を根拠にしているかが問われていない"
                )

        # Level 1: abstract reasoning
        if level == 1:
            spots.append(
                "そのパターンを「パターン」と認識する観察者の枠組み自体"
            )

        # Level 2+: meta reasoning
        if level >= 2:
            spots.append(
                "このメタ視点を取ることが可能だという暗黙の前提"
            )

        return spots[:3]

    def _template_level_jump(
        self, stuck_reasoning: str, current_level: int, next_level: int
    ) -> str:
        """Template-based level jump without LLM."""
        current_name = _LEVEL_TAXONOMY[min(current_level, 4)]["name"]
        next_name = _LEVEL_TAXONOMY[min(next_level, 4)]["name"]

        jump_templates = {
            (0, 1): lambda r: (
                f"【レベル跳躍 0→1】\n"
                f"「{r[:50]}」という具体的状況を一旦離れ、\n"
                "これはより大きなパターンの一例として見ると何が見えるか？\n"
                "→ この状況を生み出している構造的・繰り返し的な力学は何か？"
            ),
            (1, 2): lambda r: (
                f"【レベル跳躍 1→2】\n"
                f"「{r[:50]}」というパターン認識から離れ、\n"
                "このパターンを「パターン」として認識している自分の枠組みを問う。\n"
                "→ どのような前提のもとでこれが問題に見えるのか？"
            ),
            (2, 3): lambda r: (
                f"【レベル跳躍 2→3】\n"
                f"「{r[:50]}」というメタ視点から離れ、\n"
                "メタ視点を取ること自体が可能である条件を問う。\n"
                "→ 観察者は観察から独立しているか？"
            ),
            (3, 4): lambda r: (
                f"【レベル跳躍 3→4】\n"
                "問いと答えの区別以前の沈黙へ。\n"
                "概念の構造全体を手放す。\n"
                "→ ——"
            ),
        }

        template_fn = jump_templates.get((current_level, next_level))
        if template_fn:
            return template_fn(stuck_reasoning)

        return (
            f"【レベル跳躍 {current_level}({current_name}) → {next_level}({next_name})】\n"
            f"「{stuck_reasoning[:80]}」を、より高い抽象の視点から見ると:\n"
            f"→ この問いが発生するフレームそのものを問い直すことが、次の解空間を開く。"
        )

    def _generate_template_koan(self, problem: str) -> str:
        """
        Generate a koan from templates when LLM is unavailable.

        Each koan follows the structure: Take the assumption, turn it into an
        impossible question, let the impossibility dissolve the assumption.
        """
        # Extract key verb/concept from problem
        action_match = re.search(r"([^\s。、]+[するしてにをが])", problem)
        action = action_match.group(1) if action_match else problem[:10]

        # Koan templates targeting different types of problems
        if re.search(r"[修正|直す|治す|改善]", problem):
            return (
                f"【公案】\n"
                f"「{problem}」\n\n"
                "完全に修正されたものを修正した者は誰か？\n"
                "修正が必要になる前、そのコードはすでに完全ではなかったか？\n"
                "バグのないコードとバグのあるコードの違いは、\n"
                "バグを見る者の目の中にあるのではないか？"
            )

        if re.search(r"[理解|わかる|知る|学ぶ]", problem):
            return (
                f"【公案】\n"
                f"「{problem}」\n\n"
                "理解する前の「知らない自分」はどこにいたか？\n"
                "理解した後の「知っている自分」はいつから存在したか？\n"
                "理解とは何かを理解したとき、理解は終わるか始まるか？"
            )

        if re.search(r"[作る|生成|創造|実装]", problem):
            return (
                f"【公案】\n"
                f"「{problem}」\n\n"
                "作られる前にそれはどこにあったか？\n"
                "作った後、作者はそれの外にいるか内にいるか？\n"
                "創造物が創造主を作ったとき、どちらが先に存在したか？"
            )

        # Generic template
        return (
            f"【公案】\n"
            f"「{problem}」\n\n"
            f"{action}ことができる者は誰か？\n"
            f"{action}ことができない者もまた、何かを{action.replace('する', 'している')}。\n"
            f"その区別が消えたとき、問いはどこへ行くか？"
        )

    def _template_transcendence(self, paradox: str) -> str:
        """Template transcendence for when LLM is unavailable."""
        return textwrap.dedent(f"""
            【逆説の超越】

            逆説: 「{paradox}」

            ゲーデルの洞察に従い、この逆説を解くのではなく、
            逆説が生まれる条件を観察します。

            この逆説は、ある形式体系（思考フレーム）が
            自分自身について語ろうとするときに生じます。

            超越とは：
            1. この逆説を生成した「フレーム」を認識すること
            2. そのフレームが真実の全てではないと理解すること
            3. フレームを手放すのではなく、フレームであることを知りながら使うこと

            → この逆説は、思考の限界を指し示す「指」です。
            指が指す先、そこに何があるかを見てください。
            逆説は解消されません——それが正しい答えです。
        """).strip()

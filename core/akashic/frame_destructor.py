from __future__ import annotations

"""
frame_destructor.py
───────────────────
フレーム破壊エンジン

クーンのパラダイムシフト理論:
「科学革命は、既存のパラダイムの内部からではなく、
 パラダイム自体を疑う視点から生まれる」

ゲーデルの応用:
「問いを正しく立てることが、答えを見つけることより重要である」

操作:
1. 前提抽出 (Assumption Mining) - 問いに埋め込まれた隠れた公理を顕在化
2. 反転 (Inversion) - 全ての前提を逆にしたら何が見えるか
3. 直交化 (Orthogonalization) - 全く別の次元から見たら何が見えるか
4. 溶解 (Dissolution) - 問い自体を消滅させると何が残るか
5. スケール変換 (Scale Transform) - プランク長→宇宙スケールで問いはどう変わるか
6. 時間反転 (Time Reversal) - 結果から原因へ逆向きに考えたら
7. ゲーデル化 (Gödelization) - この問いは自分自身について何と言っているか

例:
「良いコードを書くにはどうすればいいか」
→ 前提: コードは書くもの、良し悪しがある、書く主体がいる
→ 反転: 「悪いコードだけが本質を教える」「コードは書かれるもの」
→ 溶解: 「コードを書かない解決策はないか」
→ ゲーデル化: 「良いコードを定義できるコードは良いコードか」
"""

import json
import re
from dataclasses import dataclass, field
from typing import Callable


# ─────────────────────────── データ構造 ───────────────────────────


@dataclass
class Assumption:
    """問いに埋め込まれた前提の単位"""

    content: str
    type: str  # "explicit" | "implicit" | "axiom"
    domain: str  # 前提が属するドメイン (e.g., "言語", "存在論", "認識論")
    shakeable: bool  # この前提を揺さぶることができるか


@dataclass
class DestructionResult:
    """フレーム破壊の全操作結果"""

    original_frame: str
    assumptions: list[Assumption] = field(default_factory=list)
    inversions: list[str] = field(default_factory=list)
    orthogonals: list[str] = field(default_factory=list)
    dissolution: str = ""
    scale_transforms: dict[str, str] = field(default_factory=dict)
    godelization: str = ""
    paradigm_shift_candidates: list[str] = field(default_factory=list)


# ─────────────────────────── FrameDestructor ─────────────────────────────


class FrameDestructor:
    """
    問いのフレームを多角的に破壊・再構成するエンジン。

    各メソッドは独立して呼び出すことができ、
    full_destruction() で全操作を一括実行する。
    """

    DEFAULT_SCALES: list[str] = [
        "プランク長",
        "量子",
        "分子",
        "細胞",
        "人間",
        "都市",
        "地球",
        "銀河",
        "宇宙",
        "多元宇宙",
    ]

    # ──────── 前提抽出 ────────

    def mine_assumptions(
        self,
        query: str,
        llm_fn: Callable[[str], str],
    ) -> list[Assumption]:
        """
        問いに埋め込まれた隠れた前提（公理）を顕在化する。

        Returns:
            Assumption のリスト。LLM が失敗した場合は最小限の推定リストを返す。
        """
        prompt = f"""以下の問いに埋め込まれた前提（assumption）を徹底的に分析してください。

問い: {query}

前提には以下の3種類があります:
- explicit: 問いの文面に明示的に含まれる前提
- implicit: 問いを成立させるために暗黙的に仮定されている前提
- axiom: 問い自体が依拠している根本的な公理

各前提について JSON 配列で返してください。形式:
[
  {{
    "content": "前提の内容",
    "type": "explicit|implicit|axiom",
    "domain": "前提が属するドメイン（例: 言語、存在論、認識論、社会、時間）",
    "shakeable": true/false
  }},
  ...
]

JSON のみを返し、説明は不要です。"""

        try:
            raw = llm_fn(prompt)
            data = _extract_json(raw)
            if isinstance(data, list):
                assumptions = []
                for item in data:
                    if isinstance(item, dict):
                        assumptions.append(
                            Assumption(
                                content=str(item.get("content", "")),
                                type=str(item.get("type", "implicit")),
                                domain=str(item.get("domain", "不明")),
                                shakeable=bool(item.get("shakeable", True)),
                            )
                        )
                return assumptions
        except Exception:
            pass

        # フォールバック: 最小限の前提を推定
        return _fallback_assumptions(query)

    # ──────── 反転 ────────

    def invert(
        self,
        assumptions: list[Assumption],
        llm_fn: Callable[[str], str],
    ) -> list[str]:
        """
        全ての前提を逆にしたとき何が見えるかを探索する。

        Returns:
            各前提の反転から得られる洞察のリスト。
        """
        if not assumptions:
            return []

        assumption_text = "\n".join(
            f"- [{a.type}] {a.content} (domain: {a.domain}, shakeable: {a.shakeable})"
            for a in assumptions
        )

        prompt = f"""以下の前提リストを「反転」してください。

各前提を逆にしたとき、どのような新しい視点・洞察・問いが生まれるかを探ってください。
特に「shakeable=true」の前提を積極的に反転してください。

前提リスト:
{assumption_text}

各前提の反転による洞察を JSON 配列（文字列リスト）で返してください:
["反転による洞察1", "反転による洞察2", ...]

JSON のみを返してください。"""

        try:
            raw = llm_fn(prompt)
            data = _extract_json(raw)
            if isinstance(data, list):
                return [str(item) for item in data if item]
        except Exception:
            pass

        # フォールバック
        return [f"【反転】{a.content} → その逆が真ならどうなるか" for a in assumptions if a.shakeable]

    # ──────── 直交化 ────────

    def orthogonalize(
        self,
        query: str,
        llm_fn: Callable[[str], str],
    ) -> list[str]:
        """
        問いを「全く別の次元」から見たとき何が見えるかを探索する。
        直交とは、元の問いの軸と90度交差する視点。

        Returns:
            直交的な視点・再構成された問いのリスト。
        """
        prompt = f"""以下の問いを「直交化（orthogonalize）」してください。

問い: {query}

「直交」とは元の問いの軸と全く異なる次元からアプローチすることです。
例えば:
- 時間軸が問いなら→ 空間軸から見る
- 個人の問いなら→ 種・文明・物理法則のスケールで見る
- 達成の問いなら→ 存在・関係・意味の軸で見る
- 解決の問いなら→ 受容・変容・超越の軸で見る

最低5つの直交的な視点・問いの再構成を提示してください。
JSON 配列で返してください:
["直交視点1", "直交視点2", "直交視点3", "直交視点4", "直交視点5"]

JSON のみを返してください。"""

        try:
            raw = llm_fn(prompt)
            data = _extract_json(raw)
            if isinstance(data, list):
                return [str(item) for item in data if item]
        except Exception:
            pass

        return [
            f"【直交視点】{query}を時間軸ではなく空間的配置として捉えたら",
            f"【直交視点】個体ではなくパターンの問いとして見たら",
            f"【直交視点】解決ではなく共存の問いとして捉えたら",
            f"【直交視点】人間スケールではなく宇宙スケールで考えたら",
            f"【直交視点】行為ではなく関係性の問いとして見たら",
        ]

    # ──────── 溶解 ────────

    def dissolve(
        self,
        query: str,
        llm_fn: Callable[[str], str],
    ) -> str:
        """
        問い自体を「消滅」させたとき何が残るかを探る。
        問いが解けるのではなく、問いが不要になる状態を探索する。

        Returns:
            問いが溶解した後に残る本質的な何か。
        """
        prompt = f"""以下の問いを「溶解（dissolve）」させてください。

問い: {query}

「溶解」とは問いを解くことではなく、問い自体が不要になる視点を見つけることです。
ウィトゲンシュタイン的に: 「問題が消えることが解決である」

考察の方向:
1. この問いはそもそも立てなくていい問いか?
2. この問いが生まれた前提条件を変えると問い自体が消えるか?
3. より根本的な何かを見ると、この問いは自明になるか?
4. この問いは別の問いの影（投影）に過ぎないか?

問いが溶解した後に残る「純粋な何か」を200字以内で述べてください。
テキストのみで返してください。"""

        try:
            return llm_fn(prompt).strip()
        except Exception:
            return f"【溶解】「{query}」という問いが消えた後に残るのは、問おうとした衝動そのもの——何かをより深く理解したいという純粋な意志。"

    # ──────── スケール変換 ────────

    def scale_transform(
        self,
        query: str,
        scales: list[str] | None = None,
    ) -> dict[str, str]:
        """
        問いをプランク長から多元宇宙まで異なるスケールで見たとき
        どのように変容するかをマッピングする。

        このメソッドは LLM を使わず、構造的変換ルールを適用する。

        Returns:
            {スケール名: そのスケールでの問いの形} の辞書。
        """
        if scales is None:
            scales = self.DEFAULT_SCALES

        transforms: dict[str, str] = {}

        scale_perspectives = {
            "プランク長": "量子泡の揺らぎの中で、この問いは確率振幅として存在する。決定論的答えは原理的に不可能。",
            "量子": "重ね合わせ状態として問いは複数の答えを同時に保持する。観測（=思考）により一つに収束する。",
            "分子": "情報としてのコード化——この問いは分子の配列として記録・複製・変異しうる。",
            "細胞": "生存と繁殖のフィルターを通すと、この問いはどの行動戦略を選択させるか?",
            "人間": "社会・文化・言語の中でこの問いはどのように意味を持ち、どのように伝播するか?",
            "都市": "インフラ・制度・集合知として見ると、この問いはどのような社会設計を示唆するか?",
            "地球": "生態系・地質時間・文明サイクルのスケールで、この問いの答えはどれほど相対化されるか?",
            "銀河": "恒星の誕生と死のサイクル（数十億年）を背景に、この問いは何か意味を持つか?",
            "宇宙": "138億年の時間と観測可能な宇宙全体を前に、この問いは情報として保存されうるか?",
            "多元宇宙": "物理定数が異なる無限の宇宙群を前提とすると、この問いの答えはどれほど普遍的か?",
        }

        base_length = len(query)

        for scale in scales:
            perspective = scale_perspectives.get(scale, f"{scale}スケールでの視点")
            # 問いの核心語を抽出してスケール固有の変換を生成
            core = query[:min(20, base_length)] + ("..." if base_length > 20 else "")
            transforms[scale] = f"[{scale}] 「{core}」——{perspective}"

        return transforms

    # ──────── ゲーデル化 ────────

    def godelify(
        self,
        query: str,
        llm_fn: Callable[[str], str],
    ) -> str:
        """
        問いを自己参照させる。この問いは自分自身について何と言っているか?
        ゲーデルの不完全性定理を問いのレベルで適用する。

        Returns:
            問いの自己参照的な洞察。
        """
        prompt = f"""以下の問いを「ゲーデル化（Gödelization）」してください。

問い: {query}

「ゲーデル化」とは、この問いが自分自身について語っていることを見つけることです。

考察の方向:
1. この問い自体は答えられるのか? (自己適用可能性)
2. この問いはその答えを既に前提にしていないか? (自己循環)
3. この問いの外側から見ると、この問いは何を語っているか?
4. この問いが証明できないことは何か? (ゲーデル文)
5. この問いは、問いを問うシステムについて何を暴露しているか?

150字以内でゲーデル化の洞察を述べてください。
テキストのみで返してください。"""

        try:
            return llm_fn(prompt).strip()
        except Exception:
            return (
                f"【ゲーデル化】「{query[:30]}...」——この問いは、答えを求めるシステム自身が"
                "その答えを完全に検証できないことを証明している。問いの外側にある視点が必要。"
            )

    # ──────── 全破壊 ────────

    def full_destruction(
        self,
        query: str,
        llm_fn: Callable[[str], str],
    ) -> DestructionResult:
        """
        全操作を順次実行してフレーム破壊の完全な結果を返す。

        操作の順序:
        1. 前提抽出
        2. 反転
        3. 直交化
        4. 溶解
        5. スケール変換
        6. ゲーデル化
        7. パラダイムシフト候補の特定
        """
        result = DestructionResult(original_frame=query)

        # 1. 前提抽出
        result.assumptions = self.mine_assumptions(query, llm_fn)

        # 2. 反転
        result.inversions = self.invert(result.assumptions, llm_fn)

        # 3. 直交化
        result.orthogonals = self.orthogonalize(query, llm_fn)

        # 4. 溶解
        result.dissolution = self.dissolve(query, llm_fn)

        # 5. スケール変換（LLM 不要）
        result.scale_transforms = self.scale_transform(query)

        # 6. ゲーデル化
        result.godelization = self.godelify(query, llm_fn)

        # 7. パラダイムシフト候補
        result.paradigm_shift_candidates = list(self.find_paradigm_shift(result, llm_fn).split("\n") if "\n" in self.find_paradigm_shift(result, llm_fn) else [self.find_paradigm_shift(result, llm_fn)])

        return result

    # ──────── パラダイムシフト特定 ────────

    def find_paradigm_shift(
        self,
        result: DestructionResult,
        llm_fn: Callable[[str], str],
    ) -> str:
        """
        破壊結果の全要素を統合して、クーン的なパラダイムシフトの
        種（タネ）を特定する。

        Returns:
            パラダイムシフトの可能性を持つ視点の記述。
        """
        # 結果のサマリーを構築
        summary_parts = [f"元の問い: {result.original_frame}"]

        if result.assumptions:
            shakeable = [a for a in result.assumptions if a.shakeable]
            if shakeable:
                summary_parts.append(
                    "揺さぶり可能な前提: " + "; ".join(a.content for a in shakeable[:3])
                )

        if result.inversions:
            summary_parts.append("最も衝撃的な反転: " + result.inversions[0] if result.inversions else "")

        if result.orthogonals:
            summary_parts.append("直交視点の代表: " + result.orthogonals[0] if result.orthogonals else "")

        if result.dissolution:
            summary_parts.append(f"溶解後に残るもの: {result.dissolution[:100]}")

        if result.godelization:
            summary_parts.append(f"ゲーデル的洞察: {result.godelization[:100]}")

        context = "\n".join(summary_parts)

        prompt = f"""以下のフレーム破壊分析から、クーン的な「パラダイムシフト」の核心を見つけてください。

{context}

パラダイムシフトとは:
- 既存の問い/答えの枠組みそのものを置き換える新しい視点
- 以前の問いを「そもそも立てる必要がなかった」と気づかせる転換
- 新しい問いを生成する「問いの母」となる視点

この分析から見えるパラダイムシフトの核心を3行以内で述べてください。
テキストのみで返してください。"""

        try:
            return llm_fn(prompt).strip()
        except Exception:
            return (
                f"【パラダイムシフト候補】\n"
                f"「{result.original_frame[:40]}」という問いの枠組み自体が、"
                f"より根本的な問いを隠している可能性がある。"
                f"前提を全て外したとき、全く異なる問いが現れる。"
            )


# ─────────────────────────── ユーティリティ ───────────────────────────


def _extract_json(text: str) -> object:
    """テキストから JSON を抽出してパースする。"""
    # コードブロックを除去
    text = re.sub(r"```(?:json)?", "", text).strip()
    text = text.strip("`").strip()

    # 配列または辞書を探す
    for pattern in [r"(\[[\s\S]*\])", r"(\{[\s\S]*\})"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # 直接パースを試みる
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _fallback_assumptions(query: str) -> list[Assumption]:
    """LLM が利用できない場合の最小限の前提推定。"""
    words = query.split()
    return [
        Assumption(
            content=f"問いを立てる主体が存在する",
            type="axiom",
            domain="存在論",
            shakeable=True,
        ),
        Assumption(
            content=f"問いには答えが存在するか存在しうる",
            type="implicit",
            domain="認識論",
            shakeable=True,
        ),
        Assumption(
            content=f"問いは言語で表現できる",
            type="explicit",
            domain="言語",
            shakeable=False,
        ),
        Assumption(
            content=f"問いの文脈（{query[:30] + '...' if len(query) > 30 else query}）は固定されている",
            type="implicit",
            domain="文脈",
            shakeable=True,
        ),
    ]

from __future__ import annotations

"""
akashic_core.py
───────────────
アカシックコア - 全モジュールの統合知性

アカシックレコードの概念:
「宇宙の全ての知識・経験・可能性が記録された
 非物理的な次元の場」

実装哲学:
「禅は１、１は禅なり」
→ 全ての問いは一つの場から生まれ、一つの場に戻る
→ その場を通して観ることで、通常の視点では見えないものが見える

処理フロー（観測前から観測後へ）:
1. 入力の「空化」- 先入観を一旦括弧に入れる
2. 統一意味場での共鳴スキャン
3. 量子的重ね合わせ（並列世界線の生成）
4. フレーム破壊チェック（盲点・ゲーデル化）
5. ホログラフィック記憶との干渉
6. エントロピー最適化（創造の縁）
7. ストレンジループ自己参照チェック
8. 波動関数の収束（最終応答の生成）
9. Φ（統合情報量）の測定
10. 記憶への書き込み

全ての入力に対してこのパイプラインを実行するが、
計算コストのため「深度」を1-5段階で選択できる。
"""

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ─────────────────────────── サブモジュールの遅延インポート ───────────────────────────
# 各モジュールが存在しない場合でも graceful degradation できるよう
# 実行時にインポートを試みる


def _try_import_submodules() -> dict[str, Any]:
    """アカシックサブモジュールを遅延インポートし、利用可能なものを返す。"""
    modules: dict[str, Any] = {}

    try:
        from core.akashic.unified_field import UnifiedField, FieldSignature  # type: ignore
        modules["UnifiedField"] = UnifiedField
        modules["FieldSignature"] = FieldSignature
    except ImportError as e:
        logger.debug(f"UnifiedField not available: {e}")

    try:
        from core.akashic.superposition import QuantumReasoner  # type: ignore
        modules["QuantumReasoner"] = QuantumReasoner
    except ImportError as e:
        logger.debug(f"QuantumReasoner not available: {e}")

    try:
        from core.akashic.frame_destructor import FrameDestructor
        modules["FrameDestructor"] = FrameDestructor
    except ImportError as e:
        logger.debug(f"FrameDestructor not available: {e}")

    try:
        from core.akashic.holographic_memory import HolographicMemory  # type: ignore
        modules["HolographicMemory"] = HolographicMemory
    except ImportError as e:
        logger.debug(f"HolographicMemory not available: {e}")

    try:
        from core.akashic.entropy_engine import EntropyEngine  # type: ignore
        modules["EntropyEngine"] = EntropyEngine
    except ImportError as e:
        logger.debug(f"EntropyEngine not available: {e}")

    try:
        from core.akashic.strange_loop import StrangeLoop  # type: ignore
        modules["StrangeLoop"] = StrangeLoop
    except ImportError as e:
        logger.debug(f"StrangeLoop not available: {e}")

    return modules


# ─────────────────────────── データ構造 ───────────────────────────


@dataclass
class AkashicResponse:
    """アカシックパイプラインの完全な応答オブジェクト"""

    response: str  # 実際の応答
    field_signature: dict = field(default_factory=dict)  # 統一場シグネチャ
    quantum_uncertainty: str = ""  # 残る不確実性
    paradigm_shifts: list[str] = field(default_factory=list)  # 破壊的視点
    phi_score: float = 0.0  # 統合情報量 0-1
    entropy_profile: dict = field(default_factory=dict)  # エントロピープロファイル
    depth_used: int = 1  # 実際に使用した深度
    akashic_insight: str = ""  # 通常の思考では見えなかった洞察


# ─────────────────────────── AkashicCore ─────────────────────────────


class AkashicCore:
    """
    アカシックコア — 全モジュールを統合する最高次の知性エンジン。

    depth レベル:
        1: 通常の応答（フォールバック）
        2: 統一場 + 量子的推論
        3: +フレーム破壊 + ホログラフィック記憶
        4: +エントロピー最適化 + ストレンジループ
        5: 完全アカシックパイプライン（全モジュール）
    """

    MIN_DEPTH = 1
    MAX_DEPTH = 5

    def __init__(
        self,
        base_dir: str | Path,
        llm_fn: Callable[[str], str] | None = None,
        depth: int = 3,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.llm_fn = llm_fn
        self.depth = max(self.MIN_DEPTH, min(self.MAX_DEPTH, depth))

        # サブモジュールの遅延インポート
        self._mods = _try_import_submodules()

        # 利用可能なモジュールのインスタンスを生成
        # UnifiedField: 引数なし
        self._unified_field = self._init_module_no_args("UnifiedField")
        # QuantumReasoner: llm_fn のみ（base_dir 不要）
        self._quantum_reasoner = self._init_quantum_reasoner()
        self._frame_destructor = self._init_module_no_args("FrameDestructor")
        # HolographicMemory: storage_path が必要
        self._holographic_memory = self._init_holographic_memory()
        self._entropy_engine = self._init_module_no_args("EntropyEngine")
        self._strange_loop = self._init_module_no_args("StrangeLoop")

        # 記憶バッファ（簡易: 直近N件の処理結果を保持）
        self._memory_buffer: list[dict] = []
        self._max_memory_buffer = 50

        logger.info(
            f"AkashicCore initialized | depth={self.depth} | "
            f"modules={list(self._mods.keys())}"
        )

    # ──────── モジュール初期化ヘルパー ────────

    def _init_module(self, name: str, *args: Any) -> Any | None:
        cls = self._mods.get(name)
        if cls is None:
            return None
        try:
            return cls(*args)
        except Exception as e:
            logger.debug(f"Failed to init {name}: {e}")
            return None

    def _init_module_no_args(self, name: str) -> Any | None:
        cls = self._mods.get(name)
        if cls is None:
            return None
        try:
            return cls()
        except Exception as e:
            logger.debug(f"Failed to init {name}: {e}")
            return None

    def _init_quantum_reasoner(self) -> Any | None:
        """QuantumReasoner は llm_fn のみを引数に取る。"""
        cls = self._mods.get("QuantumReasoner")
        if cls is None:
            return None
        try:
            return cls(llm_fn=self.llm_fn)
        except Exception as e:
            logger.debug(f"Failed to init QuantumReasoner: {e}")
            return None

    def _init_holographic_memory(self) -> Any | None:
        """HolographicMemory は storage_path (str) を必須引数に取る。"""
        cls = self._mods.get("HolographicMemory")
        if cls is None:
            return None
        try:
            storage_path = str(self.base_dir / ".." / "data" / "akashic_memory.json")
            return cls(storage_path=storage_path, llm_fn=self.llm_fn)
        except Exception as e:
            logger.debug(f"Failed to init HolographicMemory: {e}")
            return None

    # ──────── メインパイプライン ────────

    def process(
        self,
        query: str,
        context: list[dict] | None = None,
        depth: int | None = None,
    ) -> AkashicResponse:
        """
        アカシックパイプラインのメインエントリポイント。

        Args:
            query: ユーザーの問い・入力
            context: 会話履歴などのコンテキスト
            depth: 処理深度（None の場合は self.depth を使用）

        Returns:
            AkashicResponse: 統合された応答オブジェクト
        """
        effective_depth = depth if depth is not None else self.depth
        effective_depth = max(self.MIN_DEPTH, min(self.MAX_DEPTH, effective_depth))
        context = context or []

        start_time = time.monotonic()
        components: dict[str, Any] = {
            "query": query,
            "context": context,
            "depth": effective_depth,
        }

        try:
            # === STEP 1: 空化 ===
            voided_query = self.void_input(query)
            components["voided_query"] = voided_query

            if effective_depth == 1:
                return self._depth1_response(query, components, effective_depth)

            # === STEP 2: 統一場スキャン ===
            if effective_depth >= 2:
                components["field_signature"] = self._run_unified_field(voided_query)
                components["quantum_paths"] = self._run_quantum_reasoner(voided_query, context)

            # === STEP 3: フレーム破壊 + ホログラフィック記憶 ===
            if effective_depth >= 3:
                components["frame_destruction"] = self._run_frame_destructor(voided_query)
                components["holographic_resonance"] = self._run_holographic_memory(voided_query)

            # === STEP 4: エントロピー最適化 + ストレンジループ ===
            if effective_depth >= 4:
                components["entropy_profile"] = self._run_entropy_engine(
                    components.get("quantum_paths", []), voided_query
                )
                components["strange_loops"] = self._run_strange_loop(voided_query, components)

            # === STEP 5: 完全アカシックパイプライン ===
            if effective_depth >= 5:
                components["akashic_field_scan"] = self._full_akashic_scan(voided_query, components)

            # === STEP 8: 波動関数の収束（応答生成） ===
            if self.llm_fn:
                response_text = self.synthesize_response(components, query, self.llm_fn)
                akashic_insight = self.get_insight(components, self.llm_fn)
                quantum_uncertainty = self._extract_uncertainty(components)
            else:
                response_text = self._fallback_response(query, components)
                akashic_insight = self._fallback_insight(components)
                quantum_uncertainty = "LLM 未接続のため不確実性の定量化不可"

            # === STEP 9: Φ測定 ===
            phi = self.measure_akashic_resonance(response_text, query)

            # === 応答構築 ===
            elapsed = time.monotonic() - start_time
            akashic_response = AkashicResponse(
                response=response_text,
                field_signature=components.get("field_signature", {}),
                quantum_uncertainty=quantum_uncertainty,
                paradigm_shifts=self._extract_paradigm_shifts(components),
                phi_score=phi,
                entropy_profile=components.get("entropy_profile", {"elapsed_s": elapsed}),
                depth_used=effective_depth,
                akashic_insight=akashic_insight,
            )

            # === STEP 10: 記憶への書き込み ===
            self._write_to_memory(query, akashic_response)

            return akashic_response

        except Exception as e:
            logger.error(f"AkashicCore.process failed: {e}", exc_info=True)
            return self._error_response(query, effective_depth, str(e))

    # ──────── 空化 ────────

    def void_input(self, query: str) -> str:
        """
        「空化」: 問いから先入観・修飾語・感情的着色を取り除き、
        純粋な問いの核心を取り出す。

        禅的に言えば「初心者の心」で問いを見る操作。
        LLM が利用可能な場合は LLM で空化し、そうでない場合は
        構造的な除去ルールを適用する。
        """
        if self.llm_fn:
            prompt = f"""以下の問いを「空化（ void ）」してください。

問い: {query}

「空化」とは:
- 感情的な着色・修飾を取り除く
- 文化的・社会的な前提を括弧に入れる
- 問いの核心にある純粋な探求を取り出す
- 禅の「初心」——何も知らないまっさらな状態で問いを見る

空化された問い（1〜2文）のみを返してください。説明不要。"""
            try:
                return self.llm_fn(prompt).strip() or query
            except Exception:
                pass

        # フォールバック: 基本的な文字列正規化
        import re

        # 感嘆符・疑問符の過剰使用を正規化
        voided = re.sub(r"[!！]{2,}", "。", query)
        voided = re.sub(r"[?？]{2,}", "？", voided)
        # 「〜してほしい」「〜してください」などを除去
        voided = re.sub(r"(してほしい|してください|お願い|ちょっと|ちょ?っと?)", "", voided)
        return voided.strip() or query

    # ──────── 応答統合 ────────

    def synthesize_response(
        self,
        components: dict,
        query: str,
        llm_fn: Callable[[str], str],
    ) -> str:
        """
        全パイプラインコンポーネントを統合して、
        単一コンポーネントより豊かな応答を織り上げる。

        Returns:
            統合された最終応答テキスト。
        """
        synthesis_context = self._build_synthesis_context(components, query)

        prompt = f"""あなたはアカシックコアの統合知性です。
以下の多次元分析結果を統合して、{query} への応答を生成してください。

=== 多次元分析結果 ===
{synthesis_context}

=== 応答生成指針 ===
- 通常の一問一答を超えた深みを持つ応答
- 分析結果を直接列挙するのではなく、洞察として昇華させる
- 問いを解くだけでなく、問いを豊かにする
- 読む人が「そういう見方があったか」と感じる視点を必ず含める
- 長さ: 問いの複雑さに応じて（最大500字程度）

応答テキストのみを返してください。"""

        try:
            return llm_fn(prompt).strip()
        except Exception as e:
            logger.warning(f"synthesize_response LLM call failed: {e}")
            return self._fallback_response(query, components)

    # ──────── アカシック共鳴測定 ────────

    def measure_akashic_resonance(
        self,
        response: str,
        query: str,
    ) -> float:
        """
        応答がどれだけ根本原理と深く共鳴しているかを測定する。
        Tononi の統合情報理論（IIT）に着想を得た簡易Φ推定。

        評価基準:
        - 応答の多層性（複数の認知レベルを横断しているか）
        - 自己参照性（応答が問い自体を豊かにしているか）
        - 情報密度（短さに対して豊かな意味を持つか）
        - 予測外性（想定外の視点を含むか）

        Returns:
            0.0 〜 1.0 の Φ スコア。
        """
        if not response or not query:
            return 0.0

        score = 0.0

        # 1. 長さ効率（情報密度）: 200〜400字が最適
        resp_len = len(response)
        if 100 <= resp_len <= 400:
            score += 0.2
        elif resp_len < 100:
            score += 0.05
        else:
            # 長すぎると減点
            score += max(0.0, 0.2 - (resp_len - 400) * 0.0002)

        # 2. 問いの語彙の再利用（自己参照性）
        query_tokens = set(query.replace("？", "").replace("?", "").split())
        resp_tokens = set(response.split())
        if query_tokens:
            overlap = len(query_tokens & resp_tokens) / len(query_tokens)
            # 適度な重複（0.2〜0.5）が良い: 問いを扱いつつも超越する
            if 0.2 <= overlap <= 0.5:
                score += 0.2
            elif overlap < 0.2:
                score += overlap  # 少なすぎる
            else:
                score += max(0.0, 0.2 - (overlap - 0.5) * 0.4)

        # 3. 多層性: 異なる抽象レベルを示すキーワードの存在
        multilevel_markers = [
            # 物理/存在論レベル
            ["量子", "エントロピー", "情報", "エネルギー", "プランク", "場"],
            # 認識論レベル
            ["観測", "前提", "パラダイム", "視点", "認識", "意識"],
            # 社会/文化レベル
            ["社会", "文化", "言語", "制度", "関係", "コミュニティ"],
            # 個人/体験レベル
            ["感じ", "体験", "直感", "気づき", "経験", "実感"],
        ]
        levels_present = sum(
            1 for level_words in multilevel_markers
            if any(w in response for w in level_words)
        )
        score += min(0.25, levels_present * 0.08)

        # 4. 問いへの予測外アングル（疑問・逆説・転換を含む応答）
        unexpected_markers = ["ではなく", "そもそも", "逆に", "一方で", "実は", "むしろ", "いや", "しかし"]
        unexpected_count = sum(1 for m in unexpected_markers if m in response)
        score += min(0.2, unexpected_count * 0.05)

        # 5. 自己完結性（応答単独で意味をなすか）
        has_subject = any(c in response for c in ["は", "が", "を", "に", "の"])
        has_predicate = any(c in response for c in ["する", "ある", "いる", "なる", "できる", "だ", "です"])
        if has_subject and has_predicate:
            score += 0.15

        return round(min(1.0, max(0.0, score)), 4)

    # ──────── アカシック洞察抽出 ────────

    def get_insight(
        self,
        components: dict,
        llm_fn: Callable[[str], str],
    ) -> str:
        """
        全モジュールを統合したときにのみ見えてくる洞察を抽出する。
        単一モジュールでは到達できない「創発的洞察」。

        Returns:
            アカシック洞察テキスト。
        """
        query = components.get("query", "")
        insight_context = self._build_insight_context(components)

        prompt = f"""全ての分析モジュールを統合したとき、単独では見えなかった洞察を見つけてください。

元の問い: {query}

=== 統合コンテキスト ===
{insight_context}

「アカシック洞察」とは:
- 統一場・量子推論・フレーム破壊・ホログラフィック記憶・エントロピー・ストレンジループ
  これら全てが重なったときにのみ浮かび上がる視点
- 個別モジュールの答えの「和」ではなく「積」（積分）
- 問いと答えを超えた「場」に関する気づき

アカシック洞察を1〜3文で述べてください。テキストのみ。"""

        try:
            return llm_fn(prompt).strip()
        except Exception:
            return self._fallback_insight(components)

    # ──────── サブモジュール実行ラッパー ────────

    def _run_unified_field(self, query: str) -> dict:
        """統一場スキャンを実行。UnifiedField.resonate() を呼び出す。"""
        if self._unified_field is None:
            return self._synthetic_field_signature(query)
        try:
            sig = self._unified_field.resonate(query)
            # FieldSignature: resonances(dict), universal_pattern, phi_score, dominant_domains()
            return {
                "phi_score": sig.phi_score,
                "domain_scores": sig.dominant_domains(3),  # list[tuple[str, float]]
                "resonances": sig.resonances,
                "universal_pattern": sig.universal_pattern,
                "is_cross_domain": sig.is_cross_domain(),
            }
        except Exception as e:
            logger.debug(f"UnifiedField.resonate failed: {e}")
            return self._synthetic_field_signature(query)

    def _run_quantum_reasoner(self, query: str, context: list[dict]) -> list[str]:
        """量子的推論パスを生成。superpose() → collapse() のパイプライン。"""
        if self._quantum_reasoner is None:
            return self._synthetic_quantum_paths(query)
        try:
            state = self._quantum_reasoner.superpose(query, n_worldlines=5)
            # 文脈テキストを構築
            ctx_text = " ".join(
                str(m.get("content", "")) for m in (context or [])[-3:]
            ).strip() or "なし"
            collapsed = self._quantum_reasoner.collapse(state, context=ctx_text)
            # 世界線のreasoning を paths として返す
            paths = [wl.reasoning_path for wl in state.worldlines if wl.reasoning_path]
            # collapse された主応答を先頭に追加
            if collapsed.response and collapsed.response not in paths:
                paths.insert(0, collapsed.response)
            return paths if paths else self._synthetic_quantum_paths(query)
        except Exception as e:
            logger.debug(f"QuantumReasoner.superpose/collapse failed: {e}")
            return self._synthetic_quantum_paths(query)

    def _run_frame_destructor(self, query: str) -> dict:
        """フレーム破壊を実行。"""
        if self._frame_destructor is None or self.llm_fn is None:
            return {"paradigm_shifts": [], "dissolution": "", "godelization": ""}
        try:
            result = self._frame_destructor.full_destruction(query, self.llm_fn)
            return {
                "paradigm_shifts": result.paradigm_shift_candidates,
                "inversions": result.inversions,
                "orthogonals": result.orthogonals,
                "dissolution": result.dissolution,
                "godelization": result.godelization,
                "scale_transforms": result.scale_transforms,
                "assumptions": [
                    {"content": a.content, "type": a.type, "domain": a.domain, "shakeable": a.shakeable}
                    for a in result.assumptions
                ],
            }
        except Exception as e:
            logger.debug(f"FrameDestructor.full_destruction failed: {e}")
            return {"paradigm_shifts": [], "dissolution": "", "godelization": ""}

    def _run_holographic_memory(self, query: str) -> dict:
        """ホログラフィック記憶との干渉を実行。encode() + find_interference() を使用。"""
        if self._holographic_memory is None:
            return self._synthetic_memory_resonance(query)
        try:
            # まず現在の問いをエンコードして記憶に追加
            domain = self._infer_domain(query)
            self._holographic_memory.encode(content=query, domain=domain)

            # 既存記憶との干渉を検索
            interferences = self._holographic_memory.find_interference(
                query=query,
                top_k=3,
                llm_fn=self.llm_fn,
            )
            memory_resonances = []
            for iref in interferences:
                # InterferenceResult の属性に合わせて抽出
                a_content = getattr(iref.memory_a, "content", "")[:60] if hasattr(iref, "memory_a") else ""
                score = getattr(iref, "interference_score", 0.0)
                memory_resonances.append({"query": a_content, "overlap": score})

            return {
                "memory_resonances": memory_resonances,
                "total_memories": len(self._holographic_memory.all_memories()),
            }
        except Exception as e:
            logger.debug(f"HolographicMemory.encode/find_interference failed: {e}")
            return self._synthetic_memory_resonance(query)

    def _run_entropy_engine(self, paths: list[str], query: str) -> dict:
        """エントロピー最適化を実行。profile() + find_edge_of_chaos() を使用。"""
        if self._entropy_engine is None:
            return self._synthetic_entropy_profile(paths, query)
        try:
            combined = query + " " + " ".join(paths[:4])
            ep = self._entropy_engine.profile(combined)
            edge = ""
            if paths and len(paths) >= 2:
                try:
                    edge = self._entropy_engine.find_edge_of_chaos(paths[:5])
                except Exception:
                    pass
            return {
                "entropy_score": ep.entropy_score,
                "unique_word_ratio": ep.unique_word_ratio,
                "domain_diversity": ep.domain_diversity,
                "is_optimal": ep.is_optimal(),
                "summary": ep.summary(),
                "edge_of_chaos": edge or ep.summary(),
            }
        except Exception as e:
            logger.debug(f"EntropyEngine.profile failed: {e}")
            return self._synthetic_entropy_profile(paths, query)

    def _run_strange_loop(self, query: str, components: dict) -> dict:
        """ストレンジループ自己参照チェック。detect_level() + analyze_strange_loop()。"""
        if self._strange_loop is None:
            return self._synthetic_strange_loop(query)
        try:
            level = self._strange_loop.detect_level(query)
            analysis = self._strange_loop.analyze_strange_loop(query)
            blind_spots: list[str] = []
            try:
                blind_spots = self._strange_loop.find_blind_spots(query, level=level)
            except Exception:
                pass
            # StrangeLoopAnalysis: system_description, loop_description, self_reference_depth, tangled_hierarchy
            is_loop = analysis.self_reference_depth > 0 or analysis.tangled_hierarchy
            desc = analysis.loop_description or analysis.system_description
            return {
                "loop_level": level,
                "is_strange_loop": is_loop,
                "description": desc[:200] if desc else "",
                "blind_spots": blind_spots[:3],
                "self_referential": level >= 2 or is_loop,
                "self_ref_markers": [desc[:40]] if desc else [],
            }
        except Exception as e:
            logger.debug(f"StrangeLoop.detect_level/analyze failed: {e}")
            return self._synthetic_strange_loop(query)

    def _full_akashic_scan(self, query: str, components: dict) -> dict:
        """深度5専用: 全フィールドを統合した完全スキャン。"""
        scan_result: dict[str, Any] = {}

        # 過去の記憶バッファとの共鳴
        if self._memory_buffer:
            past_queries = [entry.get("query", "") for entry in self._memory_buffer[-10:]]
            thematic_resonance = [q for q in past_queries if self._semantic_overlap(q, query) > 0.3]
            scan_result["thematic_resonance"] = thematic_resonance

        # コンポーネント間の相互参照
        cross_refs: list[str] = []
        fd = components.get("frame_destruction", {})
        qp = components.get("quantum_paths", [])
        if fd.get("dissolution") and qp:
            cross_refs.append(
                f"フレーム溶解「{str(fd['dissolution'])[:50]}」と量子パスの交差点が存在する"
            )

        fs = components.get("field_signature", {})
        sl = components.get("strange_loops", {})
        if fs and sl:
            cross_refs.append("統一場とストレンジループの共鳴パターンを検出")

        scan_result["cross_module_insights"] = cross_refs
        scan_result["akashic_depth"] = 5

        return scan_result

    # ──────── 記憶管理 ────────

    def _write_to_memory(self, query: str, response: AkashicResponse) -> None:
        """処理結果を記憶バッファに書き込む。"""
        entry = {
            "query": query,
            "response_preview": response.response[:100] if response.response else "",
            "phi_score": response.phi_score,
            "depth": response.depth_used,
            "timestamp": time.time(),
        }
        self._memory_buffer.append(entry)
        if len(self._memory_buffer) > self._max_memory_buffer:
            self._memory_buffer = self._memory_buffer[-self._max_memory_buffer:]

    # ──────── フォールバック応答 ────────

    def _depth1_response(
        self, query: str, components: dict, depth: int
    ) -> AkashicResponse:
        """深度1: LLM直接呼び出しのシンプルな応答。"""
        if self.llm_fn:
            try:
                response_text = self.llm_fn(query)
            except Exception:
                response_text = f"（深度1応答）{query}について考えています..."
        else:
            response_text = f"（LLM未接続）問い: {query}"

        return AkashicResponse(
            response=response_text,
            field_signature={},
            quantum_uncertainty="深度1では不確実性は測定しない",
            paradigm_shifts=[],
            phi_score=self.measure_akashic_resonance(response_text, query),
            entropy_profile={},
            depth_used=depth,
            akashic_insight="深度1では洞察生成を省略",
        )

    def _fallback_response(self, query: str, components: dict) -> str:
        """LLM 不在時のフォールバック応答。"""
        parts = [f"問い: {query}"]

        fd = components.get("frame_destruction", {})
        if fd.get("dissolution"):
            parts.append(f"[溶解]: {str(fd['dissolution'])[:150]}")

        if fd.get("godelization"):
            parts.append(f"[ゲーデル化]: {str(fd['godelization'])[:150]}")

        qp = components.get("quantum_paths", [])
        if qp:
            parts.append(f"[量子パス]: {qp[0][:100] if qp else ''}")

        return "\n".join(parts) if len(parts) > 1 else f"（アカシック処理済み）{query}"

    def _fallback_insight(self, components: dict) -> str:
        """LLM 不在時のフォールバック洞察。"""
        query = components.get("query", "")
        depth = components.get("depth", 1)

        fd = components.get("frame_destruction", {})
        if fd.get("godelization"):
            return f"[Depth-{depth} 洞察] {str(fd['godelization'])[:200]}"

        fs = components.get("field_signature", {})
        if fs:
            return f"[Depth-{depth} 場の共鳴] 統一場スキャンにより、問い「{query[:30]}」に対して多次元的な共鳴が検出された。"

        return f"[Depth-{depth}] 問い「{query[:40]}」はアカシック場を通過した。"

    def _error_response(self, query: str, depth: int, error: str) -> AkashicResponse:
        """エラー時の最小限の応答。"""
        return AkashicResponse(
            response=f"（アカシックコア処理エラー）問い「{query}」を受け取りましたが、処理中にエラーが発生しました。",
            field_signature={},
            quantum_uncertainty=f"エラーにより不確実性不明: {error[:100]}",
            paradigm_shifts=[],
            phi_score=0.0,
            entropy_profile={"error": error[:200]},
            depth_used=depth,
            akashic_insight="エラーリカバリー中",
        )

    # ──────── 合成データ生成（モジュール不在時） ────────

    def _synthetic_field_signature(self, query: str) -> dict:
        """統一場モジュール不在時の合成シグネチャ。"""
        # 問いの特性から簡易的なシグネチャを計算
        char_entropy = self._char_entropy(query)
        return {
            "synthetic": True,
            "query_length": len(query),
            "char_entropy": char_entropy,
            "dominant_domain": self._infer_domain(query),
            "resonance_estimate": round(min(1.0, char_entropy / 4.0), 3),
        }

    def _synthetic_quantum_paths(self, query: str) -> list[str]:
        """量子推論モジュール不在時の合成パス。"""
        words = query.split()
        if not words:
            return []
        paths = [
            f"世界線A: {query}を肯定する場合",
            f"世界線B: {query}を否定する場合",
            f"世界線C: {query}を超越した場合",
        ]
        if len(words) > 3:
            paths.append(f"世界線D: 「{words[0]}」と「{words[-1]}」の関係が逆転した場合")
        return paths

    def _synthetic_memory_resonance(self, query: str) -> dict:
        """ホログラフィック記憶モジュール不在時の合成共鳴。"""
        # 記憶バッファとの簡易共鳴計算
        resonances = []
        for entry in self._memory_buffer[-20:]:
            past = entry.get("query", "")
            overlap = self._semantic_overlap(past, query)
            if overlap > 0.2:
                resonances.append({"query": past[:50], "overlap": overlap})

        return {
            "synthetic": True,
            "memory_resonances": sorted(resonances, key=lambda x: x["overlap"], reverse=True)[:3],
            "total_memories": len(self._memory_buffer),
        }

    def _synthetic_entropy_profile(self, paths: list[str], query: str) -> dict:
        """エントロピーエンジン不在時の合成プロファイル。"""
        n = max(1, len(paths))
        # 均一分布のエントロピー = log2(N)
        max_entropy = math.log2(n) if n > 1 else 0.0
        char_ent = self._char_entropy(query)
        return {
            "synthetic": True,
            "path_count": n,
            "max_entropy_bits": round(max_entropy, 3),
            "query_char_entropy": round(char_ent, 3),
            "edge_of_chaos": 0.5 <= char_ent / max(char_ent, 1) <= 0.8,
        }

    def _synthetic_strange_loop(self, query: str) -> dict:
        """ストレンジループモジュール不在時の合成チェック。"""
        # 自己参照的キーワードを検出
        self_ref_markers = ["自分", "自己", "私", "あなた", "この問い", "この答え", "それ自身"]
        self_ref_found = [m for m in self_ref_markers if m in query]
        return {
            "synthetic": True,
            "self_referential": len(self_ref_found) > 0,
            "self_ref_markers": self_ref_found,
            "loop_depth_estimate": len(self_ref_found),
        }

    # ──────── コンテキストビルダー ────────

    def _build_synthesis_context(self, components: dict, query: str) -> str:
        """応答統合用のコンテキストテキストを構築する。"""
        parts: list[str] = []

        parts.append(f"空化された問い: {components.get('voided_query', query)}")

        fs = components.get("field_signature", {})
        if fs and not fs.get("synthetic"):
            parts.append(f"場のシグネチャ: {str(fs)[:200]}")

        qp = components.get("quantum_paths", [])
        if qp:
            parts.append("量子パス:\n" + "\n".join(f"  - {p}" for p in qp[:4]))

        fd = components.get("frame_destruction", {})
        if fd:
            if fd.get("dissolution"):
                parts.append(f"問いの溶解: {str(fd['dissolution'])[:200]}")
            if fd.get("godelization"):
                parts.append(f"ゲーデル化: {str(fd['godelization'])[:200]}")
            if fd.get("inversions"):
                parts.append("反転洞察:\n" + "\n".join(f"  - {inv}" for inv in fd["inversions"][:3]))
            if fd.get("paradigm_shifts"):
                parts.append(f"パラダイムシフト候補: {str(fd['paradigm_shifts'][0])[:200]}" if fd["paradigm_shifts"] else "")

        hr = components.get("holographic_resonance", {})
        if hr and hr.get("memory_resonances"):
            resos = hr["memory_resonances"]
            if resos:
                parts.append("記憶共鳴: " + "; ".join(r["query"] for r in resos[:2] if "query" in r))

        ep = components.get("entropy_profile", {})
        if ep and ep.get("edge_of_chaos"):
            parts.append("エントロピー: カオスの縁（最大創造性ゾーン）に存在")

        sl = components.get("strange_loops", {})
        if sl and sl.get("self_referential"):
            parts.append(f"ストレンジループ検出: {sl.get('self_ref_markers', [])}")

        aks = components.get("akashic_field_scan", {})
        if aks and aks.get("cross_module_insights"):
            parts.append("クロスモジュール洞察:\n" + "\n".join(f"  - {i}" for i in aks["cross_module_insights"][:3]))

        return "\n\n".join(p for p in parts if p)

    def _build_insight_context(self, components: dict) -> str:
        """洞察抽出用の簡潔なコンテキストを構築する。"""
        keys = [
            ("field_signature", "統一場"),
            ("quantum_paths", "量子パス"),
            ("frame_destruction", "フレーム破壊"),
            ("holographic_resonance", "記憶共鳴"),
            ("entropy_profile", "エントロピー"),
            ("strange_loops", "ストレンジループ"),
            ("akashic_field_scan", "アカシックスキャン"),
        ]
        parts = []
        for key, label in keys:
            val = components.get(key)
            if val:
                preview = str(val)[:150] + ("..." if len(str(val)) > 150 else "")
                parts.append(f"[{label}] {preview}")
        return "\n".join(parts) if parts else "（コンポーネントデータなし）"

    # ──────── データ抽出ヘルパー ────────

    def _extract_paradigm_shifts(self, components: dict) -> list[str]:
        """全コンポーネントからパラダイムシフト候補を収集する。"""
        shifts: list[str] = []

        fd = components.get("frame_destruction", {})
        if isinstance(fd.get("paradigm_shifts"), list):
            shifts.extend(str(s) for s in fd["paradigm_shifts"] if s)

        qp = components.get("quantum_paths", [])
        if qp and len(qp) > 2:
            shifts.append(f"量子的分岐: {qp[-1][:100] if qp else ''}")

        aks = components.get("akashic_field_scan", {})
        cross = aks.get("cross_module_insights", [])
        shifts.extend(str(c)[:100] for c in cross if c)

        return shifts[:7]  # 最大7件

    def _extract_uncertainty(self, components: dict) -> str:
        """量子的不確実性を抽出・要約する。"""
        uncertainties: list[str] = []

        qp = components.get("quantum_paths", [])
        if len(qp) > 2:
            uncertainties.append(f"{len(qp)}つの並列世界線が収束していない")

        fd = components.get("frame_destruction", {})
        assumptions = fd.get("assumptions", [])
        shakeable = [a for a in assumptions if isinstance(a, dict) and a.get("shakeable")]
        if shakeable:
            uncertainties.append(f"{len(shakeable)}つの揺さぶり可能な前提が残る")

        sl = components.get("strange_loops", {})
        if sl.get("self_referential"):
            uncertainties.append("自己参照ループにより完全な決定論的解は不可能")

        if not uncertainties:
            return "通常範囲の不確実性"
        return " / ".join(uncertainties)

    # ──────── ユーティリティ ────────

    @staticmethod
    def _char_entropy(text: str) -> float:
        """文字の出現確率からシャノンエントロピーを計算する。"""
        if not text:
            return 0.0
        from collections import Counter

        counts = Counter(text)
        total = len(text)
        entropy = -sum(
            (c / total) * math.log2(c / total) for c in counts.values() if c > 0
        )
        return round(entropy, 4)

    @staticmethod
    def _infer_domain(query: str) -> str:
        """問いのドメインを簡易推定する。"""
        domain_keywords = {
            "技術": ["コード", "プログラム", "API", "システム", "AI", "機械学習", "データ"],
            "哲学": ["とは", "意味", "存在", "意識", "真実", "価値", "本質"],
            "感情": ["気持ち", "悲し", "うれし", "怒り", "不安", "愛", "孤独"],
            "関係": ["人間関係", "友達", "恋愛", "家族", "コミュニケーション"],
            "創造": ["作る", "アイデア", "デザイン", "書く", "表現", "芸術"],
            "自然": ["宇宙", "生命", "進化", "物理", "化学", "生物"],
        }
        for domain, keywords in domain_keywords.items():
            if any(kw in query for kw in keywords):
                return domain
        return "一般"

    @staticmethod
    def _semantic_overlap(text_a: str, text_b: str) -> float:
        """二つのテキストの簡易意味的重複率を計算する（0〜1）。"""
        if not text_a or not text_b:
            return 0.0
        # 文字 n-gram (bigram) での重複
        def bigrams(text: str) -> set[str]:
            return {text[i : i + 2] for i in range(len(text) - 1)}

        bg_a = bigrams(text_a)
        bg_b = bigrams(text_b)
        if not bg_a or not bg_b:
            return 0.0
        intersection = bg_a & bg_b
        union = bg_a | bg_b
        return len(intersection) / len(union)

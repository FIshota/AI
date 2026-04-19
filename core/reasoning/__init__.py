"""
core.reasoning — 学術的命名による公開 API

ai-chan の推論層は、もともと詩的/暗喩的な名前 (Akashic Core, Quantum Reasoner,
Unified Field など) で実装されていた。これらは開発上の思想を保持するために
`core.akashic.*` として残しつつ、**外部発表・論文・モデルカード・API 文書**
では文字通り機械学習文脈で受け入れられる用語を用いる。

| 旧名 (internal)       | 新名 (public)                       | 領域                                   |
|-----------------------|-------------------------------------|----------------------------------------|
| QuantumReasoner       | MultiPerspectiveReasoner            | 多視点アンサンブル推論                 |
| QuantumState          | EnsembleState                       | 多視点内部状態                          |
| WorldLine             | PerspectivePath                     | 視点ごとの推論パス                     |
| InterferenceMatrix    | AgreementMatrix                     | 視点間合意/不一致行列                  |
| CollapsedResponse     | ConsensusResponse                   | 収束後応答                              |
| UnifiedField          | DomainResonanceField                | 概念の多領域共鳴                       |
| FieldSignature        | DomainSignature                     | 領域シグネチャ                          |
| EntropyEngine         | DissipativeOptimizer                | 散逸構造的最適化                        |
| EntropyProfile        | DissipationProfile                  | 散逸プロファイル                        |
| HolographicMemory     | DistributedAssociativeMemory        | 分散連想記憶                            |
| MemoryHologram        | AssociativeKey                      | 連想キー                                |
| InterferencePattern   | SuperpositionTrace                  | 重ね合わせ痕跡                          |
| StrangeLoop           | SelfReferentialLoopAnalyzer         | 自己参照ループ解析                      |
| StrangeLoopAnalysis   | SelfReferentialReport               | 自己参照レポート                        |
| FrameDestructor       | FrameShiftOperator                  | 前提フレーム変換                        |
| Assumption            | HiddenPremise                       | 暗黙前提                                |
| DestructionResult     | FrameShiftResult                    | フレーム変換結果                        |

学術コンテキスト（論文・README・model card・外部発表）では **こちらの名前** を使用する。
内部コードはそのままでよい。新規コードは `from core.reasoning import ...` を推奨。

設計上の裏付け:
  - MultiPerspectiveReasoner : Tree-of-Thought / Self-Consistency / Mixture-of-Perspectives 系列
  - DomainResonanceField    : Concept-in-Context embedding + domain-projection
  - DissipativeOptimizer    : Prigogine 散逸構造 → 情報理論的エントロピー管理
  - DistributedAssociativeMemory : Hopfield / Modern Hopfield Network 着想
  - SelfReferentialLoopAnalyzer  : Hofstadter strange loop → meta-reasoning 検出
"""
from __future__ import annotations

# ─── Multi-Perspective Ensemble Reasoning ─────────────────────
from core.akashic.superposition import (
    QuantumReasoner as MultiPerspectiveReasoner,
    QuantumState as EnsembleState,
    WorldLine as PerspectivePath,
    InterferenceMatrix as AgreementMatrix,
    CollapsedResponse as ConsensusResponse,
)

# ─── Domain Resonance Field ───────────────────────────────────
from core.akashic.unified_field import (
    UnifiedField as DomainResonanceField,
    FieldSignature as DomainSignature,
)

# ─── Dissipative Optimization ─────────────────────────────────
from core.akashic.entropy_engine import (
    EntropyEngine as DissipativeOptimizer,
    EntropyProfile as DissipationProfile,
)

# ─── Distributed Associative Memory ───────────────────────────
from core.akashic.holographic_memory import (
    HolographicMemory as DistributedAssociativeMemory,
    MemoryHologram as AssociativeKey,
    InterferencePattern as SuperpositionTrace,
)

# ─── Self-Referential Loop Analysis ───────────────────────────
from core.akashic.strange_loop import (
    StrangeLoop as SelfReferentialLoopAnalyzer,
    StrangeLoopAnalysis as SelfReferentialReport,
)

# ─── Frame Shift Operator ─────────────────────────────────────
from core.akashic.frame_destructor import (
    FrameDestructor as FrameShiftOperator,
    Assumption as HiddenPremise,
    DestructionResult as FrameShiftResult,
)

# repr を学術名にする（print / logger / reprlib で新名が表示されるようにする）
# __name__ / __qualname__ はクラスオブジェクトの属性なので上書き可能。
_RENAMES = {
    MultiPerspectiveReasoner: "MultiPerspectiveReasoner",
    EnsembleState: "EnsembleState",
    PerspectivePath: "PerspectivePath",
    AgreementMatrix: "AgreementMatrix",
    ConsensusResponse: "ConsensusResponse",
    DomainResonanceField: "DomainResonanceField",
    DomainSignature: "DomainSignature",
    DissipativeOptimizer: "DissipativeOptimizer",
    DissipationProfile: "DissipationProfile",
    DistributedAssociativeMemory: "DistributedAssociativeMemory",
    AssociativeKey: "AssociativeKey",
    SuperpositionTrace: "SuperpositionTrace",
    SelfReferentialLoopAnalyzer: "SelfReferentialLoopAnalyzer",
    SelfReferentialReport: "SelfReferentialReport",
    FrameShiftOperator: "FrameShiftOperator",
    HiddenPremise: "HiddenPremise",
    FrameShiftResult: "FrameShiftResult",
}
for _cls, _new_name in _RENAMES.items():
    try:
        _cls.__name__ = _new_name
        _cls.__qualname__ = _new_name
    except (AttributeError, TypeError):
        pass
del _cls, _new_name, _RENAMES

__all__ = [
    # Reasoning ensemble
    "MultiPerspectiveReasoner",
    "EnsembleState",
    "PerspectivePath",
    "AgreementMatrix",
    "ConsensusResponse",
    # Resonance field
    "DomainResonanceField",
    "DomainSignature",
    # Optimization
    "DissipativeOptimizer",
    "DissipationProfile",
    # Memory
    "DistributedAssociativeMemory",
    "AssociativeKey",
    "SuperpositionTrace",
    # Self-reference
    "SelfReferentialLoopAnalyzer",
    "SelfReferentialReport",
    # Frame shift
    "FrameShiftOperator",
    "HiddenPremise",
    "FrameShiftResult",
]

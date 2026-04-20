"""
AiChanDeps — 依存注入コンテナ (H1, 2026-04-21)。

core/ai_chan.py の god-object `__init__` を段階的に DI 化するための
ホルダー。各 subsystem を Optional で持ち、None なら従来通り AiChan が
内部で new する fallback パスに進む。

テストからは `AiChanDeps(memory=FakeMemory(), llm=FakeLLM(), ...)` を
渡せばユニットテストが容易になる。

使い方:
    # 従来（変更なし）
    ai = AiChan(base_dir=".")

    # 新パス（H1）
    deps = AiChanDeps(
        memory=my_fake_memory,
        llm=my_fake_llm,
    )
    ai = AiChan(base_dir=".", deps=deps)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AiChanDeps:
    """AiChan が使う subsystem の注入ポイント。

    None のフィールドは AiChan 側で通常通り生成される。
    非 None のフィールドは生成をスキップしてそのまま採用される。

    すべて Any 型にしているのは、完全な Protocol 化が未了のため。
    段階的に core.protocols.*Protocol へ差し替えていく。
    """

    memory: Optional[Any] = None
    emotion: Optional[Any] = None
    llm: Optional[Any] = None
    diary: Optional[Any] = None
    emotion_history: Optional[Any] = None
    anniversary: Optional[Any] = None
    learning: Optional[Any] = None
    subject_rights: Optional[Any] = None
    audit_log: Optional[Any] = None
    scheduler: Optional[Any] = None
    event_bus: Optional[Any] = None

    def override(self, obj: Any, attr: str, label: str) -> Any:
        """`obj.attr` が未設定 or None なら self.<label> で上書きする内部ヘルパー。

        AiChan.__init__ 側から `self.deps.override(self, "memory", "memory")`
        のように呼び、注入値があれば採用、なければ従来の生成パスを許す。
        """
        injected = getattr(self, label, None)
        if injected is not None:
            setattr(obj, attr, injected)
            return injected
        return getattr(obj, attr, None)

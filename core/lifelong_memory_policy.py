"""Retention policy for the Lifelong Memory Module.

``should_retain`` is intentionally small and pure — it decides whether a given
``MemoryEvent`` is allowed into long-term storage. Callers layer real consent /
audit systems on top.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable

from core.lifelong_memory import MemoryEvent

# 最低 importance しきい値 (既定)。trend は揺らぎが大きいので緩めに。
DEFAULT_IMPORTANCE_THRESHOLD: float = 0.2
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.3
KIND_MIN_IMPORTANCE: dict = {
    "event": 0.2,
    "person": 0.3,
    "preference": 0.25,
    "trend": 0.1,
}


@dataclass(frozen=True)
class RetentionPolicy:
    """Policy knobs for ``should_retain``.

    * ``consenting_subjects``: 明示同意済みの subject_id セット。
      空集合なら全主体を許可する (PoC デフォルト)。
    * ``blocklist_tags``: これらのタグを含む event は必ず却下する
      (医療・政治信条などセンシティブ情報を想定)。
    """

    consenting_subjects: FrozenSet[str] = frozenset()
    blocklist_tags: FrozenSet[str] = frozenset()
    min_importance: float = DEFAULT_IMPORTANCE_THRESHOLD
    min_confidence: float = DEFAULT_CONFIDENCE_THRESHOLD

    def allows_subject(self, subject_id: str) -> bool:
        if not self.consenting_subjects:
            return True
        return subject_id in self.consenting_subjects


def should_retain(
    event: MemoryEvent,
    policy: RetentionPolicy = RetentionPolicy(),
) -> bool:
    """Return True iff the event is eligible for long-term retention."""
    if not policy.allows_subject(event.subject_id):
        return False
    if policy.blocklist_tags and any(t in policy.blocklist_tags for t in event.tags):
        return False
    if event.confidence < policy.min_confidence:
        return False
    kind_min = KIND_MIN_IMPORTANCE.get(event.kind, policy.min_importance)
    effective_min = max(policy.min_importance, kind_min)
    if event.importance < effective_min:
        return False
    if not event.content.strip():
        return False
    return True


def filter_retainable(
    events: Iterable[MemoryEvent],
    policy: RetentionPolicy = RetentionPolicy(),
):
    """Generator yielding only events that pass ``should_retain``."""
    for ev in events:
        if should_retain(ev, policy):
            yield ev


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_IMPORTANCE_THRESHOLD",
    "KIND_MIN_IMPORTANCE",
    "RetentionPolicy",
    "filter_retainable",
    "should_retain",
]

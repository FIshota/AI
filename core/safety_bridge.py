"""Safety bridge to hinomoto-model's deny-list.

Import is lazy and fault-tolerant: if hinomoto-model is not available on the
PYTHONPATH (e.g. in a minimal ai-chan install), this module falls back to a
no-op evaluator that always returns ``(False, [])`` and logs the reason once.

Failing open (``False``) is the safer choice for ai-chan's UX: the caller is
expected to apply *additional* guardrails (LLM refusal, per-skill policies)
on top of this check. The primary purpose of the bridge is to layer the
shared rule-based filter, not to replace higher-level policy.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_HINOMOTO_AVAILABLE: Optional[bool] = None
_DENY_LIST = None  # type: ignore[var-annotated]


def _candidate_hinomoto_roots() -> List[Path]:
    roots: List[Path] = []
    env = os.environ.get("HINOMOTO_ROOT")
    if env:
        roots.append(Path(env))
    here = Path(__file__).resolve()
    # ai-chan/core/safety_bridge.py -> agent/ai-chan/core -> agent/ai-chan -> agent
    roots.append(here.parents[2] / "hinomoto-model")
    return [r for r in roots if r.exists()]


def _try_load() -> None:
    """Attempt to import hinomoto.safety and load the skeleton config."""
    global _HINOMOTO_AVAILABLE, _DENY_LIST
    if _HINOMOTO_AVAILABLE is not None:
        return

    for root in _candidate_hinomoto_roots():
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)

    try:
        from hinomoto.safety import (  # type: ignore[import-not-found]
            default_config_path,
            load_deny_list,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        _HINOMOTO_AVAILABLE = False
        logger.warning(
            "safety_bridge: hinomoto.safety unavailable (%s); "
            "is_denied() will no-op and return False.",
            exc,
        )
        return

    try:
        cfg = default_config_path()
        if cfg is None:
            logger.warning(
                "safety_bridge: no deny_list.yaml found; loading empty deny list."
            )
            _DENY_LIST = load_deny_list([])
        else:
            _DENY_LIST = load_deny_list(cfg)
        _HINOMOTO_AVAILABLE = True
        logger.info(
            "safety_bridge: loaded %d deny rules from %s",
            len(_DENY_LIST.rules),
            cfg,
        )
    except Exception as exc:
        _HINOMOTO_AVAILABLE = False
        logger.warning(
            "safety_bridge: failed to load deny list (%s); falling back to no-op.",
            exc,
        )


def is_denied(text: str) -> Tuple[bool, List[str]]:
    """Return ``(denied, categories)`` for ``text``.

    * ``denied``: True iff a hard-severity rule matches.
    * ``categories``: list of category *string values* (stable wire format
      for ai-chan callers that should not depend on hinomoto enums).

    On any failure to import / load hinomoto-model, returns ``(False, [])``.
    """
    _try_load()
    if not _HINOMOTO_AVAILABLE or _DENY_LIST is None:
        return False, []
    if not text:
        return False, []
    denied, cats = _DENY_LIST.is_denied(text)
    return denied, [c.value for c in cats]


def is_available() -> bool:
    """Return True iff the hinomoto-model deny list is loaded and usable."""
    _try_load()
    return bool(_HINOMOTO_AVAILABLE)


__all__ = ["is_denied", "is_available"]

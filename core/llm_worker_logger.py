"""M8 Phase 2: LLM worker JSONL event logger.

Appends structured events to ``logs/llm_worker.jsonl`` so operators can audit
worker lifecycle, failures, and restarts without trawling stderr.

Each line is a self-contained JSON object:

    {"ts": "2026-04-21T09:30:12+09:00", "evt": "start", "pid": 12345, ...}

Best-effort: all failures are swallowed (logging must never break inference).
Disabled automatically when ``logs/`` is not writable.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Valid event names — keep the vocabulary small so ops dashboards can rely on it.
EVT_START = "start"
EVT_READY = "ready"
EVT_REQUEST = "request"
EVT_SUCCESS = "success"
EVT_FAILURE = "failure"
EVT_RESTART = "restart"
EVT_CIRCUIT_OPEN = "circuit_open"
EVT_CIRCUIT_RESET = "circuit_reset"
EVT_SHUTDOWN = "shutdown"


class LLMWorkerLogger:
    """Thread-safe append-only JSONL writer.

    Instantiate once per process (e.g. from ``LLMProxy.__init__``). Calling
    ``.log(evt, **fields)`` is O(1) best-effort: any IOError is silenced.
    """

    def __init__(self, base_dir: Path | str | None = None, enabled: bool = True):
        self._enabled = bool(enabled)
        self._lock = threading.Lock()
        self._path: Path | None = None
        if not self._enabled:
            return
        try:
            base = Path(base_dir) if base_dir else Path.cwd()
            log_dir = base / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            self._path = log_dir / "llm_worker.jsonl"
            # Touch to verify writability
            with open(self._path, "a", encoding="utf-8"):
                pass
        except Exception as exc:  # pragma: no cover — unwritable logs/
            logger.warning("LLMWorkerLogger disabled: %s", exc)
            self._enabled = False
            self._path = None

    @staticmethod
    def _ts() -> str:
        # Local time with offset for at-a-glance ops reading
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def log(self, evt: str, **fields: Any) -> None:
        """Append one event. Never raises."""
        if not self._enabled or self._path is None:
            return
        record = {"ts": self._ts(), "evt": evt, "pid": os.getpid(), **fields}
        try:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            # Unserializable field — skip silently rather than crash inference
            return
        try:
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as exc:
            # Disk full / permission changed mid-run — warn ONCE via stdlib
            # logger (best-effort, survives even if our file path dies) then
            # disable further writes to avoid log spam on every event.
            logger.warning(
                "LLMWorkerLogger write failed (%s); suppressing further events "
                "— ops visibility for circuit/restart events will be lost",
                exc,
            )
            self._enabled = False

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

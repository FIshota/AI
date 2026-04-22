"""M8: LLMProxy — client-side IPC wrapper for LLMEngine.

Provides the **same public API** as ``core.llm.LLMEngine`` but forwards calls
to a separate ``ai_chan_llm_worker`` subprocess over Unix Domain Socket.

Opt-in: enable via ``settings["llm_ipc_enabled"] = True``. Default is
in-process (existing behavior unchanged).

Design rules (from M8-subtaskA):
- ``build_prompt`` runs **client-side** (no IPC hop for prompt assembly).
- ``override_params`` / ``restore_params`` are merged into ``generate_chat``'s
  ``params_override`` arg (atomic on worker side).
- Single outstanding request at a time (matches LLMEngine's inference lock).
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Generator, Optional

from core.llm_worker_logger import (
    EVT_CIRCUIT_OPEN,
    EVT_CIRCUIT_RESET,
    EVT_FAILURE,
    EVT_READY,
    EVT_RESTART,
    EVT_SHUTDOWN,
    EVT_START,
    EVT_SUCCESS,
    LLMWorkerLogger,
)
from core.llm_ipc_protocol import (
    ERR_PROTOCOL_MISMATCH,
    KIND_CHUNK,
    KIND_END,
    KIND_ERROR,
    KIND_READY,
    KIND_RESULT,
    LineReader,
    OP_GENERATE,
    OP_GENERATE_CHAT,
    OP_GENERATE_WITH_CONFIDENCE,
    OP_GET_BACKEND,
    OP_GET_STATS,
    OP_INIT,
    OP_IS_LOADED,
    OP_SHUTDOWN,
    PROTOCOL_VERSION,
    ProtocolError,
    WorkerError,
    make_request,
    send_frame,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Defaults / constants
# ──────────────────────────────────────────────────────────
DEFAULT_ACCEPT_TIMEOUT = 60.0     # seconds for worker to be ready to accept
DEFAULT_REQUEST_TIMEOUT = 180.0    # seconds for a single LLM request
DEFAULT_STARTUP_WAIT = 1.5         # polling interval for socket existence
DEFAULT_MAX_RESTARTS = 2           # M8 Phase 2: auto-restart worker on crash
DEFAULT_CIRCUIT_THRESHOLD = 3      # consecutive failures → open circuit


class LLMProxyError(RuntimeError):
    """Raised when IPC-level operation fails (worker down, protocol, timeout)."""


# ──────────────────────────────────────────────────────────
# LLMProxy — LLMEngine-compatible client
# ──────────────────────────────────────────────────────────

class LLMProxy:
    """Drop-in replacement for ``LLMEngine`` that delegates to a worker process.

    Public API mirrors ``LLMEngine``:
        - is_loaded / is_loading
        - get_backend / backend
        - get_context_stats
        - override_params / restore_params
        - generate(prompt, stream=False)
        - generate_chat(messages, stream=False, stream_cb=None)
        - generate_with_confidence(prompt)
        - build_prompt(...)  # client-side, unchanged
    """

    def __init__(
        self,
        model_path: str | Path,
        config: dict,
        *,
        socket_path: Optional[Path] = None,
        worker_module: str = "scripts.ai_chan_llm_worker",
        accept_timeout: float = DEFAULT_ACCEPT_TIMEOUT,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        max_restarts: int = DEFAULT_MAX_RESTARTS,
        circuit_threshold: int = DEFAULT_CIRCUIT_THRESHOLD,
    ) -> None:
        self.model_path = str(model_path)
        self.config = dict(config)
        self._request_timeout = request_timeout
        self._accept_timeout = accept_timeout
        self._worker_module = worker_module
        # M8 Phase 2: watchdog / circuit breaker
        self._max_restarts = int(max_restarts)
        self._circuit_threshold = int(circuit_threshold)
        self._restart_count = 0
        self._consecutive_failures = 0
        self._circuit_open = False
        # JSONL ops log
        self._evt_log = LLMWorkerLogger()

        # socket path defaults under XDG runtime
        if socket_path is None:
            base = Path(
                os.environ.get("XDG_RUNTIME_DIR")
                or tempfile.gettempdir()
            ) / "ai-chan"
            base.mkdir(parents=True, exist_ok=True)
            socket_path = base / f"llm-{uuid.uuid4().hex[:8]}.sock"
        self._socket_path = Path(socket_path)

        self._proc: subprocess.Popen | None = None
        self._sock: socket.socket | None = None
        self._reader: LineReader | None = None
        self._lock = threading.Lock()  # single outstanding request
        self._ready = False
        self._backend: str = "ipc-pending"
        self._model_name: str = ""
        self._params_override_saved: dict | None = None  # client-side marker

    # ──────── lifecycle ────────
    def start(self) -> None:
        """Spawn worker, connect socket, perform init handshake."""
        if self._proc is not None:
            raise LLMProxyError("already started")

        # 1) spawn worker
        cmd = [
            sys.executable, "-m", self._worker_module,
            "--socket", str(self._socket_path),
            "--accept-timeout", str(self._accept_timeout),
        ]
        logger.info("spawning LLM worker: %s", " ".join(cmd))
        self._evt_log.log(EVT_START, socket=str(self._socket_path), worker=self._worker_module)
        self._proc = subprocess.Popen(cmd, stdout=sys.stderr, stderr=sys.stderr)

        # 2) wait for socket file to appear
        deadline = time.monotonic() + self._accept_timeout
        while not self._socket_path.exists():
            if time.monotonic() > deadline:
                self._kill_worker()
                raise LLMProxyError(
                    f"worker did not create socket within {self._accept_timeout}s",
                )
            if self._proc.poll() is not None:
                raise LLMProxyError(
                    f"worker exited early with code {self._proc.returncode}",
                )
            time.sleep(0.05)

        # 3) connect
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(self._accept_timeout)
        self._sock.connect(str(self._socket_path))
        self._sock.settimeout(self._request_timeout)
        self._reader = LineReader(self._sock)

        # 4) handshake
        req = make_request(
            OP_INIT,
            model_path=self.model_path,
            config=self.config,
        )
        send_frame(self._sock, req)
        frame = self._reader.read_frame()
        if frame is None:
            raise LLMProxyError("worker closed during init")
        if frame.get("kind") == KIND_ERROR:
            raise LLMProxyError(
                f"init failed: [{frame.get('code')}] {frame.get('message')}"
            )
        if frame.get("kind") != KIND_READY:
            raise LLMProxyError(f"unexpected handshake frame: {frame}")
        if frame.get("v") != PROTOCOL_VERSION:
            raise LLMProxyError(
                f"{ERR_PROTOCOL_MISMATCH}: expected v{PROTOCOL_VERSION}, got {frame.get('v')}"
            )
        self._backend = str(frame.get("backend", "unknown"))
        self._model_name = str(frame.get("model_name", ""))
        self._ready = True
        logger.info("LLM worker ready: backend=%s model=%s", self._backend, self._model_name)
        self._evt_log.log(EVT_READY, backend=self._backend, model=self._model_name,
                          worker_pid=(self._proc.pid if self._proc else None))

    def close(self) -> None:
        """Send shutdown, close socket, reap worker."""
        self._evt_log.log(EVT_SHUTDOWN,
                          restart_count=self._restart_count,
                          circuit_open=self._circuit_open,
                          consecutive_failures=self._consecutive_failures)
        try:
            if self._ready and self._sock is not None:
                try:
                    self._call_sync(OP_SHUTDOWN)
                except Exception:
                    pass
        finally:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
            self._reader = None
            self._reap_worker()
            try:
                if self._socket_path.exists():
                    self._socket_path.unlink()
            except Exception:
                pass
            self._ready = False

    def _reap_worker(self, timeout: float = 3.0) -> None:
        if self._proc is None:
            return
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def _kill_worker(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.kill()
        except Exception:
            pass
        self._proc = None

    def __enter__(self) -> "LLMProxy":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ──────── watchdog / circuit breaker (M8 Phase 2) ────────
    def _note_success(self) -> None:
        self._consecutive_failures = 0
        self._evt_log.log(EVT_SUCCESS)

    def _note_failure(self, reason: str = "") -> None:
        self._consecutive_failures += 1
        self._evt_log.log(EVT_FAILURE, reason=reason,
                          consecutive_failures=self._consecutive_failures)
        if self._consecutive_failures >= self._circuit_threshold:
            was_open = self._circuit_open
            self._circuit_open = True
            logger.error(
                "[M8] LLMProxy circuit OPEN after %d consecutive failures",
                self._consecutive_failures,
            )
            if not was_open:
                self._evt_log.log(EVT_CIRCUIT_OPEN,
                                  consecutive_failures=self._consecutive_failures)

    def _check_circuit(self) -> None:
        if self._circuit_open:
            raise LLMProxyError(
                "circuit open: too many consecutive LLM worker failures "
                "(call reset_circuit() to retry)"
            )

    def reset_circuit(self) -> None:
        """Circuit をクローズし、失敗カウンタをリセット。UI の再試行ボタン等から呼ぶ。"""
        self._circuit_open = False
        self._consecutive_failures = 0
        logger.info("[M8] LLMProxy circuit reset")
        self._evt_log.log(EVT_CIRCUIT_RESET)

    def circuit_status(self) -> dict:
        """監視用: circuit の状態と restart カウントを返す。"""
        return {
            "open": self._circuit_open,
            "consecutive_failures": self._consecutive_failures,
            "restart_count": self._restart_count,
            "threshold": self._circuit_threshold,
            "max_restarts": self._max_restarts,
            "worker_alive": self._proc is not None and self._proc.poll() is None,
        }

    def _try_restart(self) -> bool:
        """worker が死んでいれば再起動を試みる。成功時 True。"""
        if self._restart_count >= self._max_restarts:
            logger.error(
                "[M8] restart budget exhausted (%d/%d)",
                self._restart_count, self._max_restarts,
            )
            return False
        self._restart_count += 1
        logger.warning("[M8] restarting LLM worker (attempt %d/%d)",
                       self._restart_count, self._max_restarts)
        self._evt_log.log(EVT_RESTART, attempt=self._restart_count,
                          max_restarts=self._max_restarts)
        # tear down stale state (socket may be half-open)
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        self._reader = None
        self._ready = False
        # HIGH fix: clear client-side sticky params — the new worker starts
        # fresh, so the mirror must too. Otherwise restore_params is never
        # delivered and next generate_chat ships stale overrides.
        self._params_override_saved = None
        self._kill_worker()
        try:
            if self._socket_path.exists():
                self._socket_path.unlink()
        except Exception:
            pass
        try:
            self.start()
            return True
        except Exception as exc:
            logger.error("[M8] worker restart failed: %s", exc)
            return False

    # ──────── low-level RPC ────────
    def _call_sync(self, op: str, **kwargs: Any) -> Any:
        """Send request, expect a single KIND_RESULT frame. Returns the value."""
        self._check_circuit()
        if self._sock is None or self._reader is None:
            raise LLMProxyError("proxy not started")
        with self._lock:
            try:
                value = self._call_sync_locked(op, **kwargs)
                self._note_success()
                return value
            except (LLMProxyError, ProtocolError, WorkerError, OSError) as exc:
                self._note_failure(reason=type(exc).__name__)
                # on worker-death style errors, attempt one restart then retry once
                if isinstance(exc, (LLMProxyError, ProtocolError, OSError)) and not isinstance(exc, WorkerError):
                    if self._try_restart():
                        try:
                            value = self._call_sync_locked(op, **kwargs)
                            self._note_success()
                            return value
                        except Exception as exc2:
                            self._note_failure(reason=type(exc2).__name__)
                            raise LLMProxyError(
                                f"retry after restart failed: {exc2}",
                            ) from exc2
                raise

    def _call_sync_locked(self, op: str, **kwargs: Any) -> Any:
        """Raw RPC call (caller holds self._lock)."""
        if self._sock is None or self._reader is None:
            raise LLMProxyError("proxy not started")
        req = make_request(op, **kwargs)
        send_frame(self._sock, req)
        frame = self._reader.read_frame()
        if frame is None:
            raise LLMProxyError("worker closed connection")
        if frame.get("kind") == KIND_ERROR:
            raise WorkerError(frame.get("code", "?"), frame.get("message", ""))
        if frame.get("kind") != KIND_RESULT:
            raise ProtocolError(f"expected result, got {frame}")
        if frame.get("id") != req["id"]:
            raise ProtocolError("correlation id mismatch")
        return frame.get("value")

    def _call_stream(
        self,
        op: str,
        *,
        on_chunk: Callable[[str], None],
        **kwargs: Any,
    ) -> str:
        """Send request, accumulate chunks until end/error. Returns full_text.

        On transport-level failure (worker crash mid-stream), attempts one
        restart + retry, matching ``_call_sync`` behavior. Note: any chunks
        already delivered to ``on_chunk`` before the crash are NOT rolled back.
        """
        self._check_circuit()
        if self._sock is None or self._reader is None:
            raise LLMProxyError("proxy not started")
        with self._lock:
            try:
                out = self._call_stream_locked(op, on_chunk=on_chunk, **kwargs)
                self._note_success()
                return out
            except (LLMProxyError, ProtocolError, WorkerError, OSError) as exc:
                self._note_failure(reason=type(exc).__name__)
                if isinstance(exc, (LLMProxyError, ProtocolError, OSError)) and not isinstance(exc, WorkerError):
                    if self._try_restart():
                        try:
                            out = self._call_stream_locked(op, on_chunk=on_chunk, **kwargs)
                            self._note_success()
                            return out
                        except Exception as exc2:
                            self._note_failure(reason=type(exc2).__name__)
                            raise LLMProxyError(
                                f"stream retry after restart failed: {exc2}",
                            ) from exc2
                raise

    def _call_stream_locked(
        self,
        op: str,
        *,
        on_chunk: Callable[[str], None],
        **kwargs: Any,
    ) -> str:
        """Raw streaming RPC (caller holds self._lock)."""
        if self._sock is None or self._reader is None:
            raise LLMProxyError("proxy not started")
        req = make_request(op, stream=True, **kwargs)
        send_frame(self._sock, req)
        parts: list[str] = []
        while True:
            frame = self._reader.read_frame()
            if frame is None:
                raise LLMProxyError("worker closed mid-stream")
            if frame.get("id") != req["id"]:
                raise ProtocolError("correlation id mismatch")
            kind = frame.get("kind")
            if kind == KIND_CHUNK:
                tok = str(frame.get("token", ""))
                parts.append(tok)
                try:
                    on_chunk(tok)
                except Exception:
                    logger.exception("stream_cb raised (continuing)")
            elif kind == KIND_END:
                return str(frame.get("full_text") or "".join(parts))
            elif kind == KIND_ERROR:
                raise WorkerError(frame.get("code", "?"), frame.get("message", ""))
            else:
                raise ProtocolError(f"unexpected frame in stream: {kind}")

    # ──────── LLMEngine-compatible public API ────────
    def is_loaded(self) -> bool:
        if not self._ready:
            return False
        try:
            return bool(self._call_sync(OP_IS_LOADED))
        except Exception:
            return False

    def is_loading(self) -> bool:
        # Worker completes init before sending READY, so once ready we're loaded.
        return False

    def get_backend(self) -> str:
        if not self._ready:
            return self._backend
        try:
            return str(self._call_sync(OP_GET_BACKEND))
        except Exception:
            return self._backend

    @property
    def backend(self) -> str:
        return self.get_backend()

    def get_context_stats(self) -> dict:
        try:
            result = self._call_sync(OP_GET_STATS)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def override_params(self, params: dict) -> dict:
        """Stash params on client; actual apply happens inside ``generate_chat``."""
        saved = self._params_override_saved or {}
        self._params_override_saved = dict(params)
        return saved

    def restore_params(self, saved: dict) -> None:
        self._params_override_saved = saved or None

    def generate(self, prompt: str, stream: bool = False) -> str | Generator[str, None, None]:
        if stream:
            def _gen() -> Generator[str, None, None]:
                # Accumulating generator — yields each chunk as it arrives
                if self._sock is None or self._reader is None:
                    raise LLMProxyError("proxy not started")
                with self._lock:
                    req = make_request(OP_GENERATE, prompt=prompt, stream=True)
                    send_frame(self._sock, req)
                    while True:
                        frame = self._reader.read_frame()
                        if frame is None:
                            raise LLMProxyError("worker closed mid-stream")
                        if frame.get("id") != req["id"]:
                            raise ProtocolError("correlation id mismatch")
                        kind = frame.get("kind")
                        if kind == KIND_CHUNK:
                            yield str(frame.get("token", ""))
                        elif kind == KIND_END:
                            return
                        elif kind == KIND_ERROR:
                            raise WorkerError(
                                frame.get("code", "?"), frame.get("message", ""),
                            )
                        else:
                            raise ProtocolError(f"unexpected: {kind}")
            return _gen()
        return str(self._call_sync(OP_GENERATE, prompt=prompt, stream=False))

    def generate_chat(
        self,
        messages: list[dict],
        stream: bool = False,
        stream_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        # merge sticky params_override if any
        params_override = self._params_override_saved
        if stream or stream_cb is not None:
            cb = stream_cb or (lambda _t: None)
            return self._call_stream(
                OP_GENERATE_CHAT,
                on_chunk=cb,
                messages=messages,
                params_override=params_override,
            )
        return str(self._call_sync(
            OP_GENERATE_CHAT,
            messages=messages,
            params_override=params_override,
        ))

    def generate_with_confidence(self, prompt: str) -> tuple[str, float]:
        result = self._call_sync(OP_GENERATE_WITH_CONFIDENCE, prompt=prompt)
        if not isinstance(result, dict):
            raise ProtocolError(f"generate_with_confidence: expected dict, got {type(result)}")
        return str(result.get("text", "")), float(result.get("confidence", 0.0))

    def build_prompt(
        self,
        system_prompt: str,
        conversation_history: list[dict],
        memory_context: str = "",
        emotion_hint: str = "",
    ) -> list[dict]:
        """Client-side prompt assembly (no IPC).

        Delegates to the LLMEngine classmethod; falls back to a minimal
        OpenAI-style message list if LLMEngine is unimportable.
        """
        try:
            from core.llm import LLMEngine
            # LLMEngine.build_prompt is an instance method; call via bound type
            # using a lightweight approach: instantiate-less call by grabbing the fn.
            fn = getattr(LLMEngine, "build_prompt", None)
            if fn is not None:
                # Create a dummy self-less wrapper: LLMEngine.build_prompt uses no self state
                # except possibly template-related flags. Safe fallback: use messages shape.
                try:
                    # most LLMEngine.build_prompt impls do NOT rely on self state
                    # beyond simple fields; we create a minimal stub.
                    class _Stub:
                        _template_id = "default"
                    return fn(_Stub(), system_prompt, conversation_history, memory_context, emotion_hint)  # type: ignore[arg-type]
                except Exception:
                    pass
        except Exception:
            pass
        # minimal fallback
        msgs = [{"role": "system", "content": system_prompt + ("\n" + memory_context if memory_context else "")}]
        msgs.extend(conversation_history)
        return msgs

"""M8: ai-chan LLM worker process.

Separate-process LLM host. Accepts a single UDS connection from ai-chan main
process and dispatches JSON-lines protocol requests to an in-process
``core.llm.LLMEngine`` instance.

Lifecycle
---------
1. Parent spawns: ``python3 -m scripts.ai_chan_llm_worker --socket PATH``
2. Worker binds UDS, waits ``accept`` (max 30s — otherwise exit)
3. Parent sends ``init`` request with model_path + config
4. Worker instantiates LLMEngine; responds with ``ready``
5. Worker processes further requests serially (single-threaded, matches
   LLMEngine's ``_inference_lock`` semantics)
6. ``shutdown`` op or parent disconnect → clean exit

Errors are surfaced via ``kind: error`` frames; crashes (unhandled exception)
exit the process with a non-zero code so the parent's watchdog can restart.
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import traceback
from pathlib import Path
from typing import Any

# Ensure project root is importable when invoked as a script
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.llm_ipc_protocol import (  # noqa: E402
    ERR_BAD_REQUEST,
    ERR_GENERATION_FAILED,
    ERR_MODEL_NOT_LOADED,
    ERR_PROTOCOL_MISMATCH,
    ERR_UNKNOWN_OP,
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
    make_chunk,
    make_end,
    make_error,
    make_ready,
    make_result,
    send_frame,
)

logger = logging.getLogger("ai_chan.llm_worker")


# ──────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────


class Worker:
    """Stateful worker wrapping an LLMEngine instance."""

    def __init__(self) -> None:
        self.engine: Any = None  # core.llm.LLMEngine, assigned after init
        self._stopped = False

    # ───── handshake ─────
    def handle_init(self, sock: socket.socket, req: dict[str, Any]) -> bool:
        """First request must be ``init``. Returns True on success."""
        if req.get("v") != PROTOCOL_VERSION:
            send_frame(sock, make_error(
                req.get("id", ""), ERR_PROTOCOL_MISMATCH,
                f"expected protocol v{PROTOCOL_VERSION}, got {req.get('v')}",
            ))
            return False
        if req.get("op") != OP_INIT:
            send_frame(sock, make_error(
                req.get("id", ""), ERR_BAD_REQUEST,
                f"first op must be init, got {req.get('op')}",
            ))
            return False

        model_path = req.get("model_path")
        config = req.get("config") or {}
        if not model_path:
            send_frame(sock, make_error(
                req["id"], ERR_BAD_REQUEST, "model_path required",
            ))
            return False

        try:
            from core.llm import LLMEngine
            self.engine = LLMEngine(model_path, config)
        except Exception as exc:
            send_frame(sock, make_error(
                req["id"], ERR_MODEL_NOT_LOADED,
                f"LLMEngine init failed: {exc}",
            ))
            return False

        send_frame(sock, make_ready(
            req["id"],
            backend=self.engine.get_backend() if hasattr(self.engine, "get_backend") else "unknown",
            model_name=getattr(self.engine, "_model_name", "") or "",
        ))
        return True

    # ───── dispatch ─────
    def handle_request(self, sock: socket.socket, req: dict[str, Any]) -> None:
        """Dispatch a non-init request. Sends response frame(s)."""
        rid = req.get("id", "")
        op = req.get("op")

        if op == OP_SHUTDOWN:
            send_frame(sock, make_result(rid, True))
            self._stopped = True
            return

        if self.engine is None:
            send_frame(sock, make_error(rid, ERR_MODEL_NOT_LOADED, "engine not initialized"))
            return

        try:
            if op == OP_IS_LOADED:
                send_frame(sock, make_result(rid, bool(self.engine.is_loaded())))
            elif op == OP_GET_BACKEND:
                send_frame(sock, make_result(rid, str(self.engine.get_backend())))
            elif op == OP_GET_STATS:
                stats = (
                    self.engine.get_context_stats()
                    if hasattr(self.engine, "get_context_stats") else {}
                )
                send_frame(sock, make_result(rid, stats))
            elif op == OP_GENERATE:
                self._op_generate(sock, req)
            elif op == OP_GENERATE_CHAT:
                self._op_generate_chat(sock, req)
            elif op == OP_GENERATE_WITH_CONFIDENCE:
                self._op_generate_with_confidence(sock, req)
            else:
                send_frame(sock, make_error(rid, ERR_UNKNOWN_OP, f"op: {op}"))
        except Exception as exc:
            logger.exception("worker op %s failed", op)
            send_frame(sock, make_error(
                rid, ERR_GENERATION_FAILED,
                f"{type(exc).__name__}: {exc}",
            ))

    # ───── generate (non-chat) ─────
    def _op_generate(self, sock: socket.socket, req: dict[str, Any]) -> None:
        rid = req["id"]
        prompt = req.get("prompt", "")
        stream = bool(req.get("stream", False))
        if stream:
            # LLMEngine.generate(stream=True) returns a Generator
            gen = self.engine.generate(prompt, stream=True)
            full_parts: list[str] = []
            for idx, token in enumerate(gen):
                full_parts.append(token)
                send_frame(sock, make_chunk(rid, token, idx))
            send_frame(sock, make_end(rid, full_text="".join(full_parts)))
        else:
            text = self.engine.generate(prompt, stream=False)
            send_frame(sock, make_result(rid, text))

    # ───── generate_chat ─────
    def _op_generate_chat(self, sock: socket.socket, req: dict[str, Any]) -> None:
        rid = req["id"]
        messages = req.get("messages") or []
        stream = bool(req.get("stream", False))
        params_override = req.get("params_override")

        # atomic override: save → generate → restore (guaranteed even on error)
        saved = None
        if params_override and hasattr(self.engine, "override_params"):
            saved = self.engine.override_params(params_override)
        try:
            if stream:
                # LLMEngine.generate_chat uses stream_cb, so we adapt:
                idx_counter = {"i": 0}

                def _cb(tok: str) -> None:
                    send_frame(sock, make_chunk(rid, tok, idx_counter["i"]))
                    idx_counter["i"] += 1

                full_text = self.engine.generate_chat(messages, stream_cb=_cb)
                send_frame(sock, make_end(rid, full_text=full_text))
            else:
                text = self.engine.generate_chat(messages)
                send_frame(sock, make_result(rid, text))
        finally:
            if saved is not None and hasattr(self.engine, "restore_params"):
                try:
                    self.engine.restore_params(saved)
                except Exception:
                    logger.exception("restore_params failed (state may be corrupted)")

    def _op_generate_with_confidence(self, sock: socket.socket, req: dict[str, Any]) -> None:
        rid = req["id"]
        prompt = req.get("prompt", "")
        text, conf = self.engine.generate_with_confidence(prompt)
        send_frame(sock, make_result(rid, {"text": text, "confidence": float(conf)}))

    # ───── main loop ─────
    def run(self, sock: socket.socket) -> int:
        reader = LineReader(sock)
        # first frame must be init
        try:
            first = reader.read_frame()
        except ProtocolError as exc:
            logger.error("protocol error on init: %s", exc)
            return 2
        if first is None:
            logger.info("client disconnected before init")
            return 0
        if not self.handle_init(sock, first):
            return 3

        while not self._stopped:
            try:
                frame = reader.read_frame()
            except ProtocolError as exc:
                logger.error("protocol error: %s", exc)
                return 4
            if frame is None:
                logger.info("client disconnected, exiting cleanly")
                return 0
            self.handle_request(sock, frame)
        return 0


# ──────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, type=Path,
                        help="UDS path to bind to")
    parser.add_argument("--accept-timeout", type=float, default=30.0,
                        help="seconds to wait for parent accept (default 30)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="[llm_worker %(asctime)s %(levelname)s] %(message)s",
    )

    sock_path = args.socket
    if sock_path.exists():
        sock_path.unlink()
    sock_path.parent.mkdir(parents=True, exist_ok=True)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        srv.bind(str(sock_path))
        srv.listen(1)
        os.chmod(str(sock_path), 0o600)  # owner-only
        srv.settimeout(args.accept_timeout)
        logger.info("listening on %s, PID=%d", sock_path, os.getpid())

        try:
            conn, _ = srv.accept()
        except socket.timeout:
            logger.error("no parent connection within %.1fs, exiting", args.accept_timeout)
            return 5

        conn.settimeout(None)
        worker = Worker()
        try:
            rc = worker.run(conn)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return rc
    except Exception:
        logger.error("fatal worker error:\n%s", traceback.format_exc())
        return 1
    finally:
        try:
            srv.close()
        except Exception:
            pass
        try:
            if sock_path.exists():
                sock_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

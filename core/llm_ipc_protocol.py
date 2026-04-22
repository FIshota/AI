"""M8: LLM IPC Protocol — JSON-lines over Unix Domain Socket.

プロトコル定義とエンコード/デコードユーティリティ。

Wire format:
    1 フレーム = 1 行 = UTF-8 encoded JSON object + b'\\n'

Frame types:
    Request:   {"id": <uuid>, "op": <op>, ...args}
    Response:  {"id": <uuid>, "kind": "result" | "chunk" | "end" | "error" | "ready", ...}

Operations (client → worker):
    init                      - handshake; {"config": {...}, "model_path": "..."}
    is_loaded                 - {}
    get_backend               - {}
    get_stats                 - {}
    generate                  - {"prompt": str, "stream": bool}
    generate_chat             - {"messages": [...], "stream": bool, "params_override": {...}|null}
    generate_with_confidence  - {"prompt": str}
    shutdown                  - {}

Protocol version: 1
"""
from __future__ import annotations

import json
import socket
import uuid
from dataclasses import dataclass
from typing import Any, Iterator


PROTOCOL_VERSION = 1

# Request ops
OP_INIT = "init"
OP_IS_LOADED = "is_loaded"
OP_GET_BACKEND = "get_backend"
OP_GET_STATS = "get_stats"
OP_GENERATE = "generate"
OP_GENERATE_CHAT = "generate_chat"
OP_GENERATE_WITH_CONFIDENCE = "generate_with_confidence"
OP_SHUTDOWN = "shutdown"

VALID_OPS = frozenset({
    OP_INIT, OP_IS_LOADED, OP_GET_BACKEND, OP_GET_STATS,
    OP_GENERATE, OP_GENERATE_CHAT, OP_GENERATE_WITH_CONFIDENCE, OP_SHUTDOWN,
})

# Response kinds
KIND_READY = "ready"
KIND_RESULT = "result"
KIND_CHUNK = "chunk"
KIND_END = "end"
KIND_ERROR = "error"

# Error codes
ERR_UNKNOWN_OP = "unknown_op"
ERR_BAD_REQUEST = "bad_request"
ERR_WORKER_CRASH = "worker_crash"
ERR_PROTOCOL_MISMATCH = "protocol_mismatch"
ERR_MODEL_NOT_LOADED = "model_not_loaded"
ERR_GENERATION_FAILED = "generation_failed"

# Limits
MAX_FRAME_BYTES = 8 * 1024 * 1024  # 8 MB per frame (generous for large prompts)


class ProtocolError(RuntimeError):
    """Wire format / protocol violation."""


class WorkerError(RuntimeError):
    """Remote worker returned an error frame."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


# ──────────────────────────────────────────────────────────
# Frame encode / decode
# ──────────────────────────────────────────────────────────

def encode_frame(obj: dict[str, Any]) -> bytes:
    """dict をワイヤーフォーマット (JSON + b'\\n') にエンコードする。"""
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) + 1 > MAX_FRAME_BYTES:
        raise ProtocolError(f"frame exceeds MAX_FRAME_BYTES: {len(data)}")
    return data + b"\n"


def decode_frame(line: bytes) -> dict[str, Any]:
    """1 行ぶんの bytes を dict にデコードする。"""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError(f"frame must be object, got {type(obj).__name__}")
    return obj


# ──────────────────────────────────────────────────────────
# Request / response constructors
# ──────────────────────────────────────────────────────────

def new_request_id() -> str:
    """UUID4 (hex, 32 文字) を返す。"""
    return uuid.uuid4().hex


def make_request(op: str, **kwargs: Any) -> dict[str, Any]:
    if op not in VALID_OPS:
        raise ProtocolError(f"unknown op: {op}")
    req = {"id": new_request_id(), "op": op, "v": PROTOCOL_VERSION}
    req.update(kwargs)
    return req


def make_ready(request_id: str, *, backend: str, model_name: str) -> dict[str, Any]:
    return {
        "id": request_id, "kind": KIND_READY, "v": PROTOCOL_VERSION,
        "backend": backend, "model_name": model_name,
    }


def make_result(request_id: str, value: Any) -> dict[str, Any]:
    return {"id": request_id, "kind": KIND_RESULT, "value": value}


def make_chunk(request_id: str, token: str, idx: int) -> dict[str, Any]:
    return {"id": request_id, "kind": KIND_CHUNK, "token": token, "idx": idx}


def make_end(request_id: str, *, full_text: str, usage: dict | None = None) -> dict[str, Any]:
    frame: dict[str, Any] = {"id": request_id, "kind": KIND_END, "full_text": full_text}
    if usage is not None:
        frame["usage"] = usage
    return frame


def make_error(request_id: str, code: str, message: str) -> dict[str, Any]:
    return {"id": request_id, "kind": KIND_ERROR, "code": code, "message": message}


# ──────────────────────────────────────────────────────────
# Line-buffered socket reader
# ──────────────────────────────────────────────────────────

@dataclass
class LineReader:
    """socket.recv のバッファを保持し、行単位で frame を取り出す。

    `sock` は SOCK_STREAM で接続済みであること。
    """
    sock: socket.socket
    _buf: bytes = b""
    _chunk_size: int = 4096

    def read_frame(self) -> dict[str, Any] | None:
        """次の 1 frame を返す。peer が閉じた場合は None を返す。"""
        while b"\n" not in self._buf:
            data = self.sock.recv(self._chunk_size)
            if not data:
                if self._buf:
                    raise ProtocolError("socket closed mid-frame")
                return None
            self._buf += data
            if len(self._buf) > MAX_FRAME_BYTES:
                raise ProtocolError(f"incoming frame > MAX_FRAME_BYTES")
        line, self._buf = self._buf.split(b"\n", 1)
        return decode_frame(line)

    def iter_frames(self) -> Iterator[dict[str, Any]]:
        while True:
            frame = self.read_frame()
            if frame is None:
                return
            yield frame


def send_frame(sock: socket.socket, frame: dict[str, Any]) -> None:
    """1 frame を socket に書き出す (全バイト送信保証)。"""
    sock.sendall(encode_frame(frame))

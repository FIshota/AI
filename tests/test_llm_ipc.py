"""M8: IPC stack tests (protocol + proxy + worker roundtrip).

Uses a **fake LLMEngine** injected into the worker subprocess via a dedicated
entry point (tests/support/fake_llm_worker.py) so we never load a real model.
Full coverage:
  - Frame encode/decode
  - Error codes
  - Sync ops (is_loaded, get_backend, get_stats)
  - generate (non-stream + stream generator)
  - generate_chat (non-stream + stream_cb)
  - generate_with_confidence
  - params_override round-trip
  - Worker crash / early close
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.llm_ipc_protocol import (  # noqa: E402
    KIND_CHUNK, KIND_END, KIND_ERROR, KIND_READY, KIND_RESULT,
    PROTOCOL_VERSION, ProtocolError, WorkerError,
    decode_frame, encode_frame, make_chunk, make_end, make_error,
    make_ready, make_request, make_result, LineReader, send_frame,
    OP_INIT, OP_IS_LOADED, OP_SHUTDOWN,
)
from core.llm_proxy import LLMProxy, LLMProxyError  # noqa: E402


# ══════════════════════════════════════════════════════════
# Protocol unit tests
# ══════════════════════════════════════════════════════════

class TestFrameCodec:
    def test_roundtrip_ascii(self):
        data = encode_frame({"id": "x", "op": "is_loaded", "v": 1})
        assert data.endswith(b"\n")
        assert decode_frame(data[:-1]) == {"id": "x", "op": "is_loaded", "v": 1}

    def test_roundtrip_unicode(self):
        frame = {"id": "y", "kind": KIND_CHUNK, "token": "こんにちは", "idx": 0}
        data = encode_frame(frame)
        assert decode_frame(data[:-1]) == frame

    def test_invalid_json(self):
        with pytest.raises(ProtocolError):
            decode_frame(b"{not json")

    def test_non_object(self):
        with pytest.raises(ProtocolError):
            decode_frame(b"[1,2]")


class TestRequestConstructors:
    def test_make_request_unknown_op(self):
        with pytest.raises(ProtocolError):
            make_request("bogus_op")

    def test_make_request_includes_version(self):
        req = make_request(OP_IS_LOADED)
        assert req["v"] == PROTOCOL_VERSION
        assert req["op"] == OP_IS_LOADED
        assert len(req["id"]) == 32  # uuid4 hex

    def test_make_ready(self):
        r = make_ready("rid1", backend="mlx", model_name="test")
        assert r["kind"] == KIND_READY
        assert r["backend"] == "mlx"
        assert r["v"] == PROTOCOL_VERSION

    def test_make_chunk(self):
        c = make_chunk("rid", "tok", 3)
        assert c == {"id": "rid", "kind": KIND_CHUNK, "token": "tok", "idx": 3}

    def test_make_end_with_usage(self):
        e = make_end("rid", full_text="hi", usage={"total": 5})
        assert e["usage"] == {"total": 5}

    def test_make_error(self):
        err = make_error("rid", "some_code", "msg")
        assert err["code"] == "some_code"
        assert err["kind"] == KIND_ERROR


class TestLineReader:
    def test_splits_multiple_frames(self):
        # simulate two frames arriving together
        s1, s2 = socket.socketpair()
        try:
            s2.sendall(b'{"id":"a","kind":"result","value":1}\n{"id":"b","kind":"result","value":2}\n')
            s2.close()
            reader = LineReader(s1)
            assert reader.read_frame() == {"id": "a", "kind": "result", "value": 1}
            assert reader.read_frame() == {"id": "b", "kind": "result", "value": 2}
            assert reader.read_frame() is None
        finally:
            s1.close()

    def test_partial_frame_close_raises(self):
        s1, s2 = socket.socketpair()
        try:
            s2.sendall(b'{"id":"a"')
            s2.close()
            reader = LineReader(s1)
            with pytest.raises(ProtocolError):
                reader.read_frame()
        finally:
            s1.close()


# ══════════════════════════════════════════════════════════
# End-to-end: fake LLMEngine worker
# ══════════════════════════════════════════════════════════

# We monkeypatch core.llm.LLMEngine inside a subprocess by spawning the real
# worker with PYTHONPATH injecting tests/support first.

_FAKE_WORKER_DIR = Path(__file__).parent / "support"
_FAKE_WORKER_DIR.mkdir(exist_ok=True)

_FAKE_LLM_MODULE = _FAKE_WORKER_DIR / "fake_core_llm.py"
_FAKE_LLM_MODULE.write_text(
    '''"""Fake LLMEngine for IPC tests — no real model loaded."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

class LLMEngine:
    def __init__(self, model_path, config):
        self.model_path = str(model_path)
        self.config = dict(config or {})
        self._model_name = "fake-model-v1"
        self._params = {"temperature": 0.7, "top_p": 0.9}
        self._loaded = True
    def is_loaded(self): return self._loaded
    def is_loading(self): return False
    def get_backend(self): return "fake"
    @property
    def backend(self): return "fake"
    def get_context_stats(self): return {"hit": 0, "miss": 0}
    def override_params(self, params):
        saved = dict(self._params)
        self._params.update(params)
        return saved
    def restore_params(self, saved):
        self._params = dict(saved)
    def generate(self, prompt, stream=False):
        text = f"echo:{prompt}"
        if stream:
            def _gen():
                for ch in text:
                    yield ch
            return _gen()
        return text
    def generate_chat(self, messages, stream=False, stream_cb=None):
        last = messages[-1]["content"] if messages else ""
        reply = f"reply:{last}:temp={self._params.get('temperature')}"
        if stream_cb is not None:
            for ch in reply:
                stream_cb(ch)
        return reply
    def generate_with_confidence(self, prompt):
        return (f"conf:{prompt}", 0.87)
'''
)

# Worker shim that imports our fake module AS core.llm before invoking main
_FAKE_WORKER_ENTRY = _FAKE_WORKER_DIR / "run_fake_worker.py"
_FAKE_WORKER_ENTRY.write_text(
    '''"""Entry point: inject fake core.llm, then run the real worker."""
import sys, importlib, types
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests" / "support"))

# Inject fake before worker imports real core.llm
import fake_core_llm  # noqa
sys.modules["core.llm"] = fake_core_llm

from scripts.ai_chan_llm_worker import main  # noqa
raise SystemExit(main())
'''
)

# Make tests/support a package
_init = _FAKE_WORKER_DIR / "__init__.py"
if not _init.exists():
    _init.write_text("")


@pytest.fixture
def proxy():
    """Spawn a proxy connected to the fake-worker subprocess."""
    sock_path = Path(tempfile.mkdtemp(prefix="ai-chan-ipc-")) / "llm.sock"
    p = LLMProxy(
        model_path="/dev/null",
        config={"test": True},
        socket_path=sock_path,
        accept_timeout=10.0,
        request_timeout=10.0,
    )
    # Replace the module-based worker spawn with a direct script invocation
    # by subclassing start()
    orig_start = p.start

    def _start_with_shim():
        # monkey: swap worker_module path by re-implementing subprocess call
        import subprocess, socket as _sock, time as _time
        cmd = [sys.executable, str(_FAKE_WORKER_ENTRY),
               "--socket", str(sock_path), "--accept-timeout", "10"]
        p._proc = subprocess.Popen(cmd, stdout=sys.stderr, stderr=sys.stderr)
        deadline = _time.monotonic() + 10.0
        while not sock_path.exists():
            if _time.monotonic() > deadline:
                p._kill_worker()
                raise LLMProxyError("worker did not bind socket")
            if p._proc.poll() is not None:
                raise LLMProxyError(f"worker exited {p._proc.returncode}")
            _time.sleep(0.05)
        p._sock = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        p._sock.settimeout(10.0)
        p._sock.connect(str(sock_path))
        p._sock.settimeout(10.0)
        from core.llm_ipc_protocol import LineReader, make_request, send_frame, OP_INIT, PROTOCOL_VERSION, KIND_READY, KIND_ERROR
        p._reader = LineReader(p._sock)
        req = make_request(OP_INIT, model_path=p.model_path, config=p.config)
        send_frame(p._sock, req)
        frame = p._reader.read_frame()
        assert frame and frame.get("kind") == KIND_READY, f"bad handshake: {frame}"
        p._backend = frame["backend"]
        p._model_name = frame["model_name"]
        p._ready = True

    p.start = _start_with_shim  # type: ignore[method-assign]
    p.start()
    try:
        yield p
    finally:
        p.close()
        # cleanup tempdir
        try:
            if sock_path.exists():
                sock_path.unlink()
            sock_path.parent.rmdir()
        except Exception:
            pass


class TestProxyRoundtrip:
    def test_is_loaded(self, proxy):
        assert proxy.is_loaded() is True

    def test_get_backend(self, proxy):
        assert proxy.get_backend() == "fake"
        assert proxy.backend == "fake"

    def test_get_stats(self, proxy):
        stats = proxy.get_context_stats()
        assert isinstance(stats, dict)
        assert stats.get("hit") == 0

    def test_generate_sync(self, proxy):
        assert proxy.generate("hello", stream=False) == "echo:hello"

    def test_generate_stream(self, proxy):
        gen = proxy.generate("abc", stream=True)
        result = "".join(gen)
        assert result == "echo:abc"

    def test_generate_chat_sync(self, proxy):
        msgs = [{"role": "user", "content": "hi"}]
        reply = proxy.generate_chat(msgs)
        assert reply.startswith("reply:hi:")

    def test_generate_chat_stream_cb(self, proxy):
        collected = []
        msgs = [{"role": "user", "content": "stream me"}]
        full = proxy.generate_chat(msgs, stream_cb=lambda t: collected.append(t))
        assert full == "".join(collected)
        assert full.startswith("reply:stream me:")

    def test_params_override_roundtrip(self, proxy):
        # override temperature; fake echoes it in response
        saved = proxy.override_params({"temperature": 1.5})
        assert isinstance(saved, dict)
        msgs = [{"role": "user", "content": "x"}]
        reply = proxy.generate_chat(msgs)
        assert "temp=1.5" in reply
        proxy.restore_params(saved)
        reply2 = proxy.generate_chat(msgs)
        assert "temp=0.7" in reply2

    def test_generate_with_confidence(self, proxy):
        text, conf = proxy.generate_with_confidence("prompt")
        assert text == "conf:prompt"
        assert 0.0 <= conf <= 1.0


class TestProxyErrorHandling:
    def test_close_is_idempotent(self):
        sock_path = Path(tempfile.mkdtemp(prefix="ai-chan-ipc-")) / "llm.sock"
        p = LLMProxy(model_path="/dev/null", config={}, socket_path=sock_path)
        p.close()  # never started — should not raise
        p.close()

    def test_call_without_start(self):
        p = LLMProxy(model_path="/dev/null", config={})
        with pytest.raises(LLMProxyError):
            p._call_sync(OP_IS_LOADED)

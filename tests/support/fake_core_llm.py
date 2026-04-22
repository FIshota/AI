"""Fake LLMEngine for IPC tests — no real model loaded."""
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

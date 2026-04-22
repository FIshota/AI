"""Fake LLMEngine that deliberately crashes on demand.

Driven by env var ``AICHAN_FAKE_CRASH_MODE``:
  - "exit_on_generate"  — os._exit(7) when generate_chat is called
  - "exit_on_nth:<n>"   — crash on the N-th call (1-indexed)
  - "" or unset         — behave normally
"""
from __future__ import annotations

import os
import sys


class LLMEngine:
    _call_count = 0

    def __init__(self, model_path, config):
        self.model_path = str(model_path)
        self.config = dict(config or {})
        self._model_name = "crash-model"
        self._params = {"temperature": 0.7}
        self._loaded = True

    def is_loaded(self): return self._loaded
    def is_loading(self): return False
    def get_backend(self): return "crash-fake"
    @property
    def backend(self): return "crash-fake"
    def get_context_stats(self): return {}
    def override_params(self, p):
        saved = dict(self._params)
        self._params.update(p)
        return saved
    def restore_params(self, s):
        self._params = dict(s)

    def _maybe_crash(self):
        LLMEngine._call_count += 1
        mode = os.environ.get("AICHAN_FAKE_CRASH_MODE", "")
        if mode == "exit_on_generate":
            sys.stderr.write(f"[crashing_fake] exiting on call #{LLMEngine._call_count}\n")
            sys.stderr.flush()
            os._exit(7)
        if mode.startswith("exit_on_nth:"):
            try:
                n = int(mode.split(":", 1)[1])
            except ValueError:
                n = 1
            if LLMEngine._call_count >= n:
                sys.stderr.write(f"[crashing_fake] exiting on call #{LLMEngine._call_count} (nth={n})\n")
                sys.stderr.flush()
                os._exit(7)

    def generate(self, prompt, stream=False):
        self._maybe_crash()
        return f"echo:{prompt}"

    def generate_chat(self, messages, stream=False, stream_cb=None):
        self._maybe_crash()
        last = messages[-1]["content"] if messages else ""
        return f"reply:{last}"

    def generate_with_confidence(self, prompt):
        self._maybe_crash()
        return (f"conf:{prompt}", 0.5)

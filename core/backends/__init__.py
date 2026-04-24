"""Concrete LLM backend implementations.

Each backend module should expose a single class matching the
:class:`core.llm_backend.LLMBackend` protocol and convert import / init
failures into :class:`core.llm_backend.BackendUnavailable`.
"""

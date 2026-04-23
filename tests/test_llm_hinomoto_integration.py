"""P1-4: LLMEngine <-> HinoMoto backend integration tests.

Uses heavy mocking to avoid loading real checkpoints. Verifies:
    1. hinomoto.enabled=false → existing MLX/llama path unchanged
    2. hinomoto.enabled=true & bridge loads → self._backend == "hinomoto"
    3. generate() routes to bridge.reply() when backend=hinomoto
    4. bridge load failure → graceful fallback (no crash)
    5. generate() bridge exception → _fallback_response
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def base_config():
    return {
        "model_file": "models/test.gguf",
        "max_tokens": 128,
        "temperature": 0.8,
        "top_p": 0.95,
    }


def _patch_llmengine_side_effects():
    """Apply a stack of patches that make LLMEngine safely constructible
    without touching real filesystem / model files."""
    return [
        patch("core.llm.check_model_policy", return_value=None),
        patch("core.llm._harden_llm_cache", return_value=None),
        # Neutralize inline MLX / MLXEngine / llama backends so
        # *no* fallback path actually loads anything.
        patch("core.llm._MLXEngine", None),
        patch("core.llm.MLX_AVAILABLE", False),
        patch("core.llm.LLAMA_AVAILABLE", False),
    ]


@pytest.fixture
def stubbed_env():
    patches = _patch_llmengine_side_effects()
    ctxs = [p.start() for p in patches]
    try:
        yield ctxs
    finally:
        for p in patches:
            p.stop()


def test_hinomoto_disabled_by_default(stubbed_env, base_config):
    """hinomoto.enabled 未指定 → 従来通り MLX/llama path (ここでは fallback)."""
    from core.llm import LLMEngine
    engine = LLMEngine("models/test.gguf", base_config)
    assert engine._backend in (None, "llama", "mlx")  # hinomoto は使われない
    assert engine._hinomoto_bridge is None


def test_hinomoto_enabled_loads_bridge(stubbed_env, base_config, tmp_path):
    """hinomoto.enabled=true & bridge が成功 → backend='hinomoto'."""
    ckpt = tmp_path / "ckpt.pt"
    tok = tmp_path / "tok.json"
    ckpt.write_bytes(b"stub")
    tok.write_text("{}")

    cfg = {**base_config, "hinomoto": {
        "enabled": True, "checkpoint": str(ckpt), "tokenizer": str(tok),
    }}

    fake_bridge = MagicMock()
    fake_bridge.is_available.return_value = True
    fake_bridge.reply.return_value = "ok"

    with patch("core.hinomoto_bridge.HinoMotoBridge",
               return_value=fake_bridge):
        from core.llm import LLMEngine
        engine = LLMEngine("models/test.gguf", cfg)

    assert engine._backend == "hinomoto"
    assert engine._hinomoto_bridge is fake_bridge
    assert engine._loaded is True


def test_hinomoto_generate_routes_to_bridge(stubbed_env, base_config, tmp_path):
    ckpt = tmp_path / "ckpt.pt"; ckpt.write_bytes(b"x")
    tok = tmp_path / "tok.json"; tok.write_text("{}")
    cfg = {**base_config, "hinomoto": {
        "enabled": True, "checkpoint": str(ckpt), "tokenizer": str(tok),
        "max_new_tokens": 16, "min_new_tokens": 3, "greedy": True,
    }}

    fake_bridge = MagicMock()
    fake_bridge.is_available.return_value = True
    fake_bridge.reply.return_value = "こんにちは、元気？"

    with patch("core.hinomoto_bridge.HinoMotoBridge", return_value=fake_bridge):
        from core.llm import LLMEngine
        engine = LLMEngine("models/test.gguf", cfg)
        reply = engine.generate("やあ")

    assert reply == "こんにちは、元気？"
    # warmup + actual call
    assert fake_bridge.reply.call_count >= 2
    last = fake_bridge.reply.call_args
    assert last.kwargs["max_new_tokens"] == 16
    assert last.kwargs["min_gen_chars"] == 3
    assert last.kwargs["greedy"] is True


def test_hinomoto_bridge_load_failure_falls_back(stubbed_env, base_config, tmp_path):
    """is_available=False → _loaded=False & backend!=hinomoto."""
    cfg = {**base_config, "hinomoto": {
        "enabled": True,
        "checkpoint": str(tmp_path / "missing.pt"),
        "tokenizer": str(tmp_path / "missing.json"),
    }}

    fake_bridge = MagicMock()
    fake_bridge.is_available.return_value = False  # load fails gracefully

    with patch("core.hinomoto_bridge.HinoMotoBridge", return_value=fake_bridge):
        from core.llm import LLMEngine
        engine = LLMEngine("models/test.gguf", cfg)

    assert engine._backend != "hinomoto"
    assert engine._hinomoto_bridge is None


def test_hinomoto_generate_exception_returns_fallback(stubbed_env, base_config, tmp_path):
    ckpt = tmp_path / "ckpt.pt"; ckpt.write_bytes(b"x")
    tok = tmp_path / "tok.json"; tok.write_text("{}")
    cfg = {**base_config, "hinomoto": {
        "enabled": True, "checkpoint": str(ckpt), "tokenizer": str(tok),
    }}

    fake_bridge = MagicMock()
    fake_bridge.is_available.return_value = True
    # warmup 成功, 本番 generate で例外
    fake_bridge.reply.side_effect = ["warmup_ok", RuntimeError("boom")]

    with patch("core.hinomoto_bridge.HinoMotoBridge", return_value=fake_bridge):
        from core.llm import LLMEngine
        engine = LLMEngine("models/test.gguf", cfg)
        reply = engine.generate("やあ")

    # _fallback_response() の戻り値はプロジェクト依存だが str でなければおかしい
    assert isinstance(reply, str)
    assert reply  # non-empty


def test_hinomoto_chat_extracts_last_user_message(stubbed_env, base_config, tmp_path):
    ckpt = tmp_path / "ckpt.pt"; ckpt.write_bytes(b"x")
    tok = tmp_path / "tok.json"; tok.write_text("{}")
    cfg = {**base_config, "hinomoto": {
        "enabled": True, "checkpoint": str(ckpt), "tokenizer": str(tok),
    }}

    fake_bridge = MagicMock()
    fake_bridge.is_available.return_value = True
    fake_bridge.reply.return_value = "回答"

    with patch("core.hinomoto_bridge.HinoMotoBridge", return_value=fake_bridge):
        from core.llm import LLMEngine
        engine = LLMEngine("models/test.gguf", cfg)
        out = engine.generate_chat([
            {"role": "system", "content": "あなたは家族です"},
            {"role": "user", "content": "最初の質問"},
            {"role": "assistant", "content": "応答1"},
            {"role": "user", "content": "最後の質問"},
        ])

    assert out == "回答"
    # 最後の user content が prompt として渡される
    last_call_prompt = fake_bridge.reply.call_args_list[-1].args[0]
    assert last_call_prompt == "最後の質問"

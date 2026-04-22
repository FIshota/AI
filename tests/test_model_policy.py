"""Model Policy (docs/MODEL_POLICY.md) enforcement tests.

方針: core/llm.py の `check_model_policy` が禁止リスト (中国系ベンダー) を
正しく検知し、opt-in (`_consent_nonpreferred_model`) の有無で WARNING/ERROR を
使い分けることを保証する。
"""
from __future__ import annotations

import logging

import pytest

from core.llm import (
    _MODEL_POLICY_DENYLIST,
    _MODEL_POLICY_PREFERRED,
    check_model_policy,
)


@pytest.mark.unit
def test_denylist_contains_expected_chinese_vendors():
    for bad in ("qwen", "deepseek", "chatglm", "baichuan", "internlm", "moonshot"):
        assert bad in _MODEL_POLICY_DENYLIST


@pytest.mark.unit
def test_preferred_contains_expected_japanese_vendors():
    for good in ("sarashina", "llm-jp", "swallow", "elyza", "rinna"):
        assert good in _MODEL_POLICY_PREFERRED


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "models/qwen2.5-3b-instruct-Q4_K_M.gguf",
        "/opt/models/deepseek-coder-6.7b.gguf",
        "mlx/ChatGLM3-6B",
        "InternLM2-7B",
        "models/Yi-34B-q4.gguf",
        "baichuan2-7b.gguf",
        "Moonshot-Kimi.gguf",
    ],
)
def test_denylist_matches_known_bad_paths(path, caplog):
    caplog.set_level(logging.ERROR)
    violations = check_model_policy([path], consent=False)
    assert len(violations) == 1
    assert path in violations[0]


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "models/sarashina2.2-3b-instruct-v0.1-Q4_K_M.gguf",
        "llm-jp-3-3.7b-instruct.gguf",
        "Llama-3-Swallow-8B-instruct.gguf",
        "ELYZA-japanese-Llama-2-7b.gguf",
        "rinna-nekomata-14b-instruction.gguf",
        "calm3-22b-chat.gguf",
        "models/phi-3-mini-4k.gguf",   # 推奨リスト外だが denylist にも該当しない
        "",
    ],
)
def test_preferred_and_neutral_paths_pass(path):
    violations = check_model_policy([path], consent=False)
    assert violations == []


@pytest.mark.unit
def test_consent_downgrades_error_to_warning(caplog):
    path = "models/qwen2.5-3b.gguf"

    # consent=False → ERROR
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        check_model_policy([path], consent=False)
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("Model Policy" in r.getMessage() for r in errors)

    # consent=True → WARNING 以下 (ERROR なし)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        check_model_policy([path], consent=True)
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not errors
    assert any("Model Policy" in r.getMessage() for r in warns)


@pytest.mark.unit
def test_yi_keyword_does_not_match_unrelated_substrings():
    # "yi-" のハイフン付きなので "yield", "koyomi" 等は誤検知しない
    for safe in ("koyomi-7b.gguf", "yielding-model.gguf", "ayi.gguf"):
        assert check_model_policy([safe], consent=False) == []


@pytest.mark.unit
def test_empty_and_none_safe():
    # None や空文字列で例外が出ないこと
    assert check_model_policy([], consent=False) == []
    assert check_model_policy(["", ""], consent=False) == []


@pytest.mark.unit
def test_multiple_paths_reports_all_violations():
    paths = [
        "models/qwen2.5.gguf",
        "mlx/sarashina2.2-3b",        # OK
        "ChatGLM-6B.gguf",
        "",
    ]
    violations = check_model_policy(paths, consent=True)
    assert len(violations) == 2
    assert any("qwen" in v.lower() for v in violations)
    assert any("chatglm" in v.lower() for v in violations)


@pytest.mark.unit
def test_case_insensitive_detection():
    for path in ("Models/QWEN2.5-3B.gguf", "DeepSeek.GGUF", "ChatGLM3"):
        violations = check_model_policy([path], consent=False)
        assert len(violations) == 1

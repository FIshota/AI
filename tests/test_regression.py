"""
回帰テスト: quality_benchmark のテストケースを pytest パラメトライズで実行する。

各品質判定関数を個別にテストし、応答品質の基準が正しく機能するか検証する。
"""
from __future__ import annotations

import pytest

from core.quality_benchmark import (
    appropriate_length,
    is_japanese,
    is_not_empty,
    no_desu_masu,
    no_repetition,
    no_role_prefix,
    BENCHMARK_CASES,
)


# ── is_japanese テスト ───────────────────────────────────


@pytest.mark.parametrize(
    "text, expected_min",
    [
        ("こんにちは、今日はいい天気だね", 0.9),
        ("天気がいいから散歩に行こう", 0.9),
        ("Hello, how are you?", 0.0),
        ("", 0.0),
        ("abc日本語mixed", 0.0),
    ],
    ids=["full_jp", "natural_jp", "english", "empty", "mixed"],
)
def test_is_japanese(text: str, expected_min: float) -> None:
    score = is_japanese(text)
    assert score >= expected_min, f"is_japanese({text!r}) = {score}, expected >= {expected_min}"


# ── is_not_empty テスト ──────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("何か内容がある", 1.0),
        ("a", 1.0),
        ("", 0.0),
        ("   ", 0.0),
        ("\n", 0.0),
    ],
    ids=["content", "single_char", "empty", "whitespace", "newline"],
)
def test_is_not_empty(text: str, expected: float) -> None:
    assert is_not_empty(text) == expected


# ── no_role_prefix テスト ────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("普通の応答だよ", 1.0),
        ("AI: これはダメ", 0.0),
        ("アシスタント: これもダメ", 0.0),
        ("Assistant: bad", 0.0),
        ("ai: lowercase bad", 0.0),
        ("AIについて話そう", 1.0),
    ],
    ids=["normal", "AI_prefix", "assistant_jp", "assistant_en", "ai_lower", "ai_in_text"],
)
def test_no_role_prefix(text: str, expected: float) -> None:
    assert no_role_prefix(text) == expected


# ── appropriate_length テスト ────────────────────────────


@pytest.mark.parametrize(
    "text, expected_min",
    [
        ("a" * 10, 1.0),
        ("a" * 100, 1.0),
        ("a" * 499, 1.0),
        ("", 0.0),
        ("ab", 0.0),
    ],
    ids=["short_ok", "medium_ok", "near_limit", "empty", "too_short"],
)
def test_appropriate_length(text: str, expected_min: float) -> None:
    score = appropriate_length(text)
    assert score >= expected_min, f"appropriate_length(len={len(text)}) = {score}"


# ── no_repetition テスト ─────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("普通の文章で繰り返しがない", 1.0),
        ("短い文", 1.0),
        ("あいうえおかきくけこ" * 5, 0.0),
    ],
    ids=["normal", "short", "repeated"],
)
def test_no_repetition(text: str, expected: float) -> None:
    assert no_repetition(text) == expected


# ── no_desu_masu テスト ──────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("今日はいい天気だね", 1.0),
        ("そうだよ！", 1.0),
        ("今日はいい天気です。", 0.0),
        ("元気にしています。", 0.0),
        ("そうですね", 1.0),  # 「です」の後に「ね」があるためマッチしない
        ("今日は元気です", 0.0),  # 「です」が文末
    ],
    ids=["casual", "casual2", "desu", "masu", "desu_ne", "desu_end"],
)
def test_no_desu_masu(text: str, expected: float) -> None:
    assert no_desu_masu(text) == expected


# ── ベンチマークケースのメタテスト ───────────────────────


def test_benchmark_cases_are_defined() -> None:
    """ベンチマークケースが空でないこと。"""
    assert len(BENCHMARK_CASES) > 0


def test_benchmark_cases_have_criteria() -> None:
    """全ケースに判定基準が設定されていること。"""
    for case in BENCHMARK_CASES:
        assert len(case.criteria) > 0, f"ケース '{case.input_text}' に基準がない"


@pytest.mark.parametrize(
    "case",
    BENCHMARK_CASES,
    ids=[c.input_text for c in BENCHMARK_CASES],
)
def test_criteria_callable(case) -> None:
    """全判定関数が空文字列で例外を出さないこと。"""
    for name, fn in case.criteria:
        score = fn("")
        assert isinstance(score, float), f"{name} returned non-float"
        assert 0.0 <= score <= 1.0, f"{name} returned out-of-range: {score}"

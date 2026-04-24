"""Property-based tests for core.clipboard_watcher.contains_pii.

Invariants:
    - Text built from a curated "clean" alphabet (japanese + english words +
      short digit runs, no tokens/key-prefixes) must never be flagged.
    - "<clean prefix> + <known PII sample>" must always be flagged.

Run:
    PYTHONPATH=. pytest tests/test_pii_properties.py -v --hypothesis-seed=0
"""
from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from core.clipboard_watcher import contains_pii

# ---------------------------------------------------------------------------
# Curated clean-text strategy.
# Excludes: any digit runs >= 4 (mynumber/SSN/CC/CVV bait),
# token prefixes (AKIA, ghp_, sk-, xox, AIza, eyJ, "-----BEGIN"), CVV labels,
# and the two-letter-uppercase + 7-digit JP passport shape.
# ---------------------------------------------------------------------------

_JP_CHARS: str = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
_EN_LOWER: str = "abcdefghijklmnopqrstuvwxyz"
# Only short digit tokens (max 3) so Luhn/SSN/MyNumber cannot match.
_SHORT_DIGITS: list[str] = [str(n) for n in range(10)] + [
    "12",
    "34",
    "99",
    "007",
    "123",
]

# Whole words keep us well away from token prefixes and digit runs.
_CLEAN_WORDS: list[str] = [
    "hello",
    "world",
    "goodmorning",
    "aichan",
    "yamato",
    "おはよう",
    "ありがとう",
    "family",
    "memo",
    "note",
    "today",
    "tomorrow",
    "project",
    "status",
    "ok",
    "fine",
    "いい",
    "わるい",
    "12",
    "99",
]

clean_word: st.SearchStrategy[str] = st.sampled_from(_CLEAN_WORDS)
clean_text: st.SearchStrategy[str] = st.lists(
    clean_word, min_size=1, max_size=20
).map(lambda ws: " ".join(ws))

# Also a pure-japanese / pure-english alphabet path.
clean_alpha_text: st.SearchStrategy[str] = st.text(
    alphabet=_JP_CHARS + _EN_LOWER + " 、。",
    min_size=1,
    max_size=200,
)


PII_SAMPLES: list[str] = [
    "4242 4242 4242 4242",          # credit card
    "1234-5678-9012",                # my number (JP)
    "AB1234567",                     # JP passport
    "123-45-6789",                   # US SSN
    "AKIAIOSFODNN7EXAMPLE",          # AWS key
    "ghp_" + "a" * 40,               # GitHub PAT
    "sk-" + "A" * 30,                # OpenAI key
    "sk-ant-" + "A" * 30,            # Anthropic key
    "xoxb-" + "A" * 20,              # Slack token
    "AIza" + "A" * 35,               # Google API key
    "eyJabc.eyJdef.signaturepart",   # JWT
    "-----BEGIN RSA PRIVATE KEY-----",
    "CVV: 123",                      # CVV label
]


# ---------------------------------------------------------------------------
# Property 1: clean text is never flagged.
# ---------------------------------------------------------------------------


@given(text=clean_text)
@settings(max_examples=500)
@example(text="hello world")
@example(text="おはよう aichan")
def test_clean_word_text_never_flagged(text: str) -> None:
    flagged, labels = contains_pii(text)
    assert flagged is False, f"False positive on {text!r}: {labels}"
    assert labels == []


@given(text=clean_alpha_text)
@settings(max_examples=500)
def test_clean_alpha_text_never_flagged(text: str) -> None:
    flagged, labels = contains_pii(text)
    assert flagged is False, f"False positive on {text!r}: {labels}"


# ---------------------------------------------------------------------------
# Property 2: clean prefix + PII sample is always flagged.
# ---------------------------------------------------------------------------


@given(prefix=clean_text, sample=st.sampled_from(PII_SAMPLES))
@settings(max_examples=500)
def test_clean_prefix_plus_pii_always_flagged(prefix: str, sample: str) -> None:
    text = f"{prefix} {sample}"
    flagged, labels = contains_pii(text)
    assert flagged is True, f"Missed PII in {text!r}"
    assert labels, "Expected at least one label"


@given(suffix=clean_text, sample=st.sampled_from(PII_SAMPLES))
@settings(max_examples=500)
def test_pii_sample_plus_clean_suffix_always_flagged(
    suffix: str, sample: str
) -> None:
    text = f"{sample} {suffix}"
    flagged, labels = contains_pii(text)
    assert flagged is True, f"Missed PII in {text!r}"
    assert labels


# ---------------------------------------------------------------------------
# Regression examples — direct samples must flag.
# ---------------------------------------------------------------------------


@example(sample="4242-4242-4242-4242")
@example(sample="AKIAIOSFODNN7EXAMPLE")
@example(sample="-----BEGIN OPENSSH PRIVATE KEY-----")
@given(sample=st.sampled_from(PII_SAMPLES))
@settings(max_examples=50)
def test_direct_pii_sample_flagged(sample: str) -> None:
    flagged, labels = contains_pii(sample)
    assert flagged is True
    assert labels

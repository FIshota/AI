"""Property-based tests for core.tenant (Hypothesis).

Focus: security-critical path-traversal and input-validation invariants
around TenantId / tenant_dir / parse_tenant_id.

Run:
    PYTHONPATH=. pytest tests/test_tenant_properties.py -v --hypothesis-seed=0
"""
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from core.tenant import (
    InvalidTenantId,
    TenantId,
    parse_tenant_id,
    tenant_dir,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Allowed chars mirror the regex in core/tenant.py: ^[A-Za-z0-9_\-]{1,64}$
_VALID_TENANT_CHARS: str = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_-"
)

valid_tenant_text: st.SearchStrategy[str] = st.text(
    alphabet=_VALID_TENANT_CHARS,
    min_size=1,
    max_size=64,
)

# Any unicode text — used to try to break the validator / path containment.
arbitrary_text: st.SearchStrategy[str] = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),  # no surrogates
    min_size=0,
    max_size=200,
)


# ---------------------------------------------------------------------------
# Valid-input properties
# ---------------------------------------------------------------------------


@given(raw=valid_tenant_text)
@settings(max_examples=500)
def test_valid_tenant_id_never_raises(raw: str) -> None:
    """Any string matching the allowed pattern must construct without error."""
    tid = TenantId(raw)
    assert tid.value == raw
    assert str(tid) == raw


@given(raw=valid_tenant_text)
@settings(max_examples=500)
def test_roundtrip_parse_str(raw: str) -> None:
    """parse_tenant_id(str(tid)) == tid for all valid ids."""
    tid = TenantId(raw)
    assert parse_tenant_id(str(tid)) == tid


# ---------------------------------------------------------------------------
# Invalid-input properties — must always raise
# ---------------------------------------------------------------------------


@given(core=valid_tenant_text)
@settings(max_examples=500)
@example(core="self")
@example(core="abc")
def test_traversal_dots_always_rejected(core: str) -> None:
    """Strings containing '..' must be rejected."""
    candidate = f"{core}..{core}"
    with pytest.raises(InvalidTenantId):
        TenantId(candidate)


@given(core=valid_tenant_text, sep=st.sampled_from(["/", "\\"]))
@settings(max_examples=500)
def test_path_separators_always_rejected(core: str, sep: str) -> None:
    """Strings containing forward/back slashes must be rejected."""
    candidate = f"{core}{sep}x"
    with pytest.raises(InvalidTenantId):
        TenantId(candidate)


@given(core=valid_tenant_text)
@settings(max_examples=500)
@example(core="x")
def test_null_byte_always_rejected(core: str) -> None:
    """Null byte must always be rejected."""
    with pytest.raises(InvalidTenantId):
        TenantId(core + "\x00")


@given(rest=valid_tenant_text)
@settings(max_examples=500)
@example(rest="hidden")
def test_leading_dot_always_rejected(rest: str) -> None:
    """Leading '.' (dotfile / traversal) must be rejected."""
    with pytest.raises(InvalidTenantId):
        TenantId("." + rest)


@pytest.mark.parametrize(
    "payload",
    [
        "../../etc/passwd",
        "..",
        "./",
        "../a",
        "a/../b",
        "a\\b",
        "null\x00byte",
        ".hidden",
        "",
        "x" * 65,
        "a b",
        "a;b",
        "日本語",
    ],
)
def test_known_bad_inputs_rejected(payload: str) -> None:
    """Regression set: previously discovered or conceptually dangerous inputs."""
    with pytest.raises(InvalidTenantId):
        TenantId(payload)


# ---------------------------------------------------------------------------
# tenant_dir path-containment properties
# ---------------------------------------------------------------------------


@given(raw=valid_tenant_text)
@settings(max_examples=500, deadline=None)
def test_tenant_dir_stays_inside_base(raw: str, tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    """tenant_dir(tid) must always live inside <base>/tenants/."""
    base = tmp_path_factory.mktemp("data", numbered=True)
    tid = TenantId(raw)
    path = tenant_dir(base, tid)
    resolved = path.resolve()
    expected_root = (base / "tenants").resolve()
    # Path is exactly inside the tenants root:
    assert expected_root in resolved.parents or resolved == expected_root / raw
    # Defensive: the resolved path must start with the expected_root prefix
    assert str(resolved).startswith(str(expected_root))


@given(raw=arbitrary_text)
@settings(max_examples=500, deadline=None)
@example(raw="../../etc/passwd")
@example(raw="..")
@example(raw="a/b")
@example(raw="\u202e")  # RTL override
@example(raw="\x00")
def test_tenant_dir_never_escapes_base_with_arbitrary_unicode(
    raw: str,
    tmp_path_factory,  # type: ignore[no-untyped-def]
) -> None:
    """Even with arbitrary unicode input, tenant_dir must not escape base.

    Either it raises InvalidTenantId, or the resulting path is contained.
    """
    base = tmp_path_factory.mktemp("data", numbered=True)
    try:
        path = tenant_dir(base, raw)
    except InvalidTenantId:
        return  # acceptable — validator rejected input
    resolved = path.resolve()
    expected_root = (base / "tenants").resolve()
    assert str(resolved).startswith(str(expected_root)), (
        f"tenant_dir escaped base: {resolved} not under {expected_root}"
    )


# ---------------------------------------------------------------------------
# parse_tenant_id edge cases
# ---------------------------------------------------------------------------


@given(raw=arbitrary_text)
@settings(max_examples=500)
def test_parse_tenant_id_invalid_raises(raw: str) -> None:
    """parse_tenant_id on arbitrary input either returns a valid TenantId
    (matches the regex) or raises InvalidTenantId. No other outcomes."""
    import re

    pattern = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
    try:
        result = parse_tenant_id(raw)
    except InvalidTenantId:
        # Must not match the valid pattern (unless raw was empty → default)
        assert raw == "" or not pattern.fullmatch(raw)
        return
    assert isinstance(result, TenantId)
    # Either it was empty→default("self"), or the raw must be a valid pattern
    if raw != "":
        assert pattern.fullmatch(raw) is not None

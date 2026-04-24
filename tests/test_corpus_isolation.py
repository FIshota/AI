"""Unit tests for scripts/check_corpus_isolation.py (ADR 0002)."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_corpus_isolation import (
    check_cross_phase_leak,
    check_isolation,
    main,
)


def _make_builder(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_clean_layout_has_no_violations(tmp_path: Path) -> None:
    repo = tmp_path / "ai-chan"
    sibling = tmp_path / "hinomoto-model"
    _make_builder(
        repo,
        "scripts/build_pretrain_corpus.py",
        "# reads only data/pretrain/\nSRC = 'data/pretrain/jawiki'\n",
    )
    _make_builder(
        sibling,
        "scripts/build_dolly_splits.py",
        "SRC = 'data/sft/dolly-15k-ja.jsonl'\n",
    )
    violations = check_isolation(repo, sibling)
    assert violations == []


def test_base_builder_referencing_personal_is_violation(tmp_path: Path) -> None:
    repo = tmp_path / "ai-chan"
    _make_builder(
        repo,
        "scripts/build_pretrain_corpus.py",
        "SRC = 'ai-chan/data/personal/diary.jsonl'\n",
    )
    violations = check_isolation(repo, None)
    assert len(violations) == 1
    assert violations[0].pattern == "ai-chan/data/personal"


def test_sibling_builder_referencing_memory_is_violation(tmp_path: Path) -> None:
    repo = tmp_path / "ai-chan"
    sibling = tmp_path / "hinomoto-model"
    repo.mkdir()
    _make_builder(
        sibling,
        "scripts/build_pretrain_corpus.py",
        "MEMORY = 'ai-chan/memory/episodic.db'\n",
    )
    violations = check_isolation(repo, sibling)
    assert len(violations) == 1
    assert "memory" in violations[0].pattern


def test_cross_phase_leak_reverse_direction(tmp_path: Path) -> None:
    repo = tmp_path / "ai-chan"
    personal = repo / "data" / "personal"
    personal.mkdir(parents=True)
    (personal / "config.yaml").write_text(
        "seed_corpus: data/pretrain/jawiki\n", encoding="utf-8"
    )
    violations = check_cross_phase_leak(repo)
    assert len(violations) == 1
    assert violations[0].pattern == "data/pretrain"


def test_docs_and_tests_are_excluded(tmp_path: Path) -> None:
    repo = tmp_path / "ai-chan"
    # ドキュメントが P4/P5 パスを言及しても違反にならない
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "adr.md").write_text("See ai-chan/data/personal/ for P4.\n", encoding="utf-8")
    # builder が存在しないので何も検出されない
    violations = check_isolation(repo, None)
    assert violations == []


def test_main_returns_zero_on_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "ai-chan"
    repo.mkdir()
    rc = main(["--repo-root", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_main_returns_two_on_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "ai-chan"
    _make_builder(
        repo,
        "scripts/build_pretrain_corpus.py",
        "LEAK = 'ai-chan/data/personal/diary.jsonl'\n",
    )
    rc = main(["--repo-root", str(repo)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "VIOLATION" in out

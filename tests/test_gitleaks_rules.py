"""Tests for custom gitleaks rules defined in ai-chan/.gitleaks.toml.

These tests invoke the real ``gitleaks`` binary against synthetic fixture files
in ``tmp_path``.  We assert that leaky content is detected and that a known
clean file is not flagged.

Skipped automatically when the ``gitleaks`` binary is not available.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / ".gitleaks.toml"

_CANDIDATES = [
    Path.home() / ".local" / "bin" / "gitleaks",
]


def _find_gitleaks() -> str | None:
    for cand in _CANDIDATES:
        if cand.exists() and os.access(cand, os.X_OK):
            return str(cand)
    found = shutil.which("gitleaks")
    return found


GITLEAKS = _find_gitleaks()

pytestmark = pytest.mark.skipif(
    GITLEAKS is None, reason="gitleaks binary not installed"
)


def _run_gitleaks(source: Path) -> tuple[int, list[dict]]:
    """Run gitleaks against ``source`` using the repo config.

    Returns (exit_code, findings).  gitleaks exits 1 on findings, 0 on clean.
    """
    report = source / "_gitleaks_report.json"
    cmd = [
        GITLEAKS,
        "detect",
        "--source",
        str(source),
        "--config",
        str(CONFIG_PATH),
        "--no-git",
        "--report-format",
        "json",
        "--report-path",
        str(report),
        "--redact",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    findings: list[dict] = []
    if report.exists():
        raw = report.read_text(encoding="utf-8").strip()
        if raw:
            findings = json.loads(raw)
    return result.returncode, findings


def test_leaky_file_is_detected(tmp_path: Path) -> None:
    leaky = tmp_path / "leaky_sample.txt"
    leaky.write_text(
        "\n".join(
            [
                "contact: honnsipittu@gmail.com",
                "db_path: /Users/fujihiranoborudai/ai-chan/memories.db",
                "ckpt: artifacts/sft_dolly_v1_continue/ckpt_final.pt",
                'tenant_id = "../../../etc/passwd"',
                "see VISION_INTERNAL.md for details",
            ]
        ),
        encoding="utf-8",
    )
    code, findings = _run_gitleaks(tmp_path)

    assert code != 0, "gitleaks should exit non-zero on leaks"
    assert findings, "expected gitleaks to report at least one finding"

    rule_ids = {f.get("RuleID") for f in findings}
    expected_any = {
        "hinomoto_owner_email_leak",
        "hinomoto_user_absolute_home_path",
        "hinomoto_sqlite_db_filename_leak",
        "hinomoto_ckpt_artifact_path_leak",
        "hinomoto_tenant_id_path_traversal",
        "hinomoto_vision_internal_marker",
    }
    assert rule_ids & expected_any, (
        f"none of our custom rules fired; got={rule_ids}"
    )


def test_clean_file_is_not_detected(tmp_path: Path) -> None:
    clean = tmp_path / "clean_sample.txt"
    clean.write_text(
        "\n".join(
            [
                "# ai-chan public readme snippet",
                "The system stores emotional context in a local database.",
                "See docs for configuration options.",
                "contact: please use the GitHub issue tracker",
            ]
        ),
        encoding="utf-8",
    )
    code, findings = _run_gitleaks(tmp_path)

    assert code == 0, f"gitleaks flagged clean content: {findings}"
    assert findings == [], f"unexpected findings on clean file: {findings}"

"""scripts/check_feature_rubric.py のテスト."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ をインポート可能にする
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_feature_rubric as rubric_mod  # noqa: E402


def _base_rubric() -> dict:
    """EXAMPLE 相当の全 yes/期待値一致 rubric を返す."""
    return {
        "killswitch_purge_guaranteed": "yes",
        "killswitch_side_effects_covered": "yes",
        "targets_engagement_kpi": "no",
        "has_attention_hook": "no",
        "lineage_scope_defined": "yes",
        "leaks_ai_layer": "no",
        "survives_dependency_loss": "yes",
        "respects_maintainability_budget": "yes",
        "works_offline": "yes",
        "feeds_third_party_training": "no",
    }


def _write_proposal(tmp_path: Path, name: str, rubric: dict, title: str = "t") -> Path:
    import yaml

    path = tmp_path / name
    path.write_text(
        yaml.safe_dump({"title": title, "rubric": rubric}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def test_example_yaml_is_accept_candidate():
    example = REPO_ROOT / "docs" / "feature_proposals" / "EXAMPLE.yaml"
    proposal = rubric_mod.load_proposal(example)
    result = rubric_mod.evaluate(proposal)
    assert result["verdict"] == "accept_candidate"
    assert result["kill_switch_failed"] == []
    assert result["other_score"] == result["other_total"]


def test_kill_switch_violation_forces_rejection(tmp_path):
    r = _base_rubric()
    r["killswitch_purge_guaranteed"] = "no"  # Kill-Switch 違反
    path = _write_proposal(tmp_path, "ks_fail.yaml", r)
    result = rubric_mod.evaluate(rubric_mod.load_proposal(path))
    assert result["verdict"] == "kill_switch_violation"
    assert "killswitch_purge_guaranteed" in result["kill_switch_failed"]


def test_question_mark_on_killswitch_is_violation(tmp_path):
    r = _base_rubric()
    r["killswitch_side_effects_covered"] = "?"  # 判断保留も Kill-Switch では違反扱い
    path = _write_proposal(tmp_path, "ks_unknown.yaml", r)
    result = rubric_mod.evaluate(rubric_mod.load_proposal(path))
    assert result["verdict"] == "kill_switch_violation"


def test_below_threshold_triggers_revise(tmp_path):
    r = _base_rubric()
    # 非 Kill-Switch 8 項目中 2 つ逆転 → 6/8 で 7 点未満
    r["targets_engagement_kpi"] = "yes"
    r["has_attention_hook"] = "yes"
    path = _write_proposal(tmp_path, "low_score.yaml", r)
    result = rubric_mod.evaluate(rubric_mod.load_proposal(path))
    assert result["verdict"] == "revise"
    assert result["kill_switch_failed"] == []
    assert result["other_score"] == 6


def test_cli_exit_codes(tmp_path, capsys):
    # accept_candidate → exit 0
    ok_path = _write_proposal(tmp_path, "ok.yaml", _base_rubric())
    assert rubric_mod.main([str(ok_path)]) == 0

    # kill_switch_violation → exit 2
    bad = _base_rubric()
    bad["killswitch_purge_guaranteed"] = "no"
    bad_path = _write_proposal(tmp_path, "bad.yaml", bad)
    assert rubric_mod.main([str(bad_path)]) == 2


def test_invalid_yaml_raises(tmp_path):
    bad = _base_rubric()
    del bad["works_offline"]  # 必須項目欠落
    import yaml

    path = tmp_path / "broken.yaml"
    path.write_text(
        yaml.safe_dump({"title": "x", "rubric": bad}, allow_unicode=True),
        encoding="utf-8",
    )
    with pytest.raises(rubric_mod.RubricError):
        rubric_mod.load_proposal(path)

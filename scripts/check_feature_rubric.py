#!/usr/bin/env python3
"""VALUES_RUBRIC 採点スクリプト.

`docs/feature_proposals/*.yaml` に置かれた新機能提案ファイルを読み、
`docs/VALUES_RUBRIC.md` の 10 項目に沿って機械採点する。

判定:
  - kill_switch_violation: 即却下 (exit 2)
  - accept_candidate:      採択候補   (exit 0)
  - revise:                差し戻し  (exit 2)

使い方:
  python scripts/check_feature_rubric.py docs/feature_proposals/EXAMPLE.yaml
  python scripts/check_feature_rubric.py docs/feature_proposals/*.yaml

Python 3.9 互換。pyyaml 必須。
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


# ---------------------------------------------------------------------------
# Rubric 定義 (docs/VALUES_RUBRIC.md と一対一対応)
# ---------------------------------------------------------------------------

KILL_SWITCH_KEYS = (
    "killswitch_purge_guaranteed",
    "killswitch_side_effects_covered",
)

# key -> (期待値, 人間向け説明)
RUBRIC: Dict[str, Tuple[str, str]] = {
    "killswitch_purge_guaranteed": (
        "yes",
        "追加データを家族意思で全件 purge 可能か",
    ),
    "killswitch_side_effects_covered": (
        "yes",
        "キャッシュ/同期/学習重み等の副作用も purge 対象か",
    ),
    "targets_engagement_kpi": (
        "no",
        "滞在率・利用時間などの KPI を目的としていないか",
    ),
    "has_attention_hook": (
        "no",
        "通知・煽り・アテンション搾取を含まないか",
    ),
    "lineage_scope_defined": (
        "yes",
        "Ai / YAMATO / KAGUYA のいずれかに明確に属するか",
    ),
    "leaks_ai_layer": (
        "no",
        "Ai 層の人格・記憶・学習データを外部に出さないか",
    ),
    "survives_dependency_loss": (
        "yes",
        "外部 SDK/API が消えても単独で動作し続けるか",
    ),
    "respects_maintainability_budget": (
        "yes",
        "保守性基準 (800 行/50 行) を壊さないか",
    ),
    "works_offline": (
        "yes",
        "オフラインでも成立するか",
    ),
    "feeds_third_party_training": (
        "no",
        "家族データが外部事業者の学習対象になる経路を含まないか",
    ),
}

VALID_ANSWERS = {"yes", "no", "?"}

# YAML 1.1 の慣習により `yes`/`no` は bool にパースされる。
# 明示的に文字列へ正規化することで、提案者は素朴に `yes`/`no` と書ける。
_NORMALIZE = {
    True: "yes",
    False: "no",
    "yes": "yes",
    "no": "no",
    "Yes": "yes",
    "No": "no",
    "YES": "yes",
    "NO": "no",
    "y": "yes",
    "n": "no",
    "?": "?",
}


def _normalize_answer(value: object) -> object:
    """yaml が bool 化した yes/no を文字列に戻す. 不明値はそのまま返す."""
    if isinstance(value, bool):
        return _NORMALIZE[value]
    if isinstance(value, str):
        return _NORMALIZE.get(value, value)
    return value
ACCEPT_THRESHOLD = 7  # 非 Kill-Switch 8 項目中 7 点以上


# ---------------------------------------------------------------------------
# Loader & Validator
# ---------------------------------------------------------------------------

class RubricError(Exception):
    """提案 YAML の形式不備."""


def load_proposal(path: Path) -> Dict[str, object]:
    """YAML を読み込み、必須項目を検証する."""
    if not path.is_file():
        raise RubricError("proposal file not found: {}".format(path))

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise RubricError("proposal must be a YAML mapping: {}".format(path))

    if "title" not in data:
        raise RubricError("missing 'title' in {}".format(path))

    rubric = data.get("rubric")
    if not isinstance(rubric, dict):
        raise RubricError("missing or invalid 'rubric' mapping in {}".format(path))

    missing = [k for k in RUBRIC if k not in rubric]
    if missing:
        raise RubricError(
            "rubric missing required keys in {}: {}".format(path, ", ".join(missing))
        )

    normalized: Dict[str, str] = {}
    for key, ans in rubric.items():
        if key not in RUBRIC:
            raise RubricError("unknown rubric key '{}' in {}".format(key, path))
        norm = _normalize_answer(ans)
        if norm not in VALID_ANSWERS:
            raise RubricError(
                "invalid answer for '{}' in {}: {!r} (expected yes/no/?)".format(
                    key, path, ans
                )
            )
        normalized[key] = norm  # type: ignore[assignment]

    data["rubric"] = normalized
    return data


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_answer(key: str, answer: str) -> int:
    """期待値と一致なら 1 点。`?` は 0 点。"""
    expected, _ = RUBRIC[key]
    if answer == "?":
        return 0
    return 1 if answer == expected else 0


def evaluate(proposal: Dict[str, object]) -> Dict[str, object]:
    """提案 1 件を採点して結果辞書を返す."""
    rubric_ans: Dict[str, str] = proposal["rubric"]  # type: ignore[assignment]

    kill_switch_failed: List[str] = []
    for key in KILL_SWITCH_KEYS:
        if score_answer(key, rubric_ans[key]) == 0:
            kill_switch_failed.append(key)

    other_keys = [k for k in RUBRIC if k not in KILL_SWITCH_KEYS]
    other_score = sum(score_answer(k, rubric_ans[k]) for k in other_keys)
    other_total = len(other_keys)

    if kill_switch_failed:
        verdict = "kill_switch_violation"
    elif other_score >= ACCEPT_THRESHOLD:
        verdict = "accept_candidate"
    else:
        verdict = "revise"

    return {
        "title": proposal.get("title"),
        "verdict": verdict,
        "kill_switch_failed": kill_switch_failed,
        "other_score": other_score,
        "other_total": other_total,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def format_result(path: Path, result: Dict[str, object]) -> str:
    lines = [
        "== {} ==".format(path),
        "  title:   {}".format(result["title"]),
        "  verdict: {}".format(result["verdict"]),
        "  score:   {}/{} (非 Kill-Switch)".format(
            result["other_score"], result["other_total"]
        ),
    ]
    failed = result["kill_switch_failed"]
    if failed:
        lines.append("  kill_switch_failed:")
        for k in failed:  # type: ignore[assignment]
            lines.append("    - {} ({})".format(k, RUBRIC[k][1]))
    return "\n".join(lines)


def expand_paths(patterns: List[str]) -> List[Path]:
    out: List[Path] = []
    for pat in patterns:
        matched = sorted(glob.glob(pat))
        if not matched and Path(pat).exists():
            matched = [pat]
        if not matched:
            # パターン不一致は空のままにして後段でエラー扱い
            out.append(Path(pat))
            continue
        out.extend(Path(p) for p in matched)
    return out


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="VALUES_RUBRIC に基づいて新機能提案 YAML を採点する"
    )
    parser.add_argument("paths", nargs="+", help="feature proposal YAML ファイル")
    args = parser.parse_args(argv)

    paths = expand_paths(args.paths)
    if not paths:
        print("no proposal files matched", file=sys.stderr)
        return 2

    worst_exit = 0
    for path in paths:
        try:
            proposal = load_proposal(path)
        except RubricError as e:
            print("[ERROR] {}".format(e), file=sys.stderr)
            worst_exit = 2
            continue

        result = evaluate(proposal)
        print(format_result(path, result))

        if result["verdict"] != "accept_candidate":
            worst_exit = 2

    return worst_exit


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

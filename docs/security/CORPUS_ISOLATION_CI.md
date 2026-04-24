# Corpus Isolation CI (ADR 0002)

This document describes the CI guard that enforces the P1-P5 corpus
isolation policy defined in [ADR 0002](../adr/0002-corpus-isolation.md).

## What is enforced

Per ADR 0002, P4 / P5 personal corpora (`ai-chan/data/personal/`,
`ai-chan/memory/`) must never be read by base-model build pipelines
(`scripts/build_pretrain_corpus.py`, `scripts/build_dolly_splits.py`,
`scripts/build_stabilize_*.py`) in either this repository or the sibling
`hinomoto-model` repository.

The guard is a static check — it greps the relevant builder scripts for
forbidden path substrings. It does not execute the builders.

## Trigger events

The `.github/workflows/corpus-isolation.yml` workflow runs on:

| Event | Covered |
|-------|---------|
| `pull_request` (any branch) | yes |
| `push` to `main` | yes |
| `push` to `phase*/**` branches | yes |

The `push` trigger is **intentional and required**. An earlier
hinomoto-model direct push-to-main incident demonstrated that
`pull_request`-only CI can be bypassed by pushing straight to the
protected branch with admin override. Having the check fire on `push`
ensures the guard is evaluated regardless of merge path.

## How to run locally

```bash
cd ai-chan
python3 scripts/check_corpus_isolation.py
```

Exit codes:

- `0` — clean
- `2` — violation (one or more base builders reference P4/P5 paths, or
  personal corpora reference base pretrain/sft paths)

The script auto-detects a sibling `hinomoto-model/` checkout next to
`ai-chan/` and scans it too. Override with:

```bash
python3 scripts/check_corpus_isolation.py \
  --repo-root /path/to/ai-chan \
  --sibling-root /path/to/hinomoto-model
```

Unit tests:

```bash
cd ai-chan
PYTHONPATH=. python3 -m pytest tests/test_corpus_isolation.py -v
```

## Adding new corpora

When introducing a new corpus phase or a new builder:

1. Decide the phase (P1-P5) and storage location per ADR 0002's table.
2. If the new builder is a **base-model builder** (feeds
   HinoMoto / YAMATO / public derivatives), add its glob to
   `BASE_BUILDER_GLOBS` or `AICHAN_BASE_BUILDER_GLOBS` in
   `scripts/check_corpus_isolation.py`.
3. If the new corpus introduces a new personal (P4/P5) root, add its
   path fragment to `FORBIDDEN_IN_BASE_BUILDERS`.
4. Update [ADR 0002](../adr/0002-corpus-isolation.md)'s phase table.
5. Add a unit test in `tests/test_corpus_isolation.py` that asserts the
   new boundary is enforced.
6. Run the guard locally and ensure it is green before pushing.

No manifest/checksum file is required at this stage. If the corpus set
grows large enough that substring scanning becomes unreliable, promote
the guard to a whitelist-manifest model and update this document.

## Historical context

An earlier direct push to `main` in `hinomoto-model` bypassed a
`pull_request`-only CI check. That incident motivated:

- Adding `push` as a trigger alongside `pull_request`.
- Making the guard a dedicated workflow (`corpus-isolation.yml`)
  independent of the general `tests.yml` pipeline, so corpus isolation
  cannot be disabled by changes to the test matrix.

## Related

- [ADR 0002 — 学習コーパスの相隔離](../adr/0002-corpus-isolation.md)
- [ADR 0006 — Kill switch primacy](../adr/0006-kill-switch-primacy.md)
- [ADR 0007 — モデル派生命名](../adr/0007-model-family-naming.md)
- [PRIVACY.md](../../PRIVACY.md)

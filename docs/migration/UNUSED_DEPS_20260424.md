# Unused Dependencies Audit — 2026-04-24 (Cat 5 / C6)

> **Advisory only.** This document lists packages in `requirements.txt` for which
> no `import` / `from` statement was detected in `core/`, `ui/`, `scripts/`,
> `tests/`, `tools/`, `utils/`, `main.py`, or `web_main.py`.
>
> **Do NOT delete without further verification.** Some packages may be:
> - Required transitive dependencies installed explicitly for version pinning / CVE mitigation
> - Imported dynamically via `importlib` or string-based plugin loaders
> - Used only at runtime by a bundled binary (e.g. `uvicorn` CLI, `click` entry points)
> - Pulled in optionally by framework internals (e.g. `slowapi` via FastAPI middleware config)

## Methodology

- Parsed top-level package names from `requirements.txt` (43 total after stripping comments/markers).
- Mapped pip distribution names to their Python import names
  (e.g. `python-jose` → `jose`, `Pillow` → `PIL`, `beautifulsoup4` → `bs4`).
- Ran grep for `import <name>` / `from <name>` across source trees.
- stdlib-only Cat 5 additions confirmed to add **zero** new third-party dependencies.

## Candidate unused packages (6)

| Package | Tried imports | Status | Notes / recommendation |
|---------|---------------|--------|------------------------|
| `python-jose[cryptography]` | `jose` | No import found | Historical JWT helper. **Verify** whether FastAPI auth middleware references it indirectly before removal. Keep pinned for CVE posture if unsure. |
| `slowapi` | `slowapi` | No import found | Rate-limiting plugin for FastAPI. **Likely wired via config or middleware string**. Confirm `web_main.py` / router setup before dropping. |
| `tiktoken` | `tiktoken` | No import found | Token counter. **Candidate for removal** if the project has fully moved to `gguf` / llama-cpp token counts. Check token-budget utilities. |
| `scikit-learn` | `sklearn` | No import found | Heavy dependency (~30MB). **Candidate for removal** unless used by vector utilities that were migrated to `faiss` + numpy. |
| `click` | `click` | No import found | CLI framework. **Often a transitive dep** (uvicorn, black, etc.) — keeping it explicit is defensive but not strictly required. |
| `python-dateutil` | `dateutil` | No import found | Date parsing. **Transitive** via pandas/google-api. Safe to keep explicit; optional to drop. |

## Recommendation

1. **Do not delete in this change.** Cat 5 scope is docs + audit only.
2. Open a follow-up ticket to runtime-test removal in a throwaway venv:
   - Stage 1 (low risk): drop `tiktoken`, `scikit-learn`.
   - Stage 2 (verify first): drop `python-jose`, `slowapi` only after auditing
     `web_main.py` route handlers and any middleware configured via string reference.
   - Stage 3 (cosmetic): `click`, `python-dateutil` are transitively satisfied;
     keep them only if we want version pinning.
3. Re-run this audit after any dependency change.

## Cat 5 dependency hygiene

- All Cat 5 modules (5.1 – 5.10) are **stdlib-only**.
  - `sqlite3` (FTS5), `tkinter`, `xml.etree`, `hashlib`, `hmac`, `secrets`,
    `datetime`, `json`, `threading`, `dataclasses`, `typing`.
- No new entries were required in `requirements.txt` for this release.
- Verified: `requirements.txt` is unchanged between Cat 4 and Cat 5.

## Outdated dependency report (`pip list --outdated`, 2026-04-24)

Only packages present in `requirements.txt` or directly imported are classified.
Severity: ⚠️ MAJOR (breaking risk), ● MEDIUM (minor), ○ LOW (patch).

| Package | Current | Latest | Severity | Notes |
|---------|---------|--------|----------|-------|
| `rich` | 14.3.3 | 15.0.0 | ⚠️ MAJOR | requirements pins `<16.0.0`. Evaluate before bumping — ANSI rendering changes. |
| `magika` | 0.6.3 | 1.0.2 | ⚠️ MAJOR | Held per requirements.txt header note. |
| `pyarrow` | 23.0.1 | 24.0.0 | ⚠️ MAJOR | Held per requirements.txt header note. |
| `setuptools` | 75.8.2 | 82.0.1 | ⚠️ MAJOR | Held per requirements.txt header note. |
| `fastapi` | 0.135.3 | 0.136.1 | ● MEDIUM | Already pinned `>=0.136.0` in requirements; env lags — `pip install -U fastapi`. |
| `uvicorn` | 0.44.0 | 0.46.0 | ● MEDIUM | Requirements pin `>=0.45.0`; env lags. |
| `cryptography` | 46.0.5 | 46.0.7 | ● MEDIUM | Patch bump, already floor-pinned. |
| `requests` | 2.32.5 | 2.33.1 | ● MEDIUM | Already floor-pinned. |
| `Pillow` | 12.1.1 | 12.2.0 | ● MEDIUM | Already floor-pinned `>=12.2.0`; env lags. |
| `pydantic` | 2.13.1 | 2.13.3 | ○ LOW | Patch. |
| `click` | 8.3.2 | 8.3.3 | ○ LOW | Patch. |
| `sentence-transformers` | 5.3.0 | 5.4.1 | ● MEDIUM | Minor, verify ST model loading. |
| `onnxruntime` | 1.24.4 | 1.25.0 | ● MEDIUM | Minor; vision Tier 1 path uses it. |
| `av`, `build`, `certifi`, `charset-normalizer`, `ddgs`, `filelock`, `fsspec`, `huggingface_hub`, `idna`, `lxml`, `packaging`, `pathspec`, `platformdirs`, `primp`, `pypdfium2`, `python-engineio`, `python-socketio`, `Pygments`, `rembg`, `tifffile`, `typer`, `Werkzeug`, `wheel`, `wsproto`, `pydantic_core`, `mlx*`, `mpmath`, `mypy`, `numba`, `llvmlite`, `Flask`, `Flask-SocketIO`, `pip` | — | — | ○ LOW | Transitive / tooling / patch-level. |
| `transformers` | 5.5.0 | 5.6.2 | ● MEDIUM | Optional (H6 moved to optional install). |

### Summary

- **MAJOR (⚠️):** 4 packages (`rich`, `magika`, `pyarrow`, `setuptools`). All already held in `requirements.txt` header with explicit notes.
- **MEDIUM (●):** ~8 packages. Safe patch/minor bumps — recommend `pip install -U -r requirements.txt` in a fresh venv and re-run the test suite.
- **LOW (○):** ~25 packages. Mostly transitive / tooling.

### Recommended action

1. Refresh the venv so floor-pinned deps in `requirements.txt` actually install
   (several MEDIUM items are already satisfied by requirements but the local env
   lags).
2. Defer MAJOR bumps until a dedicated upgrade ticket — each carries breaking
   changes as annotated in `requirements.txt`.
3. No action required from Cat 5 — this audit is informational.

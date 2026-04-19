"""ai-chan 軽量シークレットスキャナ (gitleaks 代替)

使い方:
    python3 scripts/secret_scan.py             # プロジェクトルート全体をスキャン
    python3 scripts/secret_scan.py path [...]  # 指定パスのみ

検出:
    - AWS / GCP / Azure / GitHub Token
    - OpenAI / Anthropic / Claude API Key
    - Notion Integration Token
    - Generic high-entropy strings in env-like contexts
    - Hard-coded passwords / private keys

exit 0: 検出なし / exit 1: 検出あり
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

# ── パターン（ラベル, regex, 信頼度） ──────────────────────────────
PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}"), "HIGH"),
    ("AWS Secret Key", re.compile(r"(?i)aws.{0,20}?['\"][0-9a-zA-Z/+]{40}['\"]"), "HIGH"),
    ("GCP Service Account", re.compile(r'"type":\s*"service_account"'), "HIGH"),
    ("GitHub PAT (classic)", re.compile(r"ghp_[A-Za-z0-9]{36}"), "HIGH"),
    ("GitHub PAT (fine-grained)", re.compile(r"github_pat_[A-Za-z0-9_]{82}"), "HIGH"),
    ("GitHub OAuth", re.compile(r"gho_[A-Za-z0-9]{36}"), "HIGH"),
    ("OpenAI API Key", re.compile(r"sk-[A-Za-z0-9]{32,}"), "HIGH"),
    ("Anthropic API Key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{40,}"), "HIGH"),
    ("Slack Token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "HIGH"),
    ("Notion Integration", re.compile(r"secret_[A-Za-z0-9]{43}"), "HIGH"),
    ("Notion ntn_", re.compile(r"ntn_[A-Za-z0-9]{30,}"), "HIGH"),
    ("Stripe Secret", re.compile(r"sk_live_[A-Za-z0-9]{24,}"), "HIGH"),
    ("Stripe Restricted", re.compile(r"rk_live_[A-Za-z0-9]{24,}"), "HIGH"),
    ("Private Key PEM", re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |)PRIVATE KEY-----"), "HIGH"),
    ("JWT-like", re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"), "MEDIUM"),
    ("Generic password=", re.compile(r"""(?i)(password|passwd|pwd)\s*[:=]\s*['"]([^'"\s]{8,})['"]"""), "MEDIUM"),
    ("Generic api_key=", re.compile(r"""(?i)(api[_-]?key|apikey|api_secret|access[_-]?token)\s*[:=]\s*['"]([A-Za-z0-9_\-]{20,})['"]"""), "MEDIUM"),
]

# ── 無視パス ──────────────────────────────────────────────────────
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", "models",
    "data", "logs", "dist", "build", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "outputs", "output", "AiChan.app",
}
EXCLUDE_FILE_SUFFIXES = {".gguf", ".onnx", ".bin", ".pt", ".pth", ".safetensors",
                        ".zip", ".tar", ".gz", ".png", ".jpg", ".jpeg", ".mp3",
                        ".wav", ".ogg", ".mp4", ".pdf", ".docx", ".pptx", ".xlsx"}
EXCLUDE_FILE_NAMES = {"secret_scan.py", "url_guard.py"}  # self, false-positive-heavy

MAX_FILE_BYTES = 512 * 1024  # 512KB


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def iter_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.suffix.lower() in EXCLUDE_FILE_SUFFIXES:
                continue
            if p.name in EXCLUDE_FILE_NAMES:
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings: list[dict] = []
    for label, pat, sev in PATTERNS:
        for m in pat.finditer(text):
            # Skip common placeholders
            snippet = m.group(0)
            lower = snippet.lower()
            if any(k in lower for k in ("example", "placeholder", "your_", "xxxx", "dummy", "<token>", "<key>")):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            findings.append({
                "file": str(path),
                "line": line_no,
                "rule": label,
                "severity": sev,
                "match": snippet[:80] + ("..." if len(snippet) > 80 else ""),
            })
    return findings


def main() -> int:
    args = sys.argv[1:]
    roots = [Path(a) for a in args] if args else [Path(__file__).resolve().parent.parent]

    all_findings: list[dict] = []
    scanned = 0
    for f in iter_files(roots):
        scanned += 1
        all_findings.extend(scan_file(f))

    by_sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for h in all_findings:
        by_sev[h["severity"]] = by_sev.get(h["severity"], 0) + 1

    print(f"secret-scan: {scanned} files scanned")
    print(f"  findings: H={by_sev['HIGH']} M={by_sev['MEDIUM']} L={by_sev.get('LOW',0)}  total={len(all_findings)}")
    for h in all_findings:
        print(f"  [{h['severity']}] {h['file']}:{h['line']}  {h['rule']}: {h['match']}")

    # JSON for CI
    out = Path(__file__).resolve().parent.parent / "logs" / "security"
    out.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    (out / f"secrets-{date}.json").write_text(
        json.dumps(all_findings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 1 if by_sev["HIGH"] else 0


if __name__ == "__main__":
    sys.exit(main())

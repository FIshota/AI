#!/usr/bin/env bash
# ai-chan ローカル脆弱性監査
# Usage: scripts/audit.sh [quick|full]
#   quick: pip-audit のみ
#   full : pip-audit + bandit + gitleaks + outdated + SBOM
set -uo pipefail

MODE="${1:-quick}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DATE=$(date -u +%Y%m%d)
LOGDIR="logs/security"
mkdir -p "$LOGDIR"

VENV="/tmp/ai-chan-scan"
if [ ! -f "$VENV/bin/pip-audit" ]; then
  echo "[audit] bootstrapping scan venv at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip pip-audit bandit cyclonedx-bom pip-tools
fi

echo "━━━ ai-chan audit ($MODE) @ $DATE ━━━"

echo "[1/5] pip-audit (dependency CVE scan)..."
"$VENV/bin/pip-audit" -r requirements.txt --format=json --progress-spinner=off \
  > "$LOGDIR/pip-audit-$DATE.json" 2> "$LOGDIR/pip-audit-$DATE.err" || true
python3 - <<PY
import json, sys
try:
    d = json.load(open("$LOGDIR/pip-audit-$DATE.json"))
    vulns = [x for x in d.get("dependencies", []) if x.get("vulns")]
    total = len(d.get("dependencies", []))
    print(f"    ├ {total} deps scanned, {len(vulns)} vulnerable")
    for v in vulns:
        ids = ",".join(x["id"] for x in v["vulns"])
        print(f"    │   - {v['name']} {v['version']}: {ids}")
except Exception as e:
    print(f"    └ (parse error: {e})")
PY

if [ "$MODE" = "full" ]; then
  echo "[2/5] bandit (static analysis)..."
  "$VENV/bin/bandit" -r core utils ui web -f json -o "$LOGDIR/bandit-$DATE.json" -q 2>/dev/null || true
  python3 - <<PY
import json
try:
    d = json.load(open("$LOGDIR/bandit-$DATE.json"))
    results = d.get("results", [])
    sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in results:
        sev[r.get("issue_severity", "LOW")] = sev.get(r.get("issue_severity"), 0) + 1
    print(f"    ├ {len(results)} issues: H={sev.get('HIGH',0)} M={sev.get('MEDIUM',0)} L={sev.get('LOW',0)}")
except Exception as e:
    print(f"    └ (parse error: {e})")
PY

  echo "[3/5] gitleaks (secret scan)..."
  # launchd minimal PATH に対応して明示的にプロビン候補を探索
  GITLEAKS_BIN=""
  for cand in "$(command -v gitleaks 2>/dev/null)" "$HOME/.local/bin/gitleaks" "/usr/local/bin/gitleaks" "/opt/homebrew/bin/gitleaks"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then GITLEAKS_BIN="$cand"; break; fi
  done
  if [ -n "$GITLEAKS_BIN" ]; then
    GITLEAKS_CFG=""
    [ -f ".gitleaks.toml" ] && GITLEAKS_CFG="--config=.gitleaks.toml"
    "$GITLEAKS_BIN" detect --no-git -v $GITLEAKS_CFG --report-path="$LOGDIR/gitleaks-$DATE.json" --report-format=json --source=. \
      > /dev/null 2>&1 || true
    if [ -s "$LOGDIR/gitleaks-$DATE.json" ]; then
      count=$(python3 -c "import json;print(len(json.load(open('$LOGDIR/gitleaks-$DATE.json'))))" 2>/dev/null || echo "?")
      echo "    ├ $count potential secrets ($GITLEAKS_BIN)"
    else
      echo "    ├ no secrets found ($GITLEAKS_BIN)"
    fi
  else
    echo "    ├ gitleaks not installed (try: go install github.com/gitleaks/gitleaks/v8@latest, or download binary)"
  fi

  echo "[4/5] outdated check (PyPI latest vs floor)..."
  python3 scripts/check_outdated.py 2>/dev/null > "$LOGDIR/outdated-$DATE.txt" || true
  outdated_count=$(grep -c "^!" "$LOGDIR/outdated-$DATE.txt" 2>/dev/null || echo 0)
  echo "    ├ $outdated_count packages >=2 minor versions behind"

  echo "[5/5] SBOM (CycloneDX)..."
  "$VENV/bin/cyclonedx-py" requirements -i requirements.txt -o "$LOGDIR/sbom-$DATE.json" 2>/dev/null || \
    echo "    └ SBOM generation skipped (cyclonedx-py not available)"
fi

echo "━━━ done. artifacts in $LOGDIR/ ━━━"
ls -la "$LOGDIR/" | tail -10

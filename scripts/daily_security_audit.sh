#!/usr/bin/env bash
# ai-chan 毎日セキュリティ監査ラッパー (launchd から呼ばれる)
#
# 役割:
#   1. scripts/audit.sh full を実行
#   2. 結果を logs/security/YYYY-MM-DD.md にサマリ
#   3. HIGH/CRITICAL があれば macOS 通知 + Mail.app 経由でメール送信
#   4. docs/SECURITY.md の変更履歴セクションに 1 行追記
#
# 使い方:
#   直接:    scripts/daily_security_audit.sh
#   launchd: /Library/LaunchAgents/com.aichan.security-audit.plist から
#
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DATE=$(date +%Y-%m-%d)                  # JST ローカル日付 (サマリファイル名用)
AUDIT_DATE=$(date -u +%Y%m%d)            # UTC 日付 (audit.sh のファイル命名に合わせる)
TIME=$(date +%H:%M:%S)
JST_NOW=$(TZ=Asia/Tokyo date +"%Y-%m-%d %H:%M:%S JST")
LOGDIR="logs/security"
SUMMARY="$LOGDIR/$DATE.md"
EXECLOG="$LOGDIR/exec-$DATE.log"
# PII externalized 2026-04-25: source admin.env if present (plist no longer sets it)
ADMIN_ENV="$HOME/.config/ai-chan/admin.env"
[ -f "$ADMIN_ENV" ] && set -a && . "$ADMIN_ENV" && set +a
NOTIFY_EMAIL="${AICHAN_ADMIN_EMAIL:-}"
if [ -z "$NOTIFY_EMAIL" ]; then
  echo "[warn] AICHAN_ADMIN_EMAIL not set (expected in $ADMIN_ENV). Notifications will be skipped." >&2
fi

mkdir -p "$LOGDIR"

# ─── 1. audit.sh full を実行 (exec log を取る) ──────────────
{
  echo "════════════════════════════════════════════════════"
  echo "ai-chan Daily Security Audit"
  echo "Started: $JST_NOW"
  echo "Host:    $(hostname)"
  echo "User:    $(whoami)"
  echo "Root:    $ROOT"
  echo "════════════════════════════════════════════════════"
} > "$EXECLOG"

bash scripts/audit.sh full >> "$EXECLOG" 2>&1
AUDIT_RC=$?

# ─── 2. 結果を Python で集約してマークダウンサマリ生成 ─────
# $DATE は JST (サマリ表示用)、$AUDIT_DATE は UTC (audit.sh 出力ファイル参照用)
python3 - "$DATE" "$SUMMARY" "$EXECLOG" "$AUDIT_RC" "$AUDIT_DATE" <<'PY'
import json, os, sys, glob, re
from pathlib import Path

date, summary_path, exec_log, audit_rc, audit_date = sys.argv[1:6]
LOGDIR = Path("logs/security")
audit_rc = int(audit_rc)

def _load(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None

pip_audit = _load(LOGDIR / f"pip-audit-{audit_date}.json")
bandit    = _load(LOGDIR / f"bandit-{audit_date}.json")
gitleaks  = _load(LOGDIR / f"gitleaks-{audit_date}.json")

# ---- known-accepted CVE policy 読み込み ----
# 簡易 YAML 読み取り (PyYAML が無くても最小パーサで動く)
accepted_cves = {}
policy_path = Path("config/security_policy.yaml")
if policy_path.exists():
    try:
        import yaml  # type: ignore
        pol = yaml.safe_load(policy_path.read_text()) or {}
        for ent in pol.get("accepted_cves", []) or []:
            accepted_cves[ent["id"]] = ent
    except ImportError:
        # yaml が入っていない場合の最小パーサ (id と expires だけ拾う)
        current = None
        for ln in policy_path.read_text().splitlines():
            m = re.match(r"\s*-\s*id:\s*(\S+)", ln)
            if m:
                current = m.group(1).strip().strip(chr(34)).strip(chr(39))
                accepted_cves[current] = {"id": current, "expires": None, "rationale": ""}
            elif current:
                m2 = re.match(r"\s*expires:\s*['\"]?([\d-]+)", ln)
                if m2:
                    accepted_cves[current]["expires"] = m2.group(1)
                m3 = re.match(r"\s*rationale:\s*['\"](.+)['\"]", ln)
                if m3:
                    accepted_cves[current]["rationale"] = m3.group(1)

# 期限切れ判定
from datetime import date as _date
today = _date.fromisoformat(date)
def _is_accepted(cve_id):
    ent = accepted_cves.get(cve_id)
    if not ent:
        return False, None
    exp = ent.get("expires")
    if exp:
        try:
            if _date.fromisoformat(exp) < today:
                return False, f"EXPIRED ({exp})"
        except Exception:
            pass
    return True, ent.get("rationale", "")

# ---- pip-audit 集計 (accepted を分離) ----
vulns = []
accepted_vulns = []
for_all = []
if pip_audit and isinstance(pip_audit, dict):
    for d in pip_audit.get("dependencies", []):
        for v in d.get("vulns", []) or []:
            record = {
                "pkg": d.get("name"),
                "ver": d.get("version"),
                "id":  v.get("id"),
                "fix": ", ".join(v.get("fix_versions", []) or []) or "n/a",
                "desc": (v.get("description") or "").strip().replace("\n", " ")[:200],
            }
            is_ok, reason = _is_accepted(record["id"])
            if is_ok:
                record["accepted_reason"] = reason
                accepted_vulns.append(record)
            else:
                if reason and reason.startswith("EXPIRED"):
                    record["expired_note"] = reason
                vulns.append(record)

# ---- bandit 集計 ----
bandit_high = bandit_med = bandit_low = 0
bandit_high_items = []
if bandit and isinstance(bandit, dict):
    for r in bandit.get("results", []):
        sev = r.get("issue_severity", "LOW")
        if sev == "HIGH":
            bandit_high += 1
            bandit_high_items.append(f"{r.get('filename','?')}:{r.get('line_number','?')} — {r.get('issue_text','')[:100]}")
        elif sev == "MEDIUM":
            bandit_med += 1
        else:
            bandit_low += 1

# ---- gitleaks 集計 ----
secrets = []
if gitleaks and isinstance(gitleaks, list):
    for s in gitleaks:
        secrets.append({
            "file": s.get("File"),
            "rule": s.get("RuleID"),
            "line": s.get("StartLine"),
        })

# ---- outdated 集計 ----
outdated_path = LOGDIR / f"outdated-{audit_date}.txt"
outdated_count = 0
if outdated_path.exists():
    outdated_count = sum(1 for ln in outdated_path.read_text().splitlines() if ln.startswith("!"))

# ---- severity 判定 ----
has_critical = any(
    ("CRITICAL" in (v.get("desc","") or "").upper())
    or (v.get("id","").upper().startswith("CVE-") and "critical" in (v.get("desc","") or "").lower())
    for v in vulns
)
has_high = bool(vulns) or bandit_high > 0 or len(secrets) > 0

severity = "CRITICAL" if has_critical else ("HIGH" if has_high else ("MEDIUM" if bandit_med > 0 else "CLEAN"))

# ---- markdown サマリ出力 ----
lines = []
lines.append(f"# ai-chan Security Audit — {date}")
lines.append("")
lines.append(f"- **Severity**: `{severity}`")
lines.append(f"- **Exit Code**: `{audit_rc}`")
lines.append(f"- **Dependencies with vulnerabilities**: {len(vulns)} active, {len(accepted_vulns)} accepted")
lines.append(f"- **Bandit HIGH/MED/LOW**: {bandit_high} / {bandit_med} / {bandit_low}")
lines.append(f"- **Secrets detected (gitleaks)**: {len(secrets)}")
lines.append(f"- **Packages >=2 minor versions behind**: {outdated_count}")
lines.append("")

if vulns:
    lines.append("## 🔴 Dependency CVEs (ACTIVE — 要対応)")
    lines.append("")
    lines.append("| Package | Version | CVE | Fix | Description |")
    lines.append("|---|---|---|---|---|")
    for v in vulns[:50]:
        extra = f" **{v['expired_note']}**" if v.get("expired_note") else ""
        lines.append(f"| {v['pkg']} | {v['ver']} | {v['id']}{extra} | {v['fix']} | {v['desc']} |")
    lines.append("")

if accepted_vulns:
    lines.append("## 🟢 Accepted CVEs (既知受容・severity計算から除外)")
    lines.append("")
    lines.append("| Package | Version | CVE | 受容理由 |")
    lines.append("|---|---|---|---|")
    for v in accepted_vulns[:50]:
        lines.append(f"| {v['pkg']} | {v['ver']} | {v['id']} | {v.get('accepted_reason','')[:120]} |")
    lines.append("")

if bandit_high_items:
    lines.append("## 🔴 Bandit HIGH findings")
    lines.append("")
    for item in bandit_high_items[:20]:
        lines.append(f"- {item}")
    lines.append("")

if secrets:
    lines.append("## 🔴 Secret patterns detected")
    lines.append("")
    for s in secrets[:20]:
        lines.append(f"- `{s['file']}:{s['line']}` — rule: `{s['rule']}`")
    lines.append("")

lines.append("## Raw logs")
lines.append("")
lines.append(f"- pip-audit: `logs/security/pip-audit-{audit_date}.json`")
lines.append(f"- bandit:    `logs/security/bandit-{audit_date}.json`")
lines.append(f"- gitleaks:  `logs/security/gitleaks-{audit_date}.json`")
lines.append(f"- outdated:  `logs/security/outdated-{audit_date}.txt`")
lines.append(f"- exec log:  `{exec_log}`")
lines.append("")

Path(summary_path).write_text("\n".join(lines), encoding="utf-8")

# ---- severity を stdout に出す (後段の shell で使う) ----
# 書式: SEVERITY VULN_COUNT BANDIT_HIGH SECRET_COUNT (スペース区切り1行)
print(f"{severity} {len(vulns)} {bandit_high} {len(secrets)}")
PY

# 最後の行だけ読み取り (サマリ生成済みなので集計情報のみ取得)
# macOS bash 3.2 でも動くよう readarray は使わない
STATS_LINE=$(python3 - "$AUDIT_DATE" "$DATE" <<'PY'
import json, re, sys
from pathlib import Path
from datetime import date as _date
audit_date, today_s = sys.argv[1], sys.argv[2]
LOGDIR = Path("logs/security")

# policy 読み込み
accepted = set()
pol = Path("config/security_policy.yaml")
today = _date.fromisoformat(today_s)
if pol.exists():
    try:
        import yaml
        data = yaml.safe_load(pol.read_text()) or {}
        for e in data.get("accepted_cves", []) or []:
            exp = e.get("expires")
            if exp:
                try:
                    if _date.fromisoformat(exp) < today:
                        continue
                except: pass
            accepted.add(e["id"])
    except ImportError:
        current = None
        current_exp = None
        for ln in pol.read_text().splitlines():
            m = re.match(r"\s*-\s*id:\s*(\S+)", ln)
            if m:
                if current and (not current_exp or current_exp >= today_s):
                    accepted.add(current)
                current = m.group(1).strip().strip(chr(34)).strip(chr(39))
                current_exp = None
            elif current:
                m2 = re.match(r"\s*expires:\s*['\"]?([\d-]+)", ln)
                if m2: current_exp = m2.group(1)
        if current and (not current_exp or current_exp >= today_s):
            accepted.add(current)

def _load(p):
    try: return json.loads(Path(p).read_text())
    except: return None
pip_audit = _load(LOGDIR / f"pip-audit-{audit_date}.json")
bandit    = _load(LOGDIR / f"bandit-{audit_date}.json")
gitleaks  = _load(LOGDIR / f"gitleaks-{audit_date}.json")

vulns = []
for d in (pip_audit or {}).get("dependencies", []):
    for v in d.get("vulns", []) or []:
        if v.get("id") not in accepted:
            vulns.append(v)

bandit_high = sum(1 for r in (bandit or {}).get("results", []) if r.get("issue_severity") == "HIGH")
secrets = len(gitleaks) if isinstance(gitleaks, list) else 0
has_crit = any("critical" in (v.get("description","") or "").lower() for v in vulns)
sev = "CRITICAL" if has_crit else ("HIGH" if (vulns or bandit_high or secrets) else "CLEAN")
print(f"{sev} {len(vulns)} {bandit_high} {secrets}")
PY
)

SEVERITY=$(echo "$STATS_LINE" | awk '{print $1}')
VULN_COUNT=$(echo "$STATS_LINE" | awk '{print $2}')
BANDIT_HIGH=$(echo "$STATS_LINE" | awk '{print $3}')
SECRET_COUNT=$(echo "$STATS_LINE" | awk '{print $4}')
SEVERITY="${SEVERITY:-UNKNOWN}"
VULN_COUNT="${VULN_COUNT:-0}"
BANDIT_HIGH="${BANDIT_HIGH:-0}"
SECRET_COUNT="${SECRET_COUNT:-0}"

# ─── 3. 通知 (HIGH/CRITICAL のみ) ──────────────────────────
if [ "$SEVERITY" = "CRITICAL" ] || [ "$SEVERITY" = "HIGH" ]; then
  TITLE="ai-chan Security: $SEVERITY"
  MSG="CVE=$VULN_COUNT Bandit-HIGH=$BANDIT_HIGH Secrets=$SECRET_COUNT — $SUMMARY"

  # macOS 通知センター
  osascript -e "display notification \"$MSG\" with title \"$TITLE\" sound name \"Basso\"" 2>/dev/null || true

  # Mail.app 経由でメール送信
  bash scripts/notify_mail.sh "$NOTIFY_EMAIL" "[ai-chan] $TITLE ($DATE)" "$SUMMARY" "$SEVERITY" || true
else
  # CLEAN 時も通知センターに控えめに出す
  osascript -e "display notification \"All clean ($VULN_COUNT CVEs, $BANDIT_HIGH HIGH, $SECRET_COUNT secrets)\" with title \"ai-chan Security: CLEAN\"" 2>/dev/null || true
fi

# ─── 4. SECURITY.md 変更履歴に追記 ─────────────────────────
if [ -f "docs/SECURITY.md" ]; then
  ENTRY="- $DATE : 自動監査 $SEVERITY (CVE=$VULN_COUNT HIGH=$BANDIT_HIGH Secrets=$SECRET_COUNT)"
  # "## 7. 変更履歴" の直後に挿入 (既に同じ日付があればスキップ)
  if ! grep -q "^- $DATE : 自動監査" docs/SECURITY.md 2>/dev/null; then
    python3 - <<PY
from pathlib import Path
p = Path("docs/SECURITY.md")
txt = p.read_text()
marker = "## 7. 変更履歴"
if marker in txt:
    head, _, tail = txt.partition(marker)
    # マーカー直後の空行を飛ばして最初のリスト項目の前に挿入
    lines = tail.split("\n")
    # 先頭の marker 行は既に partition で分離済み。以降の空行を追加
    out = [marker]
    i = 1
    while i < len(lines) and lines[i].strip() == "":
        out.append(lines[i]); i += 1
    out.append("$ENTRY")
    out.extend(lines[i:])
    p.write_text(head + "\n".join(out))
PY
  fi
fi

echo "[daily_security_audit] done: severity=$SEVERITY summary=$SUMMARY"
exit 0

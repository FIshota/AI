#!/usr/bin/env bash
# ai-chan 週次セキュリティサマリ
# 直近 7 日間の日次監査結果を集約して 1 通のメールにまとめる
# 実行: 毎週日曜 09:30 JST (launchd)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DATE=$(date +%Y-%m-%d)
WEEK_START=$(date -v-6d +%Y-%m-%d 2>/dev/null || date -d "6 days ago" +%Y-%m-%d)
LOGDIR="logs/security"
SUMMARY="$LOGDIR/weekly-$DATE.md"
NOTIFY_EMAIL="${AICHAN_ADMIN_EMAIL:-honnsipittu@gmail.com}"

mkdir -p "$LOGDIR"

# 過去 7 日の日次サマリを読み込んで集計
python3 - "$WEEK_START" "$DATE" "$SUMMARY" <<'PY'
import sys, re, json
from pathlib import Path
from datetime import date, timedelta

week_start_s, today_s, summary_path = sys.argv[1:4]
week_start = date.fromisoformat(week_start_s)
today = date.fromisoformat(today_s)
LOGDIR = Path("logs/security")

# 各日のサマリを収集
rows = []
cve_counter = {}
severity_counter = {"CLEAN": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0, "UNKNOWN": 0}
active_cve_days = 0

d = week_start
while d <= today:
    p = LOGDIR / f"{d.isoformat()}.md"
    if p.exists():
        txt = p.read_text()
        m_sev = re.search(r"Severity.*?`(\w+)`", txt)
        m_act = re.search(r"Dependencies with vulnerabilities.*?:\s*(\d+)\s*active,\s*(\d+)\s*accepted", txt)
        m_bh  = re.search(r"Bandit HIGH/MED/LOW.*?:\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", txt)
        m_sec = re.search(r"Secrets detected.*?:\s*(\d+)", txt)
        sev = m_sev.group(1) if m_sev else "UNKNOWN"
        severity_counter[sev] = severity_counter.get(sev, 0) + 1
        active = int(m_act.group(1)) if m_act else 0
        accepted = int(m_act.group(2)) if m_act else 0
        bh = int(m_bh.group(1)) if m_bh else 0
        secrets = int(m_sec.group(1)) if m_sec else 0
        if active > 0:
            active_cve_days += 1
        rows.append((d.isoformat(), sev, active, accepted, bh, secrets))
        # CVE ID を収集
        for cve in re.findall(r"CVE-\d{4}-\d+", txt):
            cve_counter[cve] = cve_counter.get(cve, 0) + 1
    else:
        rows.append((d.isoformat(), "MISSING", 0, 0, 0, 0))
    d += timedelta(days=1)

# マークダウン出力
out = []
out.append(f"# ai-chan Weekly Security Summary")
out.append(f"**Period**: {week_start_s} ~ {today_s}")
out.append("")
out.append(f"- 実行日数: {sum(1 for r in rows if r[1] != 'MISSING')} / {len(rows)}")
out.append(f"- CLEAN: {severity_counter.get('CLEAN',0)} 日")
out.append(f"- MEDIUM: {severity_counter.get('MEDIUM',0)} 日")
out.append(f"- HIGH: {severity_counter.get('HIGH',0)} 日")
out.append(f"- CRITICAL: {severity_counter.get('CRITICAL',0)} 日")
out.append(f"- 未実行: {severity_counter.get('UNKNOWN',0) + sum(1 for r in rows if r[1] == 'MISSING')} 日")
out.append(f"- 新規 Active CVE が検出された日数: {active_cve_days}")
out.append("")

out.append("## 日次推移")
out.append("")
out.append("| 日付 | severity | Active CVE | Accepted CVE | Bandit HIGH | Secrets |")
out.append("|---|---|---|---|---|---|")
for r in rows:
    out.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")
out.append("")

if cve_counter:
    out.append("## 期間中に観測された CVE")
    out.append("")
    out.append("| CVE | 日数 |")
    out.append("|---|---|")
    for cve, cnt in sorted(cve_counter.items(), key=lambda x: -x[1]):
        out.append(f"| {cve} | {cnt} |")
    out.append("")

# 判定
if severity_counter.get("CRITICAL", 0) > 0:
    verdict = "🚨 CRITICAL detected this week"
elif active_cve_days > 0:
    verdict = "⚠️ Active CVEs observed — review accepted_cves policy"
elif severity_counter.get("UNKNOWN", 0) + sum(1 for r in rows if r[1] == "MISSING") > 2:
    verdict = "⚠️ Audit missed 3+ days — verify launchd health"
else:
    verdict = "✅ All clear this week"

out.insert(2, f"- **判定**: {verdict}")

Path(summary_path).write_text("\n".join(out) + "\n", encoding="utf-8")
print(verdict)
PY

VERDICT=$(tail -c 200 /dev/null 2>&1; bash -c "cat $SUMMARY" | grep -m1 "判定" | sed 's/.*判定.*: //' || echo "summary")

# メール送信 (必ず送信 — 週次レポートは情報として有用)
bash scripts/notify_mail.sh "$NOTIFY_EMAIL" "[ai-chan] Weekly Security Summary ($DATE)" "$SUMMARY" "WEEKLY" || true

# macOS 通知
osascript -e "display notification \"Weekly summary generated: $SUMMARY\" with title \"ai-chan Security: Weekly\"" 2>/dev/null || true

echo "[weekly_security_summary] done: $SUMMARY"
exit 0

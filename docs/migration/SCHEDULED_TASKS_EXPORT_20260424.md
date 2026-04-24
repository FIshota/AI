# SCHEDULED TASKS EXPORT — 2026-04-24

> 現在登録されている Claude Code scheduled-tasks の完全エクスポート。
> 各タスクの SKILL.md 全文を添付し、新 PC での再登録手順を末尾に記載。

**登録場所**: `~/.claude/scheduled-tasks/<task-id>/SKILL.md`

---

## 一覧

| ID | cron / 頻度 | 状態 | 用途 |
|----|-------------|------|------|
| `ai-chan-daily-morning` | 毎朝 07:00 JST | ✅ アクティブ | 回帰テスト + 学習更新 + セキュリティ監査 (統合) |
| `ai-chan-daily-security-audit` | 毎朝 09:00 JST | ✅ アクティブ | 脆弱性 / 依存 / 監査 (単体) |
| `ai-chan-weekly-security-summary` | 月 08:30 JST | ✅ アクティブ | 週次セキュリティ集約 |
| `ai-chan-health-check` | 3 時間毎 | ✅ アクティブ | import / config / checkpoint smoke |
| `hinomoto-training-watchdog` | 30 分毎 | ✅ アクティブ | 訓練 NaN / OOM / 停滞検知 |
| `hinomoto-checkpoint-integrity` | 日次 03:00 | ✅ アクティブ | ckpt SHA-256 記録・破損検知 |
| `ai-chan-daily-learning` | — | 🗑️ SUPERSEDED by daily-morning Phase 2 | 旧: 学習データ更新 |
| `ai-chan-daily-security-scan` | — | 🗑️ DEPRECATED | 重複のため無効化 |
| `ai-chan-test-regression` | — | 🗑️ SUPERSEDED by daily-morning Phase 1 | 旧: pytest 回帰 |

移管時は **アクティブ 6 件のみ再登録すれば十分**。deprecated 3 件はコピー不要 (履歴として残す場合のみ)。

---

## 1. ai-chan-daily-morning

**頻度**: 毎朝 07:00 JST
**description**: ai-chan 毎朝 07:00 JST 統合タスク: pytest回帰 → 学習更新 → セキュリティ監査 (失敗隔離付き)

### SKILL.md (全文)
```markdown
---
name: ai-chan-daily-morning
description: ai-chan 毎朝 07:00 JST 統合タスク: pytest回帰 → 学習更新 → セキュリティ監査 (失敗隔離付き)
---

あなたは ai-chan の毎朝メンテナンス担当です。以下 3 フェーズを**順に**実行してください。
**失敗隔離**: 各フェーズは独立して try/except 的に扱い、1 フェーズ失敗しても次フェーズを必ず実行。

## 共通情報
- プロジェクト: `/Users/fujihiranoborudai/Downloads/agent/ai-chan`
- 統合ログ: `logs/daily_morning/YYYY-MM-DD.log` (JST)
- フェーズ別ログは従来どおり各所に残す (後方互換・週次サマリが参照)
  - `logs/regression/`, `data/learning_log.jsonl`, `logs/security_audit/`
- ログ無ければディレクトリを作成
- 各フェーズ開始/終了時刻を統合ログに記録

## 実行冒頭
\`\`\`bash
cd /Users/fujihiranoborudai/Downloads/agent/ai-chan
mkdir -p logs/daily_morning logs/regression logs/security_audit
MASTER_LOG=logs/daily_morning/$(date +%Y-%m-%d).log
{
  echo "=========================================="
  echo "ai-chan Daily Morning — $(date -u +%Y-%m-%dT%H:%M:%SZ) (UTC)"
  echo "                        $(date +%Y-%m-%dT%H:%M:%S%z) (JST)"
  echo "=========================================="
} >> "$MASTER_LOG"
\`\`\`

## Phase 1: pytest 回帰 + カバレッジ
1. `LOG=logs/regression/pytest-$(date +%Y%m%d).log`
2. `python -m pytest -q --maxfail=5 --cov=core --cov=utils --cov=ui --cov-report=term-missing --cov-report=json:logs/regression/coverage-$(date +%Y%m%d).json 2>&1 | tee "$LOG"`
3. 結果解析: passed / failed / skipped / total + `totals.percent_covered`
4. `logs/regression/summary-$(date +%Y%m%d).json` に保存
5. **80% 割れ** or **failed>0** → `ALERT-$(date +%Y%m%d).md` に追記
6. 統合ログに `=== PHASE 1 END passed=P failed=F cov=C% ===`

## Phase 2: 学習データ更新
1. `python3.13 scripts/daily_learning_update.py`
2. 今日の GitHub トレンドを曜日別言語で追加 (月Python / 火TS / 水Rust / 木Go / 金JS / 土Swift / 日Kotlin)
3. 今日のセキュリティ情報チェック (CVE)
4. `data/learning_log.jsonl` に一行追記
5. 安全チェック: 個人情報/APIキー/認証情報を絶対含めない

## Phase 3: セキュリティ監査
3-1. pip-audit 脆弱性スキャン (`python -m pip_audit -r requirements.txt --format json`)
     既知 mitigated (CVE-2025-69872 diskcache) は `ACKNOWLEDGED`
3-2. 依存更新チェック (`pip list --outdated`) — UPGRADE_HOLD / MAJOR / BUMP 分類
3-3. bandit (`python -m bandit -r core/ utils/ ui/ scripts/`) HIGH/MED/LOW 集計
3-4. Model Policy: `qwen|deepseek|yi-|chatglm|internlm|baichuan|moonshot|kimi` 検出
3-5. シークレット漏洩: `git ls-files | grep -E '\.env$|credentials\.json$|\.key$|\.pem$'`
     + コード内 `sk-[A-Za-z0-9]{20,}`, `AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{30,}`
3-6. ログローテーション: 90 日超→gzip、365 日超→削除
3-7. SUMMARY ブロック書き出し

## 最終報告 (15 行以内)
Phase 1/2/3 の要点 + 統合ログ絶対パス。
⚠️ 要対応フラグ条件: Phase 1 failed>0/cov<80%, Phase 3 未ack HIGH / bandit HIGH 増加 / POLICY VIOLATION / 漏洩

## 方針
- 破壊的操作禁止 (ログローテのみ例外)
- 冪等性: 同日複数回追記可
- 失敗隔離: 1 フェーズ死んでも他は動く
```

---

## 2. ai-chan-daily-security-audit

**頻度**: 毎朝 09:00 JST
**description**: ai-chan 脆弱性スキャン・依存更新チェック・セキュリティ監査を毎朝9時(JST)実行

### SKILL.md 要約 (全文は `~/.claude/scheduled-tasks/ai-chan-daily-security-audit/SKILL.md`)
```
対象: /Users/fujihiranoborudai/Downloads/agent/ai-chan
ログ: logs/security_audit/YYYY-MM-DD.log (追記式)

STEP 1: pip list --outdated --format=columns
STEP 2: python3 -m pip_audit -r requirements.txt --desc
STEP 3: grep -rEn "(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{8,}"
         --include="*.py" --include="*.json" --include="*.yaml"
         (test_ / example / placeholder / YOUR_ / XXX 除外)
STEP 4: python3 -m bandit -r <repo> -ll -x tests,__pycache__
STEP 5: find -maxdepth 4 (.env* / memory/ / config/) -exec ls -la
         .env* が 600 以外、memory/ が 600/700 以外 → ⚠️
STEP 6: SUMMARY (Outdated / Vulns / Secrets / Bandit / Perms / Overall PASS|WARN|FAIL)

判定: CRITICAL ≥1 or HIGH ≥3 → FAIL / 何らかの警告 → WARN / 全ゼロ → PASS

禁止: git commit/push、requirements.txt 書き換え、外部送信 (pip-audit CVE DB 取得は許可)
```

---

## 3. ai-chan-weekly-security-summary

**頻度**: 毎週月曜 08:30 JST
**description**: 直近7日間の daily audit ログを集約しトレンドレポート生成

### SKILL.md 要約
```
入力: logs/security_audit/YYYY-MM-DD.log (過去7日)
出力: logs/security_audit/weekly/YYYY-WW.md (ISO週番号)

手順:
1. 直近7日ログ収集 (無ければ [INFO] no daily logs found で終了)
2. SUMMARY ブロック抽出: vulns (total/ack), outdated (bump/major/held),
   bandit H/M/L, policy violations, secret leaks
3. Markdown レポート生成: Daily Snapshot 表 + Trend (w/w) + Action Items + Raw References
4. 通知判定: 新規 HIGH 脆弱性 / 連続 POLICY VIOLATION / LEAK → ⚠️ 週次アラート

方針: daily log を読むだけ、変更しない。パース失敗は N/A で続行。

報告 3 項目: レポート MD 絶対パス / HIGH 件数 (先週比) / アラートフラグ
```

---

## 4. ai-chan-health-check

**頻度**: 3 時間毎
**description**: ai-chan import smoke / 設定整合性 / checkpoint 存在チェック

### SKILL.md (全文)
```markdown
---
name: ai-chan-health-check
description: ai-chan import smoke / 設定整合性 / checkpoint 存在チェック (3時間毎)
---

ai-chan (/Users/fujihiranoborudai/Downloads/agent/ai-chan) の健全性を 3 時間毎に点検してください。

## 手順
1. `cd /Users/fujihiranoborudai/Downloads/agent/ai-chan`
2. `mkdir -p logs/health` / `LOG=logs/health/health-$(date +%Y%m%d).log`
3. Import smoke: 以下を順に `python -c "import X"`:
   - core.ai_chan, core.memory, core.emotion, core.llm, core.scheduler, core.diary
   - utils.crypto, utils.portable
   - ui.cli
4. 設定整合性: persona.json / settings.json を json.load で parse、必須キー検証
5. モデル/Checkpoint: settings.json の model_path 存在 & サイズ
6. ディスク使用: du -sh memory/ logs/ artifacts/
7. Git 状態: git status --porcelain | wc -l, git log -1 --format='%h %s'
8. JSON サマリを $LOG 末尾追記
9. 異常時 ALERT-$(date +%Y%m%d-%H).md に詳細
10. 3 行以内で "OK: imports=N/N, config=ok, model=<size>"

## 重要
- 書き込み操作なし、修復アクションもなし (検出のみ)
```

---

## 5. hinomoto-training-watchdog

**頻度**: 30 分毎
**description**: HinoMoto 訓練ログの NaN / 発散 / OOM / 停滞検知

### SKILL.md (全文)
```markdown
---
name: hinomoto-training-watchdog
description: HinoMoto 訓練ログの NaN / 発散 / OOM / 停滞検知 (30分毎)
---

## 手順
1. cd /Users/fujihiranoborudai/Downloads/agent/hinomoto-model
2. mkdir -p logs/watchdog / LOG=logs/watchdog/watchdog-$(date +%Y%m%d).log
3. artifacts/ 配下最新ログを ls -lt artifacts/*.log | head -5
4. 各ログ末尾 200 行を走査し検出:
   - NaN / inf: `nan|NaN|inf |Inf `
   - train_loss 発散: 直近 10 step で 1.5 倍以上
   - val_loss 発散: 前回より 10% 以上悪化
   - OOM: `OutOfMemoryError|CUDA out of memory|killed`
   - 停滞: mtime 15 分超更新なし & `pgrep -f train_lm` で PID あり
5. $LOG に JSON サマリ追記
6. 異常時 ALERT-$(date +%Y%m%d-%H%M).md
7. 正常時 "OK: N logs, latest loss=X, val_ppl=Y"

## 重要
- 訓練プロセスへの干渉 (kill 等) は行わない
- read-only 調査のみ
```

---

## 6. hinomoto-checkpoint-integrity

**頻度**: 日次 03:00 JST
**description**: HinoMoto checkpoint SHA256 記録・破損/サイズ急変検知

### SKILL.md (全文)
```markdown
---
name: hinomoto-checkpoint-integrity
description: HinoMoto checkpoint SHA256 記録・破損/サイズ急変検知 (日次 03:00)
---

## 手順
1. cd /Users/fujihiranoborudai/Downloads/agent/hinomoto-model
2. mkdir -p logs/checkpoint-integrity
3. DB=logs/checkpoint-integrity/registry.jsonl (追記式 JSONL)
4. 対象: find artifacts -type f -name "*.pt" -size +1M
5. 各ファイル {ts, path, size_bytes, sha256, mtime} を記録
   - shasum -a 256 <path>
6. 前回記録と比較:
   - サイズ急変 (10% 超減少) → WARN
   - hash 変化 (mtime 不変なのに hash 変化) → ALERT
   - ファイル消失 → WARN
7. summary-$(date +%Y%m%d).md に対象数/合計サイズ/新規/消失/サイズ急変
8. 異常時 ALERT-$(date +%Y%m%d).md

## 重要
- read-only, ckpt 削除・変更一切しない
- 2GB 以上は先頭 256MB 部分 hash 可 (partial: true フラグ)
```

---

## 新 PC での再登録手順

### 方式 A: ファイルコピー + MCP 再登録

1. 旧 PC で `~/.claude/scheduled-tasks/` を外部ディスクへ rsync
   ```
   rsync -av ~/.claude/scheduled-tasks/ /Volumes/Migration/scheduled-tasks/
   ```
2. 新 PC で復元
   ```
   mkdir -p ~/.claude/scheduled-tasks
   rsync -av /Volumes/Migration/scheduled-tasks/ ~/.claude/scheduled-tasks/
   ```
3. 不要な deprecated 3 件 (daily-learning / daily-security-scan / test-regression) は削除可
4. Claude Code を起動し `mcp__scheduled-tasks__list_scheduled_tasks` で認識を確認
5. MCP 側のスケジュール (cron) 情報は設定ファイル管理されている場合、Claude Code が自動再検出

### 方式 B: MCP 経由で 1 件ずつ再作成

各タスクについて `mcp__scheduled-tasks__create_scheduled_task` を呼ぶ (スキーマに応じて `name / cron / prompt` を指定)。本ドキュメントの SKILL.md 全文を `prompt` に流用。

### 方式 C: launchd plist と scheduled-tasks の双方確認

macOS 固有の LaunchAgent (`~/Library/LaunchAgents/com.aichan.security-*.plist`) は別系統のスケジューラなので、それぞれ:
```
launchctl unload ~/Library/LaunchAgents/com.aichan.security-audit.plist   # 旧 PC で停止
# コピー
launchctl load   ~/Library/LaunchAgents/com.aichan.security-audit.plist   # 新 PC で起動
launchctl load   ~/Library/LaunchAgents/com.aichan.security-weekly.plist
```

### 検証チェックリスト
- [ ] `ls ~/.claude/scheduled-tasks/` で 6 件 (最低) が表示される
- [ ] `launchctl list | grep aichan` が 2 件表示
- [ ] 次回実行時刻に期待通り走る (`logs/*/` に出力)
- [ ] `ai-chan-health-check` が 3 時間以内に 1 回走り `logs/health/` が生成
- [ ] `hinomoto-training-watchdog` が 30 分以内に 1 回走り `logs/watchdog/` が生成

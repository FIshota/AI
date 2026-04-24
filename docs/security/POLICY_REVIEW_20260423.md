# Security Policy Review 2026-04-23

**レビュー実施日**: 2026-04-23
**対象ファイル**: `config/security_policy.yaml`
**レビュー方法**: 自動 + 手動確認

---

## サマリ

| 項目 | 件数 | 状態 |
|---|---|---|
| accepted_cves | 2 | 全件有効 (期限内) |
| 期限切れ | 0 | — |
| mitigation 無効化 | 0 | — |
| accepted_bandit | 0 | — |
| accepted_outdated | 0 | — |

**結論**: 全 entry 有効。policy 変更不要。

---

## 個別確認

### CVE-2025-69872 (diskcache)

| 項目 | 値 |
|---|---|
| 期限 | 2026-10-20 |
| 今日時点の残日数 | **180 日** |
| rationale | diskcache の pickle による RCE (LLM キャッシュ内部使用のみ) |
| mitigation | `_secure_cache_dir()` / `_harden_llm_cache()` でディレクトリ権限 0o700、.pkl 自動除去 |
| mitigation 確認 | `core/llm.py::_secure_cache_dir` 実装継続中 — 手動コード確認で変更なし |
| 判定 | **受容継続** |

### CVE-2026-1839 (transformers.Trainer RCE)

| 項目 | 値 |
|---|---|
| 期限 | 2026-07-20 |
| 今日時点の残日数 | **88 日** |
| rationale | `Trainer._load_rng_state()` の RCE、ai-chan は Trainer 未使用 |
| mitigation | `transformers.Trainer` API を呼び出していないことを静的に保証 |
| mitigation 確認 | `grep -r 'from transformers.*Trainer\|transformers\.Trainer' ai-chan/` → **0 件** (policy.yaml 自体のコマンド例を除く) |
| 判定 | **受容継続** |

---

## 次回レビュータイミング

- **2026-07-20 までに**: CVE-2026-1839 を再評価。transformers 6.x へ移行 or upstream 修正反映で自動解消見込み。
- **2026-10-20 までに**: CVE-2025-69872 を再評価。diskcache upstream の進展確認。
- **緊急**: daily_security_audit.sh で受容済み CVE の mitigation が破綻した場合は即時 HIGH として通知 (policy 既定の挙動)。

---

## 参考: 日次監査との関係

`scripts/daily_security_audit.sh` (毎朝 9:00 JST, launchd) が pip-audit + bandit を回し、本ファイルの accepted_cves を参照して severity を下げる。
本 policy の整合が取れなくなった時点で、日次サマリに Accepted セクションで明示される。

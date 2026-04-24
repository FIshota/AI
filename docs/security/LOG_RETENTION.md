# ログ保持ポリシー (Log Retention Policy)

> `logs/` 配下の各ログ種別について、保持期間 / 削除契機 / purge_subject との連携を定める。
>
> 原則:
> - **監査ログ (audit / system)** は長期保持 (改竄検知・インシデント対応のため)。
> - **ユーザ由来ログ (user-derived)** は短期保持 (VALUES.md「消す権利」/ GDPR「削除の権利」と整合)。
> - **デバッグログ (debug)** は揮発的 (解析が終われば即捨てる)。

---

## 1. ログ種別と保持期間

| 種別 | 例 (ディレクトリ) | 保持期間 | 根拠 |
|---|---|---|---|
| **audit** (監査) | `logs/killswitch_drills/`, `logs/backup_restore_drills/`, `logs/security_audit/`, `logs/security/` | **7 年 (2555 日)** | 監査要件 / SOC2 / 事後検証のため長期保持。tamper-evident (`core.audit_chain`)。 |
| **system** (運用) | `logs/health/`, `logs/benchmarks/`, `logs/docker_image_hashes/`, `logs/regression/`, `logs/archive/` | **1 年 (365 日)** | 性能劣化や回帰の傾向把握に必要。個人情報は含まない想定。 |
| **diagnostic** (診断) | `logs/flaky/`, `logs/api-docs/` | **1 年 (365 日)** | 非決定性テストの傾向解析。ローテーションして長期肥大を避ける。 |
| **user-derived** (ユーザ由来) | `logs/llm_worker.jsonl` 系, `logs/sessions/` (将来) | **90 日** | 会話ログ・入出力はユーザ個人情報を含みうる。短期保持 + purge_subject で即削除。 |
| **debug** (デバッグ) | `logs/debug/`, `logs/phase1_full_run.log` | **14 日 / セッションのみ** | 一時的な診断用途。長期保管禁止。 |

> `logs/archive/` 内の古いスナップショットは、元々の種別に従う (archive は格納場所にすぎない)。

---

## 2. 自動削除フロー

1. **月次 launchd** (`com.aichan.log-retention.plist`): 毎月 1 日 02:00 JST に `scripts/log_retention_sweep.py --apply` を実行。
2. **dry-run が既定**: 手動実行 (`python scripts/log_retention_sweep.py`) では `--dry-run` で候補を列挙するのみ。誤削除を防ぐ。
3. **audit_chain に記録**: 削除アクションは `logs/security_audit/` の hash-chain に追記され、後から検証可能。
4. **削除対象はファイルのみ**: ディレクトリ構造は残す (ポリシー適用先が消えないように)。

---

## 3. purge_subject との連携

`core.subject_rights.SubjectRightsManager.purge_subject()` が呼ばれた場合:

1. **ユーザ由来ログ**は subject_id に紐づくエントリを**即時削除** (保持期間を待たない)。
2. **audit ログ**は subject_id に関する**参照 (削除を実行した事実)** を残す — これは「消す権利」より優先される監査要件。
   - 具体的な個人データは含めず、ハッシュ化された subject_id のみ保持。
3. **debug ログ**は全削除 (内容を問わない)。

> 詳細は `docs/THREAT_MODEL.md` および `SECURITY.md` の「消す権利」節を参照。

---

## 4. ポリシー設定ファイル

`config/log_retention.yaml` でディレクトリごとに上書き可能。未設定ディレクトリは**削除対象外** (安全側に倒す)。

```yaml
policies:
  logs/killswitch_drills:
    max_age_days: 2555   # 7 年 (audit)
  logs/flaky:
    max_age_days: 365    # 1 年 (diagnostic)
  logs/debug:
    max_age_days: 14     # 14 日 (debug)
```

---

## 5. 運用チェックリスト

- [ ] 新しい `logs/<X>/` を作る場合は必ず `config/log_retention.yaml` に登録する
- [ ] 保持期間の変更は PR レビュー必須 (監査証跡への影響があるため)
- [ ] 四半期ごとに `logs/` 実ディスク使用量をモニタし、ポリシー妥当性を再評価
- [ ] `purge_subject` 実装変更時は本ドキュメントも更新

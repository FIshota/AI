# Multi-Tenant Isolation (H2 / 5.6)

Ai-chan は原則「1 家族 1 インスタンス」だが、開発/テスト/共有端末では
同一ホスト上に複数テナントが共存することがある。本書はその場合の
**FS 分離保証**と脅威モデルを規定する。

関連モジュール:

- `core/tenant_context.py` — root-scoped 物理分離 (本書の実装)
- `core/tenant.py` — 論理識別子 `TenantId` / `tenant_dir`
- `utils/crypto.py` — 暗号化 (別レイヤー, AES-256-GCM)
- `core/audit_chain.py` — 改竄検知ログ (テナント別 audit_dir に配置)
- `scripts/tenant_admin.py` — 運用 CLI

## 1. 脅威モデル

| # | 脅威 | 対策レイヤー |
|---|------|-------------|
| T1 | 同居テナント間の情報漏洩 (read across) | `TenantContext.root_dir` による FS 分離 + `guard_path` |
| T2 | path-traversal (`../`) による read/write | `guard_path` の lexical + `resolve()` 二重検査 |
| T3 | シンボリックリンク攻撃 (link target が root 外) | `guard_path` が symlink を lstat で追跡し拒否 |
| T4 | 並行書き込み時のクロス汚染 | tenant ごとに完全に独立した sub-tree。共有状態なし |
| T5 | 誤 purge で他テナントを巻き添え | `purge_tenant` は `tenant_id` 正規化 + base 外脱出検査 + dry-run 既定 |
| T6 | tenant_id 偽装 (UPPERcase / Unicode / null byte) | `^[a-z0-9_-]{3,32}$` のみ許可 |
| T7 | 長期運用 (10 年) の肥大化・退会ユーザー残存 | purge + export ポリシー (下記 §4) |

**スコープ外** (別レイヤーで担保):

- プロセス境界 (ptrace / /proc) — OS 権限分離
- ネットワーク分離 — 別ホスト/別コンテナ推奨
- サイドチャネル (タイミング / キャッシュ) — 本書では扱わない
- ストレージ暗号化 — `utils/crypto.py` で別途 AES-256-GCM

## 2. FS 分離保証

各テナントは以下の木構造を持つ:

```
<base>/
  <tenant_id>/          ← root_dir
    memory/             ← SQLite + JSON (記憶・感情履歴)
    config/             ← persona.json / settings.json
    logs/               ← アプリケーションログ
    data/               ← diary, その他派生データ
    audit/              ← audit_chain エントリ
```

**不変条件**:

1. `TenantContext.guard_path(p)` を通さない I/O は行わない。
2. tenant_id は `^[a-z0-9_-]{3,32}$` の外では一切生成されない。
3. `create_isolated` は冪等。既存 root を再利用しても他テナントに影響しない。
4. purge は `tenant_id` の正規化を経た上で `base` 内だけを削除する。

## 3. 並行書き込み

テナント間で共有する可変状態は持たない。したがって A の書き込みが
B に波及する経路は存在しない。`test_multi_tenant_e2e.py` で
threading による 100 件 × 2 並列書き込みを行い、
クロス汚染件数 = 0 を機械的に検証している。

SQLite は tenant 別ファイル (`memory/memory.db`) なので
WAL の write lock も tenant ローカル。

## 4. 10 年運用ポリシー

- **退会 (purge)**: `tenant_admin.py --purge <id> --confirm`。
  dry-run を既定とし、誤実行を物理的に防ぐ。
- **export**: 本人/家族の要求に応じて `root_dir` ごと tar + 暗号化して
  本人に返却 (GDPR-like / subject rights 連携)。
- **保持**: audit_chain の append-only 性質は tenant 内に閉じる。
  ハッシュ連鎖は tenant を跨がない。
- **バックアップ**: テナントごとに `scripts/backup_restore_drill.sh`
  相当を流し、復元も tenant 単位で行う。

## 5. レビュー / 運用チェックリスト

- [ ] 新規 I/O を追加するとき `guard_path` を通したか
- [ ] tenant_id をユーザー入力から取るとき `InvalidTenantIdError` を
      UI 側で握りつぶしていないか
- [ ] purge を自動スクリプトで叩く箇所で `--confirm` を意図的に付けたか
- [ ] audit_chain が tenant の `audit_dir` に書かれているか (root 外に
      漏れていないか)

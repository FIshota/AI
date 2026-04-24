# ai-chan Gitleaks カスタムルール

本ドキュメントは `/.gitleaks.toml` に追加した HinoMoto / ai-chan 固有のルール一覧とその運用方針を示す。
デフォルトルール (`useDefault = true`) に append する形で定義されており、既存検出ロジックには影響しない。

> スキャン手順:
>
> ```bash
> ~/.local/bin/gitleaks detect \
>   --source /path/to/ai-chan \
>   --config /path/to/ai-chan/.gitleaks.toml \
>   --no-git --verbose --redact
> ```

## ルール一覧

### 1. `hinomoto_sqlite_db_filename_leak`

- **検知対象**: `memories.db` / `emotion_history.db` / `diary.db` の SQLite ファイル名がソース/ドキュメント中に現れる。
- **目的**: 暗号化済みユーザーメモリ DB ファイルの公開リポジトリへの混入や、運用経路のハードコード流出を防ぐ。
- **allowlist**: `core/`, `utils/`, `scripts/`, `tests/`, `docs/`, `docs/security/`, `docs/adr/`, `ROADMAP.md`, `SECURITY.md`, `Makefile`, `.gitleaks.toml`。
- **誤検知対応**: パスを定義する単一のモジュール (`core/secure_store.py` 等) 以外から文字列定数が漏れたらリファクタ候補。どうしても必要な場合は上記 allowlist の `paths` に追加。

### 2. `hinomoto_user_absolute_home_path`

- **検知対象**: `/Users/fujihiranoborudai/` で始まる開発者ローカル絶対パス。
- **目的**: 個人情報 (ユーザー名) および環境依存パスの固定化を防止。設定は環境変数・`~` 展開などで抽象化する。
- **allowlist**: `SECURITY.md`, `NOTICE`, `docs/LICENSE_MODEL_DRAFT.md`, `docs/security/`, `docs/adr/`, このドキュメント自身、`.gitleaks.toml`、`tests/test_gitleaks_rules.py`。
- **誤検知対応**: どうしても文書内にパスを載せる必要がある場合、上記 allowlist の `paths` に該当ファイルの正規表現を追加。

### 3. `hinomoto_owner_email_leak`

- **検知対象**: 所有者メール `honnsipittu@gmail.com` の文字列。
- **目的**: 連絡先メールの不用意な拡散防止。公開を意図した箇所 (SECURITY, NOTICE, ライセンス草案) のみに限定する。
- **allowlist**: `SECURITY.md`, `NOTICE`, `docs/LICENSE_MODEL_DRAFT.md`, `.gitleaks.toml`, `tests/test_gitleaks_rules.py`, `docs/security/GITLEAKS_CUSTOM_RULES.md`。
- **誤検知対応**: 新しい公開ドキュメントで連絡先記載が必要なら、allowlist の `paths` に追加。それ以外はコードから削除し、issue tracker 経由に置き換える。

### 4. `hinomoto_vision_internal_marker`

- **検知対象**: `VISION_INTERNAL` / `VISION_INTERNAL.md` マーカー文字列。
- **目的**: 内部ビジョンドキュメントがログ・公開成果物・コメントへリークするのを阻止。
- **allowlist**: `docs/VISION_INTERNAL.md` 本体、`docs/adr/`, `docs/security/`, `SECURITY.md`, `ROADMAP.md`, `.gitleaks.toml`, `tests/test_gitleaks_rules.py`, このドキュメント。
- **誤検知対応**: 内部で言及するだけなら allowlist 追加、公開側に必要なら文言自体を公開用リライト (VISION.md 等) に置き換える。

### 5. `hinomoto_ckpt_artifact_path_leak`

- **検知対象**: `artifacts/sft_dolly_v1_continue/` 以下のパス、または `artifacts/**/ckpt_*.pt` 形式の学習済みチェックポイントパス。
- **目的**: 学習資産の保管パスが公開ドキュメントから推測可能になるのを避ける (モデルポリシー整合)。
- **allowlist**: `docs/adr/`, `docs/security/`, `scripts/`, `ROADMAP.md`, `.gitleaks.toml`, `tests/test_gitleaks_rules.py`。
- **誤検知対応**: 運用スクリプトや ADR で必要なら現行 allowlist で吸収される。README などユーザー向け文書では相対名のみ言及し、具体ディレクトリへの依存を切る。

### 6. `hinomoto_tenant_id_path_traversal`

- **検知対象**: `tenant_id` 変数/キーに続く `../` や `..\\` を含む値 (`tenant_id = "../../etc/passwd"` 等)。
- **目的**: `core/tenant.py` のバリデーションを補完する defense-in-depth。テスト fixture や config にトラバーサル型の文字列が残らないようにする。
- **allowlist**: `tests/`, `docs/security/`, `docs/adr/`, `.gitleaks.toml`。
- **誤検知対応**: セキュリティテストで意図的に使っているケースは既に allowlist 内。新規で負テストを追加する際は `tests/` 配下に置くだけで自然と吸収される。

## 新規ルール追加時のチェックリスト

1. `id` は snake_case、HinoMoto 固有なら `hinomoto_` prefix を付ける。
2. `regex` は過度に広く取らない。ヒット件数を `gitleaks detect --no-git --verbose --redact` で事前計測。
3. `allowlist.paths` に本ファイル (`docs/security/GITLEAKS_CUSTOM_RULES.md`) と `.gitleaks.toml` を忘れずに含める (自己言及による false positive 防止)。
4. `tests/test_gitleaks_rules.py` に leaky / clean の最小ケースを追加。

## 誤検知が出た場合の運用フロー

1. `--verbose --redact` 付きでローカル再現。
2. 対象ルールの `allowlist.paths` に正規表現を追記、または値そのものを安全な代替 (環境変数/相対パス/汎用語) に置換。
3. ドキュメントとテスト fixture を同時に更新し、PR で根拠を残す。

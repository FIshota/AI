# 同意（Consent）管理

ai-chan は家族の内部で使われる AI であり、10 年単位の長い時間軸のなかで
家族構成が変わる（新メンバー加入、故人の記憶の取り扱い、子の独立）ことを
想定している。このため「誰が・いつ・どの機能に同意したか」を後から再現
できる形で証跡として残す仕組みが必要である。

本ドキュメントは `core/consent.py` と `config/consent_items.yaml` の運用方針を定める。

## 設計原則

- **ローカル保存のみ**。外部送信は一切行わない。
- **不変な値オブジェクト**：`ConsentRecord` は `@dataclass(frozen=True)`。
- **追記のみ**：`accept()` は過去レコードを上書きしない。撤回は `revoked_at` に時刻を入れる。
- **疎結合**：`core/subject_rights.py` の purge 処理とフック経由で連携する。
- **バージョンごとの証跡**：項目定義を変えるときは `consent_items.yaml` の `version` を bump し、過去バージョンの履歴は削除しない。

## データモデル

### ConsentRecord

| フィールド | 型 | 説明 |
|---|---|---|
| `subject_id` | `str` | 同意主体の識別子（`self` または family member UUID） |
| `version` | `str` | `consent_items.yaml` のバージョン |
| `items` | `tuple[str, ...]` | 同意された項目 key のタプル（ソート済み） |
| `accepted_at` | `str` | ISO 8601 UTC |
| `revoked_at` | `Optional[str]` | 撤回時刻。未撤回なら `None` |
| `id` | `Optional[int]` | DB 上の主キー（比較には含めない） |

### SQLite スキーマ

```
CREATE TABLE consent_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id   TEXT NOT NULL,
    version      TEXT NOT NULL,
    items        TEXT NOT NULL,   -- JSON 配列
    accepted_at  TEXT NOT NULL,
    revoked_at   TEXT
);
CREATE INDEX idx_consent_subject ON consent_records (subject_id, accepted_at DESC);
```

既定の DB ファイルは `data/consent.db` を想定する（呼び出し側が `ConsentStore(path)` で指定）。

## 運用

### 初回セットアップ

```python
from pathlib import Path
from core.consent import ConsentStore, load_consent_items

version, items, _ = load_consent_items(Path("config/consent_items.yaml"))
store = ConsentStore(Path("data/consent.db"), allowed_items=items)
store.accept("self", version, ["diary_generation", "emotion_logging"])
```

### 機能ガード

画面読み取りなど、同意に紐づく機能の入口で必ず確認する：

```python
if not store.has_consent("self", "screenshot_reading"):
    raise PermissionError("screenshot_reading not consented")
```

### 撤回

```python
store.revoke("self", version="1.0.0")   # 特定バージョンのみ
store.revoke("self")                    # 全アクティブ撤回
```

### SubjectRightsManager との連動

`core/subject_rights.py` の `purge_subject()` を呼ぶと consent レコードも一緒に物理削除される。

```python
from core.subject_rights import SubjectRightsManager
from core.consent import ConsentStore, register_with_subject_rights

mgr = SubjectRightsManager(base_dir=..., ...)
register_with_subject_rights(mgr, store)   # 以後 mgr.purge_subject() で consent も purge
```

## 項目の追加手順

1. `config/consent_items.yaml` の `items:` に新しい key を追加する。
2. `version` を semver で bump（機能追加は minor、後方非互換は major）。
3. `history:` に旧バージョンのエントリを残したまま新バージョンを追記する。
4. アプリ起動時に `latest_active()` が旧 version なら「再同意を求める UI」を出す。
5. テスト（`tests/test_consent.py`）を更新する。

旧バージョンの定義・履歴は **絶対に消さない**。10 年後に「2026 年時点では何に同意していたか」を再現できる必要がある。

## 世代引き継ぎ

家族構成が変わるときのルール：

| シナリオ | 操作 |
|---|---|
| 新メンバー加入 | `subject_id = new_uuid` で `accept()`。既存 subject は触らない。 |
| メンバーの独立 | 独立者の `export_subject()` → 渡す → `purge_subject()`（consent も自動 purge）。 |
| 故人 | `revoke()` で全アクティブを撤回。レコードは残して記念として参照可能。物理削除する場合のみ `purge_subject()`。 |
| 鍵の世代交代 | consent DB は重要だが通常はサイズが小さい。再暗号化時は export → import の順で。 |

## 監査

- すべての `accept` / `revoke` / `purge` は `logging.INFO` 以上で出力される。
- `audit_chain` にハッシュチェーンとして残すときは、呼び出し側でイベントを発火させる（consent モジュール自体は監査ログに結合しない設計）。

## テスト

```bash
python3 -m pytest tests/test_consent.py -v
```

## 境界

- consent は **機能のトグル**ではない。feature flag は別レイヤ。
- consent は **認可**ではない。RBAC/ACL は `config/access_control.json` 側。
- consent は **法的同意の代替**ではない。あくまで家族内の内部記録。

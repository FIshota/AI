# JOURNAL 日付整合性監査

## 目的

開発日誌 (`docs/JOURNAL.md` または `docs/journal/*.md`) に記載された
日付見出しと、実際の git コミット履歴 / 現在日との整合性を自動検証し、
記録と実態の乖離 (未来日・コミット不在・降順違反) を早期に検出する。

## 監査対象

- `docs/JOURNAL.md` (単一ファイル) — 優先
- `docs/journal/*.md` (分割運用する場合)

日付見出しは以下の形式のみ認識する:

```markdown
## YYYY-MM-DD
```

## 判定ルール

| 現象 | 重大度 | 終了コード影響 |
| --- | --- | --- |
| 見出し日付 > 今日 (未来日) | ERROR | `2` |
| 見出し日付のコミットが 0 件 | WARN | なし |
| 見出し順が降順でない | WARN | なし |
| `git` が存在しない / repo でない | SKIP | なし (`0`) |

ERROR が 1 件でもあれば終了コード `2`、それ以外は `0`。

## 実行方法

```bash
# デフォルト (リポジトリルートを自動推定、今日の日付を使用)
python3 scripts/audit_journal_dates.py

# 明示指定 (CI やテスト固定日向け)
python3 scripts/audit_journal_dates.py \
    --repo-root /path/to/ai-chan \
    --today 2026-04-23
```

## 運用ルール

1. JOURNAL 追記時は必ず当日付の git commit を 1 件以上行う
2. 見出しは降順 (新しい日付を上) で記載する
3. 未来日付の見出しを先行作成しない
4. CI では `scripts/audit_journal_dates.py` を実行し、ERROR で PR をブロックする

## テスト

```bash
pytest tests/test_audit_journal_dates.py -v
```

## 関連

- [docs/JOURNAL.md](../JOURNAL.md) — 開発日誌本体
- [scripts/audit_journal_dates.py](../../scripts/audit_journal_dates.py) — 監査実装

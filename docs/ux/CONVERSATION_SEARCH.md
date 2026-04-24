# 会話履歴検索 (Sprint 5.7 UX)

## 目的

アイと家族の 10 年分の会話ログ (推定数十万〜数百万発話) から、
「2027年3月頃に父がペットの話をしていた会話」といった
**日付範囲 + キーワード + 話者** の複合検索を即時に返すこと。

## 実装スタック

| レイヤー | 採用技術 | 却下した選択肢 |
|---------|---------|--------------|
| ストレージ | SQLite FTS5 (Python 3.9 標準同梱) | Elasticsearch / Meilisearch — 依存過多 |
| トークナイザ (EN/ASCII) | `unicode61 remove_diacritics 2` | `porter` (日本語に無意味) |
| トークナイザ (日本語) | 文字 2-gram を別カラムに展開 | MeCab / Sudachi — ネイティブ依存 |
| ランキング | BM25 + 365日ハーフライフの最近性ブースト | ベクトル検索のみ — ピンポイント想起が弱い |
| UI | tkinter (既存コンポーネントと一体) | Electron — 別プロセス過多 |

### 日本語トークナイザ設計の根拠

FTS5 の `unicode61` は CJK を **単文字トークン** に分解する。
このため `「ペット」` を検索すると `「ペ」AND「ッ」AND「ト」`
になり、無関係な文にも大量にヒットして精度が崩壊する。

**解決策: 文字 2-gram を別カラムでインデックス**

- インデックス時に原文 `今日はペットの話…` を
  `今日 日は はペ ペッ ット トの の話 …` に展開して
  `text_bigrams` カラムに格納。
- 検索時にクエリ `ペット` を `ペッ` `ット` に分解し、
  `text_bigrams:"ペッ" AND text_bigrams:"ット"` として MATCH。
- 1 文字 CJK クエリ (例: `犬`) は `text_bigrams:犬*`
  プレフィックス検索にフォールバック。
- 原文も `text` カラムでインデックスされているので、
  英語/数字/記号はそのまま BM25 で働く。

**なぜ MeCab を使わないか**

- ビルド時のネイティブ依存 (mecab-python3, IPAdic, …) で
  Intel Mac / M1 / Linux / Docker のマトリクスが爆発する。
- 辞書の更新 / ライセンス追跡が要る。
- 2-gram は分かち書き精度では MeCab に劣るが、
  **再現率 (Recall) は 2-gram の方が高い** ので
  「思い出を探す」という本機能の目的に合う。

## DB サイズ試算 (10 年想定)

| 前提 | 値 |
|------|-----|
| 1 日の発話数 (家族合計) | 200 発話 |
| 1 発話あたりの平均長 | 80 文字 (UTF-8 で ~160B) |
| 10 年 | 3,650 日 × 200 = **730,000 発話** |

生データ: 730k × 160B ≈ **117 MB**

FTS5 + bigrams の展開で実測は原文の約 3〜4 倍 (bigrams は
文字数−1 のトークン × ~6 バイト)。つまり **450〜500 MB** 程度。
家庭用 SSD では無視できる。

パフォーマンスサニティ (本リポジトリの開発機で計測):

- 10,000 件一括インデックス: **0.14 秒**
- 730k 件推定インデックス時間: **10〜15 秒** (WAL + バッチ 500)
- キーワード検索 (730k 想定): **< 30 ms**

## プライバシー / ログ

- 検索クエリは **ログに残さない**。`ConversationSearchIndex.search`
  は `logger.debug` も含めてクエリ文字列を出力しない
  (FTS5 の MATCH 式を組み立てる関数もロギングしない)。
- SQLite のクエリログは標準では OFF。開発時に
  `PRAGMA trace` を有効化しないこと。
- CLI `scripts/search_conversations.py` は結果のみ stdout、
  ステータスのみ stderr に出力する。
- UI は入力フィールドの内容を永続化しない。

## セキュリティ

- クエリは常に SQL パラメータバインディングで渡す。
  FTS5 の MATCH 式に渡す側では `"();*:^` を除去して
  文法破壊を防ぐ (`_sanitize_fts_term`)。
- `'; DROP TABLE turns; --` 等の投入はテストで検証済み
  (`tests/test_conversation_search.py::test_sql_injection_safe`)。

## 使い方

### CLI

```bash
python scripts/search_conversations.py \
  --db memory/search_index.db \
  --reindex-from memory/conversation.db   # 初回のみ

python scripts/search_conversations.py \
  --from 2027-03-01 --to 2027-03-31 \
  --keyword "ペット" --speaker papa --limit 20
```

`--json` で機械可読出力。

### UI

```python
from pathlib import Path
from core.conversation_search import ConversationSearchIndex
from ui.search_window import SearchWindow

idx = ConversationSearchIndex(Path("memory/search_index.db"))
SearchWindow(parent=root, index=idx)
```

キーワード欄では `ペット OR 犬` / `父 AND 仕事` のように
大文字の `AND` / `OR` で結合子を切り替え可能。

# Lifelong Memory Module (LMM) — 設計メモ (PoC)

ai-chan は 10 年運用を前提としている。現行の `core/memory.py` は「会話履歴の
短期 / 中期 / 長期」三層で、直近の会話理解を支えるのが主目的。これに対して
本モジュール (`core/lifelong_memory.py`) は、**出来事 / 人物 / 趣味嗜好 /
感情トレンド** を "時系列に積み重ね、後から近似的に想起する" ための
長期記憶レイヤを PoC として切り出したもの。

## 1. 既存 `memory.py` との住み分け

| 観点 | `core/memory.py` (三層記憶) | `core/lifelong_memory.py` (LMM) |
|---|---|---|
| 目的 | 会話コンテキストの保持 | 人生スパンの出来事・関係・嗜好蓄積 |
| スコープ | Short / Mid / Long-term (会話起点) | subject 単位の出来事ストリーム |
| 粒度 | 発話・Memory レコード | `MemoryEvent` (kind 分類あり) |
| 想起 | 時間/タグ検索主体 | TF-IDF (bigram char) 近似 recall |
| 時間軸 | 日〜月 | 年〜十年 |
| 保護 | コア人格保護 | Kill-Switch (forget/purge) + policy |

既存 `memory.py` は触らず、LMM は並立レイヤ。将来的に上位で fusion する際は
「`memory.py` の long-term に貯まったものを LMM へ促進 (promote)」する想定。

## 2. データモデル

`MemoryEvent` (frozen dataclass, stdlib のみ):

* `id`: uuid4 hex
* `subject_id`: 記憶の主体 (ユーザー、ペット、家族メンバーなど)
* `kind`: `event` / `person` / `preference` / `trend`
* `content`: 自然文 (日本語想定)
* `ts`: ISO8601 UTC
* `tags`: tuple[str, ...] (不変)
* `confidence`: 0.0–1.0
* `importance`: 0.0–1.0

## 3. ストレージ

SQLite 単一ファイル。`utils.crypto` との連携は呼び出し側で `encrypt` /
`decrypt` コールバックを差し込む形にして疎結合化した。インデックスは
`subject_id` / `kind` / `ts` に付与。

## 4. 想起 (recall)

* 外部依存を避けるため **char-bigram bag-of-chars + TF-IDF + cosine** を自前で実装。
* 日本語は単語分割せず 2 文字 n-gram にしてトークン化。形態素解析器不要。
* スコアは `cosine × (0.5 + 0.5·importance) × (0.5 + 0.5·confidence)` で
  重要度と信頼度を穏やかに反映。

PoC としては十分な近似。将来は embeddings (Sentence Transformers / ローカル LLM) に
差し替え可能な interface を維持している。

## 5. 10 年運用想定

* **importance_decay**: 古くなった記憶は半減期 (既定 365 日) で importance を
  減衰させる。削除はしないが、recall のランキングから自然に後退していく。
* **kind 別の recall**: 10 年単位では出来事が万単位になる。kind_filter で
  person / preference など「要約的な記憶」を優先して呼び出せるように。
* **subject 単位の分割**: 家族・ペットなど主体ごとに独立して purge 可能。
* **スキーマ互換**: 将来カラム追加は `ALTER TABLE` で足すが、現在は
  最小セットに絞り、マイグレーション負担を抑える。

## 6. Kill-Switch

* `forget(event_id)` — 単一イベントを即時物理削除。
* `purge(subject_id)` — ある主体の全記憶を削除。家族が "その人に関する記憶を
  すべて忘れてほしい" と言ったときに 1 コマンドで対応できる。
* ポリシー層 (`lifelong_memory_policy.py`) に `consenting_subjects` と
  `blocklist_tags` を用意し、**書き込む前に** 弾く仕組みも併設。

## 7. 感情トレンド用途

`kind="trend"` で `importance` を低めに設定し、日次 / 週次で軽量な
要約記録を流していく想定。例:

```python
new_event(subject_id="yamato", kind="trend",
          content="最近ずっと落ち着いている",
          tags=("mood", "weekly"), importance=0.3)
```

TF-IDF recall は「最近の気分どう？」のようなクエリで `trend` のみを
kind_filter で取り出すことで、素直に時系列トレンドを引ける。

## 8. 今後

* embedding ベース recall とのハイブリッド化
* `memory.py` の long-term からの自動 promote パイプライン
* 監査チェーン (`audit_chain`) との連携で、どの記憶が何のクエリで呼び出されたかをログ化
* UI 側で "この記憶は忘れて" ボタン → `forget` 直結

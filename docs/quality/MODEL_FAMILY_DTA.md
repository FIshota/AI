# MODEL_FAMILY DTA — 運用フロー

> HinoMoto モデル家族ドキュメントの **Data-Truth-Audit** 運用手順。

## 目的

ai-chan と hinomoto-model の 2 リポジトリに散在する HinoMoto 系モデル設計情報を
**同一の Data-Truth Table で管理**し、矛盾をスクリプトで検出する。

対象ドキュメント:

- `ai-chan/docs/MODEL_FAMILY.md` (マスター)
- `hinomoto-model/docs/MODEL_FAMILY.md` (ミラー)

## 検証項目

監査スクリプト `scripts/audit_model_family.py` は以下をチェックする:

| 項目 | 動作 |
|---|---|
| 表の存在 | 両ファイルからモデル一覧表を抽出 (なければ FAIL) |
| 同名モデルの属性 | 列単位で値を比較。`[TBD]` はワイルドカード扱い |
| 片側にしかないモデル | `MISSING-IN-*` として警告出力 |
| hinomoto-model 不在 | WARN 扱いで exit 0 (ai-chan 単独開発でも OK) |
| TBD 数 | 各ファイルの未確定セル数を集計してレポート |

終了コード:

- `0` : OK / warn のみ
- `2` : 矛盾あり、または ai-chan 側ファイル不在

## 運用フロー

### 1. 新しい設計値が決まったとき

1. ai-chan 側 `docs/MODEL_FAMILY.md` の表を更新する。
2. hinomoto-model 側 `docs/MODEL_FAMILY.md` の表を **同じ値で** 更新する。
3. `python scripts/audit_model_family.py` を実行。
4. `RESULT: OK` を確認してからコミット。

### 2. 新しい派生モデルを追加するとき

1. 両方の表に同じ行 (同じモデル名・同じ列順) を追加する。
2. 未定値は `[TBD]` で埋める。
3. audit を実行し、OK を確認。
4. `docs/MODEL_FAMILY.md` の追記ルールに従い、設計差分の根拠を本文にも書く。

### 3. CI / pre-commit への組み込み (推奨)

```bash
# Makefile / pre-commit / CI いずれか
python scripts/audit_model_family.py
```

矛盾があれば exit 2 でブロックされる。

## テスト

```bash
cd ai-chan
pytest tests/test_audit_model_family.py -v
```

## 設計メモ

- Python 3.9 互換・stdlib のみ (`re`, `pathlib`, `argparse`)。
- 日本語列名を前提。ヘッダは `モデル名 / 公開範囲 / vocab` を含む markdown 表を抽出対象とする。
- `[TBD]` は「未確定」を示すリテラル。両者一致が取れない状態を明示するため conflict 判定から除外する。
- hinomoto-model ディレクトリが存在しない環境 (例: ai-chan 単独 clone) でもクラッシュしない。

## 関連

- `ai-chan/docs/MODEL_FAMILY.md` — マスタードキュメント
- `ai-chan/scripts/audit_model_family.py` — 監査スクリプト
- `ai-chan/tests/test_audit_model_family.py` — 監査スクリプトのテスト
- `hinomoto-model/docs/MODEL_FAMILY.md` — ミラードキュメント

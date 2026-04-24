# Offline Artifact Verification

10 年後、ネット切断環境でも過去の model checkpoint / tokenizer / corpus manifest の完全性を検証できるようにするための運用方針。

## 目的

- 長期保管された artifact (学習済みモデル、tokenizer、corpus manifest、評価データセット) の
  **欠損 / 改変 / サイズ不一致** を、外部ネットワーク無しで検出する。
- 検証ロジックは Python 3.9 stdlib のみで動作し、依存ドリフトを受けない。

## 対象 artifact

manifest 化の対象は以下のカテゴリ。

| カテゴリ | 例 | 理由 |
|---|---|---|
| model checkpoint | `models/*/weights.bin`, `*.safetensors` | 改変されると推論結果が変わる |
| tokenizer | `models/*/tokenizer.json`, `*.model` | 1 bit 変わっても互換性が崩れる |
| corpus manifest | `data/corpus/*.manifest.json` | 学習データの同定に必須 |
| 評価データセット | `data/eval/**/*.jsonl` | 再現性の基準 |
| ライセンス / NOTICE | `NOTICE`, `LICENSES.md` | 法的エビデンス |

以下は対象外 (揮発的で頻繁に変わる):

- `logs/`, `reports/`, `output/`, `__pycache__/`, `backups/` (別の backup chain で管理)

## Manifest 形式

JSON の配列。各要素:

```json
{
  "path": "models/yamato/weights.bin",
  "sha256": "<hex>",
  "size_bytes": 12345678
}
```

- `path`: manifest からの相対パス (推奨) もしくは絶対パス。
- `sha256`: 小文字 hex。
- `size_bytes`: 非負整数。

## 生成

```bash
python scripts/generate_artifact_manifest.py \
    --root models \
    --include-glob "**/*.bin" --include-glob "**/*.json" \
    --exclude-glob "**/tmp/*" \
    --output artifacts/manifests/models_YYYYMMDD.json
```

## 検証

```bash
python scripts/verify_offline_artifacts.py \
    --manifest artifacts/manifests/models_YYYYMMDD.json \
    --base-dir .
# exit 0 = 完全一致
# exit 2 = 1 件以上の 不一致 / 欠損 / サイズ不一致
# exit 1 = manifest 自体のパース失敗など usage error
```

`--json` で機械可読レポートを emit 可能。

## 保存場所と世代管理

- マスター manifest は `artifacts/manifests/` にコミット。
- ファイル名は `<category>_<YYYYMMDD>.json` 形式。世代保持。
- 古い世代は `artifacts/manifests/archive/` へ移動 (削除しない)。
- リリース時には該当 manifest を対応する git tag に紐づける (`git tag -a ... -m "manifest: ..."`)。
- オフサイトコピー: USB / コールドストレージ / 紙 QR として物理冗長化。

## 運用チェックリスト

- [ ] 新モデルを `models/` に配置したら、当日中に manifest を生成しコミット。
- [ ] manifest 生成時は必ず `--exclude-glob` でキャッシュ類を除外。
- [ ] 四半期ごとに全 manifest を verify (CI) し、exit 0 を確認。
- [ ] 手元コピーとオフサイトコピーの 2 箇所以上に保存。
- [ ] manifest 自体のハッシュをトップレベルの `artifacts/MANIFEST_INDEX.json` に記録。

## 既知の限界

- この仕組みは **置換攻撃** (manifest と artifact を同時に差し替える) を防がない。
  → manifest の真正性は git 署名 / 外部の anchor (タイムスタンプサービス) に委ねる。
- hash はあくまで bit-for-bit 同一性。意味的な同等性 (例: 量子化による同等モデル) は別途評価。

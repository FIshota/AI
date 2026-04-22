# scripts/vendor/

このディレクトリには **上流プロジェクトから vendored した 3rd-party コード** を置く。
ai-chan 本体のコードではないため、以下の扱いとする。

## ポリシー

- **改変しない**: 上流に追従する形でのみ更新する。ai-chan 固有のカスタマイズが必要な場合は、
  wrapper 側 (例: `scripts/convert_hf_to_gguf.py`) にロジックを足す。
- **lint/type 対象外**: `pyproject.toml` の `[tool.ruff].extend-exclude` と
  `[tool.mypy.overrides] scripts.vendor.*` で除外している。
- **テスト対象外**: ai-chan のテストスイートには含めない。動作検証は上流側に委ねる。
- **セキュリティ監査**: 日次セキュリティ監査 (`trig_01HKCA...`) でも vendor は
  自前コードと分離して報告する (上流 CVE は上流側で対応)。

## 現在の vendor 一覧

### `llama_cpp/convert_hf_to_gguf.py`

- **由来**: https://github.com/ggerganov/llama.cpp
- **役割**: HuggingFace フォーマットのモデルを GGUF に変換する CLI
- **最終更新**: 2026-04-12 (commit 未追跡)
- **呼び出し元**: `scripts/convert_hf_to_gguf.py` (薄いラッパー)
- **ライセンス**: MIT (llama.cpp 上流)

## 更新手順

```bash
# 1. 上流から最新版を取得
curl -o scripts/vendor/llama_cpp/convert_hf_to_gguf.py \
    https://raw.githubusercontent.com/ggerganov/llama.cpp/master/convert_hf_to_gguf.py

# 2. diff を目視確認
git diff scripts/vendor/llama_cpp/convert_hf_to_gguf.py

# 3. ラッパー経由で動作確認
python scripts/convert_hf_to_gguf.py --help

# 4. コミット (メッセージ例)
git commit -m "chore(vendor): update llama.cpp convert_hf_to_gguf.py to upstream $(date +%Y-%m-%d)"
```

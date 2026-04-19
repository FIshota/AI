# ai-chan Model Baseline — Phase 0

**Date**: 2026-04-20
**Branch**: `phase0/rebrand-bench-baseline`
**Owner**: honnsipittu@gmail.com
**Status**: Phase 0 (Baseline Selection)

---

## 目的

「国産AI」として堂々と発表できる水準を目指すため、**ベースモデル / ライセンス / ベンチマーク**
の三点セットを透明化する。本書はベースモデル選定の根拠を残すための決定記録 (ADR) である。

査読者・監査人が最初に確認するのは「どのモデルを基盤にしているか」と「ライセンス連鎖は
クリーンか」の二点であり、ここが不透明な限り "国産AI" を名乗っても議論にならない。

---

## 比較候補

| family | display | HF repo | license | clean | JP native | recommended |
|---|---|---|---|---|---|---|
| `sarashina2-7b` | Sarashina2-7B (SB Intuitions) | sbintuitions/sarashina2-7b | MIT | ✅ | ✅ | **★ 採用** |
| `elyza-llama3-8b` | ELYZA-japanese-Llama-3-8B-Instruct | elyza/Llama-3-ELYZA-JP-8B | Meta Llama 3 Community | ⚠ | ✅ | — |
| `swallow-8b` | Llama-3.1-Swallow-8B-Instruct | tokyotech-llm/Llama-3.1-Swallow-8B-Instruct-v0.3 | Meta 3.1 + Gemma terms | ⚠ | ✅ | — |
| `karakuri-8b` | karakuri-lm-8x7b-instruct-v0.1 | karakuri-ai/karakuri-lm-8x7b-instruct-v0.1 | Apache 2.0 | ✅ | ✅ | — |
| `qwen2-legacy` | Qwen2.5 (legacy) | — | Qwen License | ⚠ (非国産) | ❌ | — (互換) |

### 評価軸

1. **ライセンスのクリーンさ**: 商用配布・改変・再配布に法務確認が不要なもの。MIT / Apache 2.0 は安全。
   Meta 系ライセンスは「再配布時に原ライセンス全文同梱」「月間アクティブユーザー 7 億人規制」
   「出力物を他社 LLM 学習に使わない」等の制約があり、査読者から必ず指摘される。
2. **日本語コーパスの純度**: 事前学習段階から日本語が主要言語であるか。継続事前学習
   (continual pre-training) は優秀だが「元がLlamaなので国産と言い切れない」という反論を受けやすい。
3. **Intel Mac での実行可能性**: Phase 0 時点のローカル環境は Intel Mac / Py3.9 / no MLX /
   Metal 非互換。llama-cpp-python + GGUF (Q4/Q5) で動くこと。
4. **運用可能な重み配布**: HF 経由で単一コマンド (`huggingface-cli download`) で取得でき、
   GGUF が既に存在するか、もしくは変換コストが現実的であること。

### 結論: **Sarashina2-7B** を Phase 0 の既定 (`recommended: True`) に採用

- MIT ライセンスで再配布・改変・商用利用すべて制限なし。
- SB Intuitions (ソフトバンク系) が事前学習から日本語中心で構築した 7B モデル。
  日本のデータで日本の企業が事前学習した、という事実が最も明快に国産性を示せる。
- 7B スケールで Intel Mac の GGUF Q4/Q5 量子化でも現実的に動作する。
- 継続事前学習ではなく事前学習段階から日本語のため、「Llama 派生ではない」点が
  査読者への最大の説明力。

### 不採用理由

- **ELYZA-Llama-3-8B-Instruct**: 日本語 FT 性能は高いが Meta ライセンス継承。
  「国産 AI」の看板と矛盾する主張が残りうるため Phase 0 では非採用。
- **Swallow-8B**: 東工大の継続事前学習量は国内最大級だが、
  Meta Llama 3.1 + Gemma terms のライセンス連鎖が重く、再配布条項の説明責任が増える。
- **Karakuri-8B**: Apache 2.0 でクリーンだが MoE (8x7B) のためメモリ要件が高く、
  Phase 0 の Intel Mac 8-16GB クラスではローカル動作が苦しい。
- **Qwen2.5 (legacy)**: 中国製 (Alibaba) かつライセンスも独自。国産を名乗る以上は撤退方向。
  後方互換のためだけに `model_family` 定義を残す。

---

## 設定方法

`config/settings.json` の `llm` セクションに `model_family` キーを置く:

```json
{
  "llm": {
    "model_family": "sarashina2-7b",
    "context_length": 4096,
    "quantization": "Q5_K_M"
  }
}
```

ローダー (`core/llm.py::LlamaEngine._load_model`) が読み込み時に下記を出力する:

```
[LLM/P0] Model family: sarashina2-7b (MIT, clean) — Sarashina2-7B (SB Intuitions)
[LLM/P0] gguf_hint='sarashina2-7b' に合致 1/3 件に絞り込み
[LLM/P0] template override from family: chatml
[LLM/llama] ✓ 読み込み完了 (GPU): sarashina2-7b-instruct-v0.1.Q5_K_M.gguf (template=chatml)
```

未指定時は `default_model_family()` (= `sarashina2-7b`) が使われる。

---

## 再現手順

```bash
# 1) GGUF 取得 (例: Q5_K_M)
mkdir -p models
huggingface-cli download mmnga/sarashina2-7b-gguf \
    sarashina2-7b-instruct-v0.1.Q5_K_M.gguf --local-dir models/

# 2) 設定
jq '.llm.model_family = "sarashina2-7b"' config/settings.json.example > config/settings.json

# 3) 起動確認
python3 main.py --smoke-test
```

---

## 今後の Phase

- **Phase 1**: JGLUE + ELYZA-tasks-100 の自動評価結果を本書末尾に貼り付け、
  GPT-4o / Gemini 2 / Claude 3.5 / 他の国産 LLM と横並びで比較。
- **Phase 2**: 上位候補 (Karakuri / Swallow) との A/B を `bench/runner.py` で回し、
  JMT-Bench (会話型評価) も加える。
- **Phase 3**: ライセンスクリーンのまま fine-tune / LoRA を載せる場合の手順書化。

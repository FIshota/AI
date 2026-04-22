# Model Policy (モデル採用方針)

**最終更新: 2026-04-21**

## 原則

ai-chan は家族として信頼できる AI であるべきであり、中核モデルは
**信頼できる開発元 (日本 / 民主主義諸国)** 由来のものを優先採用する。

## 禁止リスト (既定で採用しない)

以下のモデルは **既定モデルとして採用しない**。
技術検証や比較目的で一時的にロードする場合は明示的オプトインを必須とする。

- Qwen 系 (Alibaba Cloud, 中国) — Qwen1.5 / Qwen2 / Qwen2.5 / Qwen3
- DeepSeek 系 (DeepSeek, 中国)
- Yi 系 (01.AI, 中国)
- ChatGLM / GLM 系 (THUDM / 智譜AI, 中国)
- InternLM 系 (上海 AI 研究所, 中国)
- Baichuan 系 (百川智能, 中国)
- 01-ai / Kimi / Moonshot 等の中国系モデル

理由: 開発者判断による信頼性評価。データ収集・トレーニングコーパスの透明性、
政治的影響、サプライチェーン安全保障を総合的に考慮。

## 推奨リスト (日本製優先)

### 3B クラス (個人 PC で実用)
- ✅ **sbintuitions/sarashina2.2-3b-instruct-v0.1** (SoftBank 子会社 SB Intuitions / 日本) ← **既定**
- ✅ llm-jp/llm-jp-3-3.7b-instruct (日本 LLM コンソーシアム)
- ✅ cyberagent/calm3-22b (CyberAgent / 日本, 大きめ)

### 7B〜8B クラス (高品質)
- ✅ sbintuitions/sarashina2-7b
- ✅ tokyotech-llm/Llama-3-Swallow-8B-Instruct (東京工業大学 / 日本 × Meta ベース)
- ✅ elyza/Llama-3-ELYZA-JP-8B (ELYZA / 日本 × Meta ベース)
- ✅ rinna/llama-3-youko-8b (rinna / 日本 × Meta ベース)
- ✅ stockmark/stockmark-13b (Stockmark / 日本, やや大きい)

### 西側 (日本製不足時のフォールバック)
- ✅ Meta Llama 3.1 / 3.2 (USA)
- ✅ Microsoft Phi-3.5 (USA) — ai-chan の補助モデルとして既存採用
- ✅ Google Gemma 2 (USA)
- ✅ Mistral 7B (France) — setup_model.py に既存

## 補助コンポーネントの現状

| 用途 | 採用 | 開発元 | 判定 |
|---|---|---|---|
| 対話 LLM | Sarashina 2.2 3B | SB Intuitions (日本) | ✅ |
| 埋め込み | paraphrase-multilingual-MiniLM-L12-v2 | Microsoft (USA) | ✅ |
| 埋め込み代替 | intfloat/multilingual-e5-small | Microsoft (USA) | ✅ |
| Wake Word STT | Vosk vosk-model-small-ja-0.22 | Alpha Cephei (チェコ) | ✅ |
| Vision (補助) | Moondream 2 | USA OSS | ✅ |
| TTS | pyttsx3 / VOICEVOX | OSS / 日本 (Hiroshiba) | ✅ |

## 変更履歴

- **2026-04-21**: Qwen 2.5 3B を中核から外し、Sarashina 2.2 3B (SB Intuitions 日本) へ切替。
  - `config/settings.json.example` 更新
  - `scripts/setup_qwen.py` → `scripts/setup_sarashina.py` に置換 (wrapper 残置)
  - `scripts/finetune_qlora.py` の検出キーワード刷新 (sarashina/llm-jp/swallow/elyza/rinna/calm)
  - `scripts/run_benchmark_compare.py` の比較対象を Phi-3 vs Sarashina に変更

## オプトイン運用 (どうしても Qwen 等を試したい場合)

`config/settings.json` に明示的に追加する:

```json
{
  "llm": {
    "_consent_nonpreferred_model": true,
    "model_file": "qwen2.5-3b-instruct-q4_k_m.gguf"
  }
}
```

`_consent_nonpreferred_model: true` が無いのに禁止リスト由来モデル名を
指定した場合は起動時に警告をログに残す (TODO: core/llm.py で実装).

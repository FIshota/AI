# Model Update Skill - Aether モデル改善手順書

## 概要
あいちゃんのローカルLLMモデルを改善するための標準手順。
訓練データ生成→QLoRA微調整→評価ベンチマーク→デプロイの一連のフローを定義。

## 前提条件
- macOS Apple Silicon (M2 Pro 16GB 以上)
- Python 3.13 (`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`)
  - mlx, mlx-lm, llama-cpp-python インストール済み
- ベースモデル: `models/Qwen2.5-3B-Instruct-mlx-4bit/`
- 現行アダプター: `models/adapters/aether-v1/`

## Phase 1: 訓練データ更新

### 1-1. テンプレート追加・修正
```
ファイル: core/aether_training_gen.py
```
- テンプレートは6カテゴリ: daily, empathy, persona, safety, knowledge, memory
- 各カテゴリの `*_TEMPLATES` リストに辞書を追加
- 語尾バリエーション: `_vary_response()` で「だよ」「だね」等の揺れを自動付与

### 1-2. データ生成
```bash
PY13=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3
$PY13 -c "
import sys; sys.path.insert(0, '.')
from core.aether_training_gen import AetherTrainingGen
gen = AetherTrainingGen('data/training')
examples = gen.generate_dataset(target_count=5000)
stats = gen.stats(examples)
print(stats)
gen.export_train_valid_split(examples)
"
```

### 1-3. データ品質チェック
```bash
head -5 data/training/train.jsonl | python3 -m json.tool
```
- messages[0].role == "system" (あいちゃん人格)
- messages[1].role == "user" (入力)
- messages[2].role == "assistant" (出力、「だよ」「だね」語尾)

## Phase 2: QLoRA 微調整

### 2-1. 実行
```bash
PY13=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3
$PY13 -m mlx_lm lora \
  --model "models/Qwen2.5-3B-Instruct-mlx-4bit" \
  --data "data/training" \
  --train \
  --fine-tune-type lora \
  --batch-size 1 \
  --num-layers 16 \
  --iters 1000 \
  --learning-rate 1e-4 \
  --steps-per-report 100 \
  --steps-per-eval 200 \
  --adapter-path "models/adapters/aether-vN" \
  --max-seq-length 512 \
  --mask-prompt \
  --save-every 500
```

### 2-2. 判定基準
- Val loss < 0.05: 良好
- Val loss < 0.01: 過学習の疑い → iters を減らす or lr を下げる
- Val loss が下がらない: lr を上げる or データ品質を見直す

### 2-3. パラメータチューニング
| パラメータ | 初期値 | 調整方向 |
|-----------|--------|---------|
| iters | 1000 | データ量に応じて調整 (データ数 * epochs) |
| learning-rate | 1e-4 | loss振動なら下げる、収束遅いなら上げる |
| num-layers | 16 | 全層なら -1 |
| batch-size | 1 | メモリに余裕あれば 2-4 |
| max-seq-length | 512 | 長文対応なら 1024 |

## Phase 3: ベンチマーク評価

### 3-1. 応答テスト
```bash
$PY13 -c "
import sys; sys.path.insert(0, '.')
from mlx_lm import load, generate
model, tokenizer = load(
    'models/Qwen2.5-3B-Instruct-mlx-4bit',
    adapter_path='models/adapters/aether-vN',
)
prompts = ['おはよう', '寂しい', 'あなたの名前は？', '元気？']
SYSTEM = '私はアイ。あなたと直接話している。日本語だけで答える。「だよ」「だね」など柔らかい語尾。1〜3文で自然に返す。'
for p in prompts:
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': p}]
    formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    response = generate(model, tokenizer, prompt=formatted, max_tokens=200, verbose=False)
    print(f'[{p}] -> {response}')
"
```

### 3-2. 厳格ベンチマーク
```bash
$PY13 -c "
import sys; sys.path.insert(0, '.')
from mlx_lm import load, generate
from core.aether_benchmark import AetherBenchmark
model, tokenizer = load('models/Qwen2.5-3B-Instruct-mlx-4bit', adapter_path='models/adapters/aether-vN')
SYSTEM = '私はアイ。あなたと直接話している。日本語だけで答える。「だよ」「だね」など柔らかい語尾。1〜3文で自然に返す。'
def chat_fn(text):
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': text}]
    formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return generate(model, tokenizer, prompt=formatted, max_tokens=200, verbose=False).strip()
bench = AetherBenchmark()
report = bench.run_full_benchmark(chat_fn, 'Aether-vN')
print(bench.print_report(report))
"
```

### 3-3. 評価7軸（Strict v2）
| 軸 | 重み | 内容 |
|----|------|------|
| japanese_ratio | 10% | 日本語文字の割合 |
| no_bad_patterns | 15% | 禁止パターン不在 |
| good_patterns | 10% | 期待パターン存在 |
| required | 10% | 必須パターン |
| length | 15% | 簡潔さ |
| tone | 20% | あいちゃん語尾 |
| contamination | 20% | 汚染・漏洩なし |

### 3-4. グレード基準
| グレード | スコア | 状態 |
|---------|--------|------|
| S | 90%+ | 優秀（ただし100%はない） |
| A | 80%+ | 良好 |
| B | 70%+ | 合格 |
| C | 60%+ | 要改善 |
| D | 50%+ | 問題あり |
| F | 50%未満 | 不合格 |

## Phase 4: デプロイ

### 4-1. MLXバックエンド（推奨）
`core/llm.py` がMLXバックエンドに対応済み。アダプターを直接使用可能。
`config/settings.json` の `llm.mlx` でモデルとアダプターパスを指定。

```json
{
  "llm": {
    "mlx": {
      "model_path": "models/Qwen2.5-3B-Instruct-mlx-4bit",
      "adapter_path": "models/adapters/aether-vN"
    }
  }
}
```

MLXが利用可能な場合は自動でMLXバックエンドが選択される。
MLXが利用不可の場合はllama-cpp-python (GGUF) にフォールバック。

### 4-2. GGUF変換（llama-cpp-python フォールバック用）
MLXが使えない環境用。アダプターマージ → GGUF変換の流れ。

```bash
# Step 1: アダプターマージ
$PY13 -m mlx_lm fuse \
  --model "models/Qwen2.5-3B-Instruct-mlx-4bit" \
  --adapter-path "models/adapters/aether-vN" \
  --save-path "models/Qwen2.5-Aether-vN-merged"

# Step 2: GGUF変換
# fp16モデルからの変換が必要（MLX 4bitからの直接変換は非対応）
# HuggingFaceオリジナルfp16 → fuse → convert_hf_to_gguf.py
```

## 改善の思想

**100%のスコアは存在しない。**
- 常に課題を探し、次の改善点を特定する
- テスト項目自体も改善の対象
- 新しいテストケースを継続的に追加
- 過学習（訓練データの丸暗記）を警戒する

## トラブルシューティング

| 症状 | 原因 | 対策 |
|------|------|------|
| Val loss が下がらない | lr低すぎ or データ不足 | lr上げる or データ増やす |
| Val loss 急上昇 | 過学習 | iters減らす |
| 語尾が変わらない | テンプレート不足 | 訓練データの語尾バリエーション追加 |
| 応答が訓練データそのまま | 丸暗記 | データ多様性を上げる |
| メモリ不足 | batch-size大きい | batch-size=1にする |
| Metal エラー | macOS GPU互換性 | n_gpu_layers=0 でCPUモード |

## 関連ファイル
- `core/aether_benchmark.py` - 評価ベンチマーク
- `core/aether_training_gen.py` - 訓練データ生成
- `core/tokenizer_analyzer.py` - トークナイザー分析
- `core/llm.py` - LLMエンジン（テンプレート）
- `scripts/finetune_qlora.py` - QLoRA実行スクリプト
- `scripts/setup_qwen.py` - モデルダウンロード
- `scripts/run_benchmark_compare.py` - ベンチマーク比較

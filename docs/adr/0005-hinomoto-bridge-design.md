# ADR 0005: HinoMoto は HinoMotoBridge 経由で ai-chan に接続する

- Status: Accepted
- Date: 2026-04-23
- Deciders: honnsipittu

## コンテキスト

ai-chan は対話 LLM として外部バックエンド (llama.cpp 経由の GGUF、
MLX (Metal 非対応機では不可)、OpenAI 互換 API 等) を切替可能に設計されてきた。
自前の HinoMoto 基盤モデルの統合にあたり、以下を満たす必要があった。

- HinoMoto を第一選択に据えつつ、未成熟ゆえのフォールバック経路を残す
- 将来 YAMATO / KAGUYA 等の派生モデルを同じ口で差し替え可能にする
- ai-chan の対話ループ (`core/llm.py`) を改変せず、バックエンド追加で済ます

## 決定

`core/llm.py` に **LLMBackend 抽象** を置き、HinoMoto 用の実装として
**HinoMotoBridge** クラスを追加する。バックエンドの優先順位は config 駆動:

```
backend_priority = ["hinomoto", "llama_cpp", "mlx", "external_api"]
```

HinoMotoBridge は以下を担う:
- HinoMoto checkpoint の遅延ロード
- `generate(prompt, **kw)` の統一シグネチャ
- ADR 0003 の既定生成パラメータ適用
- 失敗時に次バックエンドへフォールバック (明示ログ)

## 理由

- **swappability**: 派生モデル (YAMATO, Ai, KAGUYA) は同じ Bridge 抽象の
  下に並ぶ。対話ループは「どのモデルか」を知らなくてよい。
- **未成熟さへの保険**: HinoMoto は Phase 2 中で品質が暫定。
  出力が破綻した場合に llama.cpp GGUF フォールバックで事業継続できる。
- **テスト容易性**: Bridge をモックすれば対話ロジックの単体テストが独立。
- **責務分離**: HinoMoto の内部仕様 (tokenizer、generate 実装) が
  ai-chan 側に漏れない。

## 結果 / トレードオフ

- `ai-chan/core/llm.py` に LLMBackend 基底 / HinoMotoBridge / 既存バックエンド
  の 3 層構造が確立。
- Config で優先順位を runtime 切替可能 (`config/llm.yaml`)。
- トレードオフ: 間接層ぶんのオーバーヘッド。ただし対話応答の支配コストは
  LLM forward であり、bridge 層は ~µs オーダーで無視できる。

## 代替案 (検討して却下)

### 案 A: core/llm.py を HinoMoto 専用に書き換える
却下理由: 他バックエンドが必要な局面 (Metal 不可機での fallback、外部 API 評価)
で詰まる。

### 案 B: subprocess 経由で HinoMoto を呼ぶ
却下理由: Python 内同一プロセスにできるものを分離するコストが無駄。
latency 増、weights の二重ロード。

### 案 C: モデルサーバ化 (独立 HTTP)
却下理由: 単独開発、ローカル実行前提のシナリオでは over-engineering。
将来 KAGUYA (複数端末) で再検討。

## 参照

- `ai-chan/core/llm.py`
- `ai-chan/config/llm.yaml`
- `hinomoto-model/hinomoto/generate.py`
- ADR 0003 (生成既定値)
- ADR 0007 (モデル派生)

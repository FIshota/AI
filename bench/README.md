# ai-chan Benchmark Harness

**Status**: Phase 0 skeleton (stubs only)
**Owner**: honnsipittu@gmail.com

## 目的

"国産AI" と堂々と言える根拠を数字で示すため、以下の公開ベンチマークに対する
スコアを再現可能な形で出力するハーネスを用意する。

- **JGLUE** (Waseda / Yahoo Japan) — 日本語 GLUE。MARC-ja, JSTS, JNLI, JSQuAD, JCommonsenseQA
- **ELYZA-tasks-100** — 実用 100 タスクの生成品質 (LLM-as-a-Judge)
- **JMT-Bench** — マルチターン会話評価 (GPT-4 judge)
- **family-dialog-100** — ai-chan 固有の家族対話 100 問 (独自評価セット)

## 使い方 (予定)

```bash
# 全スイート
python3 bench/runner.py --model sarashina2-7b --all

# 単発
python3 bench/runner.py --model sarashina2-7b --suite jglue
python3 bench/runner.py --model sarashina2-7b --suite elyza_tasks_100
python3 bench/runner.py --model sarashina2-7b --suite family_dialog

# 結果
# bench/results/YYYY-MM-DD/sarashina2-7b/<suite>.json
# bench/results/YYYY-MM-DD/sarashina2-7b/summary.md
```

## 構成

```
bench/
├── README.md          # 本書
├── runner.py          # エントリポイント
├── metrics.py         # 共通スコアリング (accuracy, F1, BLEU, judge score)
└── suites/
    ├── __init__.py
    ├── jglue.py            # JGLUE スタブ
    ├── elyza_tasks_100.py  # ELYZA-tasks-100 スタブ
    └── family_dialog.py    # 家族対話 100 問スタブ
```

## Phase 0 での到達点

スタブを配置し、`python3 bench/runner.py --list` でスイート一覧が返ること。
実装本体 (データセット DL / 採点 / judge 呼び出し) は Phase 1 で完成させる。

## ライセンス注意

- JGLUE: CC BY-SA 4.0 — 公開評価結果に出典を明記
- ELYZA-tasks-100: Apache 2.0 互換 — judge モデル (GPT-4) の利用規約別途
- JMT-Bench: Apache 2.0 — GPT-4 judge 課金に注意

## See Also

- `docs/MODEL_BASELINE.md`
- `docs/LICENSES.md`

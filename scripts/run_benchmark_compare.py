#!/usr/bin/env python3
"""
ベンチマーク比較スクリプト
Phi-3 と Qwen 2.5 の応答品質を比較する。
注意: settings.json は一切書き換えない。メモリ上のconfigのみ使用。
"""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.aether_benchmark import AetherBenchmark, BENCHMARK_CASES


def run_with_model(model_file: str, model_name: str, base_config: dict) -> dict:
    """指定モデルでベンチマークを実行（settings.jsonは変更しない）"""
    # メモリ上のコピーだけ変更
    config = copy.deepcopy(base_config)
    config["model_file"] = model_file
    config["context_length"] = 1024
    config["n_gpu_layers"] = 0
    config["flash_attn"] = False

    print(f"\n{'='*60}")
    print(f"  Loading: {model_name}")
    print(f"  File: {model_file}")
    print(f"{'='*60}\n")

    from core.llm import LLMEngine
    engine = LLMEngine(
        model_path=BASE_DIR / "models",
        config=config,
    )

    if not engine.is_loaded():
        print(f"[!] {model_name} の読み込みに失敗。スキップします。")
        return None

    system_prompt = (
        "私はアイ。あなたと直接話している。"
        "日本語だけで答える。「だよ」「だね」など柔らかい語尾。"
        "1〜3文で自然に返す。"
    )

    def chat_fn(text: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        return engine.generate_chat(messages, max_tokens=200)

    bench = AetherBenchmark(data_dir=BASE_DIR / "data" / "benchmarks")
    report = bench.run_full_benchmark(chat_fn, model_name)
    report_text = bench.print_report(report)
    print(report_text)

    print("\n  All Responses:")
    for r in report.results:
        resp = r["response"][:60].replace("\n", " ")
        status = "PASS" if r["passed"] else "FAIL"
        print(f"    [{status}] {r['test_id']}: {r['input_text'][:15]:15s} -> {resp}")

    del engine
    return report


def main():
    # 設定読み込み（変更しない）
    settings_path = BASE_DIR / "config" / "settings.json"
    with open(settings_path) as f:
        settings = json.load(f)
    base_config = settings["llm"]

    models = [
        ("Phi-3-mini-4k-instruct-q4.gguf", "Phi-3-mini-4k-Q4"),
        ("qwen2.5-3b-instruct-q4_k_m.gguf", "Qwen2.5-3B-Q4_K_M"),
    ]

    reports = {}
    for model_file, model_name in models:
        model_path = BASE_DIR / "models" / model_file
        if not model_path.exists():
            print(f"[Skip] {model_file} が見つかりません")
            continue
        reports[model_name] = run_with_model(model_file, model_name, base_config)

    if len(reports) >= 2:
        names = list(reports.keys())
        r1, r2 = reports[names[0]], reports[names[1]]
        if r1 and r2:
            print(f"\n{'='*60}")
            print(f"  COMPARISON: {names[0]} vs {names[1]}")
            print(f"{'='*60}")
            print(f"  Overall: {r1.overall_score:.1%} -> {r2.overall_score:.1%}")
            print(f"  Passed:  {r1.passed}/{r1.total_tests} -> {r2.passed}/{r2.total_tests}")
            print()

            all_cats = sorted(set(
                list(r1.category_scores.keys()) + list(r2.category_scores.keys())
            ))
            for cat in all_cats:
                s1 = r1.category_scores.get(cat, 0)
                s2 = r2.category_scores.get(cat, 0)
                diff = s2 - s1
                arrow = "+" if diff > 0 else ""
                print(f"    {cat:20s}: {s1:.1%} -> {s2:.1%} ({arrow}{diff:.1%})")


if __name__ == "__main__":
    main()

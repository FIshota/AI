#!/usr/bin/env python3
"""
Sarashina 2.2 3B-Instruct セットアップスクリプト (日本製).

SB Intuitions (SoftBank 子会社, 日本) が開発する日本語 LLM。
HuggingFace から GGUF 形式のモデルをダウンロードし、
あいちゃんの models/ ディレクトリに配置する。

使い方:
    python scripts/setup_sarashina.py
    python scripts/setup_sarashina.py --quantize q4_k_m
    python scripts/setup_sarashina.py --quantize q8_0

なぜ Sarashina か:
    - 日本発の日本語ネイティブ LLM (SB Intuitions / SoftBank 子会社)
    - Apache-2.0 / MIT 系の寛容なライセンス
    - llama-cpp-python と互換 (llama2 アーキテクチャベース)
    - 中国系モデル (Qwen 等) への依存を排除

以前の Qwen2.5 セットアップは 2026-04-21 に廃止。
後方互換のため scripts/setup_qwen.py は wrapper として本スクリプトへ委譲する。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# ─── 設定 ─────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

# HuggingFace の GGUF リポジトリ (mmnga は日本在住のコミュニティ maintainer
# として日本語 LLM の GGUF 変換を多数公開しており、sbintuitions 公式も参照する)
GGUF_REPOS = {
    "q4_k_m": {
        "repo": "mmnga/sarashina2.2-3b-instruct-v0.1-gguf",
        "file": "sarashina2.2-3b-instruct-v0.1-Q4_K_M.gguf",
        "size_gb": 2.0,
        "description": "4bit 量子化 (推奨 - 品質と速度のバランス)",
    },
    "q5_k_m": {
        "repo": "mmnga/sarashina2.2-3b-instruct-v0.1-gguf",
        "file": "sarashina2.2-3b-instruct-v0.1-Q5_K_M.gguf",
        "size_gb": 2.4,
        "description": "5bit 量子化 (やや高品質)",
    },
    "q8_0": {
        "repo": "mmnga/sarashina2.2-3b-instruct-v0.1-gguf",
        "file": "sarashina2.2-3b-instruct-v0.1-Q8_0.gguf",
        "size_gb": 3.4,
        "description": "8bit 量子化 (最高品質、メモリ多め)",
    },
}

DEFAULT_QUANT = "q4_k_m"


def check_dependencies() -> bool:
    """必要なパッケージを確認"""
    try:
        import huggingface_hub  # noqa: F401
        return True
    except ImportError:
        print("[Setup] huggingface_hub が必要です。インストールします...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "huggingface_hub",
        ])
        return True


def download_model(quant: str = DEFAULT_QUANT) -> Path | None:
    """GGUF モデルをダウンロード"""
    if quant not in GGUF_REPOS:
        print(f"[Setup] 不明な量子化タイプ: {quant}")
        print(f"[Setup] 使用可能: {', '.join(GGUF_REPOS.keys())}")
        return None

    info = GGUF_REPOS[quant]
    out_path = MODELS_DIR / info["file"]

    if out_path.exists():
        print(f"[Setup] モデルは既にダウンロード済み: {out_path.name}")
        return out_path

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Sarashina 2.2 3B-Instruct ({quant}) ダウンロード")
    print(f"  開発元: SB Intuitions (日本)")
    print(f"  サイズ: ~{info['size_gb']:.1f} GB")
    print(f"  説明: {info['description']}")
    print(f"  リポジトリ: {info['repo']}")
    print(f"{'='*60}\n")

    try:
        from huggingface_hub import hf_hub_download
        downloaded = hf_hub_download(
            repo_id=info["repo"],
            filename=info["file"],
            local_dir=str(MODELS_DIR),
            local_dir_use_symlinks=False,
        )
        final_path = Path(downloaded)
        print(f"\n[Setup] ✓ ダウンロード完了: {final_path.name}")
        print(f"[Setup] ✓ サイズ: {final_path.stat().st_size / 1e9:.2f} GB")
        return final_path
    except Exception as e:
        print(f"[Setup] ダウンロードエラー: {e}")
        print("[Setup] 代替 repo を試したい場合は以下を試してください:")
        print("         - sbintuitions/sarashina2.2-3b-instruct-v0.1 (safetensors)")
        print("         - llm-jp/llm-jp-3-3.7b-instruct (日本コンソーシアム)")
        print("         - tokyotech-llm/Llama-3-Swallow-8B-Instruct-v0.1")
        return None


def update_settings(model_filename: str) -> None:
    """settings.json のモデルパスを更新"""
    import json
    settings_path = BASE_DIR / "config" / "settings.json"
    if not settings_path.exists():
        print("[Setup] settings.json が無いので更新をスキップ (settings.json.example を手動コピーしてください)")
        return
    with open(settings_path) as f:
        settings = json.load(f)

    settings["llm"]["model_path"] = "models/"
    settings["llm"]["model_file"] = model_filename

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    print(f"[Setup] ✓ settings.json を更新: model_file={model_filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sarashina 2.2 3B-Instruct セットアップ (日本製)")
    parser.add_argument(
        "--quantize", "-q",
        choices=list(GGUF_REPOS.keys()),
        default=DEFAULT_QUANT,
        help=f"量子化タイプ (default: {DEFAULT_QUANT})",
    )
    parser.add_argument(
        "--update-settings", "-u",
        action="store_true",
        default=True,
        help="settings.json を自動更新 (default: True)",
    )
    args = parser.parse_args()

    print("[Setup] Sarashina 2.2 3B-Instruct セットアップを開始します")
    print("[Setup] 開発元: SB Intuitions (日本) / Apache-2.0 ライセンス")
    print("[Setup] マシン: M2 Pro 16GB / Intel Mac いずれも対応")
    print()

    check_dependencies()
    model_path = download_model(args.quantize)

    if model_path and args.update_settings:
        update_settings(model_path.name)

    if model_path:
        print(f"\n{'='*60}")
        print("  セットアップ完了!")
        print(f"  モデル: {model_path.name}")
        print("  あいちゃんを起動すると Sarashina 2.2 (日本製) が使われます。")
        print(f"{'='*60}")
    else:
        print("\n[Setup] セットアップに失敗しました。")
        sys.exit(1)


if __name__ == "__main__":
    main()

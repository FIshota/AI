#!/usr/bin/env python3
"""
Qwen 2.5 3B-Instruct セットアップスクリプト

HuggingFace から GGUF 形式のモデルをダウンロードし、
あいちゃんの models/ ディレクトリに配置する。

使い方:
    python scripts/setup_qwen.py
    python scripts/setup_qwen.py --quantize q4_k_m    # 量子化指定
    python scripts/setup_qwen.py --quantize q8_0       # 高品質版
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ─── 設定 ─────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

# HuggingFace の GGUF リポジトリ（コミュニティ変換済み）
GGUF_REPOS = {
    "q4_k_m": {
        "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_gb": 2.0,
        "description": "4bit量子化（推奨 - 品質と速度のバランス）",
    },
    "q5_k_m": {
        "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "file": "qwen2.5-3b-instruct-q5_k_m.gguf",
        "size_gb": 2.4,
        "description": "5bit量子化（やや高品質）",
    },
    "q8_0": {
        "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "file": "qwen2.5-3b-instruct-q8_0.gguf",
        "size_gb": 3.4,
        "description": "8bit量子化（最高品質、メモリ多め）",
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
    """GGUFモデルをダウンロード"""
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
    print(f"  Qwen 2.5 3B-Instruct ({quant}) ダウンロード")
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
        return None


def update_settings(model_filename: str) -> None:
    """settings.json のモデルパスを更新"""
    import json
    settings_path = BASE_DIR / "config" / "settings.json"
    with open(settings_path) as f:
        settings = json.load(f)

    settings["llm"]["model_path"] = "models/"
    # model_file を明示的に指定（複数モデルがある場合にQwenを優先）
    settings["llm"]["model_file"] = model_filename

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    print(f"[Setup] ✓ settings.json を更新: model_file={model_filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen 2.5 3B-Instruct セットアップ")
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

    print("[Setup] Qwen 2.5 3B-Instruct セットアップを開始します")
    print(f"[Setup] マシン: M2 Pro 16GB に最適化")
    print()

    check_dependencies()
    model_path = download_model(args.quantize)

    if model_path and args.update_settings:
        update_settings(model_path.name)

    if model_path:
        print(f"\n{'='*60}")
        print("  セットアップ完了!")
        print(f"  モデル: {model_path.name}")
        print("  あいちゃんを起動するとQwen 2.5が使われます。")
        print(f"{'='*60}")
    else:
        print("\n[Setup] セットアップに失敗しました。")
        sys.exit(1)


if __name__ == "__main__":
    main()

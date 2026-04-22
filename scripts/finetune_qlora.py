#!/usr/bin/env python3
"""
D9: QLoRA微調整スクリプト - Aether Model Fine-tuning

MLX フレームワークを使用して Apple Silicon 上で
Sarashina 2.2 3B-Instruct (SB Intuitions / 日本) を QLoRA 微調整する。

2026-04-21: 中国ベース Qwen 2.5 依存を排除し、日本製 Sarashina に切替。

前提:
- macOS + Apple Silicon (M1/M2/M3)
- mlx / mlx-lm がインストール済み
- 訓練データが data/training/train.jsonl に存在

使い方:
    python scripts/finetune_qlora.py
    python scripts/finetune_qlora.py --epochs 3 --lr 1e-4
    python scripts/finetune_qlora.py --data data/training/train.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
TRAINING_DIR = BASE_DIR / "data" / "training"
ADAPTERS_DIR = BASE_DIR / "models" / "adapters"


def check_mlx() -> bool:
    """MLX関連パッケージを確認・インストール"""
    required = ["mlx", "mlx_lm"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[FineTune] 必要なパッケージをインストール: {missing}")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "mlx", "mlx-lm",
        ])

    return True


_PREFERRED_MODEL_KEYWORDS = ("sarashina", "llm-jp", "swallow", "elyza", "rinna", "calm")


def find_model() -> Path | None:
    """日本製優先でベースモデルを探す (sarashina/llm-jp/swallow/elyza/rinna/calm)."""
    # 1) 日本製 GGUF を優先
    for keyword in _PREFERRED_MODEL_KEYWORDS:
        for f in MODELS_DIR.glob("*.gguf"):
            if keyword in f.name.lower():
                return f
        for d in MODELS_DIR.iterdir():
            if d.is_dir() and keyword in d.name.lower():
                return d
    # 2) フォールバック: 任意の GGUF (中国系は警告)
    for f in MODELS_DIR.glob("*.gguf"):
        if "qwen" in f.name.lower() or "deepseek" in f.name.lower() or "yi-" in f.name.lower():
            print(f"[FineTune] 警告: 中国系モデル {f.name} を検出。"
                  "scripts/setup_sarashina.py で日本製に差し替えを推奨。")
        return f
    return None


def convert_to_mlx(model_path: Path) -> Path:
    """HuggingFaceモデルをMLX形式に変換"""
    mlx_dir = MODELS_DIR / f"{model_path.stem}-mlx-4bit"
    if mlx_dir.exists():
        print(f"[FineTune] MLX変換済み: {mlx_dir.name}")
        return mlx_dir

    print(f"[FineTune] MLX形式に変換中（4bit量子化）...")
    subprocess.check_call([
        sys.executable, "-m", "mlx_lm.convert",
        "--hf-path", str(model_path),
        "--mlx-path", str(mlx_dir),
        "-q",  # 量子化
    ])
    print(f"[FineTune] ✓ 変換完了: {mlx_dir.name}")
    return mlx_dir


def generate_training_data() -> Path:
    """訓練データが無ければ生成"""
    train_file = TRAINING_DIR / "train.jsonl"
    if train_file.exists():
        line_count = sum(1 for _ in open(train_file))
        print(f"[FineTune] 訓練データ: {line_count} 件")
        return train_file

    print("[FineTune] 訓練データを生成中...")
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)

    # 訓練データ生成エンジンを使用
    sys.path.insert(0, str(BASE_DIR))
    from core.aether_training_gen import AetherTrainingGen

    gen = AetherTrainingGen(TRAINING_DIR)
    examples = gen.generate_dataset(target_count=5000)
    gen.export_train_valid_split(examples)

    stats = gen.stats(examples)
    print(f"[FineTune] ✓ データ生成完了: {stats['total']} 件")
    for cat, count in stats["categories"].items():
        print(f"  {cat}: {count} 件")

    return train_file


def run_finetune(
    model_dir: Path,
    train_file: Path,
    epochs: int = 3,
    lr: float = 1e-4,
    batch_size: int = 1,
    lora_rank: int = 16,
    lora_layers: int = 16,
) -> Path:
    """QLoRA微調整を実行"""
    adapter_dir = ADAPTERS_DIR / f"aether-{time.strftime('%Y%m%d_%H%M')}"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    valid_file = train_file.parent / "valid.jsonl"

    print(f"\n{'='*60}")
    print("  Aether QLoRA Fine-tuning")
    print(f"  Model: {model_dir.name}")
    print(f"  Train: {train_file}")
    print(f"  Epochs: {epochs}")
    print(f"  LR: {lr}")
    print(f"  LoRA rank: {lora_rank}")
    print(f"  Batch size: {batch_size}")
    print(f"  Output: {adapter_dir}")
    print(f"{'='*60}\n")

    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "--model", str(model_dir),
        "--data", str(train_file.parent),
        "--train",
        "--batch-size", str(batch_size),
        "--lora-layers", str(lora_layers),
        "--lora-rank", str(lora_rank),
        "--num-epochs", str(epochs),
        "--learning-rate", str(lr),
        "--adapter-path", str(adapter_dir),
    ]

    if valid_file.exists():
        cmd.extend(["--val-data", str(valid_file)])

    start = time.time()
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"\n[FineTune] ✓ 微調整完了！({elapsed/60:.1f}分)")
        print(f"[FineTune] アダプター: {adapter_dir}")

        # メタデータ保存
        meta = {
            "model": model_dir.name,
            "epochs": epochs,
            "lr": lr,
            "lora_rank": lora_rank,
            "lora_layers": lora_layers,
            "batch_size": batch_size,
            "duration_sec": round(elapsed),
            "timestamp": time.time(),
        }
        with open(adapter_dir / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        return adapter_dir
    else:
        print(f"\n[FineTune] ✗ 微調整失敗 (exit code: {result.returncode})")
        return adapter_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Aether QLoRA微調整")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-layers", type=int, default=16)
    parser.add_argument("--data", type=str, default=None)
    args = parser.parse_args()

    print("[FineTune] Aether QLoRA 微調整を開始")
    print(f"[FineTune] 環境: Apple Silicon (M2 Pro 16GB)")
    print()

    # 1. MLX確認
    check_mlx()

    # 2. モデル確認
    model_path = find_model()
    if not model_path:
        print("[FineTune] ベースモデルが見つかりません。")
        print("[FineTune] 先に `python scripts/setup_sarashina.py` を実行してください。")
        sys.exit(1)

    # 3. MLX形式に変換（GGUF以外の場合）
    if model_path.is_dir():
        mlx_dir = convert_to_mlx(model_path)
    else:
        # GGUF の場合、HuggingFace からMLX版をダウンロード (日本製 Sarashina 2.2)
        print("[FineTune] GGUF形式は直接微調整できません。")
        print("[FineTune] HuggingFace から sbintuitions/sarashina2.2-3b-instruct-v0.1 をダウンロードします。")
        try:
            from huggingface_hub import snapshot_download
            hf_dir = MODELS_DIR / "sarashina2.2-3b-instruct-v0.1"
            if not hf_dir.exists():
                snapshot_download(
                    "sbintuitions/sarashina2.2-3b-instruct-v0.1",
                    local_dir=str(hf_dir),
                )
            mlx_dir = convert_to_mlx(hf_dir)
        except Exception as e:
            print(f"[FineTune] ダウンロードエラー: {e}")
            sys.exit(1)

    # 4. 訓練データ
    if args.data:
        train_file = Path(args.data)
    else:
        train_file = generate_training_data()

    # 5. 微調整実行
    adapter_dir = run_finetune(
        model_dir=mlx_dir,
        train_file=train_file,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        lora_rank=args.lora_rank,
        lora_layers=args.lora_layers,
    )

    print(f"\n{'='*60}")
    print("  完了！")
    print(f"  アダプター: {adapter_dir}")
    print(f"  ")
    print(f"  テスト: python -m mlx_lm.generate \\")
    print(f"    --model {mlx_dir} \\")
    print(f"    --adapter-path {adapter_dir} \\")
    print(f"    --prompt 'おはよう'")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

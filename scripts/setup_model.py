#!/usr/bin/env python3
"""
モデルセットアップスクリプト
推奨モデルをダウンロードしてmodels/ディレクトリに配置します

【推奨モデル（サイズ順）】
1. Mistral-7B-Instruct-v0.3    ~4.1GB  高性能・日本語高品質（推奨）
2. TinyLlama-1.1B-Chat-v1.0    ~0.6GB  超軽量・動作確認用
3. Phi-3-mini-4k-instruct-q4   ~2.2GB  高性能・軽量
"""
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
MODELS_DIR = BASE_DIR / "models"

MODELS = {
    "1": {
        "name": "Mistral-7B-Instruct v0.3 (推奨・4.1GB, 日本語高品質)",
        "url": "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        "filename": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        "size_gb": 4.1,
    },
    "2": {
        "name": "TinyLlama-1.1B (超軽量・0.6GB)",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "filename": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size_gb": 0.6,
    },
    "3": {
        "name": "Phi-3-mini (高性能・軽量・2.2GB)",
        "url": "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf",
        "filename": "Phi-3-mini-4k-instruct-q4.gguf",
        "size_gb": 2.2,
    },
}


def download_with_progress(url: str, dest: Path):
    """
    curl を使用してダウンロードします（macOS標準 SSL証明書を使用）。
    curl がない場合は wget、それもなければ Python urllib（SSL検証なし）にフォールバックします。
    """
    print(f"ダウンロード先: {dest}")

    # curl を優先（macOS標準・SSL証明書の問題なし）
    if shutil.which("curl"):
        result = subprocess.run(
            ["curl", "-L", "--progress-bar", "-o", str(dest), url],
            check=False,
        )
        if result.returncode == 0:
            return
        raise RuntimeError(f"curl がエラーコード {result.returncode} で終了しました")

    # wget フォールバック
    if shutil.which("wget"):
        result = subprocess.run(
            ["wget", "-O", str(dest), url],
            check=False,
        )
        if result.returncode == 0:
            return
        raise RuntimeError(f"wget がエラーコード {result.returncode} で終了しました")

    # 最終手段: urllib（SSL検証なし）
    import urllib.request
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def report(block_num, block_size, total_size):
        if total_size <= 0:
            return
        downloaded = block_num * block_size
        percent = min(100, downloaded * 100 // total_size)
        mb_done = downloaded / 1024 / 1024
        mb_total = total_size / 1024 / 1024
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
        print(f"\r  [{bar}] {percent}%  {mb_done:.1f}/{mb_total:.1f} MB", end="", flush=True)

    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    urllib.request.install_opener(opener)
    urllib.request.urlretrieve(url, dest, reporthook=report)
    print()


def install_llama_cpp():
    """llama-cpp-python をMetal対応でインストール"""
    import subprocess
    print("\nllama-cpp-python (Metal GPU対応) をインストールします...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install",
         "llama-cpp-python",
         "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/metal"],
        capture_output=False,
    )
    return result.returncode == 0


def main():
    print("=" * 50)
    print("  アイ モデルセットアップ")
    print("=" * 50)

    MODELS_DIR.mkdir(exist_ok=True)

    # llama-cpp-python の確認
    try:
        import llama_cpp
        print("✓ llama-cpp-python インストール済み")
    except ImportError:
        print("⚠ llama-cpp-python が未インストールです")
        ans = input("Metal GPU対応版をインストールしますか？ [Y/n]: ").strip().lower()
        if ans in ("", "y"):
            if install_llama_cpp():
                print("✓ インストール完了")
            else:
                print("✗ インストール失敗。手動で実行してください:")
                print("  pip install llama-cpp-python")
                sys.exit(1)

    # 既存モデルの確認
    existing = list(MODELS_DIR.glob("*.gguf"))
    if existing:
        print(f"\n既存のモデル: {[f.name for f in existing]}")
        ans = input("すでにモデルがあります。追加でダウンロードしますか？ [y/N]: ").strip().lower()
        if ans != "y":
            print("セットアップ完了！")
            return

    # モデル選択
    print("\n利用可能なモデル:")
    for key, model in MODELS.items():
        print(f"  {key}. {model['name']}")

    choice = input("\nダウンロードするモデルを選択 [1]: ").strip() or "1"
    if choice not in MODELS:
        print("無効な選択です。")
        sys.exit(1)

    model = MODELS[choice]
    dest = MODELS_DIR / model["filename"]

    if dest.exists():
        print(f"✓ {model['filename']} は既に存在します")
    else:
        print(f"\n{model['name']} をダウンロードします ({model['size_gb']} GB)")
        print("注意: ダウンロードには時間がかかります。Ctrl+C でキャンセルできます。\n")
        try:
            download_with_progress(model["url"], dest)
            print(f"✓ ダウンロード完了: {dest}")
        except KeyboardInterrupt:
            print("\nダウンロードをキャンセルしました")
            if dest.exists():
                dest.unlink()
            sys.exit(0)
        except Exception as e:
            print(f"\nダウンロードエラー: {e}")
            print("手動でダウンロードして models/ フォルダに配置してください。")
            sys.exit(1)

    print("\n✓ セットアップ完了！")
    print("  python main.py でアイを起動してください。")


if __name__ == "__main__":
    main()

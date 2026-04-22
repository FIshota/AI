#!/usr/bin/env python3
"""HuggingFace → GGUF 変換スクリプトの薄いラッパー (M6, 2026-04-21).

実体は llama.cpp 上流から vendored した 6,195 行のコードで、
ai-chan の本体コードベース (lint / bandit / grep) から切り離すため
`scripts/vendor/llama_cpp/convert_hf_to_gguf.py` へ隔離されている。

このラッパーは後方互換のため、旧パス
`scripts/convert_hf_to_gguf.py` で呼ばれても透過的に vendor 側を
実行する。CLI 引数・標準入出力・終了コードはそのまま引き継がれる。

背景:
    - vendored コピーを本体ツリーに置くと grep ノイズが爆発し、
      bandit 監査も false-positive だらけになるため。
    - 上流追従は vendor/ 配下でのみ行い、本体側の lint/type 対象からは
      pyproject.toml の extend-exclude で除外している。

使い方 (変更なし):
    python scripts/convert_hf_to_gguf.py <model_dir> --outfile <out.gguf>
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_VENDOR_SCRIPT = (
    Path(__file__).resolve().parent / "vendor" / "llama_cpp" / "convert_hf_to_gguf.py"
)


def main() -> None:
    if not _VENDOR_SCRIPT.is_file():
        print(
            f"[convert_hf_to_gguf wrapper] vendor script not found: {_VENDOR_SCRIPT}",
            file=sys.stderr,
        )
        sys.exit(2)
    # runpy で実行することで、元スクリプトの `if __name__ == '__main__':`
    # ブロックがそのまま走る。sys.argv[0] は維持されるため、ヘルプ表示も
    # 違和感がない。
    runpy.run_path(str(_VENDOR_SCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()

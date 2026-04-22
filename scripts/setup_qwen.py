#!/usr/bin/env python3
"""DEPRECATED: Qwen2.5 (中国 Alibaba) セットアップは 2026-04-21 に廃止.

本スクリプトは後方互換のための wrapper で、実体は
``scripts/setup_sarashina.py`` (SB Intuitions / 日本製) へ委譲する。

理由:
    ai-chan は家族として信頼できる基盤を持つべきであり、
    開発者判断により中国ベースモデル (Qwen 系) 依存を排除した。
    同等サイズの日本製 Sarashina 2.2 3B-Instruct に置き換える。

新しい呼び出し:
    python scripts/setup_sarashina.py
"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "setup_qwen.py は廃止されました。代わりに setup_sarashina.py を使用してください "
    "(中国ベース Qwen → 日本製 Sarashina 2.2 への移行)。",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    print("[Setup] setup_qwen.py は廃止されました。setup_sarashina.py に委譲します。\n")
    from scripts import setup_sarashina  # type: ignore[import-not-found]
    setup_sarashina.main()
    sys.exit(0)

"""
core.ops — AiChan 責務分割パッケージ（M2: God Object 解体の一部）

AiChan god object (core/ai_chan.py, 3769 行) から低結合の責務を
機能別モジュールに切り出す。各モジュールは純粋な関数として
AiChan インスタンスを第一引数に取り、戻り値は文字列（ユーザー向け応答）。

AiChan 側には後方互換のため薄い委譲メソッドを残す。
"""
from __future__ import annotations

from core.ops import security_ops, server_ops

__all__ = ["security_ops", "server_ops"]

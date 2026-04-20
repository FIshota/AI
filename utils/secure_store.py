"""
secure_store — JSON ファイルの透過的な暗号化読み書きヘルパー。

B2 fix (2026-04-21): diary / emotion_history / anniversary など個人情報を
含む JSON ファイルを AES-256-GCM で暗号化する。

ファイル形式:
- プレーン: 通常の JSON（後方互換のため読める）
- 暗号化: 1行目に magic `AICHAN_ENC_V1\n`、2行目以降に base64 暗号文

key=None を渡した場合は平文のまま読み書きする（暗号化無効モード）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from utils.crypto import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)

_MAGIC = "AICHAN_ENC_V1\n"


def load_json(path: Path, key: bytes | None, default: Any) -> Any:
    """JSON を読み込む。暗号化されていれば復号する。

    Args:
        path: ファイルパス
        key: 暗号鍵（None なら暗号化無効）
        default: ファイルが存在しない / 読めない時の返り値

    Returns:
        デシリアライズされた値（list / dict など）
    """
    if not path.exists():
        return default
    try:
        raw = path.read_text("utf-8")
    except OSError as exc:
        logger.warning("secure_store: 読み込み失敗 %s (%s)", path, exc)
        return default

    if raw.startswith(_MAGIC):
        if key is None:
            logger.error(
                "secure_store: %s は暗号化されていますが鍵が None です。"
                "データを読み込めません。",
                path,
            )
            return default
        body = raw[len(_MAGIC):]
        try:
            plain = decrypt_text(body, key)
            return json.loads(plain)
        except Exception as exc:
            logger.error("secure_store: 復号失敗 %s (%s)", path, exc)
            return default

    # 平文 JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("secure_store: JSON パース失敗 %s (%s)", path, exc)
        return default

    # 鍵があるのに平文 → 初回移行のため自動で暗号化書き戻し
    if key is not None:
        logger.info("secure_store: 平文を暗号化形式へ移行 %s", path)
        save_json(path, data, key)
    return data


def save_json(path: Path, data: Any, key: bytes | None) -> None:
    """JSON を書き出す。鍵があれば暗号化する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    if key is None:
        path.write_text(serialized, "utf-8")
        return
    cipher = encrypt_text(serialized, key)
    path.write_text(_MAGIC + cipher, "utf-8")

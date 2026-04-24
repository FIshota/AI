"""
スクリーンショット用ブラー / REDACT フィルタ。

- Pillow が使えれば box filter を用いる
- 使えなければ stdlib + zlib で粗いダウンサンプル+アップサンプルする純 Python フォールバック
- REDACT は全面単色 (黒)
- 元画像は一切ディスクに残さない (メモリ内処理のみ)

Author: ai-chan
"""
from __future__ import annotations

import io
import struct
import zlib
from typing import Optional

from core.screenshot_sensitive import SensitiveAction

try:
    from PIL import Image, ImageFilter  # type: ignore

    PILLOW_OK = True
except Exception:  # pragma: no cover
    PILLOW_OK = False


# ---------------------------------------------------------------------------
# 純 Python (stdlib) PNG ユーティリティ
# ---------------------------------------------------------------------------

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _encode_solid_png(width: int, height: int, rgb: tuple = (0, 0, 0)) -> bytes:
    """単色 PNG をメモリ上で生成する。"""
    width = max(1, int(width))
    height = max(1, int(height))
    r, g, b = rgb
    # 各行の先頭 filter byte 0 + RGB * width
    row = bytes([0]) + bytes([r, g, b]) * width
    raw = row * height
    compressed = zlib.compress(raw, 6)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def _fallback_blur(image_bytes: bytes, strength: int) -> bytes:
    """
    Pillow が無いケースのフォールバック。

    入力 PNG のサイズを読み取り、そのサイズの全面灰色 PNG を返す。
    ダウンサンプル + アップサンプルの実装は PNG を解凍する必要があり
    stdlib だけでは現実的でないため、安全側 (情報削除) に倒す。
    """
    width, height = _read_png_size(image_bytes) or (64, 64)
    # 強ブラー相当 = 中間グレー単色
    intensity = max(0, min(255, 128))
    return _encode_solid_png(width, height, (intensity, intensity, intensity))


def _read_png_size(image_bytes: bytes) -> Optional[tuple]:
    try:
        if len(image_bytes) < 24 or image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        # IHDR は署名 8B の直後、長さ 4B + "IHDR" 4B + width 4B + height 4B
        width = struct.unpack(">I", image_bytes[16:20])[0]
        height = struct.unpack(">I", image_bytes[20:24])[0]
        return (width, height)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pillow 版
# ---------------------------------------------------------------------------

def _pillow_blur(image_bytes: bytes, strength: int) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    # BoxBlur は半径。強度をそのまま半径として使う。
    blurred = img.filter(ImageFilter.BoxBlur(max(1, int(strength))))
    out = io.BytesIO()
    blurred.save(out, format="PNG")
    return out.getvalue()


def _pillow_redact(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    black = Image.new("RGB", (w, h), (0, 0, 0))
    out = io.BytesIO()
    black.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def apply_blur(
    image_bytes: bytes,
    action: SensitiveAction,
    strength: int = 25,
) -> bytes:
    """
    与えられた PNG バイト列に action に応じた処理を適用する。

    - BLOCK: 空 bytes を返す (取り込み完全禁止)
    - REDACT: 全面黒画像を返す
    - BLUR: 強ブラー画像を返す (strength が半径)

    引数 image_bytes は変更しない (immutable)。
    """
    if image_bytes is None:
        return b""

    if action is SensitiveAction.BLOCK:
        return b""

    if action is SensitiveAction.REDACT:
        if PILLOW_OK:
            try:
                return _pillow_redact(image_bytes)
            except Exception:
                pass
        size = _read_png_size(image_bytes) or (64, 64)
        return _encode_solid_png(size[0], size[1], (0, 0, 0))

    if action is SensitiveAction.BLUR:
        if PILLOW_OK:
            try:
                return _pillow_blur(image_bytes, strength)
            except Exception:
                pass
        return _fallback_blur(image_bytes, strength)

    # 未知の action は安全側 = 空バイト
    return b""

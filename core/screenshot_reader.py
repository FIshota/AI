"""
スクリーンショット読み取りシステム（macOS専用）
screencapture で画面を取得し、Pillow で解析、
tesseract が使えれば OCR でテキスト抽出します。
"""
from __future__ import annotations
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

try:
    import pytesseract
    TESSERACT_OK = True
except ImportError:
    TESSERACT_OK = False


def capture_screen(hide_windows: list = None) -> Optional[Path]:
    """
    スクリーンショットを一時ファイルに保存して Path を返します。
    失敗時は None を返します。
    機密画面検出 (screenshot_sensitive) により、検出時はブラー/黒塗り/破棄されます。
    """
    try:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, prefix="aichan_ss_"
        )
        tmp.close()
        # -x: 音なし, -t png: PNG形式
        subprocess.run(
            ["screencapture", "-x", "-t", "png", tmp.name],
            check=True, timeout=10
        )
        _apply_sensitive_guard(Path(tmp.name))
        return Path(tmp.name)
    except Exception as e:
        print(f"[Screenshot] キャプチャ失敗: {e}", flush=True)
        return None


def _apply_sensitive_guard(path: Path, window_title: str = "", bundle_id: str = "") -> None:
    """キャプチャ直後に機密画面を検出し、必要なら in-place 加工する (安全側既定)。"""
    try:
        from core.screenshot_sensitive import SensitiveClassifier, SensitiveAction
        from core.screenshot_blur import apply_blur
        pat = SensitiveClassifier().classify(window_title, bundle_id)
        if pat is None:
            return
        data = path.read_bytes()
        processed = apply_blur(data, pat.action)
        if pat.action == SensitiveAction.BLOCK or not processed:
            path.write_bytes(b"")
            print(f"[Screenshot] BLOCK 機密画面検出: {pat.name}", flush=True)
        else:
            path.write_bytes(processed)
            print(f"[Screenshot] {pat.action.name} 適用: {pat.name}", flush=True)
    except Exception as e:
        print(f"[Screenshot] 機密ガード失敗: {e}", flush=True)


def extract_text(image_path: Path, lang: str = "jpn+eng") -> str:
    """
    画像からテキストを OCR で抽出します。
    pytesseract が未インストールの場合は空文字を返します。
    """
    if not TESSERACT_OK or not PILLOW_OK:
        return ""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=lang)
        return text.strip()
    except Exception as e:
        print(f"[Screenshot] OCR 失敗: {e}", flush=True)
        return ""


def describe_screenshot(image_path: Path) -> str:
    """
    スクリーンショットを解析して説明文字列を返します。
    - Pillow あり: サイズ情報
    - tesseract あり: OCR テキストも含める
    """
    if not PILLOW_OK:
        return "スクリーンショットを撮ったよ"

    try:
        img = Image.open(image_path)
        w, h = img.size
        desc = f"スクリーンショット（{w}×{h}px）"

        ocr_text = extract_text(image_path)
        if ocr_text:
            # 長すぎる場合は先頭 300 文字に制限
            preview = ocr_text[:300].replace("\n", " ")
            desc += f"\n画面のテキスト: {preview}"

        return desc
    except Exception:
        return "スクリーンショットを撮ったよ"


def read_and_cleanup(image_path: Path) -> str:
    """読み取り後に一時ファイルを削除"""
    try:
        desc = describe_screenshot(image_path)
    finally:
        try:
            os.unlink(image_path)
        except Exception:
            pass
    return desc

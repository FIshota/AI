"""
クリップボード画像キャプチャ (Clipboard Image)
Sprint 3.0-A: クリップボードから画像を取得する macOS 対応モジュール。

macOS の osascript を使って PNGf 形式のクリップボードデータを取得し、
PIL.Image として返す。Pillow や osascript が利用できない場合は
安全にフォールバックする。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

try:
    from PIL import Image
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False


class ClipboardImageCapture:
    """macOS のクリップボードから画像を取得するクラス。"""

    def __init__(self) -> None:
        self._temp_dir = Path(tempfile.gettempdir())

    def capture(self) -> Any | None:
        """
        クリップボードの画像を PIL.Image として返す。
        画像がない場合や取得に失敗した場合は None。
        """
        if not PILLOW_OK:
            return None

        # 方法1: ImageGrab（macOS Pillow 9.3.0+ 対応）
        img = self._try_imagegrab()
        if img is not None:
            return img

        # 方法2: osascript で PNGf データを取得
        path = self._try_osascript()
        if path is not None:
            try:
                img = Image.open(path)
                # メモリにロードしてからファイルを消す
                img.load()
                return img
            except Exception:
                return None
            finally:
                self._safe_unlink(path)

        return None

    def has_image(self) -> bool:
        """クリップボードに画像データが含まれるか確認する。"""
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'try\n'
                    '  the clipboard as «class PNGf»\n'
                    '  return "yes"\n'
                    'on error\n'
                    '  return "no"\n'
                    'end try',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() == "yes"
        except Exception:
            return False

    def save_to_temp(self) -> Path | None:
        """
        クリップボード画像を一時ファイルに保存し、パスを返す。
        呼び出し側で不要になったら削除すること。
        """
        img = self.capture()
        if img is None:
            return None
        try:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png",
                prefix="aichan_clip_",
                delete=False,
            )
            tmp.close()
            img.save(tmp.name, format="PNG")
            return Path(tmp.name)
        except Exception:
            return None

    # ─── 内部メソッド ───────────────────────────────────────

    @staticmethod
    def _try_imagegrab() -> Any | None:
        """PIL.ImageGrab.grabclipboard() を試す。"""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if img is not None and hasattr(img, "size"):
                return img
        except Exception:
            pass
        return None

    @staticmethod
    def _try_osascript() -> Path | None:
        """
        osascript でクリップボードの PNGf データを一時ファイルに書き出す。
        成功時はファイルパス、失敗時は None。
        """
        try:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png",
                prefix="aichan_clip_osa_",
                delete=False,
            )
            tmp_path = tmp.name
            tmp.close()

            script = (
                'try\n'
                '  set imgData to the clipboard as «class PNGf»\n'
                f'  set filePath to POSIX file "{tmp_path}"\n'
                '  set fRef to open for access filePath with write permission\n'
                '  write imgData to fRef\n'
                '  close access fRef\n'
                '  return "ok"\n'
                'on error errMsg\n'
                '  return "error: " & errMsg\n'
                'end try'
            )

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.stdout.strip() == "ok" and os.path.getsize(tmp_path) > 0:
                return Path(tmp_path)

            # 失敗時はファイルを掃除
            ClipboardImageCapture._safe_unlink(Path(tmp_path))
            return None
        except Exception:
            return None

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        """ファイルが存在すれば安全に削除する。"""
        try:
            if path.exists():
                os.unlink(path)
        except Exception:
            pass

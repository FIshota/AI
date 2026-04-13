"""
画像解析エンジン (Image Analyzer)
Sprint 3.0-A: スクリーンショットや画像から情報を抽出・理解する。

機能:
- 色分析（支配色、カラーパレット抽出）
- テキスト検出（OCR強化、日本語対応）
- レイアウト解析（UIスクリーンショットの構造認識）
- 画像メタデータ抽出
- 簡易オブジェクト検出（色ベース）
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

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


class ImageAnalyzer:
    """
    画像の多角的な解析を行うクラス。
    Pillow / pytesseract がなくても安全にフォールバックする。
    """

    def __init__(self, base_dir: Path | str = ".") -> None:
        self.base_dir = Path(base_dir)
        self._lock = threading.Lock()

    # ─── パブリック API ─────────────────────────────────────

    def analyze(self, image_path_or_pil: Path | str | Any) -> dict:
        """
        画像を総合的に解析し、辞書で返す。

        返り値のキー:
            dominant_colors: list[str]  — 上位色の hex 一覧
            text_content: str           — OCR テキスト
            dimensions: tuple[int,int]  — (幅, 高さ)
            file_size: int              — ファイルサイズ（バイト）、PIL直渡しは 0
            has_text: bool              — テキストが含まれているか
            brightness: float           — 明るさ 0.0〜1.0
            description: str            — 自動生成の日本語要約
        """
        with self._lock:
            return self._analyze_impl(image_path_or_pil)

    def get_dominant_colors(self, image: Any, n: int = 5) -> list[str]:
        """支配的な色を hex 文字列のリストで返す。"""
        if not PILLOW_OK:
            return []
        try:
            img = self._ensure_pil(image)
            if img is None:
                return []
            # 高速化のためリサイズ
            small = img.copy()
            small.thumbnail((150, 150))
            # RGBA → RGB 変換（quantize は RGB のみ対応）
            if small.mode != "RGB":
                small = small.convert("RGB")
            quantized = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
            palette = quantized.getpalette()
            if palette is None:
                return []
            colors: list[str] = []
            available = len(palette) // 3
            for i in range(min(n, available)):
                r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
            return colors
        except Exception:
            return []

    def extract_text(self, image: Any, lang: str = "jpn+eng") -> str:
        """OCR でテキストを抽出する。pytesseract 未インストール時は空文字。"""
        if not TESSERACT_OK or not PILLOW_OK:
            return ""
        try:
            img = self._ensure_pil(image)
            if img is None:
                return ""
            text: str = pytesseract.image_to_string(img, lang=lang)
            return text.strip()
        except Exception:
            return ""

    def analyze_brightness(self, image: Any) -> float:
        """画像の平均明度を 0.0（暗い）〜1.0（明るい）で返す。"""
        if not PILLOW_OK:
            return 0.5
        try:
            img = self._ensure_pil(image)
            if img is None:
                return 0.5
            gray = img.convert("L")
            # 高速化のためリサイズ
            gray.thumbnail((100, 100))
            pixels = list(gray.getdata())
            if not pixels:
                return 0.5
            avg = sum(pixels) / len(pixels)
            return round(avg / 255.0, 3)
        except Exception:
            return 0.5

    def generate_description(self, analysis: dict) -> str:
        """解析結果から日本語の説明文を自動生成する。"""
        parts: list[str] = []

        dims = analysis.get("dimensions")
        if dims:
            w, h = dims
            parts.append(f"{w}×{h}px の画像")

        brightness = analysis.get("brightness", 0.5)
        if brightness < 0.3:
            parts.append("暗めの画像")
        elif brightness > 0.7:
            parts.append("明るめの画像")

        colors = analysis.get("dominant_colors", [])
        if colors:
            color_desc = self._describe_colors(colors[:3])
            if color_desc:
                parts.append(f"主な色は{color_desc}")

        has_text = analysis.get("has_text", False)
        if has_text:
            text_preview = analysis.get("text_content", "")[:80].replace("\n", " ")
            parts.append(f"テキストあり（{text_preview}…）")
        else:
            parts.append("テキストなし")

        file_size = analysis.get("file_size", 0)
        if file_size > 0:
            size_kb = file_size / 1024
            if size_kb > 1024:
                parts.append(f"（{size_kb / 1024:.1f}MB）")
            else:
                parts.append(f"（{size_kb:.0f}KB）")

        if not parts:
            return "画像の詳細を取得できませんでした。"

        return "。".join(parts) + "。"

    # ─── 内部メソッド ───────────────────────────────────────

    def _analyze_impl(self, source: Path | str | Any) -> dict:
        """解析の実装本体（ロック内で呼ばれる）。"""
        result: dict = {
            "dominant_colors": [],
            "text_content": "",
            "dimensions": None,
            "file_size": 0,
            "has_text": False,
            "brightness": 0.5,
            "description": "",
        }

        img = self._ensure_pil(source)

        # ファイルサイズ
        if isinstance(source, (str, Path)):
            path = Path(source)
            if path.is_file():
                result["file_size"] = path.stat().st_size

        if img is None:
            result["description"] = "画像を開けませんでした。"
            return result

        # サイズ
        result["dimensions"] = img.size

        # 色
        result["dominant_colors"] = self.get_dominant_colors(img)

        # 明度
        result["brightness"] = self.analyze_brightness(img)

        # OCR
        text = self.extract_text(img)
        result["text_content"] = text
        result["has_text"] = len(text) > 5

        # 説明
        result["description"] = self.generate_description(result)

        return result

    def _ensure_pil(self, source: Any) -> Any | None:
        """パスまたは PIL.Image を受け取り PIL.Image を返す。"""
        if not PILLOW_OK:
            return None
        if isinstance(source, Image.Image):
            return source
        try:
            return Image.open(str(source))
        except Exception:
            return None

    @staticmethod
    def _describe_colors(hex_colors: list[str]) -> str:
        """hex カラーリストを日本語の色名で近似する。"""
        names: list[str] = []
        for hx in hex_colors:
            name = _hex_to_japanese_name(hx)
            if name and name not in names:
                names.append(name)
        if not names:
            return ""
        return "・".join(names)


# ─── ユーティリティ ─────────────────────────────────────────

_COLOR_MAP: list[tuple[str, int, int, int]] = [
    ("赤", 200, 50, 50),
    ("オレンジ", 230, 150, 50),
    ("黄", 230, 220, 50),
    ("緑", 50, 180, 50),
    ("青", 50, 100, 200),
    ("紫", 150, 50, 200),
    ("ピンク", 230, 130, 170),
    ("白", 240, 240, 240),
    ("黒", 30, 30, 30),
    ("灰", 140, 140, 140),
    ("茶", 140, 90, 50),
]


def _hex_to_japanese_name(hex_color: str) -> str:
    """hex カラーを最も近い日本語色名にマッピングする。"""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return ""

    best_name = ""
    best_dist = float("inf")
    for name, cr, cg, cb in _COLOR_MAP:
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name

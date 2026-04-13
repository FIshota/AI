"""
画面理解エンジン（機能⑨）
三段階フォールバック:

Tier 1 (オプション): moondream ローカルビジョンモデル（~1.8GB, 完全オフライン）
  インストール: pip install transformers torch pillow
Tier 2 (オプション): Tesseract OCR（テキスト抽出のみ）
Tier 3 (常時): 画像ファイル情報のみ返す

Tier 1 を有効にするには初回起動時にモデルがダウンロードされます。
"""
from __future__ import annotations
import subprocess
import tempfile
import os
import platform
from pathlib import Path

IS_MAC = platform.system() == "Darwin"

# Tier 1: Moondream（ローカルビジョン LLM）
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from PIL import Image as PilImage
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

# Tier 2: Tesseract OCR
try:
    import pytesseract
    from PIL import Image as PilImage
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

_MOONDREAM_ID = "vikhyatk/moondream2"
_REVISION     = "2024-08-26"


class VisionEngine:
    """
    画像・スクリーンショット理解エンジン。
    モデルが利用可能な場合は自然言語説明を返す。
    """

    def __init__(self, enable_moondream: bool = False):
        self._enable_moondream = enable_moondream
        self._model     = None
        self._tokenizer = None
        self._loaded    = False

    # ─── モデル管理 ──────────────────────────────────────────────

    def load_moondream(self) -> bool:
        """Moondream モデルを読み込む（初回は ~1.8GB ダウンロード）"""
        if not TRANSFORMERS_AVAILABLE:
            print("[Vision] transformers が見つかりません", flush=True)
            return False
        if self._loaded:
            return True
        try:
            print("[Vision] Moondream を読み込み中...", flush=True)
            self._tokenizer = AutoTokenizer.from_pretrained(
                _MOONDREAM_ID, revision=_REVISION, trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                _MOONDREAM_ID, revision=_REVISION,
                trust_remote_code=True,
                torch_dtype=torch.float32,   # MPS/CPU 安定動作
            )
            self._model.eval()
            self._loaded = True
            print("[Vision] ✓ Moondream 読み込み完了", flush=True)
            return True
        except Exception as e:
            print(f"[Vision] Moondream 読み込みエラー: {e}", flush=True)
            return False

    def is_ready(self) -> bool:
        return self._loaded and self._model is not None

    # ─── 画像説明 ────────────────────────────────────────────────

    def describe_image(self, image_path: str, question: str = "この画像に何が映っていますか？") -> str:
        """
        画像を説明する。
        利用可能な最高 Tier で処理する。
        """
        # Tier 1: Moondream
        if self._enable_moondream and self.is_ready():
            return self._describe_with_moondream(image_path, question)

        # Tier 2: OCR
        if TESSERACT_AVAILABLE:
            return self._describe_with_ocr(image_path)

        # Tier 3: ファイル情報のみ
        return self._describe_basic(image_path)

    def _describe_with_moondream(self, image_path: str, question: str) -> str:
        """Moondream で画像を説明する"""
        try:
            img = PilImage.open(image_path).convert("RGB")
            enc_image = self._model.encode_image(img)
            answer = self._model.answer_question(
                enc_image, question, self._tokenizer
            )
            return answer.strip() if answer else "画像の内容を確認したよ。"
        except Exception as e:
            print(f"[Vision] Moondream 推論エラー: {e}", flush=True)
            return self._describe_with_ocr(image_path) if TESSERACT_AVAILABLE else ""

    def _describe_with_ocr(self, image_path: str) -> str:
        """Tesseract OCR でテキストを抽出する"""
        try:
            img = PilImage.open(image_path)
            text = pytesseract.image_to_string(img, lang="jpn+eng")
            text = text.strip()
            if text:
                snippet = text[:300].replace("\n", " ")
                return f"画面に「{snippet}」というテキストが見えるよ。"
            return "テキストは見当たらなかったよ。"
        except Exception as e:
            print(f"[Vision] OCR エラー: {e}", flush=True)
            return "画面の内容を読み取れなかったよ。"

    def _describe_basic(self, image_path: str) -> str:
        """基本的なファイル情報のみ返す"""
        p = Path(image_path)
        size_kb = p.stat().st_size // 1024 if p.exists() else 0
        return f"スクリーンショット（{size_kb}KB）を撮ったよ。"

    # ─── スクリーンショット ──────────────────────────────────────

    def capture_and_describe(self, question: str = "画面に何が表示されていますか？") -> str:
        """
        スクリーンショットを撮って説明する（macOS 専用）。
        """
        if not IS_MAC:
            return "スクリーンショットは macOS 専用だよ。"

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["screencapture", "-x", "-t", "png", tmp_path],
                capture_output=True, timeout=10
            )
            if result.returncode != 0 or not Path(tmp_path).exists():
                return "スクリーンショットの撮影に失敗したよ。"

            desc = self.describe_image(tmp_path, question)
            return desc
        except Exception as e:
            return f"スクリーンショットエラー: {e}"
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def get_tier_info(self) -> str:
        """現在利用可能な最高 Tier を返す"""
        if self._enable_moondream and self.is_ready():
            return "Tier 1: Moondream (ローカルビジョンモデル)"
        if TESSERACT_AVAILABLE:
            return "Tier 2: Tesseract OCR"
        return "Tier 3: 基本情報のみ"

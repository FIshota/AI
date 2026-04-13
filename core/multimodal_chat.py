"""
マルチモーダルチャットハンドラ (Multimodal Chat Handler)
Sprint 3.0-A: テキスト+画像の複合入力を処理する。

ImageAnalyzer で画像を解析し、その結果をテキストコンテキストとして
LLM に渡すことで、画像について自然に会話できるようにする。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.image_analyzer import ImageAnalyzer
    from core.llm import LLMEngine

try:
    from core.screenshot_reader import capture_screen
    SCREENSHOT_OK = True
except ImportError:
    SCREENSHOT_OK = False

try:
    from core.clipboard_image import ClipboardImageCapture
    CLIPBOARD_OK = True
except ImportError:
    CLIPBOARD_OK = False


class MultimodalChatHandler:
    """
    テキスト+画像の複合入力を処理するハンドラ。
    画像解析結果をテキストコンテキストに変換して LLM に渡す。
    """

    def __init__(
        self,
        base_dir: Path | str,
        image_analyzer: ImageAnalyzer,
        llm_engine: Any | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.image_analyzer = image_analyzer
        self.llm = llm_engine
        self._lock = threading.Lock()
        self._clipboard = ClipboardImageCapture() if CLIPBOARD_OK else None

    # ─── パブリック API ─────────────────────────────────────

    def process_image_query(
        self,
        image_path: Path | str,
        user_question: str = "",
    ) -> str:
        """
        画像を解析し、質問があればそれに応じた回答を生成する。
        LLM がなければ解析結果の要約を返す。
        """
        with self._lock:
            return self._process_image_query_impl(image_path, user_question)

    def describe_screenshot(self) -> str:
        """スクリーンショットを撮影・解析し、説明を返す。"""
        if not SCREENSHOT_OK:
            return "スクリーンショット機能が利用できないよ。"

        image_path = capture_screen()
        if image_path is None:
            return "スクリーンショットの撮影に失敗しちゃった…。"

        try:
            analysis = self.image_analyzer.analyze(image_path)
            context = self.build_image_context(analysis)
            response = self._generate_response(
                context,
                "この画面の内容を簡潔に説明してください。",
            )
            return response
        finally:
            self._safe_unlink(image_path)

    def describe_clipboard_image(self) -> str:
        """クリップボードの画像を解析し、説明を返す。"""
        if self._clipboard is None:
            return "クリップボード画像の取得機能が使えないよ。"

        if not self._clipboard.has_image():
            return "クリップボードに画像がないみたい。画像をコピーしてからもう一度試してね！"

        temp_path = self._clipboard.save_to_temp()
        if temp_path is None:
            return "クリップボードの画像を取得できなかったよ…。"

        try:
            analysis = self.image_analyzer.analyze(temp_path)
            context = self.build_image_context(analysis)
            response = self._generate_response(
                context,
                "この画像の内容を説明してください。",
            )
            return response
        finally:
            self._safe_unlink(temp_path)

    def build_image_context(self, analysis: dict) -> str:
        """解析結果を LLM に渡すためのコンテキスト文字列に変換する。"""
        parts: list[str] = ["【画像解析結果】"]

        dims = analysis.get("dimensions")
        if dims:
            parts.append(f"サイズ: {dims[0]}×{dims[1]}px")

        brightness = analysis.get("brightness", 0.5)
        parts.append(f"明るさ: {brightness:.2f}（0=暗い, 1=明るい）")

        colors = analysis.get("dominant_colors", [])
        if colors:
            parts.append(f"主な色: {', '.join(colors[:5])}")

        if analysis.get("has_text"):
            text = analysis.get("text_content", "")
            # LLM のトークン節約のため 500 文字まで
            preview = text[:500].replace("\n", " ")
            parts.append(f"画面テキスト: {preview}")

        desc = analysis.get("description", "")
        if desc:
            parts.append(f"概要: {desc}")

        file_size = analysis.get("file_size", 0)
        if file_size > 0:
            parts.append(f"ファイルサイズ: {file_size / 1024:.0f}KB")

        return "\n".join(parts)

    # ─── 内部メソッド ───────────────────────────────────────

    def _process_image_query_impl(
        self,
        image_path: Path | str,
        user_question: str,
    ) -> str:
        """process_image_query の実装（ロック内で呼ばれる）。"""
        analysis = self.image_analyzer.analyze(image_path)
        context = self.build_image_context(analysis)

        if user_question:
            prompt = f"{user_question}\n\n{context}"
        else:
            prompt = f"この画像について説明してください。\n\n{context}"

        return self._generate_response(context, prompt)

    def _generate_response(self, context: str, prompt: str) -> str:
        """LLM があれば使い、なければ解析結果をそのまま返す。"""
        if self.llm is not None:
            try:
                # LLMEngine.generate が受け付ける形式でコンテキスト付きプロンプトを渡す
                system_msg = (
                    "あなたはアイです。画像解析結果をもとに、"
                    "親しみやすい口調で画像の内容を説明してください。"
                )
                full_prompt = f"{system_msg}\n\n{context}\n\nユーザー: {prompt}"
                response: str = self.llm.generate(full_prompt)
                if response and response.strip():
                    return response.strip()
            except Exception:
                pass

        # LLM が使えない場合は解析結果そのものを返す
        return f"画像を見てみたよ！\n\n{context}"

    @staticmethod
    def _safe_unlink(path: Path | str) -> None:
        """一時ファイルを安全に削除する。"""
        try:
            os.unlink(str(path))
        except Exception:
            pass

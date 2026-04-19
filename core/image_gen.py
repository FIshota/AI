"""
画像生成モジュール（Pollinations.ai）

完全無料・APIキー不要の Pollinations.ai で画像生成し、
成功プロンプトを学習して品質を向上させる。
"""
from __future__ import annotations

import json
import logging
import random
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_BASE_URL = "https://image.pollinations.ai/prompt/{prompt}"
_DEFAULT_WIDTH = 1024
_DEFAULT_HEIGHT = 1024


@dataclass
class ImageResult:
    success: bool
    file_path: str
    prompt_en: str
    prompt_ja: str
    url: str
    message: str


class ImageGenerator:
    """Pollinations.ai を使って画像を生成するクラス。"""

    BASE_URL = _BASE_URL

    def __init__(self, base_dir: Path, llm_fn: Callable[[str], str]) -> None:
        self._base_dir = Path(base_dir)
        self._llm_fn = llm_fn
        self._output_dir = self._base_dir / "data" / "generated_images"
        self._patterns_path = self._base_dir / "data" / "image_patterns.json"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def generate(self, user_request: str, style: str = "") -> ImageResult:
        """日本語リクエストから画像を生成する。

        1. LLM で英語プロンプトに変換
        2. 過去の成功パターンを参照して改善
        3. Pollinations.ai から画像を取得して保存
        4. 成功プロンプトをパターン学習
        """
        # 英語プロンプト生成
        prompt_en = self._build_prompt(user_request, style)

        # URL 構築
        seed = random.randint(1, 999999)
        encoded = urllib.parse.quote(prompt_en)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={_DEFAULT_WIDTH}&height={_DEFAULT_HEIGHT}"
            f"&nologo=true&seed={seed}"
        )

        # 画像取得
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self._output_dir / f"{timestamp}.png"

        try:
            self._download_image(url, file_path)
        except Exception as exc:
            logger.warning("[ImageGen] 画像取得失敗: %s", exc)
            return ImageResult(
                success=False,
                file_path="",
                prompt_en=prompt_en,
                prompt_ja=user_request,
                url=url,
                message=f"画像の生成に失敗しました: {exc}",
            )

        # 成功パターン保存
        self._save_pattern(ja_request=user_request, en_prompt=prompt_en, score=1.0)

        message = (
            f"画像を生成したよ！\n"
            f"保存先: {file_path}\n"
            f"使用プロンプト: {prompt_en}"
        )
        return ImageResult(
            success=True,
            file_path=str(file_path),
            prompt_en=prompt_en,
            prompt_ja=user_request,
            url=url,
            message=message,
        )

    # ──────────────────────────────────────────────────────────────
    # 内部実装
    # ──────────────────────────────────────────────────────────────

    def _build_prompt(self, user_request: str, style: str) -> str:
        """LLM で日本語リクエストを英語プロンプトに変換する。

        過去の成功パターンを参考にして品質向上を試みる。
        """
        patterns = self._load_patterns()
        pattern_hint = ""
        if patterns:
            recent = patterns[-5:]
            examples = "\n".join(
                f"- ja: {p['ja']} → en: {p['en']}" for p in recent
            )
            pattern_hint = f"\n\n参考にした過去の成功例:\n{examples}"

        style_hint = f"\nスタイル: {style}" if style else ""

        prompt = (
            f"以下の日本語の画像生成リクエストを、Stable Diffusion 向けの英語プロンプトに変換してください。\n"
            f"高品質で詳細な英語プロンプト（カンマ区切り）を1行で返してください。説明は不要です。\n\n"
            f"リクエスト: {user_request}{style_hint}{pattern_hint}\n\n"
            f"英語プロンプト:"
        )
        try:
            result = self._llm_fn(prompt).strip()
            # 余分な説明文が含まれている場合は最初の行だけ使う
            result = result.split("\n")[0].strip()
            if result:
                return result
        except Exception as exc:
            logger.warning("[ImageGen] LLM プロンプト変換失敗: %s", exc)

        # フォールバック: シンプルな英訳
        return f"{user_request}, high quality, detailed, 4k"

    def _download_image(self, url: str, dest: Path) -> None:
        """URL から画像をダウンロードして dest に保存する。"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        }
        from utils.url_guard import assert_safe_http_url
        url = assert_safe_http_url(url)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)

    # ── パターン学習 ──────────────────────────────────────────────

    def _load_patterns(self) -> list[dict]:
        if not self._patterns_path.exists():
            return []
        try:
            with open(self._patterns_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("[ImageGen] パターン読み込み失敗: %s", exc)
            return []

    def _save_pattern(self, ja_request: str, en_prompt: str, score: float) -> None:
        """成功した ja→en マッピングを JSON に保存する。"""
        patterns = self._load_patterns()
        patterns.append(
            {
                "ja": ja_request,
                "en": en_prompt,
                "score": score,
                "timestamp": datetime.now().isoformat(),
            }
        )
        # 最大 500 件保持
        patterns = patterns[-500:]
        try:
            with open(self._patterns_path, "w", encoding="utf-8") as f:
                json.dump(patterns, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("[ImageGen] パターン保存失敗: %s", exc)

    # ── Akashic Core 統合 ─────────────────────────────────────────

    def enrich_prompt_with_akashic(self, prompt: str, llm_fn=None) -> str:
        """
        アカシックエントロピーでプロンプトを豊かにする。
        プリゴジン散逸: 既存のプロンプト構造を解体→再結晶化して創造的飛躍を生む。
        """
        if not prompt:
            return prompt
        try:
            from core.akashic.entropy_engine import EntropyEngine
            eng = EntropyEngine()
            # まず創造性ゾーンに最適化
            enriched = eng.optimize_for_creativity(prompt, llm_fn=llm_fn)
            return enriched if enriched and enriched != prompt else prompt
        except Exception:
            return prompt

    def get_domain_style_hints(self, prompt: str) -> dict:
        """
        プロンプトが共鳴するドメインに基づいてスタイルヒントを返す。
        UnifiedField の多ドメイン解析をビジュアルスタイルに変換。
        """
        style_map = {
            "physics": "細かい物理的ディテール、光の屈折、量子的曖昧さ",
            "biology": "有機的な曲線、生命感、自然のテクスチャ",
            "mathematics": "幾何学的精密さ、対称性、フラクタル構造",
            "consciousness": "夢幻的、内省的、深い奥行き",
            "cosmology": "宇宙的スケール、星雲、空間の広がり",
            "information": "デジタル的、データの流れ、抽象的パターン",
            "philosophy": "象徴的、メタファー的、思索的雰囲気",
            "art": "感情的表現、色彩の豊かさ、芸術的自由",
        }
        result: dict[str, str] = {}
        try:
            from core.akashic.unified_field import UnifiedField
            sig = UnifiedField().resonate(prompt)
            for domain, hint in style_map.items():
                score = sig.resonances.get(domain, 0.0)
                if score > 0.25:
                    result[domain] = hint
        except Exception:
            pass
        return result

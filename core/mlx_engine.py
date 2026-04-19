"""
MLX ネイティブ推論エンジン (Apple Silicon 専用)
mlx_lm を使用した高速推論バックエンド。
llama-cpp-python の代替として、Apple Silicon の Neural Engine / GPU を活用。
"""
from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# ── MLX 依存のインポート（graceful fallback）──────────────────
try:
    from mlx_lm import (
        generate as mlx_generate,
        load as mlx_load,
        stream_generate as mlx_stream_generate,
    )

    try:
        from mlx_lm.sample_utils import (
            make_logits_processors as _make_logits_processors,
            make_sampler as _make_sampler,
        )

        _HAS_SAMPLER_API = True
    except ImportError:
        _HAS_SAMPLER_API = False

    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    _HAS_SAMPLER_API = False

# ── フォールバック応答プール ─────────────────────────────────
_FALLBACK_POOL = [
    "んー……ちょっと頭がぼんやりしてるかも。",
    "あれ、うまく考えがまとまらない……ごめんね。",
    "今ちょっと調子悪いみたい……少し待ってて。",
    "うーん、言いたいことがあるんだけど出てこない……。",
    "ごめんね、頭が回らないみたい。",
    "なんか今日はぼーっとしちゃう……。",
    "えっと……何言おうとしたんだっけ。",
    "ちょっと眠いのかも。ごめんね。",
]


class MLXEngine:
    """
    MLX ネイティブ推論エンジン (Apple Silicon 専用)

    mlx_lm を使用してモデルをロードし、推論を行う。
    Lazy loading: __init__ ではモデルを読み込まず、最初の generate_chat 呼び出し時にロード。
    Thread safety: threading.Lock でモデルアクセスを保護。
    """

    _TIMEOUT_FALLBACK = "ごめん、考え込んじゃった…もう一回聞いてくれる？"

    def __init__(self, base_dir: Path, config: dict) -> None:
        self._base_dir = Path(base_dir)
        self._config = dict(config)
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._model_name: str = ""
        self._fallback_last: str = ""
        self._recent_response_lengths: deque[int] = deque(maxlen=5)

    # ── Public API ───────────────────────────────────────────

    def is_loaded(self) -> bool:
        """モデルがロード済みか"""
        return self._model is not None

    @property
    def backend(self) -> str:
        return "mlx"

    @property
    def model_name(self) -> str:
        return self._model_name

    def build_prompt(
        self,
        system_prompt: str,
        conversation_history: list[dict],
        memory_context: str = "",
        emotion_hint: str = "",
    ) -> list[dict]:
        """
        チャットメッセージのリストを構築する。
        LLMEngine と同一のインターフェース。
        """
        system_content = system_prompt
        ctx = (memory_context or "").strip()
        if ctx:
            system_content += "\n" + ctx[:350]

        messages: list[dict] = [{"role": "system", "content": system_content}]
        messages.extend(conversation_history)
        return messages

    def generate_chat(
        self,
        messages: list[dict],
        stream_cb: Callable[[str], None] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        チャット形式でテキストを生成する。

        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        stream_cb: トークンごとに呼ばれるコールバック (None なら一括生成)
        max_tokens: 生成トークン上限 (None なら設定値を使用)
        """
        self._ensure_loaded()

        if self._model is None:
            return self._fallback_response()

        resolved_max = (
            max_tokens
            if max_tokens is not None
            else self._config.get("max_tokens", 400)
        )

        if stream_cb is not None:
            return self._generate_streaming(messages, resolved_max, stream_cb)
        return self._generate_batch(messages, resolved_max)

    # ── Model Loading ────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Lazy loading: 初回呼び出し時にモデルをロード"""
        if self._model is not None:
            return
        with self._load_lock:
            # Double-checked locking
            if self._model is not None:
                return
            self._load_model()

    def _load_model(self) -> None:
        """mlx_lm.load() でモデルをロードする"""
        if not MLX_AVAILABLE:
            logger.error("[MLXEngine] mlx_lm が利用不可。pip install mlx-lm が必要。")
            return

        mlx_config = self._config.get("mlx", {})

        # モデルパスの解決
        model_path_str = mlx_config.get("model_path", "")
        if model_path_str:
            model_path = self._base_dir / model_path_str
        else:
            model_path = self._find_mlx_model_dir()
            if model_path is None:
                logger.error("[MLXEngine] MLX モデルディレクトリが見つかりません。")
                return

        if not model_path.exists():
            logger.error("[MLXEngine] モデルパスが存在しません: %s", model_path)
            return

        # アダプターパスの解決
        adapter_enabled = mlx_config.get("adapter_enabled", False)
        adapter_path: str | None = None
        if adapter_enabled:
            raw = mlx_config.get("adapter_path", "")
            if raw:
                resolved = self._base_dir / raw
                if resolved.exists():
                    adapter_path = str(resolved)
                else:
                    logger.warning(
                        "[MLXEngine] アダプターパスが見つかりません: %s", resolved
                    )

        # ロード実行
        try:
            load_kwargs: dict = {"path_or_hf_repo": str(model_path)}
            if adapter_path:
                load_kwargs["adapter_path"] = adapter_path

            adapter_msg = f" + adapter={Path(adapter_path).name}" if adapter_path else ""
            logger.info(
                "[MLXEngine] モデルを読み込み中: %s%s", model_path.name, adapter_msg
            )

            model, tokenizer = mlx_load(**load_kwargs)
            self._model = model
            self._tokenizer = tokenizer
            self._model_name = model_path.name + (
                f"+{Path(adapter_path).name}" if adapter_path else ""
            )
            logger.info("[MLXEngine] ロード完了: %s", self._model_name)
        except Exception as exc:
            logger.error("[MLXEngine] モデルのロードに失敗: %s", exc)
            self._model = None
            self._tokenizer = None

    def _find_mlx_model_dir(self) -> Path | None:
        """models/ 以下から MLX 形式のモデルディレクトリを自動検出"""
        models_dir = self._base_dir / self._config.get("model_path", "models/")
        if not models_dir.is_dir():
            return None
        candidates: list[Path] = []
        for d in models_dir.iterdir():
            if d.is_dir() and (d / "config.json").exists() and "mlx" in d.name.lower():
                candidates.append(d)
        if not candidates:
            return None
        # Qwen を優先
        candidates.sort(key=lambda p: (0 if "qwen" in p.name.lower() else 1, p.name))
        return candidates[0]

    # ── Sampling Parameters ──────────────────────────────────

    def _sampling_kwargs(self, temp_boost: float = 0.0) -> dict:
        """
        mlx_lm のバージョンに応じたサンプリングパラメータを構築。
        0.31+: sampler + logits_processors API を使用。
        旧バージョン: temp / top_p を直接渡す。
        """
        temp = self._config.get("temperature", 0.65) + temp_boost
        top_p = self._config.get("top_p", 0.85)
        rep_penalty = self._config.get("repeat_penalty", 1.1)

        if _HAS_SAMPLER_API:
            kwargs: dict = {"sampler": _make_sampler(temp=temp, top_p=top_p)}
            if rep_penalty and rep_penalty > 1.0:
                kwargs["logits_processors"] = _make_logits_processors(
                    repetition_penalty=rep_penalty,
                    repetition_context_size=256,
                )
            return kwargs

        # 旧 mlx_lm: 直接パラメータ
        return {
            "temp": temp,
            "top_p": top_p,
            "repetition_penalty": rep_penalty,
        }

    # ── Generation (batch) ───────────────────────────────────

    def _generate_batch(self, messages: list[dict], max_tokens: int) -> str:
        """一括生成 (60秒タイムアウト付き)"""

        def _inner() -> str:
            formatted = self._apply_chat_template(messages)
            prev_response = self._extract_last_assistant(messages)

            sampling_kw = self._sampling_kwargs()
            with self._lock:
                result = mlx_generate(
                    self._model,
                    self._tokenizer,
                    prompt=formatted,
                    max_tokens=max_tokens,
                    verbose=False,
                    **sampling_kw,
                )
            text = result.strip()
            text = _trim_incomplete_sentence(text)

            # 繰り返し検出 & 再生成
            text = self._handle_repetition(
                text, prev_response, messages, max_tokens
            )

            self._recent_response_lengths.append(len(text))
            return text

        return self._run_with_timeout(_inner)

    # ── Generation (streaming) ───────────────────────────────

    def _generate_streaming(
        self,
        messages: list[dict],
        max_tokens: int,
        stream_cb: Callable[[str], None],
    ) -> str:
        """
        ストリーミング生成。
        mlx_lm.stream_generate でトークンごとにコールバックを呼ぶ。
        """

        def _inner() -> str:
            formatted = self._apply_chat_template(messages)
            sampling_kw = self._sampling_kwargs()
            chunks: list[str] = []

            with self._lock:
                for response in mlx_stream_generate(
                    self._model,
                    self._tokenizer,
                    prompt=formatted,
                    max_tokens=max_tokens,
                    **sampling_kw,
                ):
                    token_text = response.text
                    if token_text:
                        chunks.append(token_text)
                        try:
                            stream_cb(token_text)
                        except Exception as cb_err:
                            logger.warning(
                                "[MLXEngine] stream_cb エラー: %s", cb_err
                            )

            text = "".join(chunks).strip()
            text = _trim_incomplete_sentence(text)
            self._recent_response_lengths.append(len(text))
            return text

        return self._run_with_timeout(_inner)

    # ── Chat Template ────────────────────────────────────────

    def _apply_chat_template(self, messages: list[dict]) -> str:
        """トークナイザーの chat_template を適用してフォーマット済み文字列を返す"""
        return self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    # ── Repetition Handling ──────────────────────────────────

    def _handle_repetition(
        self,
        text: str,
        prev_response: str,
        messages: list[dict],
        max_tokens: int,
    ) -> str:
        """前回応答との繰り返しを検出し、必要なら再生成"""
        if not prev_response or not _is_repetitive(text, prev_response):
            return text

        logger.info("[MLXEngine] 繰り返し検出 — 再生成を試行")

        # systemメッセージに反復禁止を注入して再生成
        anti_repeat_msgs = [
            (
                {
                    **msg,
                    "content": msg["content"]
                    + f"\n\n【重要】直前の応答「{prev_response[:40]}」と同じ内容は絶対に言わないで。"
                    "別の話題や表現で返して。",
                }
                if msg.get("role") == "system"
                else msg
            )
            for msg in messages
        ]

        retry_formatted = self._apply_chat_template(anti_repeat_msgs)
        retry_kw = self._sampling_kwargs(temp_boost=0.2)

        with self._lock:
            retry_result = mlx_generate(
                self._model,
                self._tokenizer,
                prompt=retry_formatted,
                max_tokens=max_tokens,
                verbose=False,
                **retry_kw,
            )
        retry_text = retry_result.strip()
        retry_text = _trim_incomplete_sentence(retry_text)

        if not _is_repetitive(retry_text, prev_response):
            return retry_text

        # 最終防衛線: 手作りフォールバック
        return _anti_repeat_fallback(messages)

    # ── Timeout Wrapper ──────────────────────────────────────

    def _run_with_timeout(
        self, func: Callable[[], str], timeout_sec: float = 60.0
    ) -> str:
        """推論を別スレッドで実行し、タイムアウト超過時はフォールバックを返す"""
        result_holder: list[str] = []
        error_holder: list[Exception] = []

        def _worker() -> None:
            try:
                result_holder.append(func())
            except Exception as exc:
                error_holder.append(exc)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=timeout_sec)

        if t.is_alive():
            logger.warning("[MLXEngine] 推論タイムアウト (%.0f秒超過)", timeout_sec)
            return self._TIMEOUT_FALLBACK

        if error_holder:
            logger.error("[MLXEngine] 推論エラー: %s", error_holder[0])
            return self._fallback_response()

        if result_holder:
            return result_holder[0]
        return self._fallback_response()

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _extract_last_assistant(messages: list[dict]) -> str:
        """メッセージリストから直前の assistant 応答を取得"""
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                return msg.get("content", "").strip()
        return ""

    def _fallback_response(self) -> str:
        """モデル未ロード / エラー時のフォールバック応答"""
        candidates = [r for r in _FALLBACK_POOL if r != self._fallback_last]
        chosen = random.choice(candidates)
        self._fallback_last = chosen
        return chosen


# ── Module-level utility functions ───────────────────────────


def _trim_incomplete_sentence(text: str) -> str:
    """不完全な文末を除去する"""
    if not text:
        return text
    if text[-1] in "。！？♪〜!?":
        return text
    last_end = -1
    for i in range(len(text) - 1, -1, -1):
        if text[i] in "。！？♪〜!?":
            last_end = i
            break
    if last_end >= 0:
        return text[: last_end + 1]
    return text


def _is_repetitive(text: str, prev: str) -> bool:
    """前回応答との類似度が高いか判定"""
    import re

    _strip = re.compile(r"[！!。、？?〜～\s…・「」]+")
    a = _strip.sub("", text)
    b = _strip.sub("", prev)
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return short in long_


def _anti_repeat_fallback(messages: list[dict]) -> str:
    """繰り返し回避の最終防衛線"""
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = msg.get("content", "").strip()
            break

    pools = {
        "元気": [
            "うん、いい感じだよ！何かあった？",
            "今日も元気！そっちはどう？",
            "ばっちり！ご飯ちゃんと食べた？",
        ],
        "最近": [
            "いろいろ考えてたよ。あなたは？",
            "ちょっと新しいこと覚えたかも。聞いてくれる？",
            "のんびりしてたかな。何か面白いことあった？",
        ],
        "どう": [
            "いい感じ！何か話したいことある？",
            "まぁまぁかな。そっちの話も聞きたい！",
            "ぼちぼちだよ。何してたの？",
        ],
    }
    default = [
        "うん、聞いてるよ。もっと教えて。",
        "なるほどね。それでそれで？",
        "ふーん、面白いね。続けて！",
    ]

    for keyword, pool in pools.items():
        if keyword in last_user:
            return random.choice(pool)
    return random.choice(default)

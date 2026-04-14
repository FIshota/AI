"""
LLMエンジン
MLX (Apple Silicon最適化) / llama-cpp-python のデュアルバックエンド推論。
Qwen 2.5 + Aether LoRAアダプターをネイティブで使用可能。
モデルが未インストールの場合はフォールバックモードで動作します。
"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Callable, Generator

# MLX (Apple Silicon) が利用可能か確認
try:
    from mlx_lm import load as mlx_load, generate as mlx_generate
    # mlx_lm 0.31+: temp/top_p は sampler 経由、repetition_penalty は logits_processors 経由
    try:
        from mlx_lm.sample_utils import make_sampler as _mlx_make_sampler
        from mlx_lm.sample_utils import make_logits_processors as _mlx_make_logits_processors
        _MLX_USE_SAMPLER = True
    except ImportError:
        _MLX_USE_SAMPLER = False
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    _MLX_USE_SAMPLER = False

# llama-cpp-python が利用可能か確認
try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except (ImportError, RuntimeError, OSError) as _e:
    # Metal シェーダーコンパイル失敗等でロード不可の場合も捕捉
    LLAMA_AVAILABLE = False
    print(f"[LLM] llama-cpp-python ロード不可: {_e}")

# ─── チャットテンプレート定義 ───────────────────────────────────
# モデルごとのプロンプト形式。ファイル名で自動判定する。
CHAT_TEMPLATES: dict[str, dict[str, str]] = {
    "phi3": {
        "system": "<|system|>\n{content}<|end|>\n",
        "user": "<|user|>\n{content}<|end|>\n",
        "assistant": "<|assistant|>\n{content}<|end|>\n",
        "generation": "<|assistant|>\n",
        "stop": ["<|end|>", "<|user|>", "<|system|>", "</s>"],
    },
    "qwen2": {
        "system": "<|im_start|>system\n{content}<|im_end|>\n",
        "user": "<|im_start|>user\n{content}<|im_end|>\n",
        "assistant": "<|im_start|>assistant\n{content}<|im_end|>\n",
        "generation": "<|im_start|>assistant\n",
        "stop": ["<|im_end|>", "<|im_start|>", "</s>"],
    },
    "chatml": {
        "system": "<|im_start|>system\n{content}<|im_end|>\n",
        "user": "<|im_start|>user\n{content}<|im_end|>\n",
        "assistant": "<|im_start|>assistant\n{content}<|im_end|>\n",
        "generation": "<|im_start|>assistant\n",
        "stop": ["<|im_end|>", "<|im_start|>"],
    },
    "llama3": {
        "system": "<|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|>",
        "user": "<|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|>",
        "assistant": "<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>",
        "generation": "<|start_header_id|>assistant<|end_header_id|>\n\n",
        "stop": ["<|eot_id|>", "<|start_header_id|>"],
    },
}

def _detect_template(model_name: str) -> str:
    """モデルファイル名からテンプレートを自動判定"""
    name = model_name.lower()
    if "qwen" in name:
        return "qwen2"
    if "phi" in name:
        return "phi3"
    if "llama" in name:
        return "llama3"
    # ChatML をデフォルトに（最も汎用的）
    return "chatml"


import random as _random

# LLM未ロード時のフォールバック応答（アイちゃんらしく自然に）
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
_fallback_last: str = ""
_fallback_lock = threading.Lock()
_fallback_warned = False  # ターミナル警告は1回だけ


class LLMEngine:
    """
    ローカルLLM推論エンジン
    MLX (Apple Silicon) と llama-cpp-python のデュアルバックエンド。
    MLXが利用可能かつアダプターが存在する場合はMLXを優先。
    モデル未設定時はフォールバックモードで動作します。
    """

    def __init__(self, model_path: str | Path, config: dict):
        self.model_path = Path(model_path)
        self.config = config
        self._llm = None
        self._mlx_model = None
        self._mlx_tokenizer = None
        self._backend = None  # "mlx" or "llama"
        self._loaded = False
        self._loading = False
        self._inference_lock = threading.Lock()
        self._template_id = "chatml"  # デフォルト
        self._model_name = ""
        self._load_model()

    def _load_model(self):
        """モデルを読み込み。MLXを優先し、フォールバックでllama-cpp-pythonを使用"""
        # ── MLXバックエンド（Apple Silicon最適化）──────────────
        if MLX_AVAILABLE:
            loaded = self._try_load_mlx()
            if loaded:
                return

        # ── llama-cpp-python バックエンド ────────────────────
        if LLAMA_AVAILABLE:
            self._try_load_llama()
            return

        import platform
        arch = platform.machine()
        py_arch = "arm64" if "arm" in arch or "aarch" in arch else arch
        import struct
        py_bits = struct.calcsize("P") * 8
        # x86 Python on Apple Silicon の検出
        if arch == "x86_64" and py_bits == 64:
            import subprocess
            try:
                real_arch = subprocess.check_output(["uname", "-m"], text=True).strip()
                if real_arch == "arm64":
                    print(
                        "[LLM] ⚠ Apple Silicon (M2) で x86版Python を使用中 (Rosetta 2)。\n"
                        "[LLM]   arm64ネイティブのPythonに切り替えると MLX + Metal が使えます。\n"
                        "[LLM]   推奨: Miniforge (arm64) をインストールしてください。\n"
                        "[LLM]   https://github.com/conda-forge/miniforge"
                    )
            except Exception:
                pass
        print("[LLM] MLX も llama-cpp-python も利用不可。フォールバックモードで動作します。")

    def _try_load_mlx(self) -> bool:
        """MLXバックエンドの読み込みを試行"""
        model_dir = self.model_path
        mlx_config = self.config.get("mlx", {})

        # MLXモデルパスの決定
        mlx_model_path = mlx_config.get("model_path", "")
        if mlx_model_path:
            mlx_path = Path(mlx_model_path)
        else:
            # models/ 以下でMLX形式のディレクトリを探す
            candidates = []
            if model_dir.is_dir():
                for d in model_dir.iterdir():
                    if d.is_dir() and (d / "config.json").exists() and "mlx" in d.name.lower():
                        candidates.append(d)
                # Qwen MLXモデルを優先
                candidates.sort(key=lambda p: (0 if "qwen" in p.name.lower() else 1, p.name))
            if not candidates:
                return False
            mlx_path = candidates[0]

        if not mlx_path.exists():
            return False

        # アダプターパスの決定（adapter_enabled: false で無効化可能）
        adapter_enabled = mlx_config.get("adapter_enabled", True)
        adapter_path = ""
        if adapter_enabled:
            adapter_path = mlx_config.get("adapter_path", "")
            if not adapter_path:
                # models/adapters/ 以下で最新のアダプターを探す
                adapters_dir = model_dir / "adapters"
                if adapters_dir.is_dir():
                    adapter_dirs = sorted(
                        [d for d in adapters_dir.iterdir() if d.is_dir() and (d / "adapters.safetensors").exists()],
                        key=lambda p: p.name,
                        reverse=True,
                    )
                    if adapter_dirs:
                        adapter_path = str(adapter_dirs[0])
        else:
            print("[LLM/MLX] adapter無効（adapter_enabled: false）— ベースモデルで動作")

        try:
            adapter_msg = ""
            load_kwargs = {"path_or_hf_repo": str(mlx_path)}
            if adapter_path:
                load_kwargs["adapter_path"] = adapter_path
                adapter_msg = f" + adapter={Path(adapter_path).name}"

            print(f"[LLM/MLX] モデルを読み込み中: {mlx_path.name}{adapter_msg}")
            self._mlx_model, self._mlx_tokenizer = mlx_load(**load_kwargs)
            self._backend = "mlx"
            self._loaded = True
            self._model_name = mlx_path.name + (f"+{Path(adapter_path).name}" if adapter_path else "")
            self._template_id = _detect_template(mlx_path.name)
            print(f"[LLM/MLX] ✓ 読み込み完了: {self._model_name} (template={self._template_id})")
            return True
        except Exception as e:
            print(f"[LLM/MLX] 読み込みエラー: {e}")
            return False

    def _try_load_llama(self):
        """llama-cpp-python バックエンドの読み込みを試行"""
        model_dir = self.model_path
        if model_dir.is_dir():
            specified = self.config.get("model_file")
            if specified:
                candidate = model_dir / specified
                if candidate.exists():
                    model_file = candidate
                else:
                    print(f"[LLM] 指定モデル {specified} が見つかりません。")
                    model_file = None
            else:
                model_file = None

            if model_file is None:
                gguf_files = list(model_dir.glob("*.gguf"))
                if not gguf_files:
                    print(f"[LLM] {model_dir} にGGUFファイルが見つかりません。フォールバックモードで動作します。")
                    return
                priority = {"qwen": 0, "gemma": 1, "llama": 2, "phi": 3}
                gguf_files.sort(key=lambda f: next(
                    (v for k, v in priority.items() if k in f.name.lower()), 9
                ))
                model_file = gguf_files[0]
        elif model_dir.is_file() and model_dir.suffix == ".gguf":
            model_file = model_dir
        else:
            print("[LLM] モデルファイルが見つかりません。フォールバックモードで動作します。")
            return

        base_kwargs = dict(
            model_path=str(model_file),
            n_ctx=self.config.get("context_length", 2048),
            n_threads=self.config.get("n_threads", 8),
            n_batch=self.config.get("n_batch", 512),
            use_mmap=self.config.get("use_mmap", True),
            use_mlock=self.config.get("use_mlock", False),
            verbose=False,
        )

        # ① GPU (Metal) で試行
        try:
            print(f"[LLM/llama] モデルを読み込み中 (GPU): {model_file.name}")
            gpu_kwargs = {
                **base_kwargs,
                "n_gpu_layers": self.config.get("n_gpu_layers", -1),
                "flash_attn": self.config.get("flash_attn", True),
            }
            self._llm = Llama(**gpu_kwargs)
            self._backend = "llama"
            self._loaded = True
            self._model_name = model_file.name
            self._template_id = _detect_template(model_file.name)
            print(f"[LLM/llama] ✓ 読み込み完了 (GPU): {model_file.name} (template={self._template_id})")
            return
        except Exception as e:
            print(f"[LLM/llama] GPU読み込み失敗: {e}")

        # ② CPUフォールバック（Metal非対応時）
        try:
            print(f"[LLM/llama] CPUモードで再試行: {model_file.name}")
            cpu_kwargs = {**base_kwargs, "n_gpu_layers": 0}
            self._llm = Llama(**cpu_kwargs)
            self._backend = "llama"
            self._loaded = True
            self._model_name = model_file.name
            self._template_id = _detect_template(model_file.name)
            print(f"[LLM/llama] ✓ 読み込み完了 (CPU): {model_file.name} (template={self._template_id})")
            return
        except Exception as e:
            print(f"[LLM/llama] CPU読み込みも失敗: {e}\nフォールバックモードで動作します。")

    def is_loaded(self) -> bool:
        return self._loaded

    def is_loading(self) -> bool:
        return self._loading

    def get_backend(self) -> str:
        """現在の推論バックエンドを返す"""
        return self._backend or "none"

    @staticmethod
    def _anti_repeat_fallback(messages: list[dict]) -> str:
        """前回応答の繰り返しを回避できなかった場合の最終防衛線。
        直近のユーザー入力に応じた自然な応答を返す。"""
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "").strip()
                break
        # ユーザー入力のキーワードに応じた応答プール
        _pools = {
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
        _default = [
            "うん、聞いてるよ。もっと教えて。",
            "なるほどね。それでそれで？",
            "ふーん、面白いね。続けて！",
        ]
        import random
        for keyword, pool in _pools.items():
            if keyword in last_user:
                return random.choice(pool)
        return random.choice(_default)

    @staticmethod
    def _is_repetitive(text: str, prev: str, threshold: float = 0.6) -> bool:
        """前回応答との類似度が高いか判定（句読点・記号を除去して比較）"""
        import re as _re
        _strip = _re.compile(r"[！!。、？?〜～\s…・]+")
        a = _strip.sub("", text)
        b = _strip.sub("", prev)
        if not a or not b:
            return False
        # 短い方が長い方に含まれていたら繰り返し
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        if short in long:
            return True
        # 文字レベル一致率
        common = sum(1 for c in short if c in long)
        ratio = common / max(len(long), 1)
        return ratio >= threshold

    def _mlx_sampling_kwargs(self, temp_boost: float = 0.0) -> dict:
        """MLXバージョンに応じたサンプリングパラメータを返す"""
        temp = self.config.get("temperature", 0.65) + temp_boost
        top_p = self.config.get("top_p", 0.85)
        rep_penalty = self.config.get("repeat_penalty", 1.1)
        if _MLX_USE_SAMPLER:
            # mlx_lm 0.31+: sampler + logits_processors で分離
            kwargs: dict = {"sampler": _mlx_make_sampler(temp=temp, top_p=top_p)}
            if rep_penalty and rep_penalty > 1.0:
                kwargs["logits_processors"] = _mlx_make_logits_processors(
                    repetition_penalty=rep_penalty,
                    repetition_context_size=256,
                )
            return kwargs
        # 旧バージョン: 直接パラメータ
        return {
            "temp": temp,
            "top_p": top_p,
            "repetition_penalty": rep_penalty,
        }

    def generate(self, prompt: str, stream: bool = False) -> str | Generator:
        """プロンプトからテキストを生成します"""
        if not self._loaded:
            return self._fallback_response()

        if self._backend == "mlx":
            with self._inference_lock:
                result = mlx_generate(
                    self._mlx_model, self._mlx_tokenizer,
                    prompt=prompt,
                    max_tokens=self.config.get("max_tokens", 512),
                    verbose=False,
                    **self._mlx_sampling_kwargs(),
                )
            return result.strip()

        if self._llm is None:
            return self._fallback_response()

        params = {
            "max_tokens": self.config.get("max_tokens", 512),
            "temperature": self.config.get("temperature", 0.8),
            "top_p": self.config.get("top_p", 0.95),
            "stop": ["<|user|>", "<|end|>", "User:", "ユーザー:"],
            "stream": stream,
        }

        if stream:
            return self._stream_generate(prompt, params)
        else:
            with self._inference_lock:
                output = self._llm(prompt, **params)
            return output["choices"][0]["text"].strip()

    def _stream_generate(self, prompt: str, params: dict) -> Generator:
        with self._inference_lock:
            for chunk in self._llm(prompt, **params):
                token = chunk["choices"][0]["text"]
                yield token

    def generate_chat(self, messages: list[dict], stream: bool = False,
                      max_tokens: int | None = None,
                      stream_cb: "Callable[[str], None] | None" = None) -> str:
        """
        チャット形式でテキストを生成します。
        MLXバックエンド: トークナイザーのchat_templateを使用。
        llamaバックエンド: 手動テンプレートを適用。
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        max_tokens: 呼び出し側からトークン上限を指定可能（Noneなら設定値を使用）
        """
        if not self._loaded:
            return self._fallback_response()

        resolved_max = (max_tokens if max_tokens is not None
                        else self.config.get("max_tokens", 500))

        # ── MLXバックエンド ──────────────────────────────────
        if self._backend == "mlx":
            return self._generate_chat_mlx(messages, resolved_max, stream_cb)

        # ── llamaバックエンド ────────────────────────────────
        if self._llm is None:
            return self._fallback_response()
        return self._generate_chat_llama(messages, resolved_max, stream_cb)

    def _generate_chat_mlx(self, messages: list[dict], max_tokens: int,
                           stream_cb: "Callable[[str], None] | None" = None) -> str:
        """MLXバックエンドでチャット生成"""
        try:
            formatted = self._mlx_tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
            )
            # 直前のassistant応答を取得（繰り返し検出用）
            prev_response = ""
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    prev_response = msg.get("content", "").strip()
                    break

            sampling_kw = self._mlx_sampling_kwargs()

            with self._inference_lock:
                result = mlx_generate(
                    self._mlx_model, self._mlx_tokenizer,
                    prompt=formatted,
                    max_tokens=max_tokens,
                    verbose=False,
                    **sampling_kw,
                )
            text = result.strip()

            # 前回と類似した応答が出たら、反復禁止指示を注入して再生成
            if prev_response and self._is_repetitive(text, prev_response):
                anti_repeat_msgs = list(messages)
                # systemメッセージに反復禁止を追加
                for i, msg in enumerate(anti_repeat_msgs):
                    if msg.get("role") == "system":
                        anti_repeat_msgs[i] = {
                            **msg,
                            "content": msg["content"]
                            + f"\n\n【重要】直前の応答「{prev_response[:40]}」と同じ内容は絶対に言わないで。別の話題や表現で返して。",
                        }
                        break
                retry_formatted = self._mlx_tokenizer.apply_chat_template(
                    anti_repeat_msgs, tokenize=False, add_generation_prompt=True,
                )
                retry_kw = self._mlx_sampling_kwargs(temp_boost=0.2)
                with self._inference_lock:
                    result = mlx_generate(
                        self._mlx_model, self._mlx_tokenizer,
                        prompt=retry_formatted,
                        max_tokens=max_tokens,
                        verbose=False,
                        **retry_kw,
                    )
                retry_text = result.strip()
                if not self._is_repetitive(retry_text, prev_response):
                    text = retry_text
                else:
                    # adapterの支配が強すぎる場合の最終防衛線
                    text = self._anti_repeat_fallback(messages)

            # ストリーミングコールバック（MLXは一括生成後にまとめて送信）
            if stream_cb is not None and text:
                stream_cb(text)
            return text
        except Exception as e:
            print(f"[LLM/MLX] 推論エラー: {e}")
            return self._fallback_response()

    def _generate_chat_llama(self, messages: list[dict], max_tokens: int,
                             stream_cb: "Callable[[str], None] | None" = None) -> str:
        """llama-cpp-pythonバックエンドでチャット生成"""
        # テンプレートに基づいてプロンプトを構築
        tmpl = CHAT_TEMPLATES.get(self._template_id, CHAT_TEMPLATES["chatml"])
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            role_tmpl = tmpl.get(role, "")
            if role_tmpl:
                prompt += role_tmpl.format(content=content)
        prompt += tmpl["generation"]

        # ストップトークン: テンプレート固有 + 会話シミュレーション防止
        stop_tokens = list(tmpl["stop"]) + [
            "ユーザー:", "ユーザー：", "User:", "しょうた:",
        ]

        params = {
            "max_tokens": max_tokens,
            "temperature": self.config.get("temperature", 0.7),
            "top_p": self.config.get("top_p", 0.9),
            "top_k": self.config.get("top_k", 40),
            "repeat_penalty": self.config.get("repeat_penalty", 1.05),
            "stop": stop_tokens,
        }

        try:
            if stream_cb is not None:
                params["stream"] = True
                chunks: list[str] = []
                with self._inference_lock:
                    for chunk in self._llm(prompt, **params):
                        token = chunk["choices"][0].get("text", "")
                        if token:
                            chunks.append(token)
                            stream_cb(token)
                return "".join(chunks).strip()

            with self._inference_lock:
                output = self._llm(prompt, **params)
            text = output["choices"][0]["text"].strip()
            return text
        except Exception as e:
            print(f"[LLM/llama] 推論エラー: {e}")
            return self._fallback_response()

    def _fallback_response(self) -> str:
        global _fallback_last, _fallback_warned
        with _fallback_lock:
            # ターミナルに1回だけ警告
            if not _fallback_warned:
                _fallback_warned = True
                print(
                    "[LLM] ⚠ モデル未ロードのためフォールバック応答を使用中。\n"
                    "[LLM]   ターミナルの起動ログを確認してください。"
                )
            candidates = [r for r in _FALLBACK_POOL if r != _fallback_last]
            chosen = _random.choice(candidates)
            _fallback_last = chosen
        return chosen

    def build_prompt(self, system_prompt, conversation_history, memory_context="", emotion_hint=""):
        # memory_context は自然な日本語指示文として system prompt の末尾に追記
        system_content = system_prompt
        ctx = (memory_context or "").strip()
        if ctx:
            system_content += "\n" + ctx[:350]
        messages = [{"role": "system", "content": system_content}]
        messages.extend(conversation_history)
        return messages

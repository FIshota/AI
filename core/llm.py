"""
LLMエンジン
MLX (Apple Silicon最適化) / llama-cpp-python のデュアルバックエンド推論。
Qwen 2.5 + Aether LoRAアダプターをネイティブで使用可能。
モデルが未インストールの場合はフォールバックモードで動作します。
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import stat
import threading
import time as _time
from collections import deque
from pathlib import Path
from typing import Callable, Generator

logger = logging.getLogger(__name__)


# ─── CVE-2025-69872 mitigation (diskcache pickle RCE) ────────────────
# llama-cpp-python pulls in `diskcache` (5.6.3), which uses pickle for
# on-disk serialization by default. An attacker with write access to the
# cache directory can achieve arbitrary code execution when the cache is
# read. No upstream fix exists. We harden by:
#   1. Forcing cache dirs to a user-only path inside the project
#   2. Asserting 0700 perms and current-user ownership on every launch
#   3. Refusing to load if foreign pickle files are present
# References: CVE-2025-69872 / GHSA-w8v5-vhqr-4h9v
def _secure_cache_dir(path: Path) -> Path:
    """Create or validate a user-only cache dir (mode 0700, owner == current UID).

    Raises PermissionError if ownership mismatches or perms cannot be enforced.
    Removes stray pickle artifacts to neutralize any pre-existing attack.
    """
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except PermissionError as e:
        raise PermissionError(f"[llm-security] chmod 0700 failed on {path}: {e}") from e

    st = path.stat()
    # UID check (skipped on platforms without getuid, e.g. Windows)
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise PermissionError(
            f"[llm-security] cache dir owner mismatch (uid={st.st_uid}, expected={os.getuid()}): {path}. "
            "Refusing to load to prevent CVE-2025-69872 exploitation."
        )
    # Perm check — tolerate 0700 only
    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o077:
        raise PermissionError(
            f"[llm-security] cache dir {path} has permissive mode {oct(mode)}. "
            "Expected 0o700. Refusing to load."
        )

    # Scrub suspicious pickle files that may have been planted
    suspicious_suffixes = (".pkl", ".pickle")
    for p in path.rglob("*"):
        if p.is_file() and p.suffix.lower() in suspicious_suffixes:
            try:
                p.unlink()
                logger.warning("[llm-security] removed suspicious pickle file: %s", p)
            except OSError as e:
                logger.error("[llm-security] could not remove %s: %s", p, e)
                raise PermissionError(
                    f"[llm-security] cannot remove untrusted pickle file {p}"
                ) from e
    return path


def _harden_llm_cache(base_dir: Path) -> Path:
    """Set up a hardened cache dir and redirect library caches into it.

    Called once at LLMEngine init. Sets XDG_CACHE_HOME so that llama-cpp-python,
    huggingface, and transitive diskcache users all land in the user-only path.
    """
    cache_root = (base_dir / "data" / "llm_cache").resolve()
    secured = _secure_cache_dir(cache_root)
    # Only override if caller hasn't already set something explicit
    os.environ.setdefault("XDG_CACHE_HOME", str(secured))
    os.environ.setdefault("LLAMA_CACHE", str(secured / "llama"))
    (secured / "llama").mkdir(parents=True, exist_ok=True)
    os.chmod(secured / "llama", 0o700)
    logger.info("[llm-security] hardened cache dir active: %s", secured)
    return secured

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

# MLXEngine (standalone backend) — graceful fallback
try:
    from core.mlx_engine import MLXEngine as _MLXEngine, MLX_AVAILABLE as _MLX_ENGINE_OK
except ImportError:
    _MLXEngine = None  # type: ignore[assignment,misc]
    _MLX_ENGINE_OK = False

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
    if "sarashina" in name:
        # Sarashina2 は Llama 系トークナイザ + chatml 系
        return "chatml"
    if "elyza" in name and "llama-3" in name:
        return "llama3"
    if "swallow" in name:
        return "llama3"
    if "karakuri" in name:
        return "llama3"
    if "qwen" in name:
        return "qwen2"
    if "phi" in name:
        return "phi3"
    if "llama" in name:
        return "llama3"
    return "chatml"


# ─── Model Family Catalog (Phase 0 — 国産モデル移行) ────────────────
# 「国産オリジナル AI」として発表するには Qwen / Gemma / Phi から日本製へ移行する。
# ライセンスの clean さと日本語能力を両立するベースを提示する。
#
# 判定基準:
#   license_clean : 商用・再配布まで明確に許可されているか
#   jp_native     : 事前学習段階から日本語比率が高いか
#   recommended   : Phase 0 の既定候補
MODEL_FAMILIES: dict[str, dict] = {
    "sarashina2-7b": {
        "display_name": "Sarashina2-7B (SB Intuitions)",
        "hf_repo": "sbintuitions/sarashina2-7b",
        "gguf_hint": "sarashina2-7b",
        "template": "chatml",
        "license": "MIT",
        "license_clean": True,
        "jp_native": True,
        "recommended": True,   # ← 既定
        "note": "SB Intuitions 製、MIT ライセンス。日本語 corpus 比率が高くクリーンな選択肢。",
    },
    "elyza-llama3-8b": {
        "display_name": "ELYZA-japanese-Llama-3-8B-Instruct",
        "hf_repo": "elyza/Llama-3-ELYZA-JP-8B",
        "gguf_hint": "elyza",
        "template": "llama3",
        "license": "Meta Llama 3 Community License",
        "license_clean": False,  # Meta 独自ライセンス。商用可だが制約あり
        "jp_native": True,
        "recommended": False,
        "note": "ELYZA による Llama-3 日本語ファインチューン。日本語性能が高いが Meta ライセンス要確認。",
    },
    "swallow-8b": {
        "display_name": "Llama-3.1-Swallow-8B-Instruct",
        "hf_repo": "tokyotech-llm/Llama-3.1-Swallow-8B-Instruct-v0.3",
        "gguf_hint": "swallow",
        "template": "llama3",
        "license": "Meta Llama 3.1 Community License + Gemma terms",
        "license_clean": False,
        "jp_native": True,
        "recommended": False,
        "note": "東工大 Swallow プロジェクト。日本語継続事前学習量が国内最大級。ライセンス連鎖が重い。",
    },
    "karakuri-8b": {
        "display_name": "karakuri-lm-8x7b-instruct-v0.1",
        "hf_repo": "karakuri-ai/karakuri-lm-8x7b-instruct-v0.1",
        "gguf_hint": "karakuri",
        "template": "llama3",
        "license": "Apache 2.0",
        "license_clean": True,
        "jp_native": True,
        "recommended": False,
        "note": "Karakuri (株式会社カラクリ) 製、Apache 2.0。MoE で GPU 要件がやや高い。",
    },
    # レガシー互換（非推奨・後方互換のためだけに残す）
    "qwen2-legacy": {
        "display_name": "Qwen2.5 (legacy)",
        "hf_repo": "",
        "gguf_hint": "qwen",
        "template": "qwen2",
        "license": "Qwen License (非国産)",
        "license_clean": False,
        "jp_native": False,
        "recommended": False,
        "note": "国産 AI としては非推奨。Phase 0 移行前の互換動作用。",
    },
}


def get_model_family(name: str) -> dict | None:
    """family 名から定義を返す（未知なら None）。"""
    return MODEL_FAMILIES.get(name)


def default_model_family() -> str:
    """recommended=True な family を返す。複数あれば最初を返す。"""
    for fam, info in MODEL_FAMILIES.items():
        if info.get("recommended"):
            return fam
    return "sarashina2-7b"


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

    # 推論タイムアウト超過時のフォールバック
    _TIMEOUT_FALLBACK = "ごめん、考え込んじゃった…もう一回聞いてくれる？"

    # CoT 対象インテント
    _COT_INTENTS = frozenset({"consultation", "complex", "advice", "analysis", "相談", "分析"})

    def __init__(self, model_path: str | Path, config: dict):
        self.model_path = Path(model_path)
        self.config = config
        self._llm = None
        self._mlx_model = None
        self._mlx_tokenizer = None
        self._mlx_engine: _MLXEngine | None = None  # standalone MLX backend
        self._backend = None  # "mlx" or "llama"
        self._loaded = False
        self._loading = False
        self._inference_lock = threading.Lock()
        self._template_id = "chatml"  # デフォルト
        self._model_name = ""

        # Item #2: KV cache — prompt hash で同一プロンプト再構築を回避
        self._last_prompt_hash: str = ""
        self._cached_prompt: str = ""

        # Item #P2: Response cache — 繰返しプロンプトの即時応答 (LRU, 128 entries)
        self._response_cache: "collections.OrderedDict[str, str]" = (
            __import__("collections").OrderedDict()
        )
        self._response_cache_max = int(self.config.get("response_cache_size", 128))
        self._response_cache_hits = 0
        self._response_cache_misses = 0

        # Item #P2: Auto-tune n_threads / n_batch (未指定時のみ)
        try:
            import os as _os
            cpu = _os.cpu_count() or 4
            # 物理コア推定: 大抵 cpu_count() は論理 → 半分を既定の n_threads に
            if "n_threads" not in self.config:
                self.config["n_threads"] = max(4, cpu // 2)
            if "n_batch" not in self.config:
                # M1/M2 等のユニファイドメモリ環境では 512、通常は 256
                self.config["n_batch"] = 512 if cpu >= 8 else 256
        except Exception:
            pass

        # Item #87: Dynamic repeat_penalty — 直近5応答の長さを追跡
        self._recent_response_lengths: deque[int] = deque(maxlen=5)

        # Item #89: Context window usage tracking
        self._context_stats: list[dict] = []

        # CVE-2025-69872: harden diskcache / llama-cpp cache dir before load
        try:
            # Project root: two levels up from core/llm.py
            project_root = Path(__file__).resolve().parent.parent
            _harden_llm_cache(project_root)
        except PermissionError as e:
            # Hard fail — refusing to load prevents pickle-RCE exploitation
            logger.error("[llm-security] refusing to load due to cache hardening failure: %s", e)
            raise
        except Exception as e:
            # Non-fatal fallback: log but continue (e.g. read-only FS)
            logger.warning("[llm-security] cache hardening skipped: %s", e)

        self._load_model()

    def _load_model(self):
        """モデルを読み込み。MLXEngine > インラインMLX > llama-cpp-python の順で試行"""
        # ── Phase 0: model_family provenance (国産AIとしてのライセンス透明性) ──
        fam_name = self.config.get("model_family") or default_model_family()
        fam = get_model_family(fam_name)
        if fam:
            clean = "clean" if fam.get("license_clean") else "non-clean"
            print(
                f"[LLM/P0] Model family: {fam_name} ({fam.get('license','?')}, {clean}) "
                f"— {fam.get('display_name','')}"
            )
            self._model_family = fam_name
            self._model_family_info = fam
        else:
            print(f"[LLM/P0] ⚠ 未知の model_family: {fam_name} — 自動検出にフォールバック")
            self._model_family = None
            self._model_family_info = None

        # ── MLXEngine (standalone backend) ────────────────────
        if _MLXEngine is not None and _MLX_ENGINE_OK:
            loaded = self._try_load_mlx_engine()
            if loaded:
                return

        # ── インラインMLXバックエンド（Apple Silicon最適化）────
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

    def _resolve_template(self, model_name: str) -> str:
        """Phase 0: model_family で template が明示されていれば優先、無ければ名前から自動検出。"""
        fam_info = getattr(self, "_model_family_info", None)
        if fam_info:
            tmpl = fam_info.get("template")
            if tmpl:
                print(f"[LLM/P0] template override from family: {tmpl}")
                return tmpl
        return _detect_template(model_name)

    def _try_load_mlx_engine(self) -> bool:
        """MLXEngine (standalone) バックエンドの読み込みを試行"""
        try:
            engine = _MLXEngine(base_dir=self.model_path.parent, config=self.config)
            # Lazy loading — ここでは即座にロードして成功を確認
            engine._ensure_loaded()
            if engine.is_loaded():
                self._mlx_engine = engine
                self._backend = "mlx"
                self._loaded = True
                self._model_name = engine.model_name
                self._template_id = self._resolve_template(engine.model_name)
                print(f"[LLM/MLXEngine] ✓ 読み込み完了: {engine.model_name}")
                return True
            return False
        except Exception as e:
            print(f"[LLM/MLXEngine] 読み込みエラー: {e}")
            return False

    def _try_load_mlx(self) -> bool:
        """MLXバックエンドの読み込みを試行 (インライン版, MLXEngine失敗時のフォールバック)"""
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
            self._template_id = self._resolve_template(mlx_path.name)
            print(f"[LLM/MLX] ✓ 読み込み完了: {self._model_name} (template={self._template_id})")
            return True
        except Exception as e:
            print(f"[LLM/MLX] 読み込みエラー: {e}")
            return False

    def _select_quantization(self, candidates: list[Path]) -> Path:
        """Item #P8: RAM 容量と config 指定を考慮して最適な量子化レベルを選ぶ。

        優先順位:
          1. config["quantization"] で明示指定 (例: "Q4_K_M", "Q5_K_M", "Q8_0")
          2. 利用可能 RAM に基づく自動選択
             - >= 16 GB → Q5_K_M / Q8_0 を優先
             - 8 - 16 GB → Q5_K_M / Q4_K_M
             - < 8 GB  → Q4_K_M / Q3_K
          3. 既存の priority 順（フォールバック）
        """
        if not candidates:
            raise ValueError("no GGUF candidates")

        def _level(name: str) -> str:
            low = name.lower()
            for q in ("q8_0", "q6_k", "q5_k_m", "q5_k_s", "q5_0",
                      "q4_k_m", "q4_k_s", "q4_0", "q3_k_m", "q3_k_s", "q2_k"):
                if q in low:
                    return q
            return ""

        # 1) explicit override
        explicit = str(self.config.get("quantization", "")).lower()
        if explicit:
            for f in candidates:
                if explicit in f.name.lower():
                    print(f"[LLM/P8] 量子化レベル指定: {explicit} → {f.name}")
                    return f

        # 2) RAM-based auto selection
        try:
            import psutil  # type: ignore
            total_gb = psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            # psutil が無ければ sysconf を試す
            try:
                import os as _os
                pages = _os.sysconf("SC_PHYS_PAGES")
                pagesize = _os.sysconf("SC_PAGE_SIZE")
                total_gb = (pages * pagesize) / (1024 ** 3)
            except Exception:
                total_gb = 8.0  # 保守的デフォルト

        if total_gb >= 16:
            pref = ["q5_k_m", "q8_0", "q6_k", "q5_0", "q4_k_m"]
        elif total_gb >= 8:
            pref = ["q5_k_m", "q4_k_m", "q5_0", "q4_0"]
        else:
            pref = ["q4_k_m", "q4_0", "q3_k_m", "q3_k_s", "q2_k"]

        for pr in pref:
            for f in candidates:
                if pr in f.name.lower():
                    print(f"[LLM/P8] 自動量子化選択 (RAM={total_gb:.1f}GB): {pr} → {f.name}")
                    return f

        # 3) フォールバック: 既存順序の先頭
        return candidates[0]

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
                # Phase 0: model_family の gguf_hint でフィルタ (該当があれば優先)
                fam_info = getattr(self, "_model_family_info", None)
                hint = (fam_info or {}).get("gguf_hint", "") if fam_info else ""
                if hint:
                    matched = [f for f in gguf_files if hint.lower() in f.name.lower()]
                    if matched:
                        print(f"[LLM/P0] gguf_hint='{hint}' に合致 {len(matched)}/{len(gguf_files)} 件に絞り込み")
                        gguf_files = matched
                    else:
                        print(f"[LLM/P0] ⚠ gguf_hint='{hint}' 合致なし — 全候補から選択")
                priority = {"sarashina": 0, "qwen": 1, "gemma": 2, "llama": 3, "phi": 4}
                gguf_files.sort(key=lambda f: next(
                    (v for k, v in priority.items() if k in f.name.lower()), 9
                ))
                # Item #P8: Auto-quantization — RAM に応じて Q4/Q5/Q8 を自動選択
                model_file = self._select_quantization(gguf_files)
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
            self._template_id = self._resolve_template(model_file.name)
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
            self._template_id = self._resolve_template(model_file.name)
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

    @property
    def backend(self) -> str:
        """現在の推論バックエンドを返す (property版)"""
        return self._backend or "none"

    def override_params(self, params: dict) -> dict:
        """
        推論パラメータを一時的に上書きする。
        変更前の値を返すので、呼び出し側で復元できる。

        対象キー: temperature, max_tokens, top_p, top_k, repeat_penalty
        """
        previous: dict = {}
        for key in ("temperature", "max_tokens", "top_p", "top_k", "repeat_penalty"):
            if key in params:
                previous[key] = self.config.get(key)
                self.config[key] = params[key]
        return previous

    def restore_params(self, saved: dict) -> None:
        """
        override_params で保存した値を復元する。
        Noneの値はキー自体を削除する（元々存在しなかったキー）。
        """
        for key, value in saved.items():
            if value is None:
                self.config.pop(key, None)
            else:
                self.config[key] = value

    # ─── Item #2: KV cache optimization ─────────────────────────
    def _get_prompt_hash(self, system_prompt: str) -> str:
        """system_prompt のハッシュを返す（同一判定用）"""
        return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16]

    # ─── Item #84: Chain-of-thought for 3B model ─────────────────
    @staticmethod
    def _apply_cot(user_input: str, intent: str) -> str:
        """相談・複雑なインテントに CoT プレフィクスを追加"""
        cot_prefix = "まず相手の気持ちを考えて、次に返答を考えてください。\n\n"
        return cot_prefix + user_input

    # ─── Item #87: Dynamic repeat_penalty ────────────────────────
    def _dynamic_repeat_penalty(self) -> float:
        """直近5応答の長さに基づいて repeat_penalty を動的調整"""
        if not self._recent_response_lengths:
            return self.config.get("repeat_penalty", 1.1)

        avg_len = sum(self._recent_response_lengths) / len(self._recent_response_lengths)
        if avg_len < 20:
            return 1.0
        elif avg_len > 200:
            return 1.2
        return 1.1

    # ─── Item #88: Smart stop tokens ─────────────────────────────
    @staticmethod
    def _trim_incomplete_sentence(text: str) -> str:
        """不完全な文末を除去する。。！？♪〜 で終わっていない場合、最後の完全な文で切る"""
        if not text:
            return text
        # 既に文末記号で終わっている場合はそのまま
        if text[-1] in "。！？♪〜!?":
            return text
        # 最後の文末記号の位置を探す
        last_end = -1
        for i in range(len(text) - 1, -1, -1):
            if text[i] in "。！？♪〜!?":
                last_end = i
                break
        if last_end >= 0:
            return text[: last_end + 1]
        # 文末記号が1つもない場合はそのまま返す（短い応答向け）
        return text

    # ─── Item #89: Context window usage tracking ─────────────────
    def _record_context_stats(
        self, system_tokens: int, memory_tokens: int,
        history_tokens: int, generation_tokens: int,
    ) -> None:
        """推論ごとのトークン使用量を記録"""
        self._context_stats.append({
            "system": system_tokens,
            "memory": memory_tokens,
            "history": history_tokens,
            "generation": generation_tokens,
            "total": system_tokens + memory_tokens + history_tokens + generation_tokens,
            "timestamp": _time.time(),
        })
        # 直近100件のみ保持
        if len(self._context_stats) > 100:
            self._context_stats = self._context_stats[-100:]

    def get_context_stats(self) -> dict:
        """コンテキスト使用量の平均統計を返す"""
        if not self._context_stats:
            return {
                "count": 0,
                "avg_system": 0.0,
                "avg_memory": 0.0,
                "avg_history": 0.0,
                "avg_generation": 0.0,
                "avg_total": 0.0,
            }
        n = len(self._context_stats)
        return {
            "count": n,
            "avg_system": sum(s["system"] for s in self._context_stats) / n,
            "avg_memory": sum(s["memory"] for s in self._context_stats) / n,
            "avg_history": sum(s["history"] for s in self._context_stats) / n,
            "avg_generation": sum(s["generation"] for s in self._context_stats) / n,
            "avg_total": sum(s["total"] for s in self._context_stats) / n,
        }

    # ─── Item #90: Confidence estimation ─────────────────────────
    def generate_with_confidence(self, prompt: str) -> tuple[str, float]:
        """
        テキスト生成 + 信頼度推定を返す。
        llama-cpp が logprobs を返す場合、平均 logprob を信頼度として使用。
        低信頼度 (< -2.0) はフラグする。
        """
        if not self._loaded:
            return self._fallback_response(), 0.0

        if self._backend == "mlx":
            # MLX は logprobs 非対応 — テキストのみ返す
            text = self.generate(prompt)
            return text, 0.0

        if self._llm is None:
            return self._fallback_response(), 0.0

        params = {
            "max_tokens": self.config.get("max_tokens", 512),
            "temperature": self.config.get("temperature", 0.8),
            "top_p": self.config.get("top_p", 0.95),
            "stop": ["<|user|>", "<|end|>", "User:", "ユーザー:"],
            "logprobs": 1,
        }

        try:
            with self._inference_lock:
                output = self._llm(prompt, **params)
            text = output["choices"][0]["text"].strip()

            # logprobs から平均信頼度を計算
            confidence = 0.0
            logprobs_data = output["choices"][0].get("logprobs")
            if logprobs_data and logprobs_data.get("token_logprobs"):
                token_lps = [
                    lp for lp in logprobs_data["token_logprobs"]
                    if lp is not None
                ]
                if token_lps:
                    avg_logprob = sum(token_lps) / len(token_lps)
                    confidence = avg_logprob
                    if avg_logprob < -2.0:
                        logger.warning(
                            "低信頼度応答: avg_logprob=%.2f, text=%s...",
                            avg_logprob, text[:50],
                        )
            return text, confidence
        except Exception as e:
            logger.error("generate_with_confidence エラー: %s", e)
            return self._fallback_response(), 0.0

    # ─── Item #15: Watchdog timeout ──────────────────────────────
    def _generate_with_timeout(
        self, func: Callable[[], str], timeout_sec: float = 60.0,
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
            logger.warning("推論タイムアウト (%.0f秒超過)", timeout_sec)
            return self._TIMEOUT_FALLBACK

        if error_holder:
            logger.error("推論スレッドエラー: %s", error_holder[0])
            return self._fallback_response()

        if result_holder:
            return result_holder[0]
        return self._fallback_response()

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
    def _is_repetitive(text: str, prev: str) -> bool:
        """前回応答との類似度が高いか判定（部分文字列一致のみ、false positive を抑制）"""
        import re as _re
        _strip = _re.compile(r"[！!。、？?〜～\s…・「」]+")
        a = _strip.sub("", text)
        b = _strip.sub("", prev)
        if not a or not b:
            return False
        # 短い方が長い方に完全に含まれている場合のみ繰り返しと判定
        # （文字レベル一致率は日本語で false positive が多すぎるため廃止）
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        return short in long

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
        """プロンプトからテキストを生成します（60秒タイムアウト付き）"""
        if not self._loaded:
            return self._fallback_response()

        # Item #P2: Response cache lookup（非ストリーミング時のみ）
        cache_key = None
        if not stream:
            import hashlib as _h
            cache_key = _h.md5(prompt.encode("utf-8"), usedforsecurity=False).hexdigest()
            cached = self._response_cache.get(cache_key)
            if cached is not None:
                self._response_cache.move_to_end(cache_key)
                self._response_cache_hits += 1
                return cached
            self._response_cache_misses += 1

        # MLXEngine (standalone) — prompt をメッセージ形式に変換して委譲
        if self._backend == "mlx" and self._mlx_engine is not None:
            messages = [{"role": "user", "content": prompt}]
            return self._mlx_engine.generate_chat(messages)

        if self._backend == "mlx":
            def _mlx_gen() -> str:
                with self._inference_lock:
                    result = mlx_generate(
                        self._mlx_model, self._mlx_tokenizer,
                        prompt=prompt,
                        max_tokens=self.config.get("max_tokens", 512),
                        verbose=False,
                        **self._mlx_sampling_kwargs(),
                    )
                text = result.strip()
                text = self._trim_incomplete_sentence(text)
                self._recent_response_lengths.append(len(text))
                return text
            return self._generate_with_timeout(_mlx_gen)

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
            def _llama_gen() -> str:
                with self._inference_lock:
                    output = self._llm(prompt, **params)
                text = output["choices"][0]["text"].strip()
                text = self._trim_incomplete_sentence(text)
                self._recent_response_lengths.append(len(text))
                return text
            result = self._generate_with_timeout(_llama_gen)
            # Item #P2: cache insert
            if cache_key and isinstance(result, str) and result:
                self._response_cache[cache_key] = result
                while len(self._response_cache) > self._response_cache_max:
                    self._response_cache.popitem(last=False)
            return result

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

        # ── MLXEngine (standalone) ────────────────────────────
        if self._backend == "mlx" and self._mlx_engine is not None:
            result = self._mlx_engine.generate_chat(
                messages, stream_cb=stream_cb, max_tokens=resolved_max,
            )
        # ── インラインMLXバックエンド ────────────────────────
        elif self._backend == "mlx":
            result = self._generate_chat_mlx(messages, resolved_max, stream_cb)
        # ── llamaバックエンド ────────────────────────────────
        elif self._llm is None:
            return self._fallback_response()
        else:
            result = self._generate_chat_llama(messages, resolved_max, stream_cb)

        # ── Akashic: EntropyEngine quality check ──
        try:
            from core.akashic.entropy_engine import EntropyEngine
            try:
                _profile = EntropyEngine().profile(result)
                if hasattr(_profile, "unique_word_ratio") and _profile.unique_word_ratio < 0.3:
                    logger.warning("[Akashic] Low entropy response detected (unique_word_ratio=%.2f); output may be repetitive.", _profile.unique_word_ratio)
            except Exception:
                pass
        except ImportError:
            pass

        return result

    def _generate_chat_mlx(self, messages: list[dict], max_tokens: int,
                           stream_cb: "Callable[[str], None] | None" = None) -> str:
        """MLXバックエンドでチャット生成（60秒タイムアウト付き）"""
        def _inner() -> str:
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
                text = self._trim_incomplete_sentence(text)

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
                    retry_text = self._trim_incomplete_sentence(retry_text)
                    if not self._is_repetitive(retry_text, prev_response):
                        text = retry_text
                    else:
                        # adapterの支配が強すぎる場合の最終防衛線
                        text = self._anti_repeat_fallback(messages)

                # 応答長を追跡（dynamic repeat_penalty 用）
                self._recent_response_lengths.append(len(text))

                # コンテキスト統計記録
                system_tok = sum(len(m.get("content", "")) for m in messages if m.get("role") == "system")
                history_tok = sum(len(m.get("content", "")) for m in messages if m.get("role") != "system")
                self._record_context_stats(system_tok, 0, history_tok, len(text))

                # ストリーミングコールバック（MLXは一括生成後にまとめて送信）
                if stream_cb is not None and text:
                    stream_cb(text)
                return text
            except Exception as e:
                logger.error("[LLM/MLX] 推論エラー: %s", e)
                return self._fallback_response()

        return self._generate_with_timeout(_inner)

    def _generate_chat_llama(self, messages: list[dict], max_tokens: int,
                             stream_cb: "Callable[[str], None] | None" = None) -> str:
        """llama-cpp-pythonバックエンドでチャット生成（60秒タイムアウト付き）"""
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

        # Item #87: 動的 repeat_penalty
        params = {
            "max_tokens": max_tokens,
            "temperature": self.config.get("temperature", 0.7),
            "top_p": self.config.get("top_p", 0.9),
            "top_k": self.config.get("top_k", 40),
            "repeat_penalty": self._dynamic_repeat_penalty(),
            "stop": stop_tokens,
        }

        def _inner() -> str:
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
                    text = "".join(chunks).strip()
                    text = self._trim_incomplete_sentence(text)
                    self._recent_response_lengths.append(len(text))
                    # コンテキスト統計記録
                    system_tok = sum(
                        len(m.get("content", "")) for m in messages if m.get("role") == "system"
                    )
                    history_tok = sum(
                        len(m.get("content", "")) for m in messages if m.get("role") != "system"
                    )
                    self._record_context_stats(system_tok, 0, history_tok, len(text))
                    return text

                with self._inference_lock:
                    output = self._llm(prompt, **params)
                text = output["choices"][0]["text"].strip()
                text = self._trim_incomplete_sentence(text)
                self._recent_response_lengths.append(len(text))
                # コンテキスト統計記録
                system_tok = sum(
                    len(m.get("content", "")) for m in messages if m.get("role") == "system"
                )
                history_tok = sum(
                    len(m.get("content", "")) for m in messages if m.get("role") != "system"
                )
                self._record_context_stats(system_tok, 0, history_tok, len(text))
                return text
            except Exception as e:
                logger.error("[LLM/llama] 推論エラー: %s", e)
                return self._fallback_response()

        return self._generate_with_timeout(_inner)

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

    def build_prompt(
        self,
        system_prompt: str,
        conversation_history: list[dict],
        memory_context: str = "",
        emotion_hint: str = "",
        intent: str = "",
    ) -> list[dict]:
        """
        プロンプトを構築する。
        Item #2: system_prompt のハッシュでキャッシュし、同一プロンプトの再構築を回避。
        Item #84: intent が CoT 対象なら最後の user 入力に CoT プレフィクスを追加。
        """
        # ── Item #2: KV cache optimization ──
        # BUG #4 FIX: memory_context もハッシュに含める（毎ターン変わるコンテキストが無視されていた）
        ctx = (memory_context or "").strip()
        prompt_hash = self._get_prompt_hash(system_prompt + ctx[:100])
        if prompt_hash == self._last_prompt_hash and self._cached_prompt:
            system_content = self._cached_prompt
        else:
            system_content = system_prompt
            if ctx:
                system_content += "\n" + ctx[:350]
            self._last_prompt_hash = prompt_hash
            self._cached_prompt = system_content

        messages: list[dict] = [{"role": "system", "content": system_content}]

        # ── Item #84: Chain-of-thought for consultation/complex intents ──
        history = list(conversation_history)
        if intent and intent in self._COT_INTENTS and history:
            last_msg = history[-1]
            if last_msg.get("role") == "user":
                history = history[:-1] + [{
                    **last_msg,
                    "content": self._apply_cot(last_msg["content"], intent),
                }]

        # ── Akashic: UnifiedField domain resonance hints ──
        try:
            from core.akashic.unified_field import UnifiedField
            try:
                last_user = next(
                    (m["content"] for m in reversed(list(conversation_history))
                     if m.get("role") == "user"), None
                )
                if last_user:
                    _uf = UnifiedField()
                    _sig = _uf.resonate(last_user)
                    _phi = _uf.measure_phi(last_user)
                    if _phi > 0.3:
                        _domains = ", ".join(str(d) for d in list(_sig.domains)[:3]) if hasattr(_sig, "domains") else str(_sig)
                        messages[0] = {
                            **messages[0],
                            "content": messages[0]["content"] + f"\n\n[場の共鳴: {_domains} | Φ={_phi:.2f}]",
                        }
            except Exception:
                pass
        except ImportError:
            pass

        messages.extend(history)
        return messages

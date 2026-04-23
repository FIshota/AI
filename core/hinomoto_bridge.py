"""ai-chan ← HinoMoto 統合ブリッジ (PoC, Phase 2 kickoff).

目的:
    既存の LLMEngine を変えずに、自社モデル HinoMoto を
    「テキスト生成バックエンド」として差し込めることを示す最小実装。

使い方:
    from core.hinomoto_bridge import HinoMotoBridge
    bridge = HinoMotoBridge(
        checkpoint="/path/to/hinomoto-model/artifacts/main_run_v2/ckpt_best_val.pt",
        tokenizer="/path/to/hinomoto-model/artifacts/tokenizer_jawiki.json",
    )
    reply = bridge.reply("今日の天気は")

設計方針:
    - 遅延インポート (hinomoto パッケージが見つからなくても import エラーで落ちない)
    - 決定論モード (greedy, min_gen_chars=5) を既定 — BLEU 評価で最高性能だった設定
    - 秘密トークンや外部接続なし (完全ローカル)
    - 将来的に LLMEngine の backend 選択肢へ昇格させる前提の薄い形

フェーズ:
    PoC (今) → 品質ベンチ → LLMEngine.backend=\"hinomoto\" 昇格 → 本番
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class HinoMotoBridge:
    """HinoMoto 推論を ai-chan から呼び出すための薄いアダプタ."""

    def __init__(
        self,
        checkpoint: str | Path,
        tokenizer: str | Path,
        *,
        hinomoto_repo_path: Optional[str | Path] = None,
        device: Optional[str] = None,
    ) -> None:
        self.checkpoint = Path(checkpoint)
        self.tokenizer_path = Path(tokenizer)
        self._runner = None  # 遅延初期化

        # hinomoto パッケージを sys.path に追加
        if hinomoto_repo_path is None:
            # 既定: agent ディレクトリ配下の hinomoto-model を探索
            candidates = [
                Path(__file__).resolve().parents[2] / "hinomoto-model",
                Path("/Users/fujihiranoborudai/Downloads/agent/hinomoto-model"),
            ]
            for c in candidates:
                if (c / "hinomoto").is_dir():
                    hinomoto_repo_path = c
                    break
        if hinomoto_repo_path and str(hinomoto_repo_path) not in sys.path:
            sys.path.insert(0, str(hinomoto_repo_path))
            log.debug("added to sys.path: %s", hinomoto_repo_path)

        self._device = device
        log.info(
            "HinoMotoBridge configured: ckpt=%s tokenizer=%s",
            self.checkpoint, self.tokenizer_path,
        )

    def _ensure_loaded(self) -> None:
        if self._runner is not None:
            return
        try:
            from hinomoto.infer.generate import GenerationRunner  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "HinoMoto package not importable. "
                "Ensure hinomoto-model repo is on sys.path."
            ) from e
        self._runner = GenerationRunner(
            checkpoint=self.checkpoint,
            tokenizer=self.tokenizer_path,
            device=self._device,
        )
        log.info("HinoMoto runner initialized")

    def reply(
        self,
        prompt: str,
        *,
        max_new_tokens: int = 128,
        greedy: bool = True,
        min_gen_chars: int = 5,
        seed: Optional[int] = None,
    ) -> str:
        """プロンプトに対する生成返答を返す.

        既定設定は 2026-04-23 ベンチで BLEU 最高 (0.3514) を取った
        greedy + min_gen_chars=5 の組合わせ.
        """
        self._ensure_loaded()
        assert self._runner is not None

        if greedy:
            temperature = 0.0
            top_p = None
            top_k = None
            repetition_penalty = 1.0
        else:
            temperature = 0.8
            top_p = 0.95
            top_k = 50
            repetition_penalty = 1.1

        generated = self._runner.generate(
            prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            min_new_tokens=min_gen_chars,
            seed=seed,
        )
        return generated

    def is_available(self) -> bool:
        """モデル/トークナイザファイルが揃っていて load 可能か判定."""
        return self.checkpoint.exists() and self.tokenizer_path.exists()


# スモークテスト ----------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    bridge = HinoMotoBridge(
        checkpoint="/Users/fujihiranoborudai/Downloads/agent/hinomoto-model/artifacts/main_run_v2/ckpt_best_val.pt",
        tokenizer="/Users/fujihiranoborudai/Downloads/agent/hinomoto-model/artifacts/tokenizer_jawiki.json",
    )
    print("available:", bridge.is_available())
    for prompt in ["今日の天気は", "桜の季節が", "日本の首都は"]:
        out = bridge.reply(prompt, max_new_tokens=64)
        print(f"\n>> {prompt}")
        print(f"<< {out}")

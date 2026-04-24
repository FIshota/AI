"""Smoke + unit tests for core/hinomoto_bridge.py (P1-4-alpha).

真のモデルロードは重い & ckpt path 依存なので、統合テストは
環境変数 HINOMOTO_CKPT / HINOMOTO_TOKENIZER が両方 set かつ existsの場合のみ実行。
それ以外は is_available() / 遅延インポート経路 / 設定伝播を unit test する。
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.hinomoto_bridge import HinoMotoBridge


def _real_assets_available() -> bool:
    ckpt = os.environ.get("HINOMOTO_CKPT")
    tok = os.environ.get("HINOMOTO_TOKENIZER")
    return bool(ckpt and tok and Path(ckpt).exists() and Path(tok).exists())


class TestHinoMotoBridgeUnit:
    def test_is_available_false_for_nonexistent_paths(self, tmp_path):
        bridge = HinoMotoBridge(
            checkpoint=tmp_path / "missing.pt",
            tokenizer=tmp_path / "missing.json",
        )
        assert bridge.is_available() is False

    def test_is_available_true_when_files_exist(self, tmp_path):
        ckpt = tmp_path / "ckpt.pt"
        tok = tmp_path / "tokenizer.json"
        ckpt.write_bytes(b"fake")
        tok.write_text("{}")
        bridge = HinoMotoBridge(checkpoint=ckpt, tokenizer=tok)
        assert bridge.is_available() is True

    def test_adds_hinomoto_repo_to_sys_path(self, tmp_path, monkeypatch):
        import sys
        repo = tmp_path / "hinomoto-model"
        (repo / "hinomoto").mkdir(parents=True)
        # remove any pre-existing entry to ensure insertion
        monkeypatch.setattr(sys, "path", [p for p in sys.path if str(repo) not in p])
        HinoMotoBridge(
            checkpoint=tmp_path / "x.pt",
            tokenizer=tmp_path / "y.json",
            hinomoto_repo_path=repo,
        )
        assert str(repo) in sys.path

    def test_reply_lazy_loads_runner(self, tmp_path):
        """reply() 初回呼び出しで GenerationRunner がインスタンス化される."""
        bridge = HinoMotoBridge(
            checkpoint=tmp_path / "x.pt",
            tokenizer=tmp_path / "y.json",
        )
        assert bridge._runner is None

        fake_runner = MagicMock()
        fake_runner.generate.return_value = "夢のような応答"

        with patch("hinomoto.infer.generate.GenerationRunner",
                   return_value=fake_runner, create=True):
            out = bridge.reply("こんにちは", max_new_tokens=16)
        assert out == "夢のような応答"
        assert bridge._runner is fake_runner
        fake_runner.generate.assert_called_once()

    def test_greedy_mode_disables_sampling(self, tmp_path):
        bridge = HinoMotoBridge(
            checkpoint=tmp_path / "x.pt",
            tokenizer=tmp_path / "y.json",
        )
        fake = MagicMock()
        fake.generate.return_value = "ok"
        bridge._runner = fake

        bridge.reply("テスト", greedy=True)
        kwargs = fake.generate.call_args.kwargs
        assert kwargs["temperature"] == 0.0
        assert kwargs["top_p"] is None
        assert kwargs["top_k"] is None
        # NOTE: 2026-04-23 以降 greedy 既定は 1.3 (反復抑制目的)。
        # 実装 core/hinomoto_bridge.py の既定値に合わせる。
        assert kwargs["repetition_penalty"] == 1.3

    def test_sampling_mode_has_defaults(self, tmp_path):
        bridge = HinoMotoBridge(
            checkpoint=tmp_path / "x.pt",
            tokenizer=tmp_path / "y.json",
        )
        fake = MagicMock()
        fake.generate.return_value = "ok"
        bridge._runner = fake

        bridge.reply("テスト", greedy=False)
        kwargs = fake.generate.call_args.kwargs
        assert kwargs["temperature"] == 0.8
        assert kwargs["top_p"] == 0.95
        assert kwargs["top_k"] == 50


@pytest.mark.skipif(
    not _real_assets_available(),
    reason="set HINOMOTO_CKPT and HINOMOTO_TOKENIZER to run end-to-end test",
)
class TestHinoMotoBridgeIntegration:
    def test_reply_produces_nonempty_text(self):
        bridge = HinoMotoBridge(
            checkpoint=os.environ["HINOMOTO_CKPT"],
            tokenizer=os.environ["HINOMOTO_TOKENIZER"],
        )
        assert bridge.is_available()
        out = bridge.reply("今日の天気は", max_new_tokens=32, greedy=True, seed=42)
        assert isinstance(out, str)
        assert len(out) > 0

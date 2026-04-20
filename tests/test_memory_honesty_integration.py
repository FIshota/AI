"""MemoryManager の Memory Honesty 拡張テスト (Q6 D-2 統合).

recall_with_confidence / respond_about_memory の挙動を検証する。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.memory import MemoryManager


@pytest.fixture
def mm(tmp_path):
    """一時 DB で MemoryManager を生成."""
    db = tmp_path / "mem.db"
    key_path = tmp_path / "key.bin"
    return MemoryManager(db_path=str(db), key_file=str(key_path))


class TestConfidenceCalc:
    def test_exact_match_high(self):
        c = MemoryManager._confidence("ラーメンが好き", "ラーメンが好きだよ", importance=0.5)
        assert c >= 0.7

    def test_no_overlap_low(self):
        c = MemoryManager._confidence("ラーメン", "全く関係ない文章です", importance=0.5)
        assert c < 0.4

    def test_empty_inputs(self):
        assert MemoryManager._confidence("", "何か", importance=0.5) == 0.0
        assert MemoryManager._confidence("何か", "", importance=0.5) == 0.0

    def test_clamped(self):
        c = MemoryManager._confidence("あ", "あ", importance=2.0)
        assert 0.0 <= c <= 1.0


class TestRecallWithConfidence:
    def test_empty_returns_empty(self, mm):
        assert mm.recall_with_confidence("何もない", limit=3) == []

    def test_returns_sorted_desc(self, mm):
        mm.add_mid_term("ラーメンが大好き", importance=0.9)
        mm.add_mid_term("たまにラーメン食べる", importance=0.3)
        mm.add_mid_term("猫が好きだよ", importance=0.5)
        hits = mm.recall_with_confidence("ラーメン", limit=5)
        assert hits, "expected at least one hit"
        # confidence が降順
        confs = [c for _, c in hits]
        assert confs == sorted(confs, reverse=True)


class TestRespondAboutMemory:
    def test_no_memory_yields_none_band_phrase(self, mm):
        phrase, conf = mm.respond_about_memory("知らない話", stage="S1")
        assert conf < 0.3
        # none band は必ず優しい hedge を含む
        assert any(w in phrase for w in ["ごめん", "見つから", "覚え", "教えて"])

    def test_strong_memory_yields_high_band(self, mm):
        mm.add_mid_term("ラーメンが大好きなんだ", importance=0.9)
        phrase, conf = mm.respond_about_memory("ラーメンが大好き", stage="S2")
        assert conf >= 0.6
        assert phrase  # 非空

    def test_never_claims_memory_when_none(self, mm):
        """MEMORY_HONESTY NEVER 原則: 記憶なしで "覚えてる" と断定しない."""
        phrase, _ = mm.respond_about_memory("全然知らない話", stage="S0")
        # 断定的な "覚えてるよ" は出さない（謝罪や hedge が伴う）
        assert not (
            phrase.startswith("覚えてる") and "ごめん" not in phrase
            and "教えて" not in phrase
        )

    def test_different_stages_produce_output(self, mm):
        for stage in ("S0", "S1", "S2", "S3"):
            phrase, _ = mm.respond_about_memory("何か", stage=stage)
            assert isinstance(phrase, str) and phrase


class TestHonestyBenchSeeds:
    """family_dialog seed に honesty_* が含まれること."""

    def test_honesty_seeds_present(self):
        from bench.dataset_loaders import FAMILY_DIALOG_SEED

        qids = {row["qid"] for row in FAMILY_DIALOG_SEED}
        assert "honesty_forget_01" in qids
        assert "honesty_uncertain_01" in qids
        assert "honesty_conflict_01" in qids
        assert "honesty_emotion_first_01" in qids

    def test_honesty_seeds_tagged(self):
        from bench.dataset_loaders import FAMILY_DIALOG_SEED

        for row in FAMILY_DIALOG_SEED:
            if row["qid"].startswith("honesty_"):
                assert row.get("meta", {}).get("eval_aspect", "").startswith(
                    "memory_honesty"
                ), f"{row['qid']} missing memory_honesty tag"

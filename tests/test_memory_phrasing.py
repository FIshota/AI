"""core/memory_phrasing のテスト (Q6 Memory Honesty).

MEMORY_HONESTY.md §3 の信頼度→band マッピング、4×4 マトリクスの完全性、
dedup 挙動、NEVER 原則（断定禁止）を確認する。
"""
from __future__ import annotations

import pytest

from core.memory_phrasing import (
    PHRASE_MATRIX,
    PhrasingConfig,
    band_from_confidence,
    pick_phrase,
)


class TestBandThresholds:
    @pytest.mark.parametrize("conf,expected", [
        (1.0, "high"),
        (0.90, "high"),
        (0.85, "high"),
        (0.84, "mid"),
        (0.70, "mid"),
        (0.60, "mid"),
        (0.59, "low"),
        (0.40, "low"),
        (0.30, "low"),
        (0.29, "none"),
        (0.10, "none"),
        (0.0, "none"),
    ])
    def test_band_mapping(self, conf, expected):
        assert band_from_confidence(conf) == expected

    def test_clamp_out_of_range(self):
        assert band_from_confidence(-0.5) == "none"
        assert band_from_confidence(1.5) == "high"


class TestMatrixCompleteness:
    """Stage × band の 4×4 = 16 セル全てが埋まっていること."""

    STAGES = ("S0", "S1", "S2", "S3")
    BANDS = ("high", "mid", "low", "none")

    def test_all_cells_filled(self):
        for s in self.STAGES:
            for b in self.BANDS:
                phrases = PHRASE_MATRIX[s][b]
                assert phrases, f"{s}/{b} is empty"
                assert all(isinstance(p, str) and p for p in phrases)


class TestPickPhrase:
    def test_returns_string(self):
        out = pick_phrase("S1", "mid", subject="ラーメン")
        assert isinstance(out, str) and out

    def test_subject_substitution(self):
        # S1/high の候補には {subject} を含むものがあるので、subject が反映され得る
        out = pick_phrase("S1", "high", subject="ラーメン",
                          config=PhrasingConfig(seed=0))
        # subject が入っているか、subject を使わない候補か、どちらかが正
        assert "{subject}" not in out

    def test_none_band_never_claims_memory(self):
        """NEVER 原則: none band で "覚えてる" と断定しない."""
        for _ in range(20):
            out = pick_phrase("S2", "none")
            # "覚えてる" + "よ" 系の断定（否定/疑問/謝罪なし）を含まない
            assert not (
                "覚えてるよ" in out and "ごめん" not in out
                and "忘れ" not in out and "見つから" not in out
            ), f"none band produced confident claim: {out}"

    def test_low_band_hedges(self):
        """low band では hedge 表現（曖昧/自信ない）が入る."""
        hedge_words = ["自信", "曖昧", "かな", "かも", "うっすら", "揺れ"]
        for _ in range(20):
            out = pick_phrase("S1", "low", subject="散歩")
            assert any(w in out for w in hedge_words), f"low missing hedge: {out}"

    def test_dedup_avoids_recent(self):
        """recent に入っているフレーズは選ばれない."""
        candidates = list(PHRASE_MATRIX["S0"]["high"])
        # 候補が 2 つなら、1 つを recent に入れればもう 1 つが必ず出る
        if len(candidates) >= 2:
            recent = [candidates[0]]
            for _ in range(10):
                out = pick_phrase("S0", "high", recent=recent)
                assert out != candidates[0]

    def test_seeded_deterministic(self):
        """seed 指定で決定的に同じフレーズ."""
        cfg = PhrasingConfig(seed=42)
        out1 = pick_phrase("S3", "mid", subject="X", config=cfg)
        out2 = pick_phrase("S3", "mid", subject="X", config=cfg)
        assert out1 == out2


class TestKindnessInvariants:
    """MEMORY_HONESTY §1 NEVER 原則の機械的検査."""

    BLAME_WORDS = ["じゃない?", "忘れちゃったの?", "言ったよね", "何度も言った"]

    def test_no_blame_anywhere(self):
        """マトリクス全セルに責め言葉が含まれない."""
        for stage in ("S0", "S1", "S2", "S3"):
            for band in ("high", "mid", "low", "none"):
                for phrase in PHRASE_MATRIX[stage][band]:
                    for blame in self.BLAME_WORDS:
                        assert blame not in phrase, \
                            f"blame '{blame}' found in {stage}/{band}: {phrase}"

    def test_none_band_always_hedges_or_apologizes(self):
        """none band のフレーズは必ず hedge or 謝罪を含む."""
        soft_markers = ["ごめん", "見つから", "覚え", "忘れ", "教えて"]
        for stage in ("S0", "S1", "S2", "S3"):
            for phrase in PHRASE_MATRIX[stage]["none"]:
                assert any(m in phrase for m in soft_markers), \
                    f"none/{stage} too cold: {phrase}"

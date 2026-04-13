"""ユーザー訂正学習モジュールのテスト"""
import json
import tempfile
from pathlib import Path

import pytest

from core.correction_learning import CorrectionLearning, CorrectionEntry


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def cl(tmp_dir):
    return CorrectionLearning(data_dir=tmp_dir)


class TestCorrectionDetection:
    """訂正パターンの検出テスト"""

    def test_no_correction_without_prior_turn(self, cl):
        """直前のターンがなければ訂正にならない"""
        assert cl.detect_correction("違うよ") is None

    def test_detect_chigau(self, cl):
        cl.record_turn("東京タワーの高さは？", "200メートルです。")
        entry = cl.detect_correction("違うよ")
        assert entry is not None
        assert entry.ai_wrong_response == "200メートルです。"

    def test_detect_souja_nakute(self, cl):
        cl.record_turn("明日の予定は？", "特にないんじゃない？")
        entry = cl.detect_correction("そうじゃなくて、会議があるんだよ")
        assert entry is not None
        assert entry.correct_info == "会議があるんだよ"

    def test_detect_iya(self, cl):
        cl.record_turn("好きな食べ物は？", "ラーメンかな？")
        entry = cl.detect_correction("いや、寿司だよ")
        assert entry is not None

    def test_detect_machigai(self, cl):
        cl.record_turn("計算して", "答えは5です。")
        entry = cl.detect_correction("間違ってるよ")
        assert entry is not None

    def test_detect_chotto_chigau(self, cl):
        cl.record_turn("説明して", "これはAです。")
        entry = cl.detect_correction("ちょっと違う")
        assert entry is not None

    def test_detect_sore_wa_chigau(self, cl):
        cl.record_turn("何色？", "青だよ。")
        entry = cl.detect_correction("それは違うよ")
        assert entry is not None

    def test_detect_janakute_pattern(self, cl):
        cl.record_turn("名前は？", "太郎さん？")
        entry = cl.detect_correction("太郎じゃなくて花子だよ")
        assert entry is not None

    def test_no_false_positive_normal_chat(self, cl):
        cl.record_turn("元気？", "元気だよ！")
        assert cl.detect_correction("今日はいい天気だね") is None

    def test_no_false_positive_greeting(self, cl):
        cl.record_turn("おはよう", "おはよう！")
        assert cl.detect_correction("ありがとう") is None


class TestCorrectionPersistence:
    """訂正データの永続化テスト"""

    def test_save_and_reload(self, tmp_dir):
        cl1 = CorrectionLearning(data_dir=tmp_dir)
        cl1.record_turn("質問", "間違った回答")
        cl1.detect_correction("違う、正しくはこう")

        # 新しいインスタンスで読み込み
        cl2 = CorrectionLearning(data_dir=tmp_dir)
        assert cl2.stats()["total_corrections"] == 1
        assert cl2.corrections[0].correction_input == "違う、正しくはこう"

    def test_jsonl_format(self, tmp_dir):
        cl = CorrectionLearning(data_dir=tmp_dir)
        cl.record_turn("Q", "A wrong")
        cl.detect_correction("違うよ")

        path = tmp_dir / "corrections.jsonl"
        assert path.exists()
        data = json.loads(path.read_text("utf-8").strip())
        assert "ai_wrong" in data
        assert "correction" in data


class TestCorrectionContext:
    """LLMコンテキスト生成テスト"""

    def test_build_correction_context(self, cl):
        entry = CorrectionEntry(
            timestamp=0,
            user_original="質問",
            ai_wrong_response="間違い",
            correction_input="違う、正しいよ",
            correct_info="正しいよ",
        )
        ctx = cl.build_correction_context(entry)
        assert "訂正" in ctx
        assert "間違い" in ctx
        assert "正しいよ" in ctx

    def test_recent_corrections_hint_empty(self, cl):
        assert cl.get_recent_corrections_hint() == ""

    def test_recent_corrections_hint_with_data(self, cl):
        cl.record_turn("Q", "Wrong A")
        cl.detect_correction("違う、Right A")
        hint = cl.get_recent_corrections_hint()
        assert "Wrong A" in hint
        assert "Right A" in hint


class TestCorrectInfoExtraction:
    """訂正文から正しい情報の抽出テスト"""

    def test_extract_from_chigau(self, cl):
        cl.record_turn("Q", "A")
        entry = cl.detect_correction("違う、本当は10だよ")
        assert entry is not None
        assert "本当は10だよ" in entry.correct_info

    def test_extract_from_souja_nakute(self, cl):
        cl.record_turn("Q", "A")
        entry = cl.detect_correction("そうじゃなくて、Bだよ")
        assert entry is not None
        assert "Bだよ" in entry.correct_info

    def test_no_extract_from_simple_denial(self, cl):
        cl.record_turn("Q", "A")
        entry = cl.detect_correction("間違ってるよ")
        assert entry is not None
        assert entry.correct_info == ""

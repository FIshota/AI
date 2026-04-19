"""
メモリリーク検出テスト

tracemalloc を使って 100 ターンの会話シミュレーションを行い、
メモリ使用量が閾値を超えて増加しないか検証する。
"""
from __future__ import annotations

import gc
import tracemalloc
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.slow
def test_memory_no_leak_100_turns() -> None:
    """100 ターンの会話でメモリリークがないことを確認する。

    判定基準: 開始時と終了時のメモリ差分が 50MB 未満であること。
    """
    # tracemalloc でメモリ追跡を開始
    tracemalloc.start()

    # メモリの初期スナップショット
    gc.collect()
    snapshot_start = tracemalloc.take_snapshot()
    start_current, start_peak = tracemalloc.get_traced_memory()

    try:
        # core.emotion は軽量なので直接 import 可能
        from core.emotion import EmotionState

        # メモリシステムをモックで構築
        # 実際の LLM はロードしない（テストの高速化）
        mock_memory = MagicMock()
        mock_memory.get_context.return_value = []
        mock_memory.add_conversation.return_value = None

        # 100 ターンのシミュレーション
        state = EmotionState()
        conversation_history: list[dict[str, str]] = []

        for turn in range(100):
            user_msg = f"テストメッセージ {turn}: " + "あ" * 50
            ai_msg = f"テスト応答 {turn}: " + "い" * 80

            # 会話履歴の蓄積
            conversation_history.append({"role": "user", "content": user_msg})
            conversation_history.append({"role": "assistant", "content": ai_msg})

            # 感情更新（実オブジェクトで計算）
            state = EmotionState(
                happiness=max(0.0, min(1.0, state.happiness + 0.001)),
                curiosity=max(0.0, min(1.0, state.curiosity - 0.001)),
                affection=state.affection,
                energy=max(0.0, min(1.0, state.energy - 0.002)),
                anxiety=state.anxiety,
            )
            _ = state.to_dict()
            _ = state.dominant()

            # mock_memory に記録
            mock_memory.add_conversation(user_msg, ai_msg)

            # 定期的に GC 実行（実運用を模倣）
            if turn % 20 == 0:
                gc.collect()

        # 終了スナップショット
        gc.collect()
        end_current, end_peak = tracemalloc.get_traced_memory()
        snapshot_end = tracemalloc.take_snapshot()

        # メモリ増分の計算
        delta_mb = (end_current - start_current) / (1024 * 1024)

        # 上位メモリ消費の統計（デバッグ用）
        stats = snapshot_end.compare_to(snapshot_start, "lineno")
        top_leaks = stats[:5]
        leak_info = "\n".join(str(s) for s in top_leaks)

        # 判定: 50 MB 未満の増加であること
        max_allowed_mb = 50.0
        assert delta_mb < max_allowed_mb, (
            f"メモリリーク検出: {delta_mb:.2f} MB 増加 "
            f"(上限: {max_allowed_mb} MB)\n"
            f"Top allocations:\n{leak_info}"
        )

    finally:
        tracemalloc.stop()


@pytest.mark.slow
def test_emotion_state_no_accumulation() -> None:
    """EmotionState の生成・破棄で参照が蓄積しないことを確認する。"""
    from core.emotion import EmotionState

    gc.collect()
    initial_objects = len(gc.get_objects())

    states = []
    for i in range(1000):
        s = EmotionState(
            happiness=float(i % 10) / 10,
            curiosity=0.5,
            affection=0.5,
            energy=0.5,
            anxiety=0.1,
        )
        states.append(s.to_dict())

    # 明示的に解放
    del states
    gc.collect()

    final_objects = len(gc.get_objects())
    delta = final_objects - initial_objects

    # オブジェクト数の増加が 500 以内であること（GC の余裕を考慮）
    assert delta < 500, f"オブジェクト蓄積: {delta} 個増加"

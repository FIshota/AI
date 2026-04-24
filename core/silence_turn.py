"""
沈黙イベントを会話履歴の turn レコードに変換するユーティリティ。

speaker="_silence_" の特殊 turn として履歴に刻むことで、
検索・表示・解析の下流で一貫して扱える。

Python 3.9 互換, stdlib のみ。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

from core.silence_token import SilenceEvent

SILENCE_SPEAKER = "_silence_"


def silence_event_to_turn(event: SilenceEvent) -> Dict[str, Any]:
    """
    SilenceEvent を turn レコード (dict) に変換する。

    形式:
        {
          "turn_id": "<uuid4>",
          "timestamp": <ended_at isoformat>,
          "speaker": "_silence_",
          "text": "<silence:<category>:<Ns>>",
          "meta": {
            "started_at": ...,
            "ended_at":   ...,
            "duration_s": ...,
            "category":   ...,
            "ambient_context": ...,
          },
        }
    """
    duration_int = int(round(event.duration_s))
    text = f"<silence:{event.category.value}:{duration_int}s>"
    return {
        "turn_id": str(uuid.uuid4()),
        "timestamp": event.ended_at.isoformat(),
        "speaker": SILENCE_SPEAKER,
        "text": text,
        "meta": {
            "started_at": event.started_at.isoformat(),
            "ended_at": event.ended_at.isoformat(),
            "duration_s": round(event.duration_s, 3),
            "category": event.category.value,
            "ambient_context": event.ambient_context,
        },
    }


__all__ = ["silence_event_to_turn", "SILENCE_SPEAKER"]

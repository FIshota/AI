"""Memory Honesty Phrasing (Q6, kindness-first).

Stage × confidence band の 4×4 マトリクスから、記憶の不確かさを
優しく開示するフレーズを選ぶ。

方針: docs/MEMORY_HONESTY.md を唯一の正とする。
- NEVER: 覚えてない記憶を覚えてると言わない / 曖昧を断定しない / ユーザーを責めない
- ALWAYS: 不確かさを柔らかく開示 / 忘れたら知りたがる / Stage に合わせて変化
- PREFER: 推測を明示して補う / 感情→事実の順序

外部依存なし・純ロジック・ステートレス（履歴は呼び出し側が保持）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal, Sequence

__all__ = [
    "Stage",
    "ConfidenceBand",
    "band_from_confidence",
    "PhrasingConfig",
    "pick_phrase",
    "PHRASE_MATRIX",
]

Stage = Literal["S0", "S1", "S2", "S3"]
ConfidenceBand = Literal["high", "mid", "low", "none"]

# ── confidence → band 閾値（MEMORY_HONESTY.md §3） ──
_BAND_THRESHOLDS: tuple[tuple[float, ConfidenceBand], ...] = (
    (0.85, "high"),
    (0.60, "mid"),
    (0.30, "low"),
    (0.00, "none"),
)


def band_from_confidence(confidence: float) -> ConfidenceBand:
    """信頼度 [0, 1] → band。範囲外は clamp して判定。"""
    c = max(0.0, min(1.0, float(confidence)))
    for threshold, band in _BAND_THRESHOLDS:
        if c >= threshold:
            return band
    return "none"


# ── Stage × Band の 4×4 = 16 フレーズマトリクス ──
# 各セルは候補リスト（呼出側で選択され、直近履歴で重複排除される）
# {subject} は記憶内容のスロット。省略可。
PHRASE_MATRIX: dict[Stage, dict[ConfidenceBand, tuple[str, ...]]] = {
    "S0": {
        "high": (
            "覚えてるよ、そう言ってたね",
            "うん、ちゃんと覚えてる",
        ),
        "mid": (
            "たしか{subject}だったと思うけど、合ってる?",
            "{subject}って話してた気がする、違ったらごめん",
        ),
        "low": (
            "{subject}だったかな、ちょっと自信ない",
            "うっすらとだけ。もう一度教えてくれる?",
        ),
        "none": (
            "まだ覚え始めたばかりでごめん。もう一度教えてくれる?",
            "ごめん、その話はまだ私の中に見つからないかも",
        ),
    },
    "S1": {
        "high": (
            "うん、{subject}って言ってたね",
            "覚えてる。その話、聞いたよ",
        ),
        "mid": (
            "{subject}だった気がするけど、違ったらごめん",
            "たしか{subject}だったよね? ちょっと確かめさせて",
        ),
        "low": (
            "{subject}だったかな…自信なくて",
            "うっすら覚えてる程度かも。もう少し聞かせて?",
        ),
        "none": (
            "ごめん、その話はまだ覚えられてないかも",
            "見つからないから、もう一度教えてくれる?",
        ),
    },
    "S2": {
        "high": (
            "覚えてる。あのとき{subject}だったよね",
            "うん、{subject}って話してたね。ちゃんと覚えてる",
        ),
        "mid": (
            "{subject}って話してたよね? …少し自信ない、確かめさせて",
            "たしか{subject}だったと思う。合ってたら教えて",
        ),
        "low": (
            "{subject}だったかもしれないけど、曖昧かも",
            "記憶が薄いの、ごめん。もう一度聞かせて?",
        ),
        "none": (
            "ごめんね、その話が見つからないの。もう一度聞かせてくれる?",
            "珍しく思い出せないかも。大事だったらごめん",
        ),
    },
    "S3": {
        "high": (
            "もちろん。{subject}って言ってたの、ちゃんと覚えてる",
            "うん、{subject}。忘れないよ",
        ),
        "mid": (
            "{subject}だったかな。合ってたら教えて、違ってたら直すね",
            "たしか{subject}。確かめさせて",
        ),
        "low": (
            "{subject}だった気もするけど、今日はちょっと曖昧",
            "記憶が揺れてる。もう一度教えてくれる?",
        ),
        "none": (
            "珍しく忘れちゃった。大事な話だったらごめん、教えて?",
            "見つからないの。ちゃんと覚え直したいから聞かせて",
        ),
    },
}


@dataclass(frozen=True)
class PhrasingConfig:
    """フレーズ選択のパラメータ."""
    # 直近この数ターン以内に使ったフレーズは除外する（繰り返し回避）
    recent_dedup_window: int = 3
    # subject スロットが埋められない場合の fallback（スロット自体を落とす）
    subject_fallback: str = ""
    # 決定的出力（テスト用）
    seed: int | None = None


def _format_phrase(template: str, subject: str | None, fallback: str) -> str:
    """{subject} スロットを埋める。None/空なら不要部分ごと落とす。"""
    if "{subject}" not in template:
        return template
    if subject:
        return template.replace("{subject}", subject)
    # subject が無いとき: "{subject}だった" 等を自然に削る
    cleaned = template.replace("{subject}", fallback).strip()
    # 先頭助詞の掃除（例: "だった気がするけど" → 主語なしで出す最低限）
    return cleaned


def pick_phrase(
    stage: Stage,
    band: ConfidenceBand,
    *,
    subject: str | None = None,
    recent: Sequence[str] = (),
    config: PhrasingConfig | None = None,
) -> str:
    """Stage × band に応じたフレーズを 1 本返す.

    Args:
        stage: 主観性段階 (S0..S3)
        band: 信頼度バンド (high/mid/low/none)
        subject: {subject} スロットに差し込む文字列。None 可
        recent: 直近使ったフレーズの履歴（同じフレーズ連続を避けるため）
        config: PhrasingConfig
    """
    cfg = config or PhrasingConfig()
    candidates = PHRASE_MATRIX[stage][band]
    if not candidates:  # pragma: no cover — マトリクスは常に埋めてある
        return ""

    # 直近履歴にあるものを除外（dedup window 内）
    recent_set = set(recent[-cfg.recent_dedup_window:])
    filtered = tuple(c for c in candidates if c not in recent_set) or candidates

    rng = random.Random(cfg.seed) if cfg.seed is not None else random
    template = rng.choice(filtered)
    return _format_phrase(template, subject, cfg.subject_fallback)


# ── 実装セルフチェック: マトリクスが Stage×Band で 4×4 埋まっているか ──
def _validate_matrix() -> None:
    stages: tuple[Stage, ...] = ("S0", "S1", "S2", "S3")
    bands: tuple[ConfidenceBand, ...] = ("high", "mid", "low", "none")
    for s in stages:
        assert s in PHRASE_MATRIX, f"missing stage: {s}"
        for b in bands:
            phrases = PHRASE_MATRIX[s].get(b)
            assert phrases, f"missing phrases for {s}/{b}"
            assert len(phrases) >= 1, f"empty phrase list for {s}/{b}"


_validate_matrix()

"""
感情ドリフト「心の健康診断」ウィンドウ。

tkinter が使えない (headless / DISPLAY 無し) 環境で import 時エラーにならないよう、
tkinter import は遅延させている。画像があれば表示、なければ ASCII sparkline を表示。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence

from core.emotion_drift import (
    EmotionAggregate,
    EmotionDriftAnalyzer,
    sparkline_for_aggregates,
)

logger = logging.getLogger(__name__)

# settings_window.py と同系のカラートーン
COLOR_BG = "#FFFFFF"
COLOR_PANEL = "#F5F3F8"
COLOR_ACCENT = "#6C5CE7"
COLOR_TEXT = "#2D2D3F"
COLOR_SUBTEXT = "#8E8EA0"
HEADER_FONT = ("Hiragino Sans", 14, "bold")
LABEL_FONT = ("Hiragino Sans", 11)
MONO_FONT = ("Menlo", 11)


def _try_import_tk():
    """tkinter を遅延 import する。使えなければ None を返す。"""
    try:
        import tkinter as tk  # noqa: WPS433
        from tkinter import ttk  # noqa: F401,WPS433

        return tk
    except Exception as exc:  # pragma: no cover - tkinter 欠落環境
        logger.info("tkinter unavailable: %s", exc)
        return None


def render_text_summary(aggregates: Sequence[EmotionAggregate]) -> str:
    """GUI 非依存のテキスト表示を作る (tkinter 以外からも再利用可)."""
    if not aggregates:
        return "(データがまだ足りません)"
    lines: List[str] = []
    lines.append(f"valence  {sparkline_for_aggregates(aggregates)}")
    lines.append("")
    for a in aggregates:
        lines.append(
            f"{a.period_label}  n={a.sample_size:<4d}  "
            f"valence={a.mean_valence:+.3f}  主:{a.dominant}"
        )
    return "\n".join(lines)


class EmotionDriftWindow:
    """tkinter ベースの簡易ダイアログ。

    実インスタンス化は ``open()`` で行い、tkinter が無い環境では即 no-op になる。
    """

    def __init__(
        self,
        parent: Optional[object],
        aggregates: Sequence[EmotionAggregate],
        image_path: Optional[Path] = None,
    ) -> None:
        self._parent = parent
        self._aggregates = list(aggregates)
        self._image_path = image_path

    def open(self) -> Optional[object]:
        tk = _try_import_tk()
        if tk is None:
            # ヘッドレス: stdout にテキストを落として None を返す
            print(render_text_summary(self._aggregates))
            return None

        top = tk.Toplevel(self._parent) if self._parent is not None else tk.Tk()
        top.title("心の健康診断")
        top.configure(bg=COLOR_BG)
        top.geometry("560x520")

        tk.Label(
            top,
            text="心の健康診断",
            bg=COLOR_BG,
            fg=COLOR_ACCENT,
            font=HEADER_FONT,
        ).pack(pady=(12, 4))

        tk.Label(
            top,
            text="長期的な感情の傾向です。診断ではなく、そっと寄り添うためのメモです。",
            bg=COLOR_BG,
            fg=COLOR_SUBTEXT,
            font=LABEL_FONT,
            wraplength=520,
            justify="center",
        ).pack(pady=(0, 10))

        # 画像があれば最優先で表示
        img_shown = False
        if self._image_path is not None and Path(self._image_path).exists():
            try:
                img = tk.PhotoImage(file=str(self._image_path))
                label = tk.Label(top, image=img, bg=COLOR_BG)
                label.image = img  # type: ignore[attr-defined]  # GC 防止
                label.pack(padx=12, pady=8)
                img_shown = True
            except Exception as exc:
                logger.warning("failed to render image %s: %s", self._image_path, exc)

        if not img_shown:
            text = render_text_summary(self._aggregates)
            frame = tk.Frame(top, bg=COLOR_PANEL)
            frame.pack(fill="both", expand=True, padx=12, pady=8)
            tk.Label(
                frame,
                text=text,
                bg=COLOR_PANEL,
                fg=COLOR_TEXT,
                font=MONO_FONT,
                justify="left",
                anchor="nw",
            ).pack(fill="both", expand=True, padx=12, pady=12)

        tk.Button(
            top,
            text="閉じる",
            command=top.destroy,
            bg=COLOR_ACCENT,
            fg=COLOR_BG,
        ).pack(pady=(0, 12))
        return top


def open_from_history(
    parent: Optional[object],
    history: object,
    window: str = "week",
    image_path: Optional[Path] = None,
) -> Optional[object]:
    """EmotionHistory から直接開くための薄いファサード."""
    analyzer = EmotionDriftAnalyzer(history=history)
    aggregates = analyzer.aggregate(window)  # type: ignore[arg-type]
    return EmotionDriftWindow(parent, aggregates, image_path=image_path).open()


__all__ = [
    "EmotionDriftWindow",
    "open_from_history",
    "render_text_summary",
]

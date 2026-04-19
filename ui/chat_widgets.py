"""
チャットUI用カスタムウィジェット

ChatWindow から抽出した再利用可能ウィジェット群。
タイプライター演出、感情バー、入力インジケータ、メッセージバブル、
フィードバックボタン、コマンドパレット、キーボードショートカットを提供する。
"""
from __future__ import annotations

import json
import logging
import platform
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── カラーパレット（Clean × Soft） ──────────────────────

COLOR_BG = "#FFFFFF"
COLOR_PANEL = "#F5F3F8"
COLOR_ACCENT = "#6C5CE7"
COLOR_TEXT = "#2D2D3F"
COLOR_SUBTEXT = "#8E8EA0"
COLOR_BUBBLE = "#F0EEFF"
COLOR_USER_BUB = "#E8F4FD"
COLOR_BORDER = "#E5E5EA"

# ライトテーマ用カラー（デフォルトと同一）
LIGHT_BG = "#FFFFFF"
LIGHT_PANEL = "#F5F3F8"
LIGHT_ACCENT = "#6C5CE7"
LIGHT_TEXT = "#2D2D3F"
LIGHT_SUBTEXT = "#8E8EA0"
LIGHT_BUBBLE = "#F0EEFF"
LIGHT_USER_BUB = "#E8F4FD"

IS_MAC = platform.system() == "Darwin"


def detect_dark_mode() -> bool:
    """macOS のシステムダークモード設定を検出する。非 macOS は True を返す。"""
    if not IS_MAC:
        return True
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip().lower() == "dark"
    except Exception:
        return True


def get_theme_colors(dark: bool = True) -> Dict[str, str]:
    """テーマに応じたカラーパレットを辞書で返す。"""
    if dark:
        return {
            "bg": COLOR_BG,
            "panel": COLOR_PANEL,
            "accent": COLOR_ACCENT,
            "text": COLOR_TEXT,
            "subtext": COLOR_SUBTEXT,
            "bubble": COLOR_BUBBLE,
            "user_bubble": COLOR_USER_BUB,
            "border": COLOR_BORDER,
        }
    return {
        "bg": LIGHT_BG,
        "panel": LIGHT_PANEL,
        "accent": LIGHT_ACCENT,
        "text": LIGHT_TEXT,
        "subtext": LIGHT_SUBTEXT,
        "bubble": LIGHT_BUBBLE,
        "user_bubble": LIGHT_USER_BUB,
        "border": "#E5E5EA",
    }


# ── TypewriterMixin ──────────────────────────────────────


class TypewriterMixin:
    """タイプライター効果でテキストを挿入するミックスイン。

    対象クラスが ``after()`` メソッド (tk.Widget) を持っている前提。
    """

    def typewriter_insert(
        self,
        widget: tk.Text,
        text: str,
        tag: str,
        delay: int = 25,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """1 文字ずつ *widget* へ挿入する。完了後に *callback* を呼ぶ。"""
        self._tw_queue: List[str] = list(text)
        self._tw_widget = widget
        self._tw_tag = tag
        self._tw_delay = delay
        self._tw_callback = callback
        self._tw_step()

    def _tw_step(self) -> None:
        try:
            if not self._tw_queue:
                if self._tw_callback:
                    self._tw_callback()
                return
            ch = self._tw_queue.pop(0)
            self._tw_widget.configure(state="normal")
            self._tw_widget.insert("end", ch, self._tw_tag)
            self._tw_widget.configure(state="disabled")
            self._tw_widget.see("end")
            # after() は tk.Misc のメソッド
            self.after(self._tw_delay, self._tw_step)  # type: ignore[attr-defined]
        except tk.TclError:
            pass


# ── EmotionBar ───────────────────────────────────────────


class EmotionBar(tk.Canvas):
    """感情状態を色付きグラデーションバーで表示するキャンバスウィジェット。"""

    COLORS: Dict[str, str] = {
        "happiness": "#6C5CE7",
        "curiosity": "#F9A825",
        "affection": "#E84393",
        "energy": "#00B894",
        "anxiety": "#E17055",
    }

    def __init__(self, parent: tk.Widget, height: int = 8, **kwargs: object) -> None:
        super().__init__(parent, height=height, highlightthickness=0, **kwargs)
        self._emotions: Dict[str, float] = {}

    def update_emotions(self, emotions: Dict[str, float]) -> None:
        """感情辞書を受け取りバーを再描画する。"""
        self._emotions = dict(emotions)
        self.delete("all")
        width = self.winfo_width()
        if width < 10:
            width = 300

        total = sum(max(0.0, v) for v in self._emotions.values()) or 1.0
        x = 0
        for key, value in self._emotions.items():
            ratio = max(0.0, value) / total
            seg_w = int(width * ratio)
            if seg_w < 1:
                continue
            color = self.COLORS.get(key, "#888888")
            self.create_rectangle(x, 0, x + seg_w, self.winfo_height(), fill=color, outline="")
            x += seg_w


# ── TypingIndicator ──────────────────────────────────────


class TypingIndicator(tk.Label):
    """「...」をアニメーションさせる入力中インジケータ。"""

    def __init__(self, parent: tk.Widget, **kwargs: object) -> None:
        defaults = {
            "text": "",
            "bg": kwargs.pop("bg", COLOR_BG),
            "fg": kwargs.pop("fg", COLOR_SUBTEXT),
            "font": ("Hiragino Sans", 11),
        }
        defaults.update(kwargs)
        super().__init__(parent, **defaults)
        self._running = False
        self._dots = 0

    def start(self) -> None:
        """アニメーション開始。"""
        self._running = True
        self._dots = 0
        self._tick()

    def stop(self) -> None:
        """アニメーション停止してテキストを空にする。"""
        self._running = False
        self.configure(text="")

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            self._dots = (self._dots % 3) + 1
            self.configure(text="アイが考えてるよ" + "." * self._dots)
            self.after(400, self._tick)
        except tk.TclError:
            self._running = False


# ── MessageBubble ────────────────────────────────────────


class MessageBubble:
    """Text ウィジェットへスタイル付きメッセージバブルを挿入するヘルパー。"""

    @staticmethod
    def insert_ai_message(
        text_widget: tk.Text,
        message: str,
        timestamp: str,
        colors: Optional[Dict[str, str]] = None,
    ) -> None:
        """AI メッセージをバブルスタイルで挿入する。"""
        c = colors or get_theme_colors(dark=True)
        text_widget.configure(state="normal")
        text_widget.insert("end", f" [{timestamp}] アイ\n", "ai_name")
        text_widget.insert("end", f" {message}\n\n", "ai_msg")
        text_widget.configure(state="disabled")
        text_widget.see("end")

    @staticmethod
    def insert_user_message(
        text_widget: tk.Text,
        message: str,
        timestamp: str,
        user_name: str = "あなた",
        colors: Optional[Dict[str, str]] = None,
    ) -> None:
        """ユーザーメッセージをバブルスタイルで挿入する。"""
        c = colors or get_theme_colors(dark=True)
        text_widget.configure(state="normal")
        text_widget.insert("end", f" [{timestamp}] {user_name}\n", "user_name")
        text_widget.insert("end", f" {message}\n\n", "user_msg")
        text_widget.configure(state="disabled")
        text_widget.see("end")


# ── FeedbackButtons ──────────────────────────────────────


class FeedbackButtons(tk.Frame):
    """AI 応答へのフィードバック (いいね / よくない) ボタン。"""

    def __init__(
        self,
        parent: tk.Widget,
        callback: Callable[[bool], None],
        bg: str = COLOR_BG,
        **kwargs: object,
    ) -> None:
        super().__init__(parent, bg=bg, **kwargs)
        self._callback = callback
        self._voted = False

        btn_cfg = {"font": ("Arial", 12), "relief": "flat", "cursor": "hand2", "bg": bg}
        self._up_btn = tk.Button(
            self, text="\U0001F44D", command=lambda: self._vote(True), **btn_cfg
        )
        self._up_btn.pack(side="left", padx=2)
        self._down_btn = tk.Button(
            self, text="\U0001F44E", command=lambda: self._vote(False), **btn_cfg
        )
        self._down_btn.pack(side="left", padx=2)

    def _vote(self, positive: bool) -> None:
        if self._voted:
            return
        self._voted = True
        try:
            self._callback(positive)
        except Exception as exc:
            logger.warning("フィードバックコールバックエラー: %s", exc)
        self._up_btn.configure(state="disabled")
        self._down_btn.configure(state="disabled")
        selected = self._up_btn if positive else self._down_btn
        selected.configure(fg=COLOR_ACCENT)


# ── CommandPalette ───────────────────────────────────────


class CommandPalette(tk.Toplevel):
    """Ctrl+K で開くコマンド検索パレット。"""

    def __init__(
        self,
        parent: tk.Widget,
        commands: Dict[str, str],
        callback: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=COLOR_PANEL)

        self._commands = commands
        self._callback = callback
        self._filtered: List[str] = list(commands.keys())

        # 親ウィンドウの中央に配置
        self.update_idletasks()
        pw = parent.winfo_width() if parent.winfo_width() > 1 else 400
        ph = parent.winfo_height() if parent.winfo_height() > 1 else 560
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w, h = 340, 320
        x = px + (pw - w) // 2
        y = py + (ph - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")

        # 検索入力
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_filter)
        entry = tk.Entry(
            self,
            textvariable=self._search_var,
            bg=COLOR_PANEL,
            fg=COLOR_TEXT,
            insertbackground=COLOR_ACCENT,
            font=("Hiragino Sans", 13),
            relief="flat",
        )
        entry.pack(fill="x", padx=8, pady=(8, 4), ipady=6)
        entry.focus_set()
        entry.bind("<Escape>", lambda e: self.destroy())
        entry.bind("<Return>", self._on_select)
        entry.bind("<Up>", self._on_key_up)
        entry.bind("<Down>", self._on_key_down)

        # コマンドリスト
        self._listbox = tk.Listbox(
            self,
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            selectbackground=COLOR_ACCENT,
            selectforeground=COLOR_BG,
            font=("Hiragino Sans", 12),
            relief="flat",
            highlightthickness=0,
        )
        self._listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._listbox.bind("<Double-Button-1>", self._on_select)
        self._refresh_list()

        self.bind("<FocusOut>", lambda e: self.destroy())

    def _on_filter(self, *_args: object) -> None:
        query = self._search_var.get().lower()
        self._filtered = [
            k for k in self._commands if query in k.lower() or query in self._commands[k].lower()
        ]
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._listbox.delete(0, "end")
        for key in self._filtered:
            desc = self._commands[key]
            self._listbox.insert("end", f"{key}  - {desc}")
        if self._filtered:
            self._listbox.selection_set(0)

    def _on_select(self, event: Optional[tk.Event] = None) -> None:
        sel = self._listbox.curselection()
        if sel and self._filtered:
            cmd_key = self._filtered[sel[0]]
            self.destroy()
            self._callback(cmd_key)

    def _on_key_up(self, event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if sel and sel[0] > 0:
            self._listbox.selection_clear(sel[0])
            self._listbox.selection_set(sel[0] - 1)
            self._listbox.see(sel[0] - 1)

    def _on_key_down(self, event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if sel and sel[0] < self._listbox.size() - 1:
            self._listbox.selection_clear(sel[0])
            self._listbox.selection_set(sel[0] + 1)
            self._listbox.see(sel[0] + 1)


# ── KeyboardShortcuts ────────────────────────────────────


class KeyboardShortcuts:
    """キーボードショートカットの登録と表示。"""

    SHORTCUTS: Dict[str, str] = {
        "<Control-Return>": "送信",
        "<Control-m>": "マイク切替",
        "<Control-e>": "感情表示",
        "<Control-k>": "コマンドパレット",
        "<Control-plus>": "フォント拡大",
        "<Control-minus>": "フォント縮小",
        "<Escape>": "閉じる",
    }

    @classmethod
    def bind_all(
        cls,
        root: tk.Tk,
        handlers: Dict[str, Callable[..., None]],
    ) -> None:
        """ショートカットを一括バインドする。

        *handlers* のキーは SHORTCUTS のキーと同じイベント文字列。
        """
        for seq, handler in handlers.items():
            if seq in cls.SHORTCUTS:
                try:
                    root.bind(seq, handler)
                except tk.TclError as exc:
                    logger.warning("ショートカットバインド失敗 %s: %s", seq, exc)

    @classmethod
    def show_help(cls, parent: tk.Widget) -> None:
        """ショートカット一覧をポップアップで表示する。"""
        win = tk.Toplevel(parent)
        win.title("キーボードショートカット")
        win.configure(bg=COLOR_PANEL)
        win.attributes("-topmost", True)
        win.geometry("300x280")

        tk.Label(
            win,
            text="ショートカット一覧",
            bg=COLOR_PANEL,
            fg=COLOR_ACCENT,
            font=("Hiragino Sans", 14, "bold"),
        ).pack(pady=(12, 8))

        for seq, desc in cls.SHORTCUTS.items():
            key_display = seq.replace("<", "").replace(">", "").replace("-", "+")
            row = tk.Frame(win, bg=COLOR_PANEL)
            row.pack(fill="x", padx=16, pady=2)
            tk.Label(
                row, text=key_display, bg=COLOR_BG, fg=COLOR_TEXT,
                font=("Menlo", 11), padx=6, pady=2,
            ).pack(side="left")
            tk.Label(
                row, text=desc, bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                font=("Hiragino Sans", 11),
            ).pack(side="left", padx=(8, 0))

        tk.Button(
            win, text="閉じる", command=win.destroy,
            bg=COLOR_ACCENT, fg=COLOR_BG, relief="flat",
            font=("Hiragino Sans", 12),
        ).pack(pady=12)

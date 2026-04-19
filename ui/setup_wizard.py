"""
初回セットアップウィザード

Tkinter ベースの 4 ステップウィザードで初期設定を行います。
ステップ: 名前入力 → 音声選択 → 趣味登録 → テスト挨拶
"""
from __future__ import annotations

import logging
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── 初回判定 ─────────────────────────────────────────────────

MEMORIES_DB_PATH: Path = Path("data/memories.db")


def is_first_run() -> bool:
    """初回起動かどうかを判定する"""
    return not MEMORIES_DB_PATH.exists()


# ─── 音声オプション ───────────────────────────────────────────

VOICE_OPTIONS: Dict[str, str] = {
    "Kyoko（女性・日本語）": "Kyoko",
    "Otoya（男性・日本語）": "Otoya",
}


# ─── ウィザードUI ─────────────────────────────────────────────


class SetupWizard:
    """初回セットアップウィザード"""

    STEP_COUNT: int = 4

    def __init__(self) -> None:
        self._result: Dict[str, Any] = {
            "user_name": "",
            "voice": "Kyoko",
            "hobbies": [],
            "completed": False,
        }
        self._current_step: int = 0
        self._root: Optional[tk.Tk] = None
        self._content_frame: Optional[ttk.Frame] = None

    def run(self) -> Dict[str, Any]:
        """ウィザードを実行し設定辞書を返す

        Returns:
            設定辞書（user_name, voice, hobbies, completed）
        """
        self._root = tk.Tk()
        self._root.title("アイちゃん セットアップ")
        self._root.geometry("500x400")
        self._root.resizable(False, False)

        self._build_ui()
        self._show_step(0)

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

        return dict(self._result)

    def _build_ui(self) -> None:
        """ウィザード共通UI構造を構築する"""
        assert self._root is not None

        header = ttk.Label(
            self._root,
            text="アイちゃん 初回セットアップ",
            font=("Helvetica", 16, "bold"),
        )
        header.pack(pady=(20, 10))

        self._step_label = ttk.Label(self._root, text="")
        self._step_label.pack()

        self._content_frame = ttk.Frame(self._root)
        self._content_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=10)

        btn_frame = ttk.Frame(self._root)
        btn_frame.pack(pady=(0, 20))

        self._back_btn = ttk.Button(
            btn_frame, text="戻る", command=self._prev_step
        )
        self._back_btn.pack(side=tk.LEFT, padx=5)

        self._next_btn = ttk.Button(
            btn_frame, text="次へ", command=self._next_step
        )
        self._next_btn.pack(side=tk.LEFT, padx=5)

    def _show_step(self, step: int) -> None:
        """指定ステップの画面を表示する"""
        self._current_step = step
        assert self._content_frame is not None

        for widget in self._content_frame.winfo_children():
            widget.destroy()

        self._step_label.config(
            text=f"ステップ {step + 1} / {self.STEP_COUNT}"
        )
        self._back_btn.config(state=tk.NORMAL if step > 0 else tk.DISABLED)
        self._next_btn.config(
            text="完了" if step == self.STEP_COUNT - 1 else "次へ"
        )

        builders = [
            self._build_name_step,
            self._build_voice_step,
            self._build_hobby_step,
            self._build_test_step,
        ]
        builders[step]()

    def _build_name_step(self) -> None:
        """ステップ1: 名前入力"""
        assert self._content_frame is not None

        ttk.Label(
            self._content_frame,
            text="あなたの名前を教えてください",
            font=("Helvetica", 12),
        ).pack(pady=(20, 10))

        self._name_var = tk.StringVar(value=self._result.get("user_name", ""))
        entry = ttk.Entry(
            self._content_frame,
            textvariable=self._name_var,
            font=("Helvetica", 14),
            width=25,
        )
        entry.pack(pady=5)
        entry.focus_set()

    def _build_voice_step(self) -> None:
        """ステップ2: 音声選択"""
        assert self._content_frame is not None

        ttk.Label(
            self._content_frame,
            text="アイの声を選んでください",
            font=("Helvetica", 12),
        ).pack(pady=(20, 10))

        self._voice_var = tk.StringVar()
        current_voice: str = self._result.get("voice", "Kyoko")
        for label, value in VOICE_OPTIONS.items():
            if value == current_voice:
                self._voice_var.set(label)
                break

        for label in VOICE_OPTIONS:
            ttk.Radiobutton(
                self._content_frame,
                text=label,
                variable=self._voice_var,
                value=label,
            ).pack(anchor=tk.W, pady=2, padx=20)

    def _build_hobby_step(self) -> None:
        """ステップ3: 趣味登録"""
        assert self._content_frame is not None

        ttk.Label(
            self._content_frame,
            text="趣味を入力してください（カンマ区切り）",
            font=("Helvetica", 12),
        ).pack(pady=(20, 10))

        existing: List[str] = self._result.get("hobbies", [])
        self._hobby_var = tk.StringVar(value=", ".join(existing))
        entry = ttk.Entry(
            self._content_frame,
            textvariable=self._hobby_var,
            font=("Helvetica", 12),
            width=35,
        )
        entry.pack(pady=5)

        ttk.Label(
            self._content_frame,
            text="例: プログラミング, 読書, ゲーム",
            foreground="gray",
        ).pack()

    def _build_test_step(self) -> None:
        """ステップ4: テスト挨拶"""
        assert self._content_frame is not None

        name: str = self._result.get("user_name", "")
        display_name: str = name if name else "あなた"

        ttk.Label(
            self._content_frame,
            text=f"こんにちは、{display_name}さん！",
            font=("Helvetica", 14, "bold"),
        ).pack(pady=(20, 5))

        ttk.Label(
            self._content_frame,
            text="アイだよ！これからよろしくね！",
            font=("Helvetica", 12),
        ).pack(pady=5)

        test_btn = ttk.Button(
            self._content_frame,
            text="テスト音声を再生",
            command=lambda: self._test_voice(display_name),
        )
        test_btn.pack(pady=15)

        ttk.Label(
            self._content_frame,
            text="「完了」を押すとセットアップを終了します",
            foreground="gray",
        ).pack(pady=(10, 0))

    def _test_voice(self, name: str) -> None:
        """テスト音声を再生する"""
        voice: str = self._result.get("voice", "Kyoko")
        text: str = f"こんにちは、{name}さん！アイだよ！よろしくね！"
        try:
            subprocess.Popen(
                ["say", "-v", voice, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            logger.warning("say コマンドが使えません")

    def _next_step(self) -> None:
        """次のステップへ進む"""
        if not self._validate_current():
            return

        self._save_current()

        if self._current_step >= self.STEP_COUNT - 1:
            self._finish()
        else:
            self._show_step(self._current_step + 1)

    def _prev_step(self) -> None:
        """前のステップへ戻る"""
        self._save_current()
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _validate_current(self) -> bool:
        """現在のステップの入力をバリデーションする"""
        if self._current_step == 0:
            name: str = self._name_var.get().strip()
            if not name:
                messagebox.showwarning("入力エラー", "名前を入力してください")
                return False
        return True

    def _save_current(self) -> None:
        """現在のステップの入力を結果に保存する"""
        if self._current_step == 0:
            self._result["user_name"] = self._name_var.get().strip()
        elif self._current_step == 1:
            selected: str = self._voice_var.get()
            self._result["voice"] = VOICE_OPTIONS.get(selected, "Kyoko")
        elif self._current_step == 2:
            raw: str = self._hobby_var.get().strip()
            hobbies: List[str] = [
                h.strip() for h in raw.split(",") if h.strip()
            ]
            self._result["hobbies"] = hobbies

    def _finish(self) -> None:
        """ウィザードを完了する"""
        self._result["completed"] = True
        logger.info(
            "セットアップ完了: user=%s voice=%s hobbies=%s",
            self._result["user_name"],
            self._result["voice"],
            self._result["hobbies"],
        )
        if self._root is not None:
            self._root.destroy()

    def _on_close(self) -> None:
        """ウィンドウが閉じられた場合"""
        if messagebox.askyesno("確認", "セットアップを中断しますか？"):
            self._result["completed"] = False
            if self._root is not None:
                self._root.destroy()

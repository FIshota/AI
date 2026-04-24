"""
会話履歴検索ウィンドウ (Sprint 5.7 UX).

10年分の会話履歴から日付範囲 + キーワード + speaker で検索する GUI。
既存の settings_window / desktop_pet_a11y と同じトーンで、外部ライブラリ
は使わず stdlib + tkinter のみで構成しています。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

# tkinter は重いので import は関数内で遅延ロード。
# 型ヒントのために TYPE_CHECKING でのみ import する。
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import tkinter as tk

from core.conversation_search import (
    ConversationSearchIndex,
    SearchHit,
    SearchQuery,
)


# settings_window と揃えたパレット
COLOR_BG = "#FFFFFF"
COLOR_PANEL = "#F5F3F8"
COLOR_INPUT = "#FFFFFF"
COLOR_ACCENT = "#6C5CE7"
COLOR_ACCENT2 = "#A29BFE"
COLOR_TEXT = "#2D2D3F"
COLOR_SUBTEXT = "#8E8EA0"
COLOR_BORDER = "#E5E5EA"

LABEL_FONT = ("Hiragino Sans", 11)
HEADER_FONT = ("Hiragino Sans", 12, "bold")
SMALL_FONT = ("Hiragino Sans", 9)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(s: str) -> Optional[date]:
    if not s:
        return None
    if not _DATE_RE.match(s):
        raise ValueError(f"expected YYYY-MM-DD, got {s!r}")
    return datetime.strptime(s, "%Y-%m-%d").date()


@dataclass(frozen=True)
class ParsedKeywordInput:
    keywords: Tuple[str, ...]
    mode: str  # "AND" or "OR"


def parse_keyword_input(raw: str) -> ParsedKeywordInput:
    """Parse the keyword text box.

    - ``foo AND bar`` / ``foo OR bar`` (uppercase) switches the combinator.
    - Otherwise whitespace splits keywords and the default is AND.
    """
    if not raw:
        return ParsedKeywordInput(keywords=(), mode="AND")
    tokens = raw.split()
    mode = "AND"
    kept: List[str] = []
    for tok in tokens:
        if tok == "AND":
            mode = "AND"
        elif tok == "OR":
            mode = "OR"
        else:
            kept.append(tok)
    return ParsedKeywordInput(keywords=tuple(kept), mode=mode)


class SearchWindow:
    """Conversation history search Toplevel.

    The tkinter import is deferred until the window is actually shown so
    that headless test runs that import this module do not require a
    display.
    """

    def __init__(self, parent, index: ConversationSearchIndex) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self._ttk = ttk
        self.index = index

        self.win = tk.Toplevel(parent)
        self.win.title("🔎 会話履歴検索")
        self.win.configure(bg=COLOR_BG)
        self.win.geometry("720x560")
        self.win.resizable(True, True)

        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        tk = self._tk

        header = tk.Frame(self.win, bg=COLOR_BG)
        header.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(
            header, text="会話履歴検索", bg=COLOR_BG, fg=COLOR_TEXT,
            font=HEADER_FONT,
        ).pack(anchor="w")
        tk.Label(
            header,
            text="日付範囲とキーワードで過去の会話を探します。AND / OR で複合検索できます。",
            bg=COLOR_BG, fg=COLOR_SUBTEXT, font=SMALL_FONT,
        ).pack(anchor="w", pady=(2, 0))

        form = tk.Frame(self.win, bg=COLOR_PANEL)
        form.pack(fill="x", padx=16, pady=8)

        self.kw_var = tk.StringVar()
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.speaker_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")

        self._row(form, 0, "キーワード", self.kw_var, width=40,
                  hint="例: ペット OR 犬")
        self._row(form, 1, "開始日 (YYYY-MM-DD)", self.from_var, width=16,
                  hint="例: 2027-03-01")
        self._row(form, 2, "終了日 (YYYY-MM-DD)", self.to_var, width=16,
                  hint="例: 2027-03-31")
        self._row(form, 3, "話者", self.speaker_var, width=16,
                  hint="例: papa / ai / mama (空欄で全員)")

        btns = tk.Frame(form, bg=COLOR_PANEL)
        btns.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 4), padx=8)
        search_btn = tk.Button(
            btns, text="検索", command=self._on_search,
            bg=COLOR_ACCENT, fg="#FFFFFF", font=LABEL_FONT,
            relief="flat", padx=18, pady=4,
        )
        search_btn.pack(side="left")
        tk.Label(
            btns, textvariable=self.status_var,
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=SMALL_FONT,
        ).pack(side="left", padx=12)

        # Results list
        results = tk.Frame(self.win, bg=COLOR_BG)
        results.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self.listbox = tk.Listbox(
            results, bg=COLOR_INPUT, fg=COLOR_TEXT,
            selectbackground=COLOR_ACCENT, selectforeground="#FFFFFF",
            font=("Menlo", 10), activestyle="none",
            highlightbackground=COLOR_BORDER, highlightthickness=1, relief="flat",
        )
        self.listbox.pack(fill="both", expand=True, side="left")
        self.listbox.bind("<Double-Button-1>", self._on_open_detail)

        sb = tk.Scrollbar(results, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        self._hits: Tuple[SearchHit, ...] = ()

        # Enter key triggers search
        self.win.bind("<Return>", lambda _e: self._on_search())

    def _row(self, parent, r: int, label: str, var, width: int, hint: str) -> None:
        tk = self._tk
        tk.Label(parent, text=label, bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=LABEL_FONT).grid(row=r, column=0, sticky="w", padx=(8, 6), pady=4)
        entry = tk.Entry(
            parent, textvariable=var, width=width,
            bg=COLOR_INPUT, fg=COLOR_TEXT,
            insertbackground=COLOR_ACCENT, relief="flat",
            highlightbackground=COLOR_ACCENT2, highlightthickness=1,
            font=LABEL_FONT,
        )
        entry.grid(row=r, column=1, sticky="w", pady=4)
        tk.Label(parent, text=hint, bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                 font=SMALL_FONT).grid(row=r, column=2, sticky="w", padx=10)

    # ------------------------------------------------------------------ #
    def _on_search(self) -> None:
        from tkinter import messagebox
        parsed = parse_keyword_input(self.kw_var.get().strip())
        try:
            d_from = _validate_date(self.from_var.get().strip())
            d_to = _validate_date(self.to_var.get().strip())
        except ValueError as exc:
            messagebox.showerror("日付エラー", str(exc), parent=self.win)
            return
        speaker = self.speaker_var.get().strip() or None

        query = SearchQuery(
            keywords=parsed.keywords, mode=parsed.mode,
            date_from=d_from, date_to=d_to,
            speaker=speaker, limit=200,
        )
        try:
            hits = self.index.search(query)
        except Exception as exc:  # pragma: no cover - defensive UI
            messagebox.showerror("検索エラー", str(exc), parent=self.win)
            return

        self._hits = hits
        self.listbox.delete(0, "end")
        if not hits:
            self.status_var.set("ヒットなし")
            return
        self.status_var.set(f"{len(hits)} 件")
        for h in hits:
            snippet = h.text.replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "…"
            self.listbox.insert(
                "end",
                f"{h.timestamp.date().isoformat()}  [{h.speaker:<6}]  {snippet}",
            )

    def _on_open_detail(self, _event) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        h = self._hits[sel[0]]
        self._show_detail(h)

    def _show_detail(self, hit: SearchHit) -> None:
        tk = self._tk
        win = tk.Toplevel(self.win)
        win.title(f"詳細 — {hit.timestamp.isoformat()}")
        win.configure(bg=COLOR_BG)
        win.geometry("620x440")
        body = tk.Text(
            win, wrap="word", bg=COLOR_INPUT, fg=COLOR_TEXT,
            font=("Hiragino Sans", 11), relief="flat",
            highlightbackground=COLOR_BORDER, highlightthickness=1,
        )
        body.pack(fill="both", expand=True, padx=16, pady=12)

        body.insert("end", f"時刻  : {hit.timestamp.isoformat()}\n")
        body.insert("end", f"話者  : {hit.speaker}\n")
        body.insert("end", f"score : {hit.score:.3f}\n")
        body.insert("end", "\n── 前のコンテキスト ──\n")
        for c in hit.context_before:
            body.insert("end", f"  {c}\n")
        body.insert("end", "\n── 本文 ──\n")
        body.insert("end", hit.text + "\n")
        body.insert("end", "\n── 次のコンテキスト ──\n")
        for c in hit.context_after:
            body.insert("end", f"  {c}\n")
        body.configure(state="disabled")

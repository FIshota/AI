"""
成長記録ウィンドウ
感情グラフ・好み関心マップ・目標トラッキングを表示します
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

COLOR_BG      = "#2D1B3D"
COLOR_PANEL   = "#3D2255"
COLOR_INPUT   = "#1A0F2E"
COLOR_ACCENT  = "#E8A5C8"
COLOR_ACCENT2 = "#B57BDC"
COLOR_TEXT    = "#F5E6FF"
COLOR_SUBTEXT = "#C9A8E8"

LABEL_FONT = ("Hiragino Sans", 11)
SMALL_FONT = ("Hiragino Sans", 9)
HEADER_FONT = ("Hiragino Sans", 12, "bold")

# 感情ラインカラー
EMOTION_COLORS = {
    "happiness": "#F9D342",
    "affection":  "#E8A5C8",
    "curiosity":  "#7FD4F0",
    "energy":     "#98E88A",
    "anxiety":    "#FF8080",
}
EMOTION_LABELS = {
    "happiness": "幸福",
    "affection":  "愛情",
    "curiosity":  "好奇心",
    "energy":     "元気",
    "anxiety":    "不安",
}


class GraphWindow(tk.Toplevel):
    def __init__(self, parent, ai_chan_instance):
        super().__init__(parent)
        self.ai_chan = ai_chan_instance
        self.title("成長記録")
        self.configure(bg=COLOR_BG)
        self.geometry("620x560")
        self.resizable(True, True)
        self.attributes("-topmost", True)
        self._build_ui()

    def _build_ui(self):
        tk.Label(self, text="成長記録", bg=COLOR_BG, fg=COLOR_ACCENT,
                 font=("Hiragino Sans", 14, "bold")).pack(pady=(12, 4))

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("TNotebook",     background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_PANEL,
                        foreground=COLOR_SUBTEXT, padding=[12, 6],
                        font=("Hiragino Sans", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", COLOR_ACCENT)],
                  foreground=[("selected", COLOR_BG)])
        style.configure("TFrame", background=COLOR_PANEL)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._tab_emotion  = tk.Frame(nb, bg=COLOR_PANEL)
        self._tab_interest = tk.Frame(nb, bg=COLOR_PANEL)
        self._tab_goals    = tk.Frame(nb, bg=COLOR_PANEL)

        nb.add(self._tab_emotion,  text="感情グラフ")
        nb.add(self._tab_interest, text="関心マップ")
        nb.add(self._tab_goals,    text="目標")

        self._build_emotion_tab()
        self._build_interest_tab()
        self._build_goals_tab()

    # ─── 感情グラフタブ ─────────────────────────────────────────

    def _build_emotion_tab(self):
        f = self._tab_emotion
        try:
            history = self.ai_chan.emotion_history
            daily = history.get_daily_averages(days=14)
        except AttributeError:
            tk.Label(f, text="感情データがまだありません",
                     bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                     font=LABEL_FONT).pack(pady=40)
            return

        if not daily:
            tk.Label(f, text="まだ会話が少ないよ。話しかけると記録されていくね！",
                     bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                     font=LABEL_FONT, wraplength=480).pack(pady=40)
            return

        # 凡例
        legend_frame = tk.Frame(f, bg=COLOR_PANEL)
        legend_frame.pack(fill="x", padx=12, pady=(8, 2))
        for key, color in EMOTION_COLORS.items():
            tk.Label(legend_frame, text=f"■ {EMOTION_LABELS[key]}",
                     bg=COLOR_PANEL, fg=color,
                     font=SMALL_FONT).pack(side="left", padx=6)

        # キャンバスグラフ
        canvas = tk.Canvas(f, bg=COLOR_INPUT, highlightthickness=0,
                           height=280)
        canvas.pack(fill="x", padx=12, pady=(0, 8))
        # デバウンス付きリサイズハンドラ（連続発火を抑制）
        self._emotion_resize_id: str | None = None
        def _on_resize(e):
            if self._emotion_resize_id is not None:
                try:
                    self.after_cancel(self._emotion_resize_id)
                except Exception:
                    pass
            self._emotion_resize_id = self.after(
                80, lambda: self._draw_emotion_graph(canvas, daily)
            )
        canvas.bind("<Configure>", _on_resize)
        self.after(100, lambda: self._draw_emotion_graph(canvas, daily))

        # 最新の感情値テキスト
        if daily:
            last = daily[-1]
            lines = [f"{EMOTION_LABELS[k]}: {last[k]:.0%}"
                     for k in EMOTION_COLORS if k in last]
            info = tk.Label(f, text="最新  " + "  ".join(lines),
                            bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                            font=SMALL_FONT)
            info.pack(pady=(0, 4))

    def _draw_emotion_graph(self, canvas: tk.Canvas, daily: list):
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 10 or h < 10 or not daily:
            return

        pad_l, pad_r, pad_t, pad_b = 40, 20, 16, 36
        graph_w = w - pad_l - pad_r
        graph_h = h - pad_t - pad_b
        n = len(daily)

        # グリッド線（0.25刻み）
        for ratio in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = pad_t + graph_h * (1 - ratio)
            canvas.create_line(pad_l, y, w - pad_r, y,
                               fill="#4A2870", width=1)
            canvas.create_text(pad_l - 4, y, text=f"{ratio:.0%}",
                               anchor="e", fill=COLOR_SUBTEXT,
                               font=("Helvetica", 8))

        # 日付ラベル（最大5つ）
        step = max(1, n // 5)
        for i in range(0, n, step):
            x = pad_l + (i / max(n - 1, 1)) * graph_w
            canvas.create_text(x, h - pad_b + 6,
                               text=daily[i]["date"][5:],
                               fill=COLOR_SUBTEXT,
                               font=("Helvetica", 8))

        # 各感情ライン
        for key, color in EMOTION_COLORS.items():
            points = []
            for i, d in enumerate(daily):
                x = pad_l + (i / max(n - 1, 1)) * graph_w
                y = pad_t + graph_h * (1 - d.get(key, 0.5))
                points.extend([x, y])
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2,
                                   smooth=True)

    # ─── 関心マップタブ ──────────────────────────────────────────

    def _build_interest_tab(self):
        f = self._tab_interest
        try:
            interest_map = self.ai_chan.interest_map
            by_cat = interest_map.get_by_category()
        except AttributeError:
            tk.Label(f, text="関心データがまだありません",
                     bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                     font=LABEL_FONT).pack(pady=40)
            return

        if not by_cat:
            tk.Label(f, text="まだ会話が少ないよ。話しかけると関心マップが育っていくね！",
                     bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                     font=LABEL_FONT, wraplength=480).pack(pady=40)
            return

        # スクロール可能リスト
        outer = tk.Frame(f, bg=COLOR_PANEL)
        outer.pack(fill="both", expand=True, padx=12, pady=8)

        canvas = tk.Canvas(outer, bg=COLOR_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=COLOR_PANEL)
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(
                       scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(cw, width=e.width))

        max_count = max(
            (item["count"]
             for items in by_cat.values()
             for item in items),
            default=1
        )

        for cat, items in sorted(by_cat.items()):
            tk.Label(inner, text=cat, bg=COLOR_PANEL, fg=COLOR_ACCENT,
                     font=HEADER_FONT).pack(anchor="w", pady=(10, 2), padx=8)
            for item in items[:8]:
                row = tk.Frame(inner, bg=COLOR_PANEL)
                row.pack(fill="x", padx=16, pady=1)
                tk.Label(row, text=item["keyword"],
                         bg=COLOR_PANEL, fg=COLOR_TEXT,
                         font=LABEL_FONT, width=12,
                         anchor="w").pack(side="left")
                # バー
                bar_frame = tk.Frame(row, bg=COLOR_INPUT, height=14)
                bar_frame.pack(side="left", fill="x", expand=True,
                               padx=(4, 8))
                bar_w = max(4, int((item["count"] / max_count) * 200))
                tk.Frame(bar_frame, bg=COLOR_ACCENT2,
                         width=bar_w, height=14).place(x=0, y=0)
                tk.Label(row, text=f"{item['count']}回",
                         bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                         font=SMALL_FONT, width=5).pack(side="left")

    # ─── 目標タブ ────────────────────────────────────────────────

    def _build_goals_tab(self):
        f = self._tab_goals
        try:
            goal_tracker = self.ai_chan.goal_tracker
        except AttributeError:
            tk.Label(f, text="目標データがまだありません",
                     bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                     font=LABEL_FONT).pack(pady=40)
            return

        # ヘッダー
        hdr = tk.Frame(f, bg=COLOR_PANEL)
        hdr.pack(fill="x", padx=12, pady=(8, 4))
        stats = goal_tracker.stats()
        tk.Label(hdr,
                 text=f"目標  進行中: {stats['active']}個  達成: {stats['done']}個",
                 bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                 font=SMALL_FONT).pack(side="left")
        tk.Button(hdr, text="更新",
                  bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                  font=SMALL_FONT, relief="flat",
                  command=self._refresh_goals).pack(side="right")

        # リストボックス
        lb_frame = tk.Frame(f, bg=COLOR_INPUT)
        lb_frame.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        self._goals_lb = tk.Listbox(
            lb_frame, bg=COLOR_INPUT, fg=COLOR_TEXT,
            selectbackground=COLOR_ACCENT, selectforeground=COLOR_BG,
            font=("Hiragino Sans", 11), relief="flat"
        )
        sb2 = ttk.Scrollbar(lb_frame, command=self._goals_lb.yview)
        self._goals_lb.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self._goals_lb.pack(fill="both", expand=True, padx=2, pady=2)

        # 手動追加フォーム
        add_frame = tk.Frame(f, bg=COLOR_PANEL)
        add_frame.pack(fill="x", padx=12, pady=(4, 4))
        self._goal_var = tk.StringVar()
        tk.Entry(add_frame, textvariable=self._goal_var,
                 bg=COLOR_INPUT, fg=COLOR_TEXT,
                 insertbackground=COLOR_ACCENT, relief="flat",
                 font=LABEL_FONT
                 ).pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(add_frame, text="追加",
                  bg=COLOR_ACCENT, fg=COLOR_BG,
                  font=LABEL_FONT, relief="flat",
                  command=self._add_goal, padx=8
                  ).pack(side="left", padx=(6, 0))

        # 操作ボタン
        btn_frame = tk.Frame(f, bg=COLOR_PANEL)
        btn_frame.pack(fill="x", padx=12, pady=(0, 8))
        tk.Button(btn_frame, text="達成済みにする",
                  bg=COLOR_ACCENT2, fg=COLOR_BG,
                  font=SMALL_FONT, relief="flat",
                  command=self._complete_goal, padx=8, pady=4
                  ).pack(side="left", padx=(0, 6))
        tk.Button(btn_frame, text="削除",
                  bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                  font=SMALL_FONT, relief="flat",
                  command=self._delete_goal, padx=8, pady=4
                  ).pack(side="left")

        self._refresh_goals()

    def _refresh_goals(self):
        if not hasattr(self, "_goals_lb"):
            return
        self._goals_lb.delete(0, "end")
        try:
            goals = self.ai_chan.goal_tracker.list_goals()
            for g in goals:
                prefix = "✓ " if g["status"] == "done" else "○ "
                self._goals_lb.insert(
                    "end",
                    f"{prefix}[{g['created_at'][:10]}] {g['text']}"
                )
        except Exception:
            pass

    def _add_goal(self):
        text = self._goal_var.get().strip()
        if not text:
            return
        try:
            self.ai_chan.goal_tracker.add_manual(text)
            self._goal_var.set("")
            self._refresh_goals()
        except Exception as e:
            messagebox.showerror("エラー", str(e), parent=self)

    def _complete_goal(self):
        sel = self._goals_lb.curselection()
        if not sel:
            return
        try:
            goals = self.ai_chan.goal_tracker.list_goals()
            idx = sel[0]
            if idx < len(goals):
                self.ai_chan.goal_tracker.complete_goal(goals[idx]["id"])
                self._refresh_goals()
        except Exception:
            pass

    def _delete_goal(self):
        sel = self._goals_lb.curselection()
        if not sel:
            return
        try:
            goals = self.ai_chan.goal_tracker.list_goals()
            idx = sel[0]
            if idx < len(goals):
                self.ai_chan.goal_tracker.delete_goal(goals[idx]["id"])
                self._refresh_goals()
        except Exception:
            pass

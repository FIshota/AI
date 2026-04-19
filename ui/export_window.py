"""
会話ログエクスポートウィンドウ
記憶DBから会話履歴を取り出してファイルに保存します。
"""
from __future__ import annotations
import json
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

COLOR_BG      = "#FFFFFF"
COLOR_PANEL   = "#F5F3F8"
COLOR_INPUT   = "#FFFFFF"
COLOR_ACCENT  = "#6C5CE7"
COLOR_ACCENT2 = "#A29BFE"
COLOR_TEXT    = "#2D2D3F"
COLOR_SUBTEXT = "#8E8EA0"
COLOR_BORDER  = "#E5E5EA"


def _parse_exchange(content: str) -> Optional[dict]:
    """記憶コンテンツから会話ペアを抽出"""
    # タイムスタンプ抽出
    ts_m = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]', content)
    ts = ts_m.group(1) if ts_m else ""
    # ユーザー・AIの発言を抽出
    m = re.search(
        r'ユーザー[：:][「"](.+?)[」"]\s*[→→]\s*アイ[：:][「"](.+?)[」"]',
        content, re.DOTALL
    )
    if m:
        return {"timestamp": ts, "user": m.group(1).strip(),
                "ai": m.group(2).strip()}
    return None


class ExportWindow(tk.Toplevel):
    def __init__(self, parent, memory_manager, base_dir: Path):
        super().__init__(parent)
        self.memory  = memory_manager
        self.base_dir = Path(base_dir)

        self.title("📋 会話ログのエクスポート")
        self.configure(bg=COLOR_BG)
        self.geometry("480x400")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._build_ui()

    def _build_ui(self):
        # タイトル
        tk.Label(self, text="📋 会話ログのエクスポート",
                 bg=COLOR_BG, fg=COLOR_ACCENT,
                 font=("Hiragino Sans", 14, "bold")).pack(pady=(16, 8))

        # フォーム
        form = tk.Frame(self, bg=COLOR_PANEL, padx=20, pady=16)
        form.pack(fill="x", padx=16)

        # 期間選択
        tk.Label(form, text="期間:", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Hiragino Sans", 11)).grid(row=0, column=0, sticky="w", pady=4)
        period_frame = tk.Frame(form, bg=COLOR_PANEL)
        period_frame.grid(row=0, column=1, sticky="w")

        self.period_var = tk.StringVar(value="all")
        for val, label in [("week", "直近1週間"), ("month", "直近1ヶ月"),
                           ("all", "全て")]:
            tk.Radiobutton(
                period_frame, text=label, variable=self.period_var, value=val,
                bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                activebackground=COLOR_PANEL,
                font=("Hiragino Sans", 10)
            ).pack(side="left", padx=4)

        # フォーマット選択
        tk.Label(form, text="形式:", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Hiragino Sans", 11)).grid(row=1, column=0, sticky="w", pady=4)
        fmt_frame = tk.Frame(form, bg=COLOR_PANEL)
        fmt_frame.grid(row=1, column=1, sticky="w")

        self.fmt_var = tk.StringVar(value="txt")
        for val, label in [("txt", "テキスト (.txt)"), ("md", "Markdown (.md)"),
                           ("json", "JSON (.json)")]:
            tk.Radiobutton(
                fmt_frame, text=label, variable=self.fmt_var, value=val,
                bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                activebackground=COLOR_PANEL,
                font=("Hiragino Sans", 10)
            ).pack(side="left", padx=4)

        # プレビュー
        tk.Label(self, text="プレビュー:", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=("Hiragino Sans", 10)).pack(anchor="w", padx=20, pady=(12, 2))

        preview_frame = tk.Frame(self, bg=COLOR_INPUT)
        preview_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.preview_text = tk.Text(
            preview_frame, bg=COLOR_INPUT, fg=COLOR_TEXT,
            font=("Hiragino Mincho ProN", 10),
            relief="flat", wrap="word", state="disabled",
            height=8
        )
        sb = ttk.Scrollbar(preview_frame, command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.preview_text.pack(fill="both", expand=True, padx=4, pady=4)

        # ボタン
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(pady=(0, 16))

        tk.Button(btn_frame, text="プレビュー更新",
                  bg=COLOR_PANEL, fg=COLOR_TEXT,
                  font=("Hiragino Sans", 11), relief="flat",
                  command=self._update_preview, padx=12, pady=6
                  ).pack(side="left", padx=8)

        tk.Button(btn_frame, text="💾 エクスポート",
                  bg=COLOR_ACCENT, fg=COLOR_BG,
                  font=("Hiragino Sans", 11, "bold"), relief="flat",
                  command=self._do_export, padx=12, pady=6
                  ).pack(side="left", padx=8)

        self._update_preview()

    def _get_exchanges(self) -> list[dict]:
        """期間でフィルタした会話ペアリスト"""
        period = self.period_var.get()
        mems = self.memory.get_recent(limit=2000, memory_type="mid")

        if period == "week":
            cutoff = (date.today() - timedelta(days=7)).isoformat()
        elif period == "month":
            cutoff = (date.today() - timedelta(days=30)).isoformat()
        else:
            cutoff = ""

        exchanges = []
        for m in mems:
            if cutoff and m.created_at < cutoff:
                continue
            if "conversation" not in m.tags:
                continue
            parsed = _parse_exchange(m.content)
            if parsed:
                exchanges.append(parsed)
        return list(reversed(exchanges))  # 古い順に

    def _format_exchanges(self, exchanges: list[dict]) -> str:
        fmt = self.fmt_var.get()
        if fmt == "json":
            return json.dumps(exchanges, ensure_ascii=False, indent=2)
        elif fmt == "md":
            lines = ["# アイ 会話ログ\n"]
            cur_date = ""
            for ex in exchanges:
                d = ex["timestamp"][:10] if ex["timestamp"] else ""
                if d and d != cur_date:
                    lines.append(f"\n## {d}\n")
                    cur_date = d
                lines.append(f"**あなた:** {ex['user']}")
                lines.append(f"**アイ:** {ex['ai']}\n")
            return "\n".join(lines)
        else:  # txt
            lines = ["アイ 会話ログ", "=" * 40, ""]
            for ex in exchanges:
                if ex["timestamp"]:
                    lines.append(f"[{ex['timestamp']}]")
                lines.append(f"あなた: {ex['user']}")
                lines.append(f"アイ: {ex['ai']}")
                lines.append("")
            return "\n".join(lines)

    def _update_preview(self):
        exchanges = self._get_exchanges()
        text = self._format_exchanges(exchanges[:10])  # プレビューは最初の10件
        if len(exchanges) > 10:
            text += f"\n... （他 {len(exchanges)-10} 件）"
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text or "（会話記録がありません）")
        self.preview_text.configure(state="disabled")

    def _do_export(self):
        fmt = self.fmt_var.get()
        ext_map = {"txt": ".txt", "md": ".md", "json": ".json"}
        ext = ext_map.get(fmt, ".txt")

        default_name = f"aichan_log_{date.today().isoformat()}{ext}"
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=ext,
            initialfile=default_name,
            filetypes=[("All files", "*.*")],
            title="会話ログの保存先を選択"
        )
        if not path:
            return

        exchanges = self._get_exchanges()
        content = self._format_exchanges(exchanges)
        try:
            Path(path).write_text(content, encoding="utf-8")
            messagebox.showinfo(
                "保存完了",
                f"{len(exchanges)}件の会話を保存したよ！\n{path}",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("エラー", str(e), parent=self)

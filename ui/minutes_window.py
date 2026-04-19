"""
議事録アプリ ウィンドウ
スタンドアローン動作。アイとの連携で学習も可能。
"""
from __future__ import annotations
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# ─── カラーパレット（Clean × Soft） ─────────────────────────────
COLOR_BG      = "#FFFFFF"
COLOR_PANEL   = "#F5F3F8"
COLOR_CARD    = "#EDE9FE"
COLOR_INPUT   = "#FFFFFF"
COLOR_ACCENT  = "#6C5CE7"
COLOR_ACCENT2 = "#A29BFE"
COLOR_GREEN   = "#34C759"
COLOR_RED     = "#FF3B30"
COLOR_TEXT    = "#2D2D3F"
COLOR_SUBTEXT = "#8E8EA0"
COLOR_LINE    = "#E5E5EA"

FONT_H1    = ("Hiragino Sans", 14, "bold")
FONT_H2    = ("Hiragino Sans", 12, "bold")
FONT_BODY  = ("Hiragino Sans", 11)
FONT_SMALL = ("Hiragino Sans", 9)
FONT_MONO  = ("Monaco", 10)


class MinutesWindow(tk.Toplevel):
    """議事録アプリ メインウィンドウ"""

    def __init__(self, parent, ai_chan_instance=None):
        super().__init__(parent)
        self.ai_chan = ai_chan_instance
        self.title("議事録アプリ")
        self.configure(bg=COLOR_BG)
        self.geometry("780x640")
        self.resizable(True, True)
        self.attributes("-topmost", False)

        # エンジン初期化
        from core.minutes_engine import MinutesEngine
        data_dir = BASE_DIR / "data"
        self.engine = MinutesEngine(data_dir)
        self.engine.set_status_callback(self._on_status)

        # 構造化抽出エンジン
        from core.minutes_extractor import MinutesExtractor
        self.extractor = MinutesExtractor()
        self._structured: dict | None = None  # 最後に抽出した構造データ

        # 連携コネクタを設定から初期化
        self._init_connectors()

        # 録音状態
        self._recording     = False
        self._current_wav   = None
        self._current_entry = None
        self._rec_lock      = threading.Lock()
        self._after_ids: set[str] = set()  # after() id 追跡

        self._build_ui()

        # 閉じるときのクリーンアップ
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Whisperをバックグラウンドでウォームアップ（録音停止時に即時応答するため）
        cfg = self._load_settings()
        model = cfg.get("minutes", {}).get("whisper_model", "small")
        self.engine.load_whisper_async(model_size=model)
        # ウォームアップ完了を監視してステータス更新
        self._poll_whisper_ready()

    def _safe_after(self, ms: int, fn, *args) -> str | None:
        """winfo_exists を検証してから after を呼ぶ"""
        try:
            if not self.winfo_exists():
                return None
            aid = self.after(ms, fn, *args)
            self._after_ids.add(aid)
            return aid
        except tk.TclError:
            return None

    def _on_close(self):
        self._recording = False
        # 全ての after をキャンセル
        for aid in list(self._after_ids):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _load_settings(self) -> dict:
        p = BASE_DIR / "config" / "settings.json"
        try:
            import json
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return {}

    def _init_connectors(self):
        """settings.json から連携設定を読み込んでコネクタを初期化"""
        cfg  = self._load_settings()
        intg = cfg.get("integrations", {})

        from core.notion_connector import NotionConnector
        nc = intg.get("notion", {})
        self.notion = NotionConnector(
            api_key=nc.get("api_key", ""),
            database_id=nc.get("minutes_database_id", ""),
        )
        self._notion_todo_db = nc.get("todo_database_id", "")

        from core.gcal_connector import GCalConnector
        gc = intg.get("google_calendar", {})
        self.gcal = GCalConnector(
            credentials_file=gc.get("credentials_file", ""),
            calendar_id=gc.get("calendar_id", "primary"),
        )

    # ─── UI 構築 ─────────────────────────────────────────────────

    def _build_ui(self):
        # ─ タイトルバー ─
        title_bar = tk.Frame(self, bg=COLOR_PANEL)
        title_bar.pack(fill="x")
        tk.Label(title_bar, text="📋  議事録アプリ",
                 bg=COLOR_PANEL, fg=COLOR_ACCENT,
                 font=FONT_H1).pack(side="left", padx=16, pady=10)
        self._status_lbl = tk.Label(
            title_bar, text="準備中…",
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=FONT_SMALL
        )
        self._status_lbl.pack(side="right", padx=16)

        # ─ タブ ─
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Min.TNotebook",     background=COLOR_BG, borderwidth=0)
        style.configure("Min.TNotebook.Tab", background=COLOR_CARD,
                        foreground=COLOR_SUBTEXT, padding=[14, 6],
                        font=("Hiragino Sans", 10))
        style.map("Min.TNotebook.Tab",
                  background=[("selected", COLOR_ACCENT)],
                  foreground=[("selected", COLOR_BG)])
        style.configure("Min.TFrame", background=COLOR_PANEL)

        nb = ttk.Notebook(self, style="Min.TNotebook")
        nb.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        self._tab_record  = tk.Frame(nb, bg=COLOR_PANEL)
        self._tab_history = tk.Frame(nb, bg=COLOR_PANEL)
        self._tab_connect = tk.Frame(nb, bg=COLOR_PANEL)
        nb.add(self._tab_record,  text="  録音・作成  ")
        nb.add(self._tab_history, text="  履歴  ")
        nb.add(self._tab_connect, text="  連携設定  ")

        self._build_record_tab()
        self._build_connect_tab()
        self._build_history_tab()

    # ─── 録音・作成タブ ─────────────────────────────────────────

    def _build_record_tab(self):
        f = self._tab_record

        # ── メタ情報入力 ──
        meta_f = tk.Frame(f, bg=COLOR_PANEL)
        meta_f.pack(fill="x", padx=16, pady=(12, 6))

        tk.Label(meta_f, text="会議タイトル", bg=COLOR_PANEL,
                 fg=COLOR_SUBTEXT, font=FONT_SMALL).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        self._title_var = tk.StringVar()
        tk.Entry(meta_f, textvariable=self._title_var,
                 bg=COLOR_INPUT, fg=COLOR_TEXT,
                 insertbackground=COLOR_ACCENT, relief="flat",
                 font=FONT_BODY, width=36,
                 highlightbackground=COLOR_LINE, highlightthickness=1
                 ).grid(row=0, column=1, sticky="ew", pady=2)

        tk.Label(meta_f, text="参加者", bg=COLOR_PANEL,
                 fg=COLOR_SUBTEXT, font=FONT_SMALL).grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        self._attendees_var = tk.StringVar()
        tk.Entry(meta_f, textvariable=self._attendees_var,
                 bg=COLOR_INPUT, fg=COLOR_TEXT,
                 insertbackground=COLOR_ACCENT, relief="flat",
                 font=FONT_BODY, width=36,
                 highlightbackground=COLOR_LINE, highlightthickness=1
                 ).grid(row=1, column=1, sticky="ew", pady=2)
        tk.Label(meta_f, text="（カンマ区切り）",
                 bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=FONT_SMALL
                 ).grid(row=1, column=2, sticky="w", padx=4)
        meta_f.columnconfigure(1, weight=1)

        # ── 録音コントロール ──
        rec_f = tk.Frame(f, bg=COLOR_PANEL)
        rec_f.pack(pady=(8, 4))

        self._rec_btn = tk.Button(
            rec_f, text="⏺  録音開始",
            bg=COLOR_ACCENT, fg=COLOR_BG,
            font=FONT_H2, relief="flat",
            command=self._toggle_recording, padx=20, pady=10,
            cursor="hand2"
        )
        self._rec_btn.pack(side="left", padx=8)

        # マイク権限確認ボタン
        tk.Button(
            rec_f, text="🎤  マイク権限",
            bg=COLOR_CARD, fg=COLOR_SUBTEXT,
            font=FONT_SMALL, relief="flat",
            command=self._show_mic_permission_guide, padx=8, pady=4,
            cursor="hand2"
        ).pack(side="left", padx=4)

        self._rec_time_lbl = tk.Label(
            rec_f, text="00:00",
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=("Monaco", 22)
        )
        self._rec_time_lbl.pack(side="left", padx=16)

        # ファイル読み込みボタン
        tk.Button(
            rec_f, text="📂  音声ファイルを開く",
            bg=COLOR_CARD, fg=COLOR_TEXT,
            font=FONT_BODY, relief="flat",
            command=self._open_audio_file, padx=12, pady=10,
            cursor="hand2"
        ).pack(side="left", padx=8)

        # ── 文字起こし・整形ボタン ──
        action_f = tk.Frame(f, bg=COLOR_PANEL)
        action_f.pack(pady=4)

        self._transcribe_btn = tk.Button(
            action_f, text="📝  文字起こし",
            bg=COLOR_ACCENT2, fg=COLOR_BG,
            font=FONT_BODY, relief="flat",
            command=self._do_transcribe, padx=14, pady=7,
            state="disabled", cursor="hand2"
        )
        self._transcribe_btn.pack(side="left", padx=6)

        self._format_btn = tk.Button(
            action_f, text="✨  議事録を整形",
            bg=COLOR_ACCENT2, fg=COLOR_BG,
            font=FONT_BODY, relief="flat",
            command=self._do_format, padx=14, pady=7,
            state="disabled", cursor="hand2"
        )
        self._format_btn.pack(side="left", padx=6)

        self._save_btn = tk.Button(
            action_f, text="💾  保存",
            bg=COLOR_GREEN, fg=COLOR_BG,
            font=FONT_BODY, relief="flat",
            command=self._do_save, padx=14, pady=7,
            state="disabled", cursor="hand2"
        )
        self._save_btn.pack(side="left", padx=6)

        self._pdf_btn = tk.Button(
            action_f, text="📄  PDF出力",
            bg=COLOR_CARD, fg=COLOR_TEXT,
            font=FONT_BODY, relief="flat",
            command=self._do_export_pdf, padx=14, pady=7,
            state="disabled", cursor="hand2"
        )
        self._pdf_btn.pack(side="left", padx=6)

        # ── 連携エクスポートボタン行 ──
        export_f = tk.Frame(f, bg=COLOR_PANEL)
        export_f.pack(pady=(0, 4))

        self._extract_btn = tk.Button(
            export_f, text="🔍  アクション抽出",
            bg=COLOR_CARD, fg=COLOR_TEXT,
            font=FONT_SMALL, relief="flat",
            command=self._do_extract, padx=10, pady=5,
            state="disabled", cursor="hand2"
        )
        self._extract_btn.pack(side="left", padx=4)

        self._notion_btn = tk.Button(
            export_f, text="N  Notionへ送る",
            bg="#2F2F2F", fg=COLOR_TEXT,
            font=FONT_SMALL, relief="flat",
            command=self._do_push_notion, padx=10, pady=5,
            state="disabled", cursor="hand2"
        )
        self._notion_btn.pack(side="left", padx=4)

        self._gcal_btn = tk.Button(
            export_f, text="📅  カレンダーへ",
            bg="#1A73E8", fg=COLOR_TEXT,
            font=FONT_SMALL, relief="flat",
            command=self._do_push_gcal, padx=10, pady=5,
            state="disabled", cursor="hand2"
        )
        self._gcal_btn.pack(side="left", padx=4)

        # 抽出結果ラベル
        self._extract_lbl = tk.Label(
            f, text="",
            bg=COLOR_PANEL, fg=COLOR_GREEN,
            font=FONT_SMALL, wraplength=700, justify="left"
        )
        self._extract_lbl.pack(anchor="w", padx=16, pady=(0, 2))

        # ── テキストエリア（文字起こし / 議事録） ──
        text_nb = ttk.Notebook(f, style="Min.TNotebook")
        text_nb.pack(fill="both", expand=True, padx=16, pady=(6, 10))

        # 文字起こしタブ
        trans_f = tk.Frame(text_nb, bg=COLOR_INPUT)
        text_nb.add(trans_f, text=" 文字起こし ")
        self._transcript_text = _make_textbox(trans_f, COLOR_INPUT)
        self._transcript_text.pack(fill="both", expand=True, padx=2, pady=2)

        # 議事録タブ
        min_f = tk.Frame(text_nb, bg=COLOR_INPUT)
        text_nb.add(min_f, text=" 議事録 ")
        self._minutes_text = _make_textbox(min_f, COLOR_INPUT)
        self._minutes_text.pack(fill="both", expand=True, padx=2, pady=2)

    # ─── 履歴タブ ────────────────────────────────────────────────

    def _build_history_tab(self):
        f = self._tab_history

        # ── 上部: リスト ──
        top = tk.Frame(f, bg=COLOR_PANEL)
        top.pack(fill="both", expand=True, padx=12, pady=(10, 0))

        # リストヘッダー
        hdr = tk.Frame(top, bg=COLOR_CARD)
        hdr.pack(fill="x", pady=(0, 2))
        for text, w in [("日付", 10), ("時刻", 6), ("タイトル", 30), ("参加者", 16)]:
            tk.Label(hdr, text=text, bg=COLOR_CARD, fg=COLOR_ACCENT,
                     font=("Hiragino Sans", 10, "bold"),
                     width=w, anchor="w").pack(side="left", padx=4)

        # スクロール可能リスト
        list_outer = tk.Frame(top, bg=COLOR_INPUT)
        list_outer.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(list_outer)
        sb.pack(side="right", fill="y")
        self._hist_lb = tk.Listbox(
            list_outer, yscrollcommand=sb.set,
            bg=COLOR_INPUT, fg=COLOR_TEXT,
            selectbackground=COLOR_ACCENT2, selectforeground=COLOR_BG,
            font=FONT_BODY, relief="flat",
            activestyle="none", height=8
        )
        sb.config(command=self._hist_lb.yview)
        self._hist_lb.pack(fill="both", expand=True)
        self._hist_lb.bind("<<ListboxSelect>>", self._on_hist_select)
        self._hist_entries: list[dict] = []

        # ── 操作ボタン ──
        hist_btn_f = tk.Frame(f, bg=COLOR_PANEL)
        hist_btn_f.pack(fill="x", padx=12, pady=6)
        tk.Button(hist_btn_f, text="更新",
                  bg=COLOR_CARD, fg=COLOR_TEXT,
                  font=FONT_SMALL, relief="flat",
                  command=self._refresh_history, padx=8, pady=4
                  ).pack(side="left", padx=(0, 6))
        self._hist_pdf_btn = tk.Button(
            hist_btn_f, text="PDF出力",
            bg=COLOR_ACCENT, fg=COLOR_BG,
            font=FONT_SMALL, relief="flat",
            command=self._hist_export_pdf, padx=8, pady=4,
            state="disabled"
        )
        self._hist_pdf_btn.pack(side="left", padx=(0, 6))
        self._hist_learn_btn = tk.Button(
            hist_btn_f, text="アイに学習させる",
            bg=COLOR_ACCENT2, fg=COLOR_BG,
            font=FONT_SMALL, relief="flat",
            command=self._hist_learn, padx=8, pady=4,
            state="disabled"
        )
        self._hist_learn_btn.pack(side="left", padx=(0, 6))

        self._hist_notion_btn = tk.Button(
            hist_btn_f, text="N Notion",
            bg="#2F2F2F", fg=COLOR_TEXT,
            font=FONT_SMALL, relief="flat",
            command=self._hist_push_notion, padx=8, pady=4,
            state="disabled"
        )
        self._hist_notion_btn.pack(side="left", padx=(0, 4))

        self._hist_gcal_btn = tk.Button(
            hist_btn_f, text="📅 GCal",
            bg="#1A73E8", fg=COLOR_TEXT,
            font=FONT_SMALL, relief="flat",
            command=self._hist_push_gcal, padx=8, pady=4,
            state="disabled"
        )
        self._hist_gcal_btn.pack(side="left")

        # ── 下部: プレビュー ──
        tk.Label(f, text="選択した議事録のプレビュー",
                 bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL).pack(anchor="w", padx=14, pady=(4, 0))
        prev_f = tk.Frame(f, bg=COLOR_INPUT)
        prev_f.pack(fill="both", expand=True, padx=12, pady=(2, 10))
        self._preview_text = _make_textbox(prev_f, COLOR_INPUT, readonly=True)
        self._preview_text.pack(fill="both", expand=True, padx=2, pady=2)

        self._refresh_history()

    # ─── マイク権限ガイド ────────────────────────────────────────

    def _show_mic_permission_guide(self):
        """マイク権限の設定方法をダイアログで表示し、システム設定を開く"""
        import subprocess, platform

        # 現在のステータスを確認（クラッシュしない方法）
        status = -1
        try:
            from AVFoundation import AVCaptureDevice, AVMediaTypeAudio  # type: ignore
            status = int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
        except Exception:
            pass

        status_msg = {
            3: "✅ マイク権限あり\n録音できる状態です。",
            2: "❌ マイク権限が拒否されています\nシステム設定で手動で許可してください。",
            0: "⚠️ マイク権限がまだ設定されていません",
            -1: "マイク権限のステータスを確認できませんでした",
        }.get(status, f"不明なステータス ({status})")

        msg = (
            f"{status_msg}\n\n"
            "【マイク権限の設定方法】\n\n"
            "① 下の「システム設定を開く」をクリック\n\n"
            "② 画面左下の「＋」ボタンをクリック\n\n"
            "③ キーボードで Cmd+Shift+G を押して\n"
            "   /Applications/Utilities/ と入力 → Enter\n\n"
            "④ Terminal.app を選択 → 「開く」\n\n"
            "⑤ Terminal の横のトグルを ON にする\n\n"
            "⑥ Terminal を完全に終了（Cmd+Q）して再起動\n\n"
            "⑦ python3 main.py --desktop を再実行"
        )

        result = messagebox.askokcancel(
            "マイク権限の設定",
            msg,
            parent=self
        )
        if result and platform.system() == "Darwin":
            subprocess.Popen([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
            ])

    # ─── 録音 ────────────────────────────────────────────────────

    def _toggle_recording(self):
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        # macOS: マイク権限の事前確認
        try:
            from AVFoundation import AVCaptureDevice, AVMediaTypeAudio  # type: ignore
            status = int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
            if status == 2:  # denied
                messagebox.showerror(
                    "マイク権限エラー",
                    "マイクへのアクセスが拒否されています。\n\n"
                    "「🎤 マイク権限」ボタンをクリックして設定方法を確認してください。",
                    parent=self
                )
                return
            if status == 0:  # undetermined
                messagebox.showinfo(
                    "マイク権限の設定が必要です",
                    "マイク権限がまだ設定されていません。\n\n"
                    "「🎤 マイク権限」ボタンをクリックして設定してください。\n\n"
                    "設定後にTerminalを再起動してから録音してください。",
                    parent=self
                )
                return
        except Exception:
            pass  # pyobjc なし → チェックをスキップして録音を試みる

        with self._rec_lock:
            if self._recording:
                return
            ok = self.engine.start_recording()
            if not ok:
                messagebox.showerror("エラー", "録音を開始できなかったよ。\nsounddevice が必要です。", parent=self)
                return
            self._recording = True
            self._rec_start = time.time()
        self._rec_btn.configure(text="⏹  録音停止", bg=COLOR_RED)
        self._transcribe_btn.configure(state="disabled")
        self._format_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._pdf_btn.configure(state="disabled")
        self._update_timer()

    def _stop_recording(self):
        """録音を停止してバックグラウンドで wav 保存 → 自動で文字起こし開始"""
        with self._rec_lock:
            if not self._recording:
                return
            self._recording = False
        self._rec_btn.configure(
            text="⏳  保存中…", bg=COLOR_SUBTEXT, state="disabled"
        )
        self._on_status("録音停止 — 音声を保存しています…")

        def _save_bg():
            wav = self.engine.stop_recording()
            # 無音チェックはバックグラウンドで
            rms = None
            if wav:
                try:
                    import soundfile as _sf, numpy as _np
                    audio, _ = _sf.read(str(wav), dtype='float32')
                    rms = float(_np.sqrt(_np.mean(audio ** 2)))
                except Exception:
                    rms = None

            def _saved():
                try:
                    if not self.winfo_exists():
                        return
                    self._rec_btn.configure(
                        text="⏺  録音開始", bg=COLOR_ACCENT, state="normal"
                    )
                    if wav:
                        if rms is not None and rms < 1e-9:
                            self._on_status("⚠️ 無音です — マイク権限を確認してください")
                            messagebox.showwarning(
                                "マイク権限エラー",
                                "録音が無音です。macOSのマイク権限が必要です。\n\n"
                                "【設定方法】\n"
                                "システム設定 → プライバシーとセキュリティ → マイク\n"
                                "→「ターミナル」をオンにする\n"
                                "→ アプリを再起動する",
                                parent=self,
                            )
                            return
                        self._current_wav = wav
                        self._on_status("録音完了 — 文字起こしを開始します")
                        self._do_transcribe()
                    else:
                        self._on_status("録音データがありません")
                except tk.TclError:
                    pass

            try:
                if self.winfo_exists():
                    self.after(0, _saved)
            except tk.TclError:
                pass

        threading.Thread(target=_save_bg, daemon=True).start()

    def _update_timer(self):
        try:
            if not self.winfo_exists() or not self._recording:
                return
        except tk.TclError:
            return
        elapsed = int(time.time() - self._rec_start)
        m, s = divmod(elapsed, 60)
        try:
            self._rec_time_lbl.configure(
                text=f"{m:02d}:{s:02d}",
                fg=COLOR_RED if elapsed % 2 == 0 else COLOR_SUBTEXT,
            )
        except tk.TclError:
            return
        self._safe_after(500, self._update_timer)

    # ─── 音声ファイルを開く ──────────────────────────────────────

    def _open_audio_file(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="音声ファイルを選択",
            filetypes=[("音声ファイル", "*.wav *.mp3 *.m4a *.ogg *.flac"),
                       ("すべてのファイル", "*.*")]
        )
        if path:
            self._current_wav = Path(path)
            self._transcribe_btn.configure(state="normal")
            self._on_status(f"ファイル: {Path(path).name}")

    # ─── 文字起こし ──────────────────────────────────────────────

    def _do_transcribe(self):
        if not self._current_wav:
            messagebox.showwarning("エラー", "先に録音するかファイルを開いてね", parent=self)
            return
        self._transcribe_btn.configure(state="disabled", text="処理中…")
        self._format_btn.configure(state="disabled")

        # 起動時点の wav をキャプチャ（後続操作で変わっても安全）
        wav = self._current_wav

        def _bg():
            text = self.engine.transcribe(
                wav,
                progress_cb=lambda m: self._on_status(m),
            )
            def _done():
                try:
                    if not self.winfo_exists():
                        return
                    self._set_text(self._transcript_text, text)
                    self._transcribe_btn.configure(state="normal", text="📝  文字起こし")
                    self._format_btn.configure(state="normal")
                    self._on_status("文字起こし完了 — LLMで議事録を整形します")
                    if self.ai_chan and getattr(self.ai_chan, "llm_loaded", False):
                        self._safe_after(300, self._do_format)
                    else:
                        self._on_status("文字起こし完了 — 「議事録を整形」ボタンを押してください")
                except tk.TclError:
                    pass
            try:
                if self.winfo_exists():
                    self.after(0, _done)
            except tk.TclError:
                pass

        threading.Thread(target=_bg, daemon=True).start()

    # ─── 議事録整形 ──────────────────────────────────────────────

    def _do_format(self):
        transcript = self._transcript_text.get("1.0", "end").strip()
        if not transcript:
            messagebox.showwarning("エラー", "文字起こしテキストがないよ", parent=self)
            return

        # LLMがなくてもフォールバック整形で続行できる
        llm = None
        if self.ai_chan and getattr(self.ai_chan, "llm_loaded", False):
            llm = self.ai_chan.llm
        elif self.ai_chan and not getattr(self.ai_chan, "llm_loaded", False):
            self._on_status("LLM読み込み中のため簡易整形モードで実行します")

        self._format_btn.configure(state="disabled", text="整形中…")
        self._save_btn.configure(state="disabled")

        # ストリーミング: 生成トークンをリアルタイムでテキストボックスに追記
        def _stream_token(token: str):
            def _append():
                try:
                    if not self.winfo_exists():
                        return
                    self._minutes_text.configure(state="normal")
                    self._minutes_text.insert("end", token)
                    self._minutes_text.see("end")
                except tk.TclError:
                    pass
            try:
                if self.winfo_exists():
                    self.after(0, _append)
            except tk.TclError:
                pass

        def _bg():
            # 生成前にテキストをクリア
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self._set_text(self._minutes_text, ""))
            except tk.TclError:
                pass
            formatted = self.engine.format_minutes(
                transcript,
                llm_engine=llm,
                title=self._title_var.get(),
                attendees=self._attendees_var.get(),
                progress_cb=lambda m: self._on_status(m),
                stream_cb=_stream_token if llm else None,
            )
            def _done():
                try:
                    if not self.winfo_exists():
                        return
                    if not llm:
                        self._set_text(self._minutes_text, formatted)
                    self._format_btn.configure(state="normal", text="✨  議事録を整形")
                    self._save_btn.configure(state="normal")
                    self._extract_btn.configure(state="normal")
                    char_count = len(formatted)
                    self._on_status(f"✅ 整形完了 ({char_count}文字)")
                except tk.TclError:
                    pass
            try:
                if self.winfo_exists():
                    self.after(0, _done)
            except tk.TclError:
                pass

        threading.Thread(target=_bg, daemon=True).start()

    # ─── 保存 ────────────────────────────────────────────────────

    def _do_save(self):
        transcript = self._transcript_text.get("1.0", "end").strip()
        formatted  = self._minutes_text.get("1.0", "end").strip()
        if not transcript and not formatted:
            messagebox.showwarning("エラー", "保存するテキストがないよ", parent=self)
            return

        title     = self._title_var.get().strip() or ""
        attendees = self._attendees_var.get().strip()

        self._current_entry = self.engine.save_minutes(
            transcript=transcript,
            formatted=formatted,
            title=title,
            attendees=attendees,
            wav_path=self._current_wav,
        )
        self._pdf_btn.configure(state="normal")
        self._extract_btn.configure(state="normal")
        self._refresh_history()
        self._on_status(f"保存完了: {self._current_entry['title']}")
        messagebox.showinfo("保存完了",
                            f"議事録を保存したよ！\n「{self._current_entry['title']}」",
                            parent=self)

    # ─── PDF出力（録音タブ） ─────────────────────────────────────

    def _do_export_pdf(self):
        if not self._current_entry:
            messagebox.showwarning("エラー", "先に保存してからPDF出力してね", parent=self)
            return
        self._export_pdf_for(self._current_entry["id"])

    def _export_pdf_for(self, mid: str):
        def _bg():
            pdf_path = self.engine.export_pdf(mid)
            def _done():
                try:
                    if not self.winfo_exists():
                        return
                    if pdf_path:
                        self._refresh_history()
                        if messagebox.askyesno(
                            "PDF出力完了",
                            f"PDFを保存したよ！\n{pdf_path}\n\nFinderで開く？",
                            parent=self,
                        ):
                            import subprocess
                            subprocess.run(["open", "-R", str(pdf_path)])
                    else:
                        messagebox.showerror("エラー", "PDF出力に失敗したよ", parent=self)
                except tk.TclError:
                    pass
            try:
                if self.winfo_exists():
                    self.after(0, _done)
            except tk.TclError:
                pass

        threading.Thread(target=_bg, daemon=True).start()
        self._on_status("PDF出力中…")

    # ─── 履歴 ────────────────────────────────────────────────────

    def _refresh_history(self):
        self._hist_entries = self.engine.list_minutes()
        self._hist_lb.delete(0, "end")
        for e in self._hist_entries:
            pdf_mark  = " 📄" if e.get("pdf_path") else ""
            attendees = e.get("attendees", "")[:14]
            line = f"{e['date']}  {e['time']}  {e['title'][:28]}{pdf_mark}  {attendees}"
            self._hist_lb.insert("end", line)

    def _on_hist_select(self, event=None):
        sel = self._hist_lb.curselection()
        if not sel:
            return
        idx   = sel[0]
        if idx >= len(self._hist_entries):
            return
        entry = self._hist_entries[idx]
        # プレビュー表示
        preview = (
            f"【{entry['title']}】\n"
            f"日時: {entry['date']} {entry['time']}\n"
            f"参加者: {entry.get('attendees','')}\n"
            f"ID: {entry['id']}\n"
            f"{'─'*40}\n"
        ) + (entry.get("formatted") or entry.get("transcript", ""))
        self._set_text(self._preview_text, preview, readonly=True)
        self._hist_pdf_btn.configure(state="normal")
        self._hist_learn_btn.configure(
            state="normal" if self.ai_chan else "disabled"
        )
        self._hist_notion_btn.configure(
            state="normal" if self.notion.is_configured() else "disabled"
        )
        self._hist_gcal_btn.configure(
            state="normal" if self.gcal.is_configured() else "disabled"
        )

    def _hist_export_pdf(self):
        sel = self._hist_lb.curselection()
        if not sel:
            return
        entry = self._hist_entries[sel[0]]
        self._export_pdf_for(entry["id"])

    def _hist_learn(self):
        """選択した議事録をアイに学習させる"""
        sel = self._hist_lb.curselection()
        if not sel or not self.ai_chan:
            return
        entry = self._hist_entries[sel[0]]
        learn_text = self.engine.build_learning_text(entry)
        try:
            self.ai_chan.learning.add_conversation(
                user=f"{entry['title']}の議事録を教えて",
                ai=learn_text[:500],
                save=True,
            )
            self.ai_chan.auto_learner.add_memo(
                learn_text[:200],
                tags=["議事録", entry["date"]]
            )
            self._on_status(f"学習完了: {entry['title']}")
            messagebox.showinfo("学習完了",
                                f"アイが「{entry['title']}」を学習したよ！",
                                parent=self)
        except Exception as e:
            messagebox.showerror("学習エラー", str(e), parent=self)

    def _hist_push_notion(self):
        """履歴から選択した議事録を Notion に送信"""
        sel = self._hist_lb.curselection()
        if not sel:
            return
        entry = self._hist_entries[sel[0]]
        self._hist_notion_btn.configure(state="disabled", text="送信中…")

        def _bg():
            llm = self.ai_chan.llm if (self.ai_chan and self.ai_chan.llm_loaded) else None
            text = entry.get("formatted") or entry.get("transcript", "")
            structured = self.extractor.extract_structured(text, llm_engine=llm) if text else None
            ok, msg = self.notion.push_minutes(entry, structured)
            def _done():
                try:
                    if not self.winfo_exists():
                        return
                    self._hist_notion_btn.configure(state="normal", text="N Notion")
                    if ok:
                        self._on_status(f"Notion送信完了: {entry['title']}")
                        if messagebox.askyesno("Notion送信完了",
                                               f"送信完了！\n{msg}\n\nブラウザで開く？", parent=self):
                            import webbrowser
                            webbrowser.open(msg)
                    else:
                        messagebox.showerror("送信失敗", msg, parent=self)
                except tk.TclError:
                    pass
            try:
                if self.winfo_exists():
                    self.after(0, _done)
            except tk.TclError:
                pass

        threading.Thread(target=_bg, daemon=True).start()

    def _hist_push_gcal(self):
        """履歴から選択した議事録のアクションアイテムをGoogleカレンダーに登録"""
        sel = self._hist_lb.curselection()
        if not sel:
            return
        entry = self._hist_entries[sel[0]]
        self._hist_gcal_btn.configure(state="disabled", text="登録中…")

        def _bg():
            llm = self.ai_chan.llm if (self.ai_chan and self.ai_chan.llm_loaded) else None
            text = entry.get("formatted") or entry.get("transcript", "")
            structured = self.extractor.extract_structured(text, llm_engine=llm) if text else {}
            items = structured.get("action_items", [])
            nm    = structured.get("next_meeting", {})
            parts = []
            if items:
                res = self.gcal.push_all_action_items(items, meeting_title=entry["title"])
                parts.append(f"タスク: {res['ok']}件登録")
            if nm.get("date"):
                ok2, _ = self.gcal.push_meeting(
                    title=f"【次回会議】{entry['title']}",
                    start_date=nm["date"],
                    description=nm.get("label", ""),
                )
                parts.append("次回会議: 登録" + ("成功" if ok2 else "失敗"))
            summary = "  /  ".join(parts) if parts else "登録対象がありませんでした"
            def _done():
                self._hist_gcal_btn.configure(state="normal", text="📅 GCal")
                self._on_status(f"GCal登録完了: {entry['title']}")
                messagebox.showinfo("カレンダー登録完了", summary, parent=self)
            self.after(0, _done)

        threading.Thread(target=_bg, daemon=True).start()

    # ─── アクション抽出 ──────────────────────────────────────────

    def _do_extract(self):
        """議事録テキストから構造化データを抽出"""
        text = self._minutes_text.get("1.0", "end").strip()
        if not text:
            text = self._transcript_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("エラー", "抽出する議事録テキストがないよ", parent=self)
            return

        self._extract_btn.configure(state="disabled", text="抽出中…")
        self._extract_lbl.configure(text="🔍 抽出中…", fg=COLOR_SUBTEXT)

        def _bg():
            llm = self.ai_chan.llm if (self.ai_chan and self.ai_chan.llm_loaded) else None
            result = self.extractor.extract_structured(text, llm_engine=llm)
            def _done():
                self._structured = result
                items   = result.get("action_items", [])
                decs    = result.get("decisions", [])
                nm      = result.get("next_meeting", {})
                parts   = []
                if items:
                    parts.append(f"📋 アクション: {len(items)}件")
                if decs:
                    parts.append(f"✅ 決定事項: {len(decs)}件")
                if nm.get("label"):
                    parts.append(f"📅 次回会議: {nm['label']}")
                summary = "  ／  ".join(parts) if parts else "構造データが見つかりませんでした"
                self._extract_lbl.configure(text=summary, fg=COLOR_GREEN)
                self._extract_btn.configure(state="normal", text="🔍  アクション抽出")
                # Notion/GCal ボタンを有効化
                if self.notion.is_configured():
                    self._notion_btn.configure(state="normal")
                if self.gcal.is_configured():
                    self._gcal_btn.configure(state="normal")
                self._on_status(f"抽出完了 — {len(items)}件のアクションアイテム")
            self.after(0, _done)

        threading.Thread(target=_bg, daemon=True).start()

    # ─── Notion へ送る ───────────────────────────────────────────

    def _do_push_notion(self):
        """議事録と構造化データを Notion に送信"""
        if not self.notion.is_configured():
            messagebox.showwarning(
                "Notion未設定",
                "連携設定タブでNotionのAPIキーとデータベースIDを設定してね",
                parent=self
            )
            return

        entry = self._current_entry
        if not entry:
            # 未保存の場合はテキストだけで entry を作る
            import uuid, datetime
            now = datetime.datetime.now()
            entry = {
                "id":         str(uuid.uuid4())[:8],
                "title":      self._title_var.get() or "無題の会議",
                "date":       now.strftime("%Y-%m-%d"),
                "time":       now.strftime("%H:%M"),
                "attendees":  self._attendees_var.get(),
                "transcript": self._transcript_text.get("1.0", "end").strip(),
                "formatted":  self._minutes_text.get("1.0", "end").strip(),
                "created_at": now.isoformat()[:16],
            }

        self._notion_btn.configure(state="disabled", text="送信中…")
        structured = self._structured

        def _bg():
            ok, msg = self.notion.push_minutes(entry, structured)
            def _done():
                self._notion_btn.configure(state="normal", text="N  Notionへ送る")
                if ok:
                    self._on_status(f"Notion送信完了: {msg}")
                    if messagebox.askyesno(
                        "Notion送信完了",
                        f"NotionにページをつくったよURL:\n{msg}\n\nブラウザで開く？",
                        parent=self
                    ):
                        import webbrowser
                        webbrowser.open(msg)
                else:
                    self._on_status(f"Notion送信失敗: {msg}")
                    messagebox.showerror("送信失敗", msg, parent=self)
            self.after(0, _done)

        threading.Thread(target=_bg, daemon=True).start()

    # ─── Google Calendar へ送る ──────────────────────────────────

    def _do_push_gcal(self):
        """アクションアイテム＋次回会議をGoogleカレンダーに登録"""
        if not self.gcal.is_configured():
            messagebox.showwarning(
                "GCal未設定",
                "連携設定タブでGoogle Calendarの認証ファイルを設定してね",
                parent=self
            )
            return

        structured = self._structured
        if not structured:
            messagebox.showwarning("未抽出", "先に🔍アクション抽出を実行してね", parent=self)
            return

        self._gcal_btn.configure(state="disabled", text="登録中…")
        title = (self._current_entry or {}).get("title") or self._title_var.get() or "会議"

        def _bg():
            results_parts = []
            # ── アクションアイテム一括登録 ──
            items = structured.get("action_items", [])
            if items:
                res = self.gcal.push_all_action_items(items, meeting_title=title)
                results_parts.append(
                    f"タスク登録: {res['ok']}件成功 / {res['fail']}件失敗 / {res['skip']}件スキップ"
                )
            # ── 次回会議 ──
            nm = structured.get("next_meeting", {})
            if nm.get("date"):
                ok, link = self.gcal.push_meeting(
                    title=f"【次回会議】{title}",
                    start_date=nm["date"],
                    start_time="10:00",
                    description=nm.get("label", ""),
                    location=nm.get("location", ""),
                )
                if ok:
                    results_parts.append(f"次回会議登録: 成功")
                else:
                    results_parts.append(f"次回会議登録: 失敗 ({link})")

            summary = "\n".join(results_parts) if results_parts else "登録対象がありませんでした"

            def _done():
                self._gcal_btn.configure(state="normal", text="📅  カレンダーへ")
                self._on_status("Googleカレンダー登録完了")
                messagebox.showinfo("カレンダー登録完了", summary, parent=self)
            self.after(0, _done)

        threading.Thread(target=_bg, daemon=True).start()

    # ─── 連携設定タブ ────────────────────────────────────────────

    def _build_connect_tab(self):
        f = self._tab_connect
        import json

        # スクロール可能コンテナ
        canvas = tk.Canvas(f, bg=COLOR_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=COLOR_PANEL)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        pad = dict(padx=16, pady=6)

        # ──────────────── Notion セクション ────────────────
        tk.Label(inner, text="Notion 連携",
                 bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_H2
                 ).pack(anchor="w", **pad)

        # API Key
        self._n_key_var = tk.StringVar()
        _row(inner, "APIキー", self._n_key_var, show="*")

        # Minutes DB
        self._n_min_db_var = tk.StringVar()
        _row(inner, "議事録データベースID", self._n_min_db_var)

        # Todo DB
        self._n_todo_db_var = tk.StringVar()
        _row(inner, "TODOデータベースID (オプション)", self._n_todo_db_var)

        # テスト接続 & ステータス
        n_test_f = tk.Frame(inner, bg=COLOR_PANEL)
        n_test_f.pack(anchor="w", padx=16, pady=(2, 8))
        tk.Button(n_test_f, text="接続テスト",
                  bg=COLOR_CARD, fg=COLOR_TEXT,
                  font=FONT_SMALL, relief="flat",
                  command=self._test_notion, padx=10, pady=4,
                  cursor="hand2").pack(side="left", padx=(0, 10))
        self._n_status_lbl = tk.Label(
            n_test_f, text="未テスト",
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=FONT_SMALL
        )
        self._n_status_lbl.pack(side="left")

        _divider(inner)

        # ──────────────── Google Calendar セクション ────────────
        tk.Label(inner, text="Google Calendar 連携",
                 bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_H2
                 ).pack(anchor="w", **pad)

        tk.Label(
            inner,
            text="Google Cloud Console でOAuth2認証情報JSONをダウンロードして指定してください。",
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=FONT_SMALL,
            wraplength=680, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 4))

        # credentials file
        cred_f = tk.Frame(inner, bg=COLOR_PANEL)
        cred_f.pack(fill="x", padx=16, pady=4)
        tk.Label(cred_f, text="credentials.json", bg=COLOR_PANEL,
                 fg=COLOR_SUBTEXT, font=FONT_SMALL, width=22, anchor="w"
                 ).pack(side="left")
        self._gc_cred_var = tk.StringVar()
        tk.Entry(cred_f, textvariable=self._gc_cred_var,
                 bg=COLOR_INPUT, fg=COLOR_TEXT,
                 insertbackground=COLOR_ACCENT, relief="flat",
                 font=FONT_SMALL, width=38,
                 highlightbackground=COLOR_LINE, highlightthickness=1
                 ).pack(side="left", padx=(0, 6))
        tk.Button(cred_f, text="選択…",
                  bg=COLOR_CARD, fg=COLOR_TEXT,
                  font=FONT_SMALL, relief="flat",
                  command=self._pick_cred_file, padx=6, pady=2,
                  cursor="hand2").pack(side="left")

        # calendar_id
        self._gc_cal_var = tk.StringVar()
        _row(inner, "カレンダーID", self._gc_cal_var, default="primary")

        # テスト接続
        gc_test_f = tk.Frame(inner, bg=COLOR_PANEL)
        gc_test_f.pack(anchor="w", padx=16, pady=(2, 8))
        tk.Button(gc_test_f, text="接続テスト (ブラウザ認証が開くことがあります)",
                  bg=COLOR_CARD, fg=COLOR_TEXT,
                  font=FONT_SMALL, relief="flat",
                  command=self._test_gcal, padx=10, pady=4,
                  cursor="hand2").pack(side="left", padx=(0, 10))
        self._gc_status_lbl = tk.Label(
            gc_test_f, text="未テスト",
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=FONT_SMALL
        )
        self._gc_status_lbl.pack(side="left")

        _divider(inner)

        # ──────────────── 保存ボタン ─────────────────────────────
        save_f = tk.Frame(inner, bg=COLOR_PANEL)
        save_f.pack(pady=(4, 16))
        tk.Button(save_f, text="💾  設定を保存",
                  bg=COLOR_GREEN, fg=COLOR_BG,
                  font=FONT_H2, relief="flat",
                  command=self._save_connect_settings, padx=20, pady=8,
                  cursor="hand2").pack()

        # ── 現在の設定値を読み込んで表示 ──
        cfg  = self._load_settings()
        intg = cfg.get("integrations", {})
        nc   = intg.get("notion", {})
        gc   = intg.get("google_calendar", {})
        self._n_key_var.set(nc.get("api_key", ""))
        self._n_min_db_var.set(nc.get("minutes_database_id", ""))
        self._n_todo_db_var.set(nc.get("todo_database_id", ""))
        self._gc_cred_var.set(gc.get("credentials_file", ""))
        self._gc_cal_var.set(gc.get("calendar_id", "primary"))

    def _pick_cred_file(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Google Calendar credentials JSON を選択",
            filetypes=[("JSONファイル", "*.json"), ("すべてのファイル", "*.*")]
        )
        if path:
            self._gc_cred_var.set(path)

    def _test_notion(self):
        from core.notion_connector import NotionConnector
        conn = NotionConnector(
            api_key=self._n_key_var.get().strip(),
            database_id=self._n_min_db_var.get().strip(),
        )
        self._n_status_lbl.configure(text="テスト中…", fg=COLOR_SUBTEXT)
        def _bg():
            ok, msg = conn.test_connection()
            def _done():
                self._n_status_lbl.configure(
                    text=msg, fg=COLOR_GREEN if ok else COLOR_RED
                )
            self.after(0, _done)
        threading.Thread(target=_bg, daemon=True).start()

    def _test_gcal(self):
        from core.gcal_connector import GCalConnector
        conn = GCalConnector(
            credentials_file=self._gc_cred_var.get().strip(),
            calendar_id=self._gc_cal_var.get().strip() or "primary",
        )
        self._gc_status_lbl.configure(text="テスト中…", fg=COLOR_SUBTEXT)
        def _bg():
            ok, msg = conn.test_connection()
            def _done():
                self._gc_status_lbl.configure(
                    text=msg, fg=COLOR_GREEN if ok else COLOR_RED
                )
            self.after(0, _done)
        threading.Thread(target=_bg, daemon=True).start()

    def _save_connect_settings(self):
        """連携設定を settings.json に保存してコネクタを再初期化"""
        import json
        p = BASE_DIR / "config" / "settings.json"
        try:
            cfg = json.loads(p.read_text("utf-8"))
        except Exception:
            cfg = {}

        cfg.setdefault("integrations", {})
        cfg["integrations"]["notion"] = {
            "enabled":              bool(self._n_key_var.get().strip()),
            "api_key":              self._n_key_var.get().strip(),
            "minutes_database_id":  self._n_min_db_var.get().strip(),
            "todo_database_id":     self._n_todo_db_var.get().strip(),
        }
        cfg["integrations"]["google_calendar"] = {
            "enabled":          bool(self._gc_cred_var.get().strip()),
            "credentials_file": self._gc_cred_var.get().strip(),
            "calendar_id":      self._gc_cal_var.get().strip() or "primary",
        }

        try:
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        except Exception as e:
            messagebox.showerror("保存エラー", str(e), parent=self)
            return

        # コネクタを再初期化
        self._init_connectors()
        self._on_status("連携設定を保存したよ")
        messagebox.showinfo("保存完了", "連携設定を保存して反映したよ！", parent=self)

    # ─── ステータス表示 ──────────────────────────────────────────

    def _poll_whisper_ready(self):
        """Whisperウォームアップ完了をポーリングして録音ボタンを有効化"""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self.engine.whisper_ready:
            self._rec_btn.configure(state="normal")
            self._on_status("✅ 準備完了 — 録音できます")
        else:
            self._rec_btn.configure(state="disabled")
            self._on_status("⏳ Whisper 読み込み中… (初回のみ数秒かかります)")
            self._safe_after(500, self._poll_whisper_ready)

    def _on_status(self, msg: str):
        def _upd():
            try:
                if self.winfo_exists():
                    self._status_lbl.configure(text=msg)
            except tk.TclError:
                pass
        try:
            if self.winfo_exists():
                self.after(0, _upd)
        except tk.TclError:
            pass

    # ─── テキストボックス操作 ────────────────────────────────────

    @staticmethod
    def _set_text(widget: tk.Text, text: str, readonly: bool = False):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        if readonly:
            widget.configure(state="disabled")


# ─── ヘルパー ────────────────────────────────────────────────────

def _row(parent, label: str, var: tk.StringVar,
         show: str = "", default: str = "") -> tk.Entry:
    """ラベル + エントリー の一行を parent に追加して Entry を返す"""
    f = tk.Frame(parent, bg=COLOR_PANEL)
    f.pack(fill="x", padx=16, pady=4)
    tk.Label(f, text=label, bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
             font=FONT_SMALL, width=24, anchor="w").pack(side="left")
    if default and not var.get():
        var.set(default)
    e = tk.Entry(f, textvariable=var, show=show,
                 bg=COLOR_INPUT, fg=COLOR_TEXT,
                 insertbackground=COLOR_ACCENT, relief="flat",
                 font=FONT_SMALL, width=42,
                 highlightbackground=COLOR_LINE, highlightthickness=1)
    e.pack(side="left", fill="x", expand=True)
    return e


def _divider(parent):
    tk.Frame(parent, bg=COLOR_LINE, height=1).pack(
        fill="x", padx=16, pady=10)


def _make_textbox(parent, bg: str, readonly: bool = False) -> tk.Text:
    frame = tk.Frame(parent, bg=bg)
    sb = ttk.Scrollbar(frame)
    sb.pack(side="right", fill="y")
    t = tk.Text(
        frame,
        yscrollcommand=sb.set,
        bg=bg, fg=COLOR_TEXT,
        insertbackground=COLOR_ACCENT,
        selectbackground=COLOR_ACCENT2,
        font=FONT_BODY, relief="flat",
        wrap="word", padx=10, pady=8,
        state="disabled" if readonly else "normal"
    )
    sb.config(command=t.yview)
    t.pack(side="left", fill="both", expand=True)
    # frame を返さず Text を返すためのトリック: frame を parent に置く
    frame.pack(fill="both", expand=True)
    return t


# ─── スタンドアローン起動 ────────────────────────────────────────

def launch_standalone():
    """アイなしで単独起動"""
    root = tk.Tk()
    root.withdraw()
    win = MinutesWindow(root, ai_chan_instance=None)
    win.protocol("WM_DELETE_WINDOW", root.quit)
    root.mainloop()


if __name__ == "__main__":
    launch_standalone()

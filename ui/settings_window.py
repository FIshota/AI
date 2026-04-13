"""
設定GUIウィンドウ
settings.json / 記念日 / 自律行動 をアプリ内から編集できます。
"""
from __future__ import annotations
import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional

COLOR_BG      = "#2D1B3D"
COLOR_PANEL   = "#3D2255"
COLOR_INPUT   = "#1A0F2E"
COLOR_ACCENT  = "#E8A5C8"
COLOR_ACCENT2 = "#B57BDC"
COLOR_TEXT    = "#F5E6FF"
COLOR_SUBTEXT = "#C9A8E8"

LABEL_FONT  = ("Hiragino Sans", 11)
HEADER_FONT = ("Hiragino Sans", 12, "bold")
SMALL_FONT  = ("Hiragino Sans", 9)


def _label(parent, text, fg=None, font=None, **kwargs):
    return tk.Label(parent, text=text,
                    bg=COLOR_PANEL, fg=fg or COLOR_TEXT,
                    font=font or LABEL_FONT, **kwargs)


def _entry(parent, textvariable, width=12):
    return tk.Entry(parent, textvariable=textvariable,
                    bg=COLOR_INPUT, fg=COLOR_TEXT,
                    insertbackground=COLOR_ACCENT,
                    relief="flat", font=LABEL_FONT, width=width,
                    highlightbackground=COLOR_ACCENT2, highlightthickness=1)


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, ai_chan_instance, base_dir: Path):
        super().__init__(parent)
        self.ai_chan  = ai_chan_instance
        self.base_dir = Path(base_dir)
        self.cfg_path = self.base_dir / "config" / "settings.json"

        self.title("⚙️ アイ 設定")
        self.configure(bg=COLOR_BG)
        self.geometry("540x560")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # ttk スタイル（ダークテーマ）
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("TNotebook",        background=COLOR_BG,      borderwidth=0)
        style.configure("TNotebook.Tab",    background=COLOR_PANEL,   foreground=COLOR_SUBTEXT,
                        padding=[12, 6],    font=("Hiragino Sans", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", COLOR_ACCENT)],
                  foreground=[("selected", COLOR_BG)])
        style.configure("TFrame",           background=COLOR_PANEL)
        style.configure("TScale",           background=COLOR_PANEL, troughcolor=COLOR_INPUT)
        style.configure("Vertical.TScrollbar", background=COLOR_PANEL, troughcolor=COLOR_INPUT)

        self._build_ui()
        self._load_values()

    # ─── UI 構築 ──────────────────────────────────────────────────

    def _build_ui(self):
        tk.Label(self, text="⚙️ 設定", bg=COLOR_BG, fg=COLOR_ACCENT,
                 font=("Hiragino Sans", 14, "bold")).pack(pady=(14, 6))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self._tab_llm         = self._make_tab(nb, "会話")
        self._tab_auto        = self._make_tab(nb, "自律行動")
        self._tab_anniversary = self._make_tab(nb, "記念日")
        self._tab_memory      = self._make_tab(nb, "記憶")
        self._tab_icons       = self._make_tab(nb, "アイコン")
        self._tab_voice       = self._make_tab(nb, "音声・AI")
        self._tab_autolearn   = self._make_tab(nb, "自動学習")

        self._build_llm_tab()
        self._build_auto_tab()
        self._build_anniversary_tab()
        self._build_memory_tab()
        self._build_icons_tab()
        self._build_voice_tab()
        self._build_autolearn_tab()

        # 保存・閉じるボタン
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(pady=(0, 14))
        tk.Button(btn_frame, text="保存して閉じる",
                  bg=COLOR_ACCENT, fg=COLOR_BG,
                  font=("Hiragino Sans", 12, "bold"), relief="flat",
                  command=self._save_and_close, padx=16, pady=8
                  ).pack(side="left", padx=8)
        tk.Button(btn_frame, text="キャンセル",
                  bg=COLOR_PANEL, fg=COLOR_TEXT,
                  font=LABEL_FONT, relief="flat",
                  command=self.destroy, padx=16, pady=8
                  ).pack(side="left", padx=8)

    def _make_tab(self, nb, label):
        frame = tk.Frame(nb, bg=COLOR_PANEL, padx=16, pady=12)
        nb.add(frame, text=label)
        return frame

    # ── 会話タブ
    def _build_llm_tab(self):
        f = self._tab_llm

        self.v_max_tokens   = tk.IntVar()
        self.v_temperature  = tk.DoubleVar()
        self.v_max_sentences = tk.IntVar()

        rows = [
            ("最大トークン数", self.v_max_tokens,  50, 500,
             "応答の最大長。大きいほど長い文章（推論も遅くなる）"),
            ("文章上限",      self.v_max_sentences, 1, 12,
             "何文まで返答するか（デフォルト: 6）"),
        ]
        for i, (label, var, lo, hi, hint) in enumerate(rows):
            _label(f, label).grid(row=i*2, column=0, sticky="w", pady=(6, 0))
            tk.Scale(f, variable=var, from_=lo, to=hi, orient="horizontal",
                     bg=COLOR_PANEL, fg=COLOR_TEXT, troughcolor=COLOR_INPUT,
                     highlightthickness=0, length=260
                     ).grid(row=i*2, column=1, sticky="w", padx=8)
            _label(f, hint, fg=COLOR_SUBTEXT, font=SMALL_FONT
                   ).grid(row=i*2+1, column=0, columnspan=2, sticky="w",
                          padx=4, pady=(0, 4))

        # temperature は小数
        _label(f, "温度（個性）").grid(row=4, column=0, sticky="w", pady=(6, 0))
        tk.Scale(f, variable=self.v_temperature, from_=0.1, to=1.5,
                 resolution=0.05, orient="horizontal",
                 bg=COLOR_PANEL, fg=COLOR_TEXT, troughcolor=COLOR_INPUT,
                 highlightthickness=0, length=260
                 ).grid(row=4, column=1, sticky="w", padx=8)
        _label(f, "低い=安定、高い=個性的（デフォルト: 0.7）",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=5, column=0, columnspan=2, sticky="w", padx=4)

    # ── 自律行動タブ
    def _build_auto_tab(self):
        f = self._tab_auto

        self.v_idle_minutes   = tk.IntVar()
        self.v_allow_network  = tk.BooleanVar()
        self.v_weather_city   = tk.StringVar()
        self.v_schedule_en    = tk.BooleanVar()
        self.v_clipboard_watch = tk.BooleanVar()

        # アイドル
        _label(f, "放置タイマー（分）").grid(row=0, column=0, sticky="w", pady=6)
        tk.Spinbox(f, textvariable=self.v_idle_minutes,
                   from_=5, to=120, width=6,
                   bg=COLOR_INPUT, fg=COLOR_TEXT, relief="flat",
                   font=LABEL_FONT).grid(row=0, column=1, sticky="w", padx=8)

        # スケジュール
        tk.Checkbutton(f, text="日課リマインダーを有効にする",
                       variable=self.v_schedule_en,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)

        # クリップボード
        tk.Checkbutton(f, text="クリップボード監視を有効にする（macOS）",
                       variable=self.v_clipboard_watch,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)

        # ネットワーク
        tk.Checkbutton(f, text="ネットワーク取得を許可（天気・ニュース）",
                       variable=self.v_allow_network,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        _label(f, "天気の都市名").grid(row=4, column=0, sticky="w", pady=6)
        _entry(f, self.v_weather_city, width=16).grid(row=4, column=1, sticky="w", padx=8)

    # ── 記念日タブ
    def _build_anniversary_tab(self):
        f = self._tab_anniversary

        _label(f, "登録済み記念日・誕生日",
               font=HEADER_FONT).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # リストボックス
        lb_frame = tk.Frame(f, bg=COLOR_INPUT)
        lb_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.anniv_lb = tk.Listbox(
            lb_frame, bg=COLOR_INPUT, fg=COLOR_TEXT,
            selectbackground=COLOR_ACCENT, selectforeground=COLOR_BG,
            font=("Hiragino Sans", 11), relief="flat", height=6
        )
        sb = ttk.Scrollbar(lb_frame, command=self.anniv_lb.yview)
        self.anniv_lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.anniv_lb.pack(fill="both", expand=True, padx=2, pady=2)

        # 追加フォーム
        add_frame = tk.Frame(f, bg=COLOR_PANEL)
        add_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.v_anniv_label = tk.StringVar()
        self.v_anniv_month = tk.IntVar(value=1)
        self.v_anniv_day   = tk.IntVar(value=1)
        self.v_anniv_bday  = tk.BooleanVar()

        _label(add_frame, "名前").grid(row=0, column=0, sticky="w")
        _entry(add_frame, self.v_anniv_label, width=14
               ).grid(row=0, column=1, padx=4)

        _label(add_frame, "月").grid(row=0, column=2)
        tk.Spinbox(add_frame, textvariable=self.v_anniv_month,
                   from_=1, to=12, width=4,
                   bg=COLOR_INPUT, fg=COLOR_TEXT, relief="flat",
                   font=LABEL_FONT).grid(row=0, column=3, padx=2)

        _label(add_frame, "日").grid(row=0, column=4)
        tk.Spinbox(add_frame, textvariable=self.v_anniv_day,
                   from_=1, to=31, width=4,
                   bg=COLOR_INPUT, fg=COLOR_TEXT, relief="flat",
                   font=LABEL_FONT).grid(row=0, column=5, padx=2)

        tk.Checkbutton(add_frame, text="誕生日",
                       variable=self.v_anniv_bday,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=0, column=6, padx=4)

        btn_row = tk.Frame(f, bg=COLOR_PANEL)
        btn_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=6)

        tk.Button(btn_row, text="追加",
                  bg=COLOR_ACCENT, fg=COLOR_BG,
                  font=LABEL_FONT, relief="flat",
                  command=self._add_anniversary, padx=10, pady=4
                  ).pack(side="left", padx=4)
        tk.Button(btn_row, text="削除",
                  bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                  font=LABEL_FONT, relief="flat",
                  command=self._remove_anniversary, padx=10, pady=4
                  ).pack(side="left", padx=4)

        f.rowconfigure(1, weight=1)

    # ── 記憶タブ
    def _build_memory_tab(self):
        f = self._tab_memory

        self.v_short_max  = tk.IntVar()
        self.v_encrypt    = tk.BooleanVar()

        _label(f, "短期記憶の最大件数").grid(row=0, column=0, sticky="w", pady=6)
        tk.Spinbox(f, textvariable=self.v_short_max,
                   from_=5, to=100, width=6,
                   bg=COLOR_INPUT, fg=COLOR_TEXT, relief="flat",
                   font=LABEL_FONT).grid(row=0, column=1, sticky="w", padx=8)

        tk.Checkbutton(f, text="記憶を暗号化する（AES-256）",
                       variable=self.v_encrypt,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)

        _label(f, "※ 暗号化の変更は再起動後に反映されます",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=2, column=0, columnspan=2, sticky="w")

        # 記憶統計
        if self.ai_chan and hasattr(self.ai_chan, "memory"):
            stats = self.ai_chan.memory.stats()
            info = (f"現在の記憶: 短期={stats['short_term_count']}件  "
                    f"DB={stats['db_total']}件  保護={stats['protected']}件")
            _label(f, info, fg=COLOR_SUBTEXT, font=SMALL_FONT
                   ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

    # ── アイコンタブ
    def _build_icons_tab(self):
        f = self._tab_icons

        self.v_ai_icon        = tk.StringVar()
        self.v_user_icon      = tk.StringVar()
        self.v_user_name      = tk.StringVar()
        self.v_pet_image      = tk.StringVar()
        self.v_ai_icon_image  = tk.StringVar()
        self.v_user_icon_image = tk.StringVar()

        # 表示名
        _label(f, "あなたの表示名").grid(row=0, column=0, sticky="w", pady=(8, 0))
        _entry(f, self.v_user_name, width=16).grid(row=0, column=1, sticky="w", padx=8)
        _label(f, "チャットに表示される名前",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=1, column=0, columnspan=2, sticky="w", padx=4)

        # 絵文字フォールバック
        _label(f, "アイの絵文字アイコン").grid(row=2, column=0, sticky="w", pady=(10, 0))
        _entry(f, self.v_ai_icon, width=6).grid(row=2, column=1, sticky="w", padx=8)
        _label(f, "画像未設定時に使用", fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=3, column=0, columnspan=2, sticky="w", padx=4)

        _label(f, "あなたの絵文字アイコン").grid(row=4, column=0, sticky="w", pady=(6, 0))
        _entry(f, self.v_user_icon, width=6).grid(row=4, column=1, sticky="w", padx=8)
        _label(f, "画像未設定時に使用", fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=5, column=0, columnspan=2, sticky="w", padx=4)

        # アイアイコン画像
        _label(f, "アイのアイコン画像").grid(row=6, column=0, sticky="w", pady=(12, 0))
        ai_img_frame = tk.Frame(f, bg=COLOR_PANEL)
        ai_img_frame.grid(row=7, column=0, columnspan=2, sticky="w")
        _entry(ai_img_frame, self.v_ai_icon_image, width=22).pack(side="left")
        tk.Button(ai_img_frame, text="選択...",
                  bg=COLOR_ACCENT2, fg=COLOR_BG, font=SMALL_FONT, relief="flat",
                  command=lambda: self._pick_image(self.v_ai_icon_image), padx=6
                  ).pack(side="left", padx=6)

        # ユーザーアイコン画像
        _label(f, "あなたのアイコン画像").grid(row=8, column=0, sticky="w", pady=(10, 0))
        user_img_frame = tk.Frame(f, bg=COLOR_PANEL)
        user_img_frame.grid(row=9, column=0, columnspan=2, sticky="w")
        _entry(user_img_frame, self.v_user_icon_image, width=22).pack(side="left")
        tk.Button(user_img_frame, text="選択...",
                  bg=COLOR_ACCENT2, fg=COLOR_BG, font=SMALL_FONT, relief="flat",
                  command=lambda: self._pick_image(self.v_user_icon_image), padx=6
                  ).pack(side="left", padx=6)

        _label(f, "PNG/JPG（32x32推奨）。チャット再起動で反映",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=10, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 0))

        # ペット本体画像
        _label(f, "アイの本体画像").grid(row=11, column=0, sticky="w", pady=(12, 0))
        pet_frame = tk.Frame(f, bg=COLOR_PANEL)
        pet_frame.grid(row=12, column=0, columnspan=2, sticky="w")
        _entry(pet_frame, self.v_pet_image, width=22).pack(side="left")
        tk.Button(pet_frame, text="選択...",
                  bg=COLOR_ACCENT2, fg=COLOR_BG, font=SMALL_FONT, relief="flat",
                  command=lambda: self._pick_image(self.v_pet_image), padx=6
                  ).pack(side="left", padx=6)
        _label(f, "デスクトップに表示される画像。再起動で反映",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=13, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 0))

    # ── 音声・AI タブ
    def _build_voice_tab(self):
        f = self._tab_voice

        self.v_tts_enabled     = tk.BooleanVar()
        self.v_tts_voice       = tk.StringVar()
        self.v_tts_rate        = tk.IntVar()
        self.v_stt_enabled     = tk.BooleanVar()
        self.v_stt_model       = tk.StringVar()
        self.v_semantic_enabled = tk.BooleanVar()
        self.v_moondream       = tk.BooleanVar()

        row = 0

        # TTS
        _label(f, "読み上げ（TTS）", font=HEADER_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1
        tk.Checkbutton(f, text="アイの返事を読み上げる（macOS say）",
                       variable=self.v_tts_enabled,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        _label(f, "音声").grid(row=row, column=0, sticky="w", pady=4)
        voice_frame = tk.Frame(f, bg=COLOR_PANEL)
        voice_frame.grid(row=row, column=1, sticky="w", padx=8)
        for v in ["Kyoko", "Otoya"]:
            tk.Radiobutton(voice_frame, text=v, variable=self.v_tts_voice, value=v,
                           bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                           activebackground=COLOR_PANEL, font=LABEL_FONT
                           ).pack(side="left", padx=4)
        row += 1
        _label(f, "速度").grid(row=row, column=0, sticky="w")
        tk.Scale(f, variable=self.v_tts_rate, from_=100, to=280,
                 orient="horizontal", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 troughcolor=COLOR_INPUT, highlightthickness=0, length=200
                 ).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        _label(f, "速度: 低=ゆっくり、高=速い（デフォルト: 175）",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        row += 1
        tk.Button(f, text="音声テスト",
                  bg=COLOR_ACCENT2, fg=COLOR_BG,
                  font=LABEL_FONT, relief="flat",
                  command=self._test_tts, padx=10, pady=4
                  ).grid(row=row, column=1, sticky="w", padx=8, pady=(0, 8))
        row += 1

        # STT
        _label(f, "音声入力（STT）", font=HEADER_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        tk.Checkbutton(f, text="マイク入力を有効にする（faster-whisper 必要）",
                       variable=self.v_stt_enabled,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        _label(f, "モデルサイズ").grid(row=row, column=0, sticky="w", pady=4)
        model_frame = tk.Frame(f, bg=COLOR_PANEL)
        model_frame.grid(row=row, column=1, sticky="w", padx=8)
        for m in ["tiny", "small", "medium"]:
            tk.Radiobutton(model_frame, text=m, variable=self.v_stt_model, value=m,
                           bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                           activebackground=COLOR_PANEL, font=SMALL_FONT
                           ).pack(side="left", padx=2)
        row += 1
        _label(f, "pip install faster-whisper sounddevice soundfile",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 8))
        row += 1

        # セマンティック検索
        _label(f, "セマンティック記憶検索", font=HEADER_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        tk.Checkbutton(f, text="文章の意味で記憶を検索する（sentence-transformers 必要）",
                       variable=self.v_semantic_enabled,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        _label(f, "pip install sentence-transformers faiss-cpu",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 8))
        row += 1

        # Vision
        _label(f, "画面理解（Vision）", font=HEADER_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        tk.Checkbutton(f, text="Moondream ローカルビジョンモデルを使う（~1.8GB DL）",
                       variable=self.v_moondream,
                       bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                       activebackground=COLOR_PANEL, font=LABEL_FONT
                       ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        _label(f, "pip install transformers torch pillow",
               fg=COLOR_SUBTEXT, font=SMALL_FONT
               ).grid(row=row, column=0, columnspan=2, sticky="w", padx=4)

    def _test_tts(self):
        """設定中の音声でテスト読み上げを行う（バックグラウンドでUIフリーズ回避）"""
        from core.tts import TTSEngine
        import threading
        voice = self.v_tts_voice.get()
        rate  = self.v_tts_rate.get()
        def _bg():
            try:
                engine = TTSEngine(enabled=True, voice=voice, rate=rate)
                engine.speak("こんにちは！アイだよ。聞こえてる？")
            except Exception as e:
                def _show_err():
                    try:
                        if self.winfo_exists():
                            from tkinter import messagebox
                            messagebox.showerror("TTS エラー", str(e), parent=self)
                    except Exception:
                        pass
                try:
                    if self.winfo_exists():
                        self.after(0, _show_err)
                except Exception:
                    pass
        threading.Thread(target=_bg, daemon=True).start()

    # ── 自動学習タブ ────────────────────────────────────────────
    def _build_autolearn_tab(self):
        """
        自動学習タブ。左ペイン：スケジュール設定、右ペイン：ソース一覧管理。
        ソース追加後はリストにリアルタイム反映。
        """
        f = self._tab_autolearn
        f.configure(bg=COLOR_PANEL)
        # タブ全体をスクロール可能にする
        canvas = tk.Canvas(f, bg=COLOR_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=COLOR_PANEL)
        _cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(_cw, width=e.width))

        # ─── スケジュール設定 ──
        tk.Label(inner, text="スケジュール設定", bg=COLOR_PANEL, fg=COLOR_ACCENT,
                 font=HEADER_FONT).pack(anchor="w", padx=12, pady=(12, 4))

        self._al_vars: dict[str, tk.BooleanVar] = {}
        self._al_hour_vars: dict[str, tk.IntVar] = {}
        self._al_min_vars:  dict[str, tk.IntVar] = {}
        self._al_schedules = []
        if self.ai_chan and hasattr(self.ai_chan, "auto_learner"):
            self._al_schedules = self.ai_chan.auto_learner.get_schedule()

        for sched in self._al_schedules:
            sid = sched["id"]
            enabled_var = tk.BooleanVar(value=sched.get("enabled", False))
            hour_var    = tk.IntVar(value=sched.get("hour", 9))
            min_var     = tk.IntVar(value=sched.get("minute", 0))
            self._al_vars[sid]      = enabled_var
            self._al_hour_vars[sid] = hour_var
            self._al_min_vars[sid]  = min_var

            row_f = tk.Frame(inner, bg=COLOR_PANEL)
            row_f.pack(fill="x", padx=12, pady=2)
            tk.Checkbutton(row_f, text=sched["name"], variable=enabled_var,
                           bg=COLOR_PANEL, fg=COLOR_TEXT, selectcolor=COLOR_INPUT,
                           activebackground=COLOR_PANEL,
                           font=LABEL_FONT, width=16, anchor="w"
                           ).pack(side="left")
            tk.Label(row_f, text="時刻:", bg=COLOR_PANEL,
                     fg=COLOR_SUBTEXT, font=SMALL_FONT).pack(side="left", padx=(8, 2))
            tk.Spinbox(row_f, from_=0, to=23, textvariable=hour_var,
                       width=3, bg=COLOR_INPUT, fg=COLOR_TEXT,
                       buttonbackground=COLOR_PANEL, font=LABEL_FONT
                       ).pack(side="left")
            tk.Label(row_f, text=":", bg=COLOR_PANEL,
                     fg=COLOR_TEXT, font=LABEL_FONT).pack(side="left")
            tk.Spinbox(row_f, from_=0, to=59, textvariable=min_var,
                       width=3, bg=COLOR_INPUT, fg=COLOR_TEXT,
                       buttonbackground=COLOR_PANEL, font=LABEL_FONT
                       ).pack(side="left", padx=(0, 8))
            tk.Label(row_f, text=sched.get("note", ""),
                     bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                     font=SMALL_FONT).pack(side="left")

        # ─── ソース入力フォーム ──
        sep = tk.Frame(inner, bg=COLOR_ACCENT2, height=1)
        sep.pack(fill="x", padx=12, pady=(14, 0))
        tk.Label(inner, text="学習ソース管理", bg=COLOR_PANEL, fg=COLOR_ACCENT,
                 font=HEADER_FONT).pack(anchor="w", padx=12, pady=(8, 4))

        input_f = tk.Frame(inner, bg=COLOR_PANEL)
        input_f.pack(fill="x", padx=12, pady=(0, 6))

        # URL入力欄
        self._al_url_var = tk.StringVar()
        url_entry = tk.Entry(input_f, textvariable=self._al_url_var,
                             bg=COLOR_INPUT, fg=COLOR_TEXT,
                             insertbackground=COLOR_ACCENT,
                             relief="flat", font=SMALL_FONT, width=38,
                             highlightbackground=COLOR_ACCENT2, highlightthickness=1)
        url_entry.pack(side="left", ipady=4)
        url_entry.insert(0, "YouTube/Web URL を貼り付け")
        url_entry.bind("<FocusIn>",  lambda e: url_entry.delete(0, "end")
                       if url_entry.get() == "YouTube/Web URL を貼り付け" else None)
        url_entry.bind("<FocusOut>", lambda e: url_entry.insert(0, "YouTube/Web URL を貼り付け")
                       if not url_entry.get() else None)
        url_entry.bind("<Return>", lambda e: self._al_add_url())

        tk.Button(input_f, text="追加", bg=COLOR_ACCENT, fg=COLOR_BG,
                  font=LABEL_FONT, relief="flat",
                  command=self._al_add_url, padx=10, pady=4
                  ).pack(side="left", padx=(6, 0))

        # 種類自動判定の説明
        tk.Label(inner,
                 text="YouTube URL → YouTube学習リスト　Web URL → Webリスト　に自動振り分け",
                 bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=SMALL_FONT
                 ).pack(anchor="w", padx=12, pady=(0, 8))

        # ─── YouTube ソース一覧 ──
        tk.Label(inner, text="YouTube 学習リスト", bg=COLOR_PANEL,
                 fg=COLOR_ACCENT2, font=("Hiragino Sans", 11, "bold")
                 ).pack(anchor="w", padx=12, pady=(4, 2))
        yt_outer = tk.Frame(inner, bg=COLOR_INPUT, bd=0)
        yt_outer.pack(fill="x", padx=12, pady=(0, 8))
        self._yt_list_frame = tk.Frame(yt_outer, bg=COLOR_INPUT)
        self._yt_list_frame.pack(fill="x", padx=2, pady=2)

        # ─── Web ソース一覧 ──
        tk.Label(inner, text="Web 学習リスト", bg=COLOR_PANEL,
                 fg=COLOR_ACCENT2, font=("Hiragino Sans", 11, "bold")
                 ).pack(anchor="w", padx=12, pady=(4, 2))
        web_outer = tk.Frame(inner, bg=COLOR_INPUT, bd=0)
        web_outer.pack(fill="x", padx=12, pady=(0, 8))
        self._web_list_frame = tk.Frame(web_outer, bg=COLOR_INPUT)
        self._web_list_frame.pack(fill="x", padx=2, pady=2)

        # ─── 操作ボタン ──
        sep2 = tk.Frame(inner, bg=COLOR_ACCENT2, height=1)
        sep2.pack(fill="x", padx=12, pady=(4, 8))
        act_f = tk.Frame(inner, bg=COLOR_PANEL)
        act_f.pack(fill="x", padx=12, pady=(0, 8))
        tk.Button(act_f, text="今すぐ学習開始",
                  bg=COLOR_ACCENT, fg=COLOR_BG,
                  font=LABEL_FONT, relief="flat",
                  command=self._run_al_now, padx=12, pady=6
                  ).pack(side="left", padx=(0, 8))
        self._al_status_lbl = tk.Label(act_f, text="",
                                       bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                                       font=SMALL_FONT, wraplength=260,
                                       justify="left")
        self._al_status_lbl.pack(side="left")

        # ─── 学習メモ一覧 ──
        sep3 = tk.Frame(inner, bg=COLOR_ACCENT2, height=1)
        sep3.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(inner, text="学習メモ一覧", bg=COLOR_PANEL,
                 fg=COLOR_ACCENT, font=HEADER_FONT
                 ).pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(inner,
                 text="チャットで「学習メモを覚えて: ○○」と入力すると追加されます",
                 bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=SMALL_FONT
                 ).pack(anchor="w", padx=12, pady=(0, 4))
        self._al_memo_frame = tk.Frame(inner, bg=COLOR_INPUT)
        self._al_memo_frame.pack(fill="x", padx=12, pady=(0, 8))

        # ─── 学習ログ（最新5件） ──
        sep4 = tk.Frame(inner, bg=COLOR_ACCENT2, height=1)
        sep4.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(inner, text="最近の学習ログ", bg=COLOR_PANEL,
                 fg=COLOR_ACCENT, font=HEADER_FONT
                 ).pack(anchor="w", padx=12, pady=(8, 2))
        self._al_log_frame = tk.Frame(inner, bg=COLOR_INPUT)
        self._al_log_frame.pack(fill="x", padx=12, pady=(0, 12))

        # 初期描画
        self._al_refresh_lists()
        self._al_refresh_log()
        self._al_refresh_memos()

    # ── ソース一覧の描画 ───────────────────────────────────────
    def _al_refresh_lists(self):
        """YouTube・Webリストを再描画"""
        if not (self.ai_chan and hasattr(self.ai_chan, "auto_learner")):
            return
        al = self.ai_chan.auto_learner
        self._al_render_source_list(
            self._yt_list_frame, al.get_sources("youtube"), "youtube"
        )
        self._al_render_source_list(
            self._web_list_frame, al.get_sources("web"), "web"
        )

    def _al_render_source_list(self, frame: tk.Frame, sources: list, kind: str):
        """指定フレームにソース行を描画（削除ボタン付き）"""
        for w in frame.winfo_children():
            w.destroy()
        if not sources:
            tk.Label(frame, text="（未登録）",
                     bg=COLOR_INPUT, fg=COLOR_SUBTEXT,
                     font=SMALL_FONT).pack(anchor="w", padx=6, pady=4)
            return
        for url in sources:
            row = tk.Frame(frame, bg=COLOR_INPUT)
            row.pack(fill="x", pady=1)
            # 学習済みかどうか確認してアイコン変更
            status = self._al_get_source_status(url, kind)
            icon  = "✓" if status == "learned" else "・"
            color = "#98E88A" if status == "learned" else COLOR_SUBTEXT
            tk.Label(row, text=icon, bg=COLOR_INPUT,
                     fg=color, font=SMALL_FONT, width=2).pack(side="left")
            tk.Label(row, text=url[:55] + ("…" if len(url) > 55 else ""),
                     bg=COLOR_INPUT, fg=COLOR_TEXT,
                     font=SMALL_FONT, anchor="w"
                     ).pack(side="left", fill="x", expand=True)
            if status:
                tk.Label(row, text=status[:10],
                         bg=COLOR_INPUT, fg=COLOR_SUBTEXT,
                         font=("Hiragino Sans", 8)).pack(side="left", padx=(0, 4))
            tk.Button(row, text="削除", bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
                      font=("Hiragino Sans", 9), relief="flat", padx=4,
                      command=lambda u=url, k=kind: self._al_delete_source(u, k)
                      ).pack(side="right", padx=2)

    def _al_get_source_status(self, url: str, kind: str) -> str:
        """URLの学習済みステータスを返す"""
        if not (self.ai_chan and hasattr(self.ai_chan, "auto_learner")):
            return ""
        log_path = self.ai_chan.auto_learner._log_path
        if not log_path.exists():
            return ""
        import json
        last_ts = ""
        try:
            for line in log_path.read_text("utf-8").splitlines():
                entry = json.loads(line)
                if entry.get("url") == url and entry.get("status") == "ok":
                    if entry.get("ts", "") > last_ts:
                        last_ts = entry["ts"]
        except Exception:
            return ""
        return last_ts[:10] if last_ts else ""

    def _al_refresh_log(self):
        """最近の学習ログ5件を描画"""
        for w in self._al_log_frame.winfo_children():
            w.destroy()
        if not (self.ai_chan and hasattr(self.ai_chan, "auto_learner")):
            return
        log_path = self.ai_chan.auto_learner._log_path
        if not log_path.exists():
            tk.Label(self._al_log_frame, text="（ログなし）",
                     bg=COLOR_INPUT, fg=COLOR_SUBTEXT,
                     font=SMALL_FONT).pack(anchor="w", padx=6, pady=4)
            return
        import json
        entries = []
        try:
            for line in log_path.read_text("utf-8").splitlines():
                if line.strip():
                    entries.append(json.loads(line))
        except Exception:
            pass
        recent = list(reversed(entries))[:5]
        if not recent:
            tk.Label(self._al_log_frame, text="（ログなし）",
                     bg=COLOR_INPUT, fg=COLOR_SUBTEXT,
                     font=SMALL_FONT).pack(anchor="w", padx=6, pady=4)
            return
        for e in recent:
            ok   = e.get("status") == "ok"
            icon = "✓" if ok else "✗"
            col  = "#98E88A" if ok else "#FF8080"
            kind = e.get("kind", "")
            url  = e.get("url", "")[:40]
            ts   = e.get("ts", "")[:16]
            row = tk.Frame(self._al_log_frame, bg=COLOR_INPUT)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=icon, bg=COLOR_INPUT,
                     fg=col, font=SMALL_FONT, width=2).pack(side="left")
            tk.Label(row, text=f"[{kind}] {url}",
                     bg=COLOR_INPUT, fg=COLOR_TEXT,
                     font=SMALL_FONT, anchor="w"
                     ).pack(side="left", fill="x", expand=True)
            tk.Label(row, text=ts, bg=COLOR_INPUT,
                     fg=COLOR_SUBTEXT,
                     font=("Hiragino Sans", 8)).pack(side="right", padx=4)

    def _al_refresh_memos(self):
        """学習メモ一覧を描画"""
        for w in self._al_memo_frame.winfo_children():
            w.destroy()
        if not (self.ai_chan and hasattr(self.ai_chan, "auto_learner")):
            return
        memos = self.ai_chan.auto_learner.get_memos()
        if not memos:
            tk.Label(self._al_memo_frame,
                     text="（メモなし）",
                     bg=COLOR_INPUT, fg=COLOR_SUBTEXT,
                     font=SMALL_FONT).pack(anchor="w", padx=6, pady=4)
            return
        for m in list(reversed(memos))[:10]:
            row = tk.Frame(self._al_memo_frame, bg=COLOR_INPUT)
            row.pack(fill="x", pady=1)
            reviewed = m.get("reviews", 0)
            color = "#98E88A" if reviewed > 0 else COLOR_SUBTEXT
            tk.Label(row, text=f"×{reviewed}",
                     bg=COLOR_INPUT, fg=color,
                     font=("Hiragino Sans", 8), width=4
                     ).pack(side="left")
            tk.Label(row, text=m["text"][:55] + ("…" if len(m["text"]) > 55 else ""),
                     bg=COLOR_INPUT, fg=COLOR_TEXT,
                     font=SMALL_FONT, anchor="w"
                     ).pack(side="left", fill="x", expand=True)
            tk.Label(row, text=m.get("ts", "")[:10],
                     bg=COLOR_INPUT, fg=COLOR_SUBTEXT,
                     font=("Hiragino Sans", 8)).pack(side="right", padx=4)

    # ── ソース追加・削除 ────────────────────────────────────────
    def _al_add_url(self):
        if not (self.ai_chan and hasattr(self.ai_chan, "auto_learner")):
            return
        url = self._al_url_var.get().strip()
        placeholder = "YouTube/Web URL を貼り付け"
        if not url or url == placeholder:
            messagebox.showwarning("入力エラー", "URLを入力してね", parent=self)
            return

        al = self.ai_chan.auto_learner
        # YouTube か Web か自動判定
        from core.youtube_learner import extract_youtube_url
        from core.web_learner import is_web_url
        if extract_youtube_url(url):
            al.add_source("youtube", url)
            kind_label = "YouTube"
        elif is_web_url(url):
            al.add_source("web", url)
            kind_label = "Web"
        else:
            messagebox.showwarning("URL エラー",
                                   "YouTube または Web の URL を入力してね",
                                   parent=self)
            return

        self._al_url_var.set("")
        self._al_refresh_lists()
        self._al_status_lbl.configure(
            fg="#98E88A",
            text=f"{kind_label} リストに追加したよ！\n{url[:50]}"
        )

    def _al_delete_source(self, url: str, kind: str):
        if not (self.ai_chan and hasattr(self.ai_chan, "auto_learner")):
            return
        if not messagebox.askyesno("削除確認",
                                   f"このソースを削除する？\n{url[:60]}",
                                   parent=self):
            return
        self.ai_chan.auto_learner.remove_source(kind, url)
        self._al_refresh_lists()
        self._al_status_lbl.configure(
            fg=COLOR_SUBTEXT, text="削除したよ。"
        )

    # ── 今すぐ学習 ──────────────────────────────────────────────
    def _run_al_now(self):
        if not (self.ai_chan and hasattr(self.ai_chan, "auto_learner")):
            messagebox.showwarning("エラー", "アイが起動していないよ", parent=self)
            return
        al = self.ai_chan.auto_learner
        if not al.get_sources("youtube") and not al.get_sources("web"):
            messagebox.showwarning("ソースなし",
                                   "学習ソースが登録されていないよ。\nURLを追加してから実行してね。",
                                   parent=self)
            return

        self._al_status_lbl.configure(fg=COLOR_ACCENT, text="学習中…しばらく待ってね")
        import threading

        def _bg():
            results = []
            if al.get_sources("youtube"):
                r = al.run_now("youtube", max_items=3)
                if r:
                    results.append(r)
            if al.get_sources("web"):
                r = al.run_now("web", max_items=3)
                if r:
                    results.append(r)
            msg = "\n".join(results) or "学習するコンテンツがなかったよ。"

            def _done():
                self._al_status_lbl.configure(fg="#98E88A", text="学習完了！")
                self._al_refresh_lists()
                self._al_refresh_log()
                messagebox.showinfo("学習完了", msg, parent=self)

            self.after(0, _done)

        threading.Thread(target=_bg, daemon=True).start()

    def _pick_image(self, var: tk.StringVar):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self,
            title="画像ファイルを選択",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.gif"),
                       ("All files", "*.*")]
        )
        if path:
            var.set(path)

    # ─── 値の読み込み ──────────────────────────────────────────────

    def _load_values(self):
        try:
            cfg = json.loads(self.cfg_path.read_text("utf-8"))
        except Exception:
            cfg = {}

        llm  = cfg.get("llm", {})
        auto = cfg.get("autonomous", {})
        mem  = cfg.get("memory", {})
        sec  = cfg.get("security", {})

        self.v_max_tokens.set(llm.get("max_tokens", 200))
        self.v_max_sentences.set(llm.get("max_sentences", 6))
        self.v_temperature.set(llm.get("temperature", 0.7))

        self.v_idle_minutes.set(auto.get("idle_minutes", 30))
        self.v_allow_network.set(auto.get("allow_network", False))
        self.v_weather_city.set(auto.get("weather_city", "Tokyo"))
        self.v_schedule_en.set(auto.get("schedule_enabled", True))
        self.v_clipboard_watch.set(auto.get("clipboard_watch", False))

        self.v_short_max.set(mem.get("short_term_max", 20))
        self.v_encrypt.set(sec.get("encrypt_database", True))

        ui = cfg.get("ui", {})
        self.v_ai_icon.set(ui.get("ai_icon", "💗"))
        self.v_user_icon.set(ui.get("user_icon", "👤"))
        self.v_user_name.set(ui.get("user_name", "あなた"))
        self.v_pet_image.set(ui.get("pet_image", ""))
        self.v_ai_icon_image.set(ui.get("ai_icon_image", ""))
        self.v_user_icon_image.set(ui.get("user_icon_image", ""))

        tts = cfg.get("tts", {})
        self.v_tts_enabled.set(tts.get("enabled", False))
        self.v_tts_voice.set(tts.get("voice", "Kyoko"))
        self.v_tts_rate.set(tts.get("rate", 175))

        stt = cfg.get("stt", {})
        self.v_stt_enabled.set(stt.get("enabled", False))
        self.v_stt_model.set(stt.get("model_size", "small"))

        self.v_semantic_enabled.set(cfg.get("semantic_search", {}).get("enabled", False))
        self.v_moondream.set(cfg.get("vision", {}).get("enable_moondream", False))

        # 記念日リスト
        self._refresh_anniv_list()

    def _refresh_anniv_list(self):
        self.anniv_lb.delete(0, "end")
        if self.ai_chan and hasattr(self.ai_chan, "anniversary"):
            for item in self.ai_chan.anniversary.list_all():
                kind = "🎂" if item.get("is_birthday") else "🎉"
                self.anniv_lb.insert(
                    "end",
                    f"{kind} {item['label']}  {item['month']}/{item['day']}"
                )

    def _add_anniversary(self):
        label = self.v_anniv_label.get().strip()
        if not label:
            messagebox.showwarning("入力エラー", "名前を入力してください", parent=self)
            return
        month = self.v_anniv_month.get()
        day   = self.v_anniv_day.get()
        bday  = self.v_anniv_bday.get()

        if self.ai_chan and hasattr(self.ai_chan, "anniversary"):
            self.ai_chan.anniversary.add(label, month, day, is_birthday=bday)
            self._refresh_anniv_list()
            self.v_anniv_label.set("")

    def _remove_anniversary(self):
        sel = self.anniv_lb.curselection()
        if not sel or not (self.ai_chan and hasattr(self.ai_chan, "anniversary")):
            return
        idx = sel[0]
        items = self.ai_chan.anniversary.list_all()
        if idx < len(items):
            self.ai_chan.anniversary.remove(items[idx]["id"])
            self._refresh_anniv_list()

    # ─── 保存 ─────────────────────────────────────────────────────

    def _save_and_close(self):
        try:
            cfg = json.loads(self.cfg_path.read_text("utf-8"))
        except Exception:
            cfg = {}

        cfg.setdefault("llm", {})
        cfg["llm"]["max_tokens"]    = self.v_max_tokens.get()
        cfg["llm"]["max_sentences"] = self.v_max_sentences.get()
        cfg["llm"]["temperature"]   = round(self.v_temperature.get(), 2)

        cfg.setdefault("autonomous", {})
        cfg["autonomous"]["idle_minutes"]   = self.v_idle_minutes.get()
        cfg["autonomous"]["allow_network"]  = self.v_allow_network.get()
        cfg["autonomous"]["weather_city"]   = self.v_weather_city.get()
        cfg["autonomous"]["schedule_enabled"] = self.v_schedule_en.get()
        cfg["autonomous"]["clipboard_watch"] = self.v_clipboard_watch.get()

        cfg.setdefault("memory", {})
        cfg["memory"]["short_term_max"] = self.v_short_max.get()

        cfg.setdefault("security", {})
        cfg["security"]["encrypt_database"] = self.v_encrypt.get()

        cfg.setdefault("ui", {})
        cfg["ui"]["ai_icon"]        = self.v_ai_icon.get() or "💗"
        cfg["ui"]["user_icon"]      = self.v_user_icon.get() or "👤"
        cfg["ui"]["user_name"]      = self.v_user_name.get() or "あなた"
        cfg["ui"]["pet_image"]      = self.v_pet_image.get()
        cfg["ui"]["ai_icon_image"]  = self.v_ai_icon_image.get()
        cfg["ui"]["user_icon_image"] = self.v_user_icon_image.get()

        cfg.setdefault("tts", {})
        cfg["tts"]["enabled"] = self.v_tts_enabled.get()
        cfg["tts"]["voice"]   = self.v_tts_voice.get()
        cfg["tts"]["rate"]    = self.v_tts_rate.get()

        cfg.setdefault("stt", {})
        cfg["stt"]["enabled"]    = self.v_stt_enabled.get()
        cfg["stt"]["model_size"] = self.v_stt_model.get()

        cfg.setdefault("semantic_search", {})
        cfg["semantic_search"]["enabled"] = self.v_semantic_enabled.get()

        cfg.setdefault("vision", {})
        cfg["vision"]["enable_moondream"] = self.v_moondream.get()

        self.cfg_path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8"
        )

        # ライブ反映できる設定を即時更新
        if self.ai_chan:
            self.ai_chan._max_sentences = cfg["llm"]["max_sentences"]
            self.ai_chan._idle_minutes  = cfg["autonomous"]["idle_minutes"]
            self.ai_chan._allow_network = cfg["autonomous"]["allow_network"]
            self.ai_chan._weather_city  = cfg["autonomous"]["weather_city"]
            self.ai_chan._sched_enabled = cfg["autonomous"]["schedule_enabled"]
            if hasattr(self.ai_chan, "memory"):
                self.ai_chan.memory.short_term_max = cfg["memory"]["short_term_max"]
            # TTS ライブ反映
            if hasattr(self.ai_chan, "tts"):
                self.ai_chan.tts.enabled = cfg["tts"]["enabled"]
                self.ai_chan.tts.voice   = cfg["tts"]["voice"]
                self.ai_chan.tts.rate    = cfg["tts"]["rate"]
            try:
                self.ai_chan.llm.config["max_tokens"]   = cfg["llm"]["max_tokens"]
                self.ai_chan.llm.config["temperature"]  = cfg["llm"]["temperature"]
            except Exception:
                pass
            # 自動学習スケジュールのライブ反映
            if hasattr(self.ai_chan, "auto_learner"):
                al = self.ai_chan.auto_learner
                for sched in self._al_schedules:
                    sid = sched["id"]
                    if sid in self._al_vars:
                        al.set_schedule_enabled(sid, self._al_vars[sid].get())
                    if sid in self._al_hour_vars and sid in self._al_min_vars:
                        al.update_schedule(
                            sid,
                            self._al_hour_vars[sid].get(),
                            self._al_min_vars[sid].get(),
                            sched.get("days", [0, 1, 2, 3, 4]),
                        )

        messagebox.showinfo("保存完了", "設定を保存したよ！\n（一部は再起動後に反映されます）",
                            parent=self)
        self.destroy()

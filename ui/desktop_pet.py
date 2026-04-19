"""
デスクトップペット UI
アイがデスクトップ上に表示され、アニメーションし、
クリックで会話できるウィンドウを提供します。
"""
from __future__ import annotations
import logging
import tkinter as tk
from tkinter import ttk, filedialog
import threading
import math
import time
import sys
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

IS_MAC = platform.system() == "Darwin"
# ウィンドウ背景色（ペットウィンドウの透過用）
WIN_BG = "#F5F3F8"

try:
    from PIL import Image, ImageTk, ImageFilter, ImageEnhance
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from ui.chat_widgets import (
    CommandPalette,
    EmotionBar,
    FeedbackButtons,
    KeyboardShortcuts,
    MessageBubble,
    TypewriterMixin,
    TypingIndicator,
    detect_dark_mode,
    get_theme_colors,
)


def _all_children(widget):
    """winfo_descendants の代替（Python 3.13 で廃止されたため再帰実装）"""
    result = []
    for child in widget.winfo_children():
        result.append(child)
        result.extend(_all_children(child))
    return result

# アイ画像の候補パス（上から順に探索）
IMAGE_CANDIDATES = [
    BASE_DIR / "assets" / "ai_chan.png",
    BASE_DIR / "assets" / "ai_chan.jpg",
    BASE_DIR / "assets" / "ai_chan.gif",
    BASE_DIR / "config"  / "assets" / "ai_chan.png",
]

# 表情差分画像のベースパス（{emotion} を置換して使う）
EXPRESSION_CANDIDATES = [
    BASE_DIR / "assets" / "ai_chan_{emotion}.png",
    BASE_DIR / "assets" / "expressions" / "ai_chan_{emotion}.png",
]

# ──────── カラーパレット（Clean × Soft — Cotomo inspired） ────────
COLOR_BG       = "#FFFFFF"   # 白背景（クリーン・高視認性）
COLOR_PANEL    = "#F5F3F8"   # ソフトラベンダーグレー（パネル）
COLOR_INPUT    = "#FFFFFF"   # 入力欄（白）
COLOR_ACCENT   = "#6C5CE7"   # メインアクセント（上品な紫）
COLOR_ACCENT2  = "#A29BFE"   # セカンドアクセント（明るい紫）
COLOR_TEXT     = "#2D2D3F"   # ダークネイビー（テキスト・高コントラスト）
COLOR_SUBTEXT  = "#8E8EA0"   # ミューテッドグレー（サブテキスト）
COLOR_BUBBLE   = "#F0EEFF"   # AIバブル（うすいラベンダー）
COLOR_USER_BUB = "#E8F4FD"   # ユーザーバブル（うすいブルー）
COLOR_BORDER   = "#E5E5EA"   # ボーダー（ソフトグレー）
COLOR_SUCCESS  = "#34C759"   # アクティブ（グリーン）
COLOR_DANGER   = "#FF3B30"   # 録音中（レッド）
COLOR_GLOW     = "#EDE9FE"   # フォーカス（うすい紫）

PET_WIDTH  = 220
PET_HEIGHT = 260
CHAT_WIDTH = 400
CHAT_HEIGHT= 560


def find_character_image(custom_path: str = "") -> Path | None:
    # 設定で指定されたカスタムパスを優先
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
    for p in IMAGE_CANDIDATES:
        if p.exists():
            return p
    return None


class SpeechBubble(tk.Toplevel):
    """アイの台詞吹き出し（クリーン・ミニマル）"""

    def __init__(self, parent, text: str, x: int, y: int):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(bg=COLOR_BORDER)

        # ボーダー効果: 外側フレーム → 内側フレームで1pxボーダーを再現
        outer = tk.Frame(self, bg=COLOR_BORDER, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=COLOR_BG, padx=18, pady=14)
        inner.pack()

        label = tk.Label(
            inner, text=text, bg=COLOR_BG, fg=COLOR_TEXT,
            font=("Hiragino Sans", 13), wraplength=280, justify="left"
        )
        label.pack()

        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry(f"+{x - w//2}+{y - h - 10}")

        # フェードイン
        self._fade_in()
        # 4秒後にフェードアウト
        self.after(4000, self._fade_out)

    def _fade_in(self, alpha=0.0):
        try:
            if not self.winfo_exists():
                return
            if alpha < 0.92:
                self.attributes("-alpha", alpha)
                self.after(20, lambda: self._fade_in(alpha + 0.08))
            else:
                self.attributes("-alpha", 0.92)
        except tk.TclError:
            return

    def _fade_out(self, alpha=0.92):
        try:
            if not self.winfo_exists():
                return
            if alpha > 0.0:
                self.attributes("-alpha", alpha)
                self.after(30, lambda: self._fade_out(alpha - 0.08))
            else:
                self.destroy()
        except tk.TclError:
            return


class ChatWindow(tk.Toplevel, TypewriterMixin):
    """チャットウィンドウ"""

    def __init__(self, parent, ai_chan_instance, pet=None):
        super().__init__(parent)
        self._ai_chan_direct = ai_chan_instance
        self._pet   = pet  # DesktopPet インスタンス（アイドルタイマーリセット用）

        # ダークモード検出とテーマ色
        self._dark_mode = detect_dark_mode()
        self._theme = get_theme_colors(dark=self._dark_mode)

        # フォントサイズ（Ctrl++/- で変更可能）
        self._font_size: int = 12
        self._font_name: str = "Hiragino Sans"

        # アイコン・名前設定を読み込む（ai_chan が None でも安全にデフォルト使用）
        _ai = self.ai_chan  # property 経由で pet からも解決
        ui_cfg = {}
        if _ai and hasattr(_ai, "settings"):
            ui_cfg = _ai.settings.get("ui", {})
        self._ai_icon   = ui_cfg.get("ai_icon",   "💗")
        self._user_icon = ui_cfg.get("user_icon",  "👤")
        self._user_name = ui_cfg.get("user_name",  "あなた")

        # 画像アイコンを読み込む（Pillow 必須）
        self._ai_icon_photo   = None
        self._user_icon_photo = None
        if PILLOW_AVAILABLE:
            # 1) 明示的に ai_icon_image が設定されていればそれを使う
            # 2) そうでなければ pet_image の頭部分を自動クロップして使う
            self._ai_icon_photo = self._load_icon_image(ui_cfg.get("ai_icon_image", ""))
            if self._ai_icon_photo is None:
                self._ai_icon_photo = self._load_head_icon_from_pet_image(
                    ui_cfg.get("pet_image", "")
                )
            self._user_icon_photo = self._load_icon_image(ui_cfg.get("user_icon_image", ""))
        self.title("アイとおはなし")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self.minsize(350, 400)
        self.attributes("-topmost", True)
        # 画面中央に安全配置
        self.update_idletasks()
        sw = self.winfo_screenwidth() or 1440
        sh = self.winfo_screenheight() or 900
        cx = max(0, (sw - CHAT_WIDTH) // 2)
        cy = max(30, (sh - CHAT_HEIGHT) // 2)
        self.geometry(f"{CHAT_WIDTH}x{CHAT_HEIGHT}+{cx}+{cy}")
        self.bind("<Configure>", self._on_window_resize)

        self._build_ui()
        # macOS overrideredirect 親ウィンドウ配下でも入力欄にフォーカスを当てる
        self.after(50, self._focus_input)
        # 開いた時はLLMに自然な挨拶を生成させる
        self._generate_open_greeting()

    @property
    def ai_chan(self):
        """ai_chan を動的に解決する。
        初期化時に None が渡されても、後から DesktopPet に ai_chan がセットされれば
        自動的にそちらを参照する。
        """
        if self._ai_chan_direct is not None:
            return self._ai_chan_direct
        if self._pet is not None and getattr(self._pet, "ai_chan", None) is not None:
            return self._pet.ai_chan
        return None

    @ai_chan.setter
    def ai_chan(self, value):
        self._ai_chan_direct = value
        # ai_chan が後からセットされた場合、アイコン画像を再読み込みする
        if value is not None and hasattr(value, "settings"):
            self._reload_icons_if_needed(value)

    def _reload_icons_if_needed(self, ai):
        """ai_chan が後からセットされた時にアイコン画像を再読み込みする。
        既に読み込み済みの場合はスキップ。"""
        try:
            ui_cfg = ai.settings.get("ui", {})

            # メッセージアイコン
            if self._ai_icon_photo is None and PILLOW_AVAILABLE:
                self._ai_icon_photo = self._load_icon_image(
                    ui_cfg.get("ai_icon_image", "")
                )
                if self._ai_icon_photo is None:
                    self._ai_icon_photo = self._load_head_icon_from_pet_image(
                        ui_cfg.get("pet_image", "")
                    )
            if self._user_icon_photo is None and PILLOW_AVAILABLE:
                self._user_icon_photo = self._load_icon_image(
                    ui_cfg.get("user_icon_image", "")
                )

            # アイコン・名前もデフォルトのままなら更新
            if self._ai_icon == "💗":
                self._ai_icon = ui_cfg.get("ai_icon", "💗")
            if self._user_name == "あなた":
                self._user_name = ui_cfg.get("user_name", "あなた")

            # タイトルバーアイコン
            if self._title_head_photo is None and PILLOW_AVAILABLE:
                pet_img_path = ui_cfg.get("pet_image", "")
                self._title_head_photo = self._load_head_icon_from_pet_image(
                    pet_img_path, size=28
                )
                if self._title_head_photo is not None:
                    # タイトルバーにアイコンを追加（既存レイアウトに差し込み）
                    for child in self.winfo_children():
                        if isinstance(child, tk.Frame) and child.cget("height") == 48:
                            title_icon = tk.Label(
                                child, image=self._title_head_photo,
                                bg=COLOR_PANEL
                            )
                            title_icon.image = self._title_head_photo
                            title_icon.pack(side="left", padx=(16, 0), before=child.winfo_children()[0] if child.winfo_children() else None)
                            break
        except Exception as e:
            print(f"[Chat] アイコン再読み込み失敗: {e}", flush=True)

    def _load_icon_image(self, path: str, size: int = 36):
        """アイコン画像を読み込んでリサイズする。失敗したら None を返す"""
        if not path:
            return None
        try:
            img = Image.open(path).convert("RGBA")
            img = img.resize((size, size), Image.LANCZOS)
            # 透明部分を背景色と合成
            r = int(COLOR_BG[1:3], 16)
            g = int(COLOR_BG[3:5], 16)
            b = int(COLOR_BG[5:7], 16)
            bg = Image.new("RGBA", img.size, (r, g, b, 255))
            composited = Image.alpha_composite(bg, img)
            photo = ImageTk.PhotoImage(composited.convert("RGB"))
            return photo
        except Exception as e:
            print(f"[Chat] アイコン画像読み込みエラー: {e}", flush=True)
            return None

    def _load_head_icon_from_pet_image(self, path: str, size: int = 40):
        """
        pet_image（全身イラスト）から頭部分だけを正方形にクロップして
        チャットアイコンに使う。失敗時は None を返す。
        """
        if not path:
            return None
        try:
            img = Image.open(path).convert("RGBA")
            W, H = img.size
            # 頭部分は上から約 12%〜52% あたり、横は中央寄り約 25%〜75%
            # ちびキャラを想定した経験値。画像によってはズレるが安全側でクロップ。
            top    = int(H * 0.08)
            bottom = int(H * 0.52)
            left   = int(W * 0.22)
            right  = int(W * 0.78)
            head = img.crop((left, top, right, bottom))

            # 正方形にパディング（白い余白は透明に保つ）
            side = max(head.size)
            square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
            square.paste(head, ((side - head.width) // 2, (side - head.height) // 2))

            # チャットの背景色にオーバーレイ合成
            r = int(COLOR_BG[1:3], 16)
            g = int(COLOR_BG[3:5], 16)
            b = int(COLOR_BG[5:7], 16)
            bg = Image.new("RGBA", square.size, (r, g, b, 255))
            composited = Image.alpha_composite(bg, square)
            composited = composited.resize((size, size), Image.LANCZOS)

            photo = ImageTk.PhotoImage(composited.convert("RGB"))
            return photo
        except Exception as e:
            print(f"[Chat] 頭部アイコン生成エラー: {e}", flush=True)
            return None

    def _generate_open_greeting(self):
        """チャットウィンドウを開いた時の自然な挨拶をLLMで生成"""
        if self.ai_chan and self.ai_chan.llm_loaded:
            def _gen():
                try:
                    prompt = self.ai_chan.build_greeting_prompt("chat_open")
                    resp = self.ai_chan.chat(prompt)
                except Exception:
                    resp = "どうしたの？"
                try:
                    if self.winfo_exists():
                        self.after(0, lambda: self._safe_add_message("アイ", resp, True))
                except tk.TclError:
                    pass
            threading.Thread(target=_gen, daemon=True).start()
        else:
            self._add_message("アイ", "どうしたの？", is_ai=True)

    def _build_ui(self):
        # ══════════════════════════════════════════════════════
        # タイトルバー（ライト・クリーン）
        # ══════════════════════════════════════════════════════
        title_bar = tk.Frame(self, bg=COLOR_BG, height=48)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        # タイトルバー用の頭部アイコン
        self._title_head_photo = None
        if PILLOW_AVAILABLE and self.ai_chan and hasattr(self.ai_chan, "settings"):
            pet_img_path = self.ai_chan.settings.get("ui", {}).get("pet_image", "")
            self._title_head_photo = self._load_head_icon_from_pet_image(
                pet_img_path, size=30
            )

        if self._title_head_photo is not None:
            title_icon = tk.Label(
                title_bar, image=self._title_head_photo, bg=COLOR_BG
            )
            title_icon.image = self._title_head_photo  # GC 防止
            title_icon.pack(side="left", padx=(16, 8), pady=9)

        # タイトルテキスト
        tk.Label(
            title_bar, text="アイ",
            bg=COLOR_BG, fg=COLOR_ACCENT,
            font=("Hiragino Sans", 15, "bold")
        ).pack(side="left", padx=(4 if self._title_head_photo else 16, 0), pady=9)

        # オンラインステータスドット
        tk.Label(
            title_bar, text="●", bg=COLOR_BG, fg=COLOR_SUCCESS,
            font=("Arial", 7)
        ).pack(side="left", padx=(6, 0), pady=9)

        # 閉じるボタン（ホバー効果付き）
        close_btn = tk.Label(
            title_bar, text="✕", bg=COLOR_BG, fg=COLOR_SUBTEXT,
            font=("Arial", 14), cursor="hand2", padx=8
        )
        close_btn.pack(side="right", padx=(0, 12))
        close_btn.bind("<Button-1>", lambda e: self.withdraw())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg=COLOR_DANGER))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg=COLOR_SUBTEXT))

        # タイトルバー下の区切り線
        tk.Frame(self, bg=COLOR_BORDER, height=1).pack(fill="x")

        # ══════════════════════════════════════════════════════
        # チャット履歴エリア（白背景・広々）
        # ══════════════════════════════════════════════════════
        chat_frame = tk.Frame(self, bg=COLOR_BG)
        chat_frame.pack(fill="both", expand=True, padx=0, pady=0)

        self.chat_canvas = tk.Canvas(
            chat_frame, bg=COLOR_BG, highlightthickness=0, bd=0
        )
        scrollbar = ttk.Scrollbar(chat_frame, orient="vertical",
                                   command=self.chat_canvas.yview)
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.chat_canvas.pack(side="left", fill="both", expand=True)

        self.msg_frame = tk.Frame(self.chat_canvas, bg=COLOR_BG)
        self.canvas_window = self.chat_canvas.create_window(
            (0, 0), window=self.msg_frame, anchor="nw"
        )
        self.msg_frame.bind("<Configure>", self._on_frame_configure)
        self.chat_canvas.bind("<Configure>", self._on_canvas_configure)

        # ══════════════════════════════════════════════════════
        # ステータスバー（感情 + 音声ステータス）
        # ══════════════════════════════════════════════════════
        self.emotion_var = tk.StringVar(value="😊 元気")
        status_bar = tk.Frame(self, bg=COLOR_PANEL, height=28)
        status_bar.pack(fill="x")
        status_bar.pack_propagate(False)
        tk.Label(
            status_bar, textvariable=self.emotion_var,
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
            font=("Hiragino Sans", 10)
        ).pack(side="left", padx=16)

        # 音声ステータスインジケータ
        self._voice_status_var = tk.StringVar(value="")
        self._voice_status_label = tk.Label(
            status_bar, textvariable=self._voice_status_var,
            bg=COLOR_PANEL, fg=COLOR_DANGER,
            font=("Hiragino Sans", 10, "bold")
        )
        self._voice_status_label.pack(side="right", padx=16)

        # ══════════════════════════════════════════════════════
        # 入力エリア（Cotomo風・クリーンデザイン）
        # ══════════════════════════════════════════════════════
        input_separator = tk.Frame(self, bg=COLOR_BORDER, height=1)
        input_separator.pack(fill="x")

        input_frame = tk.Frame(self, bg=COLOR_BG, pady=10)
        input_frame.pack(fill="x", side="bottom")

        # 入力欄 + 送信ボタン行
        entry_row = tk.Frame(input_frame, bg=COLOR_BG)
        entry_row.pack(fill="x", padx=14)

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            entry_row, textvariable=self.input_var,
            bg=COLOR_PANEL, fg=COLOR_TEXT, insertbackground=COLOR_ACCENT,
            font=("Hiragino Sans", 14), relief="flat",
            highlightbackground=COLOR_BORDER, highlightthickness=1,
            highlightcolor=COLOR_ACCENT,
        )
        self.input_entry.pack(side="left", fill="x", expand=True,
                               padx=(0, 8), ipady=10)
        self.input_entry.bind("<Return>", self._on_send)

        send_btn = tk.Button(
            entry_row, text="➤",
            bg=COLOR_ACCENT, fg="#FFFFFF",
            font=("Arial", 16, "bold"),
            relief="flat", cursor="hand2",
            command=self._on_send,
            padx=12, pady=8,
            activebackground=COLOR_ACCENT2, activeforeground="#FFFFFF",
        )
        send_btn.pack(side="right")

        # ── ツールボタン行（入力欄の下） ──
        tool_row = tk.Frame(input_frame, bg=COLOR_BG)
        tool_row.pack(fill="x", padx=14, pady=(8, 0))

        # マイクボタン（大きく目立つ）
        self._mic_btn = tk.Button(
            tool_row, text="🎤 録音",
            bg=COLOR_PANEL, fg=COLOR_TEXT,
            font=("Hiragino Sans", 11),
            relief="flat", cursor="hand2",
            command=self._toggle_mic,
            padx=12, pady=5,
            highlightthickness=0,
            activebackground=COLOR_GLOW,
        )
        self._mic_btn.pack(side="left", padx=(0, 6))
        self._mic_recording = False
        self._mic_processing = False

        # 連続リスニングボタン
        self._continuous_btn = tk.Button(
            tool_row, text="♾ 連続",
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
            font=("Hiragino Sans", 11),
            relief="flat", cursor="hand2",
            command=self._toggle_continuous_mode,
            padx=12, pady=5,
            highlightthickness=0,
            activebackground=COLOR_GLOW,
        )
        self._continuous_btn.pack(side="left", padx=(0, 6))
        self._continuous_mode = False

        # 画像ボタン
        self._img_btn = tk.Button(
            tool_row, text="🖼 画像",
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
            font=("Hiragino Sans", 11),
            relief="flat", cursor="hand2",
            command=self._on_image_select,
            padx=12, pady=5,
            highlightthickness=0,
            activebackground=COLOR_GLOW,
        )
        self._img_btn.pack(side="left", padx=(0, 6))

        self._update_mic_button_visibility()

        # キーボードショートカット
        self.bind("<Control-m>", lambda e: self._toggle_mic())
        self.input_entry.bind("<Control-m>", lambda e: self._toggle_mic())
        self.bind("<Control-Shift-M>", lambda e: self._toggle_continuous_mode())
        self.input_entry.bind("<Control-Shift-M>", lambda e: self._toggle_continuous_mode())

        # TTS 読み上げ中インジケータの定期チェックを開始
        self._start_voice_status_poll()

        # ── 新機能ウィジェット群 ────────────────────────────

        # 感情バー（グラデーション）
        self._emotion_bar = EmotionBar(self, bg=self._theme["panel"], height=4)
        self._emotion_bar.pack(fill="x", before=input_separator)

        # 入力中インジケータ
        self._typing_indicator = TypingIndicator(
            self.msg_frame, bg=self._theme["bg"], fg=self._theme["subtext"]
        )

        # フォントサイズ変更ショートカット
        self.bind("<Control-plus>", lambda e: self._change_font_size(1))
        self.bind("<Control-minus>", lambda e: self._change_font_size(-1))
        self.bind("<Control-equal>", lambda e: self._change_font_size(1))
        self.input_entry.bind("<Control-plus>", lambda e: self._change_font_size(1))
        self.input_entry.bind("<Control-minus>", lambda e: self._change_font_size(-1))
        self.input_entry.bind("<Control-equal>", lambda e: self._change_font_size(1))

        # キーボードショートカット一括バインド
        self._command_map = {
            "chat": "チャット送信",
            "mic": "マイク切替",
            "emotion": "感情表示",
            "palette": "コマンドパレット",
            "zoom_in": "フォント拡大",
            "zoom_out": "フォント縮小",
            "image": "画像分析",
            "shortcuts": "ショートカット一覧",
        }

        # コマンドパレット
        self.bind("<Control-k>", lambda e: self._open_command_palette())
        self.input_entry.bind("<Control-k>", lambda e: self._open_command_palette())

        # 追加ショートカット
        self.bind("<Control-e>", lambda e: self._show_emotion_detail())
        self.input_entry.bind("<Control-e>", lambda e: self._show_emotion_detail())

    def _now_timestamp(self) -> str:
        """現在時刻を HH:MM 形式で返す。"""
        return datetime.now().strftime("%H:%M")

    def _change_font_size(self, delta: int) -> None:
        """フォントサイズを変更して全メッセージに反映する (#36)。"""
        self._font_size = max(8, min(24, self._font_size + delta))
        for widget in _all_children(self.msg_frame):
            if isinstance(widget, tk.Label):
                try:
                    current_font = widget.cget("font")
                    if isinstance(current_font, str) and "bold" in current_font:
                        widget.configure(font=(self._font_name, self._font_size, "bold"))
                    elif isinstance(current_font, tuple) and len(current_font) > 2 and "bold" in current_font:
                        widget.configure(font=(self._font_name, self._font_size, "bold"))
                    else:
                        widget.configure(font=(self._font_name, self._font_size))
                except Exception:
                    pass

    def _on_image_select(self) -> None:
        """ファイルダイアログで画像を選択して AI に分析させる (#34)。"""
        filetypes = [
            ("画像ファイル", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
            ("すべて", "*.*"),
        ]
        path = filedialog.askopenfilename(
            title="画像を選択",
            filetypes=filetypes,
            parent=self,
        )
        if not path:
            return
        self._add_message(self._user_name, f"[画像: {Path(path).name}]", is_ai=False)

        def _analyze() -> None:
            response = "画像分析機能は準備中だよ"
            try:
                if self.ai_chan and hasattr(self.ai_chan, "analyze_image"):
                    response = self.ai_chan.analyze_image(path)
                elif self.ai_chan and hasattr(self.ai_chan, "image_analyzer"):
                    response = self.ai_chan.image_analyzer.analyze(path)
            except Exception as exc:
                logger.warning("画像分析エラー: %s", exc)
                response = f"画像を見れなかったよ...({exc})"

            def _apply() -> None:
                try:
                    if self.winfo_exists():
                        self._add_message("アイ", response, is_ai=True)
                except tk.TclError:
                    pass
            try:
                self.after(0, _apply)
            except tk.TclError:
                pass

        threading.Thread(target=_analyze, daemon=True).start()

    def _open_command_palette(self) -> None:
        """コマンドパレットを開く (#39)。"""
        CommandPalette(self, self._command_map, self._run_command)

    def _run_command(self, cmd_key: str) -> None:
        """コマンドパレットから選択されたコマンドを実行する。"""
        actions = {
            "chat": lambda: self.input_entry.focus_set(),
            "mic": lambda: self._toggle_mic(),
            "emotion": lambda: self._show_emotion_detail(),
            "palette": lambda: self._open_command_palette(),
            "zoom_in": lambda: self._change_font_size(1),
            "zoom_out": lambda: self._change_font_size(-1),
            "image": lambda: self._on_image_select(),
            "shortcuts": lambda: KeyboardShortcuts.show_help(self),
        }
        action = actions.get(cmd_key)
        if action:
            action()

    def _show_emotion_detail(self) -> None:
        """感情の詳細を表示する。"""
        if self.ai_chan and hasattr(self.ai_chan, "emotion"):
            text = self.ai_chan.emotion.get_display_string()
            self._add_message("アイ", f"今の気持ち: {text}", is_ai=True)

    def _focus_input(self):
        """入力欄にフォーカスを確実にセットする（macOS 対策）"""
        try:
            self.lift()
            self.focus_force()
            self.input_entry.focus_set()
        except (tk.TclError, AttributeError):
            pass

    def _update_mic_button_visibility(self):
        """STT が有効な場合のみマイクボタン・連続モードボタンを表示する。
        設定ファイルで enabled=true なら常に表示（whisperロード失敗時も入力可能にする）。
        """
        stt_enabled = False
        if self.ai_chan and hasattr(self.ai_chan, "settings"):
            stt_enabled = self.ai_chan.settings.get("stt", {}).get("enabled", False)

        # TTS 設定も確認: TTS が有効なら音声操作ボタンも表示する
        tts_enabled = False
        if self.ai_chan and hasattr(self.ai_chan, "settings"):
            tts_enabled = self.ai_chan.settings.get("tts", {}).get("enabled", False)

        show_voice_buttons = stt_enabled or tts_enabled

        if show_voice_buttons:
            try:
                self._mic_btn.pack(side="right", padx=(0, 4))
                self._continuous_btn.pack(side="right", padx=(0, 2))
            except tk.TclError:
                pass  # ウィジェットが既に破棄されている場合
        else:
            try:
                self._mic_btn.pack_forget()
                self._continuous_btn.pack_forget()
            except tk.TclError:
                pass

    def _toggle_mic(self):
        """マイク録音を開始/停止して、変換テキストを自動送信する"""
        if not (self.ai_chan and hasattr(self.ai_chan, "settings")):
            return
        stt_enabled = self.ai_chan.settings.get("stt", {}).get("enabled", False)
        if not stt_enabled:
            return
        # 連続モード中は通常マイク操作を無視
        if self._continuous_mode:
            return
        # 変換処理中は操作を無視
        if self._mic_processing:
            return

        if not self._mic_recording:
            # 録音開始
            self._mic_recording = True
            self._mic_btn.configure(bg=COLOR_DANGER, fg="#FFFFFF", text="■ 停止")
            self._voice_status_var.set("● 録音中...")
            self._voice_status_label.configure(fg=COLOR_DANGER)
            from core.stt import STTEngine
            model_size = self.ai_chan.settings.get("stt", {}).get("model_size", "small")
            if not hasattr(self, "_stt_engine"):
                self._stt_engine = STTEngine(model_size=model_size)
                self._stt_engine.load_model_async()
                # 話者識別マネージャを接続
                if self.ai_chan and hasattr(self.ai_chan, "voice_id"):
                    vid = self.ai_chan.voice_id
                    if vid and len(vid.profiles) > 0:
                        self._stt_engine.set_voice_id(vid)
            self._stt_engine.start_recording()
        else:
            # 録音停止・変換・自動送信
            self._mic_recording = False
            self._mic_processing = True
            self._mic_btn.configure(bg=COLOR_GLOW, fg=COLOR_ACCENT, text="⏳ 変換")
            self._voice_status_var.set("変換中...")
            self._voice_status_label.configure(fg=COLOR_ACCENT)

            def _transcribe_and_send():
                utterances = []
                timed_out = False
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        if hasattr(self, "_stt_engine"):
                            if self._stt_engine.multi_speaker_enabled:
                                future = pool.submit(
                                    self._stt_engine.stop_recording_and_transcribe_multi
                                )
                                utterances = future.result(timeout=30)
                            else:
                                future = pool.submit(
                                    self._stt_engine.stop_recording_and_transcribe
                                )
                                text = future.result(timeout=30)
                                if text:
                                    from core.stt import SpeakerUtterance
                                    utterances = [SpeakerUtterance("", text, 0.0)]
                except concurrent.futures.TimeoutError:
                    timed_out = True
                    print("[STT] 変換タイムアウト(30秒)", flush=True)
                except Exception as e:
                    print(f"[STT] 変換エラー: {e}", flush=True)

                def _on_result():
                    self._mic_processing = False
                    self._mic_btn.configure(bg=COLOR_PANEL, fg=COLOR_TEXT, text="🎤 録音")
                    self._voice_status_var.set("")
                    if timed_out:
                        self._voice_status_var.set("変換に時間がかかりすぎました")
                        self._voice_status_label.configure(fg=COLOR_DANGER)
                        self.after(3000, lambda: self._voice_status_var.set(""))
                    elif utterances:
                        for utt in utterances:
                            labeled = (
                                f"[{utt.speaker}] {utt.text}"
                                if utt.speaker
                                else utt.text
                            )
                            self.input_var.set(labeled)
                            self._on_send()
                    else:
                        self._voice_status_var.set("音声が聞き取れませんでした")
                        self._voice_status_label.configure(fg=COLOR_SUBTEXT)
                        self.after(2000, lambda: self._voice_status_var.set(""))

                self.after(0, _on_result)

            threading.Thread(target=_transcribe_and_send, daemon=True).start()

    # ─── 連続リスニングモード（Phase C） ────────────────────────

    def _toggle_continuous_mode(self):
        """連続リスニングモードの ON/OFF を切り替える"""
        if not (self.ai_chan and hasattr(self.ai_chan, "settings")):
            return
        stt_enabled = self.ai_chan.settings.get("stt", {}).get("enabled", False)
        if not stt_enabled:
            return

        # 通常のマイク録音中は切り替え不可
        if self._mic_recording or self._mic_processing:
            return

        if not self._continuous_mode:
            self._start_continuous_mode()
        else:
            self._stop_continuous_mode()

    def _start_continuous_mode(self):
        """連続リスニングモードを開始する"""
        from core.stt import STTEngine

        model_size = self.ai_chan.settings.get("stt", {}).get("model_size", "small")
        if not hasattr(self, "_stt_engine"):
            self._stt_engine = STTEngine(model_size=model_size)
            self._stt_engine.load_model_async()
            # 話者識別マネージャを接続
            if self.ai_chan and hasattr(self.ai_chan, "voice_id"):
                vid = self.ai_chan.voice_id
                if vid and len(vid.profiles) > 0:
                    self._stt_engine.set_voice_id(vid)

        if not self._stt_engine.is_ready():
            self._voice_status_var.set("モデル読み込み中...")
            self._voice_status_label.configure(fg=COLOR_ACCENT2)
            # モデルがまだ読み込み中の場合、1秒後に再試行
            self._stt_engine.load_model_async()
            self.after(1000, self._retry_continuous_start)
            return

        self._activate_continuous_listening()

    def _retry_continuous_start(self):
        """モデル読み込み完了を待って連続モード開始を再試行"""
        if not hasattr(self, "_stt_engine"):
            self._voice_status_var.set("")
            return
        if self._stt_engine.is_ready():
            self._activate_continuous_listening()
        elif self._stt_engine.get_status().startswith("error"):
            self._voice_status_var.set("モデル読み込みエラー")
            self._voice_status_label.configure(fg=COLOR_DANGER)
            self.after(2000, lambda: self._voice_status_var.set(""))
        else:
            # まだ読み込み中 — 再試行
            self.after(1000, self._retry_continuous_start)

    def _activate_continuous_listening(self):
        """STT エンジンの連続リスニングを実際に起動する"""
        if not hasattr(self, "_stt_engine"):
            return

        def _on_continuous_text(text: str):
            """連続リスニングで認識されたテキストを UI スレッドで処理。
            Phase D: "[話者名] テキスト" 形式もそのまま処理する。
            """
            def _apply():
                try:
                    if not self.winfo_exists():
                        return
                    if text.strip():
                        self.input_var.set(text)
                        self._on_send()
                        # 複数話者モード時はステータスに話者名表示
                        import re
                        m = re.match(r'^\[([^\]]+)\]', text)
                        if m:
                            self._voice_status_var.set(
                                f"🎤 {m.group(1)} → 連続リスニング中"
                            )
                            self.after(
                                2000,
                                lambda: self._voice_status_var.set(
                                    "連続リスニング中"
                                ),
                            )
                except tk.TclError:
                    pass
            try:
                self.after(0, _apply)
            except Exception:
                pass

        ok = self._stt_engine.start_continuous_listening(
            on_text=_on_continuous_text,
            silence_threshold=0.01,
            silence_duration=1.5,
        )
        if ok:
            self._continuous_mode = True
            self._continuous_btn.configure(bg=COLOR_SUCCESS, fg="#FFFFFF")
            self._mic_btn.configure(state="disabled")
            self._voice_status_var.set("連続リスニング中")
            self._voice_status_label.configure(fg=COLOR_SUCCESS)
            # TTS 読み上げ中の自動一時停止を開始
            self._start_continuous_tts_monitor()
        else:
            self._voice_status_var.set("連続リスニング開始失敗")
            self._voice_status_label.configure(fg=COLOR_DANGER)
            self.after(2000, lambda: self._voice_status_var.set(""))

    def _stop_continuous_mode(self):
        """連続リスニングモードを停止する"""
        self._continuous_mode = False
        if hasattr(self, "_stt_engine"):
            self._stt_engine.stop_continuous_listening()
        self._continuous_btn.configure(bg=COLOR_PANEL, fg=COLOR_SUBTEXT)
        self._mic_btn.configure(state="normal")
        self._voice_status_var.set("")

    def _start_continuous_tts_monitor(self):
        """
        連続モード中、TTS が読み上げ中ならリスニングを一時停止し、
        終わったら再開するモニター。
        """
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        if not self._continuous_mode:
            return

        tts = self._get_tts_engine()
        stt = getattr(self, "_stt_engine", None)

        if tts is not None and stt is not None:
            if tts.is_speaking():
                if not stt.is_continuous_paused:
                    stt.pause_continuous_listening()
                    self._voice_status_var.set("🔊 読み上げ中（一時停止）")
                    self._voice_status_label.configure(fg=COLOR_ACCENT2)
            else:
                if stt.is_continuous_paused:
                    stt.resume_continuous_listening()
                    self._voice_status_var.set("連続リスニング中")
                    self._voice_status_label.configure(fg=COLOR_SUCCESS)

        self.after(200, self._start_continuous_tts_monitor)

    def _start_voice_status_poll(self):
        """TTS 読み上げ中かどうかを定期的にチェックしてインジケータを更新する"""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        # 連続モード中はそちらの TTS モニターが表示を管理するのでスキップ
        if self._continuous_mode:
            self.after(300, self._start_voice_status_poll)
            return

        # 録音中・変換中はそちらの表示を優先
        if not self._mic_recording and not self._mic_processing:
            tts = self._get_tts_engine()
            if tts is not None and tts.is_speaking():
                self._voice_status_var.set("🔊 読み上げ中")
                self._voice_status_label.configure(fg=COLOR_ACCENT2)
            else:
                # 他のステータス表示がなければクリア
                current = self._voice_status_var.get()
                if current == "🔊 読み上げ中":
                    self._voice_status_var.set("")

        self.after(300, self._start_voice_status_poll)

    def _get_tts_engine(self):
        """AiChan インスタンスから TTS エンジンを取得する"""
        if self.ai_chan and hasattr(self.ai_chan, "tts"):
            return self.ai_chan.tts
        return None

    def _on_frame_configure(self, event):
        self.chat_canvas.configure(
            scrollregion=self.chat_canvas.bbox("all")
        )

    def _on_canvas_configure(self, event):
        self.chat_canvas.itemconfig(
            self.canvas_window, width=event.width
        )

    def _on_window_resize(self, event):
        if event.widget == self:
            new_wrap = max(200, event.width - 120)
            for widget in _all_children(self.msg_frame):
                if isinstance(widget, tk.Label):
                    try:
                        if widget.cget('wraplength'):
                            widget.configure(wraplength=new_wrap)
                    except Exception:
                        pass

    def _add_message(self, sender: str, text: str, is_ai: bool = True):
        row = tk.Frame(self.msg_frame, bg=COLOR_BG, pady=5)
        row.pack(fill="x", padx=16)

        # アイコン（画像優先、なければ絵文字）
        icon_photo = self._ai_icon_photo if is_ai else self._user_icon_photo
        if icon_photo:
            icon = tk.Label(row, image=icon_photo, bg=COLOR_BG)
            icon.image = icon_photo  # GC防止
        else:
            icon_text = self._ai_icon if is_ai else self._user_icon
            icon = tk.Label(row, text=icon_text, bg=COLOR_BG, font=("Arial", 18))

        # ── バブルデザイン（クリーン・ライト） ──
        bubble_color = COLOR_BUBBLE if is_ai else COLOR_USER_BUB
        name_color   = COLOR_ACCENT if is_ai else COLOR_ACCENT2

        bubble = tk.Frame(row, bg=bubble_color, padx=16, pady=12)

        # 名前 + タイムスタンプ行
        ts = self._now_timestamp()
        header_frame = tk.Frame(bubble, bg=bubble_color)
        header_frame.pack(fill="x", anchor="w")

        tk.Label(
            header_frame, text=sender,
            bg=bubble_color, fg=name_color,
            font=(self._font_name, max(9, self._font_size - 1), "bold")
        ).pack(side="left")

        tk.Label(
            header_frame, text=ts,
            bg=bubble_color, fg=COLOR_SUBTEXT,
            font=(self._font_name, max(8, self._font_size - 3))
        ).pack(side="left", padx=(8, 0))

        # メッセージ本文
        wrap = max(200, self.winfo_width() - 130) if self.winfo_width() > 1 else 300
        msg_label = tk.Label(
            bubble, text=text,
            bg=bubble_color, fg=COLOR_TEXT,
            font=(self._font_name, self._font_size),
            wraplength=wrap, justify="left"
        )
        msg_label.pack(anchor="w", pady=(4, 0))

        # フィードバックボタン（AI 応答のみ）
        if is_ai and text not in ("んー…✨",):
            fb = FeedbackButtons(
                bubble,
                callback=self._on_feedback,
                bg=bubble_color,
            )
            fb.pack(anchor="w", pady=(6, 0))

        if is_ai:
            icon.pack(side="left", anchor="n", padx=(0, 10))
            bubble.pack(side="left", anchor="w")
        else:
            bubble.pack(side="right", anchor="e")
            icon.pack(side="right", anchor="n", padx=(10, 0))

        # 感情バー更新
        if is_ai and self.ai_chan and hasattr(self.ai_chan, "emotion"):
            try:
                emotions = self.ai_chan.emotion.state.to_dict()
                self._emotion_bar.update_emotions(emotions)
            except Exception:
                pass

        # 最下部へスクロール
        self.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

    def _on_feedback(self, positive: bool) -> None:
        """フィードバックボタンのコールバック (#54)。"""
        label = "good" if positive else "bad"
        logger.info("ユーザーフィードバック: %s", label)
        if self.ai_chan and hasattr(self.ai_chan, "correction_learning"):
            try:
                self.ai_chan.correction_learning.record_feedback(positive)
            except Exception as exc:
                logger.warning("フィードバック記録エラー: %s", exc)

    def _safe_add_message(self, name: str, text: str, is_ai: bool):
        """winfo_exists 検証付きの _add_message ラッパー"""
        try:
            if self.winfo_exists():
                self._add_message(name, text, is_ai=is_ai)
        except tk.TclError:
            pass

    def _on_send(self, event=None):
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        # 送信後すぐにフォーカスを入力欄に戻す（連続入力できるように）
        self.after(10, self._focus_input)
        self._add_message(self._user_name, text, is_ai=False)

        # アイドルタイマーリセット
        if self._pet is not None:
            self._pet._last_interaction = time.time()

        # #32 入力中インジケータを表示
        self._typing_indicator.pack(fill="x", padx=8, pady=2)
        self._typing_indicator.start()

        # AI応答を別スレッドで生成（UIフリーズ防止）
        # プレースホルダーを追加し、その参照を覚えて後で安全に削除
        self._add_message("アイ", "んー…✨", is_ai=True)
        children = self.msg_frame.winfo_children()
        placeholder = children[-1] if children else None

        def _generate():
            # アイ本体がまだ準備できていない場合、最大30秒待つ
            if self.ai_chan is None or not getattr(self.ai_chan, "llm_loaded", False):
                import time as _t
                for _wait in range(30):
                    _t.sleep(1)
                    if self.ai_chan is not None and getattr(self.ai_chan, "llm_loaded", False):
                        break
                # 待っても駄目なら準備中メッセージ
                if self.ai_chan is None:
                    response = "準備中だよ、もうちょっとだけ待ってね…✨"
                    emotion_str = "😊 元気"
                elif not getattr(self.ai_chan, "llm_loaded", False):
                    response = "モデルを読み込んでるところ…準備できたら返事するね！"
                    emotion_str = "😊 元気"
                else:
                    try:
                        response = self.ai_chan.chat(text)
                        emotion_str = self.ai_chan.emotion.get_display_string()
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        response = f"（エラーが発生したよ: {e}）"
                        emotion_str = "😊 元気"
            else:
                try:
                    response = self.ai_chan.chat(text)
                    emotion_str = self.ai_chan.emotion.get_display_string()
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    response = f"（エラーが発生したよ: {e}）"
                    emotion_str = "😊 元気"

            def _apply():
                try:
                    if not self.winfo_exists():
                        return
                    # #32 入力中インジケータ停止
                    self._typing_indicator.stop()
                    self._typing_indicator.pack_forget()
                    # 特定のプレースホルダーだけを削除（最後の子ではなく）
                    if placeholder is not None:
                        try:
                            placeholder.destroy()
                        except tk.TclError:
                            pass
                    # モードインジケータを付与（familyモード以外）
                    display_response = response
                    _mode_icons = {"family": "\U0001f497", "agent": "\U0001f4bc", "learning": "\U0001f4da", "creative": "\U0001f3a8"}
                    _mm = getattr(self.ai_chan, "mode_manager", None)
                    if _mm and _mm.current_mode != "family":
                        _icon = _mode_icons.get(_mm.current_mode, "")
                        display_response = f"{_icon} {response}"
                    self._add_message("アイ", display_response, is_ai=True)
                    self.emotion_var.set(emotion_str)
                except tk.TclError:
                    pass

            try:
                if self.winfo_exists():
                    self.after(0, _apply)
            except tk.TclError:
                pass

        threading.Thread(target=_generate, daemon=True).start()


class DesktopPet:
    """
    デスクトップペットメインクラス
    透明ウィンドウ上にアイを表示します
    """

    def __init__(self, ai_chan_instance=None):
        self.ai_chan = ai_chan_instance
        self.root = tk.Tk()
        self._setup_window()
        self._load_sprite()
        self._build_ui()
        self._start_animation()
        self.chat_window: ChatWindow | None = None
        self.bubble: SpeechBubble | None = None
        self._clipboard_watcher = None

        # 自律行動タイマー
        self._last_interaction = time.time()
        self._idle_minutes = 30  # デフォルト値（AiChan 読み込み後に上書き）

        # mainloop 開始後に右下へ移動 → その後挨拶
        self.root.after(100,   self._move_to_bottom_right)
        self.root.after(800,   self._greet)
        # 1分ごとにアイドル・スケジュールチェック
        self.root.after(60000, self._autonomous_tick)

    def _setup_window(self):
        # macOS Sequoia (15.x) + Tk 8.6.12+ では overrideredirect(True) が
        # マウスイベントを消すバグがある。MacWindowStyle で枠なしウィンドウにする。
        # 'plain' はドラッグ不可、'floating' はタイトルバーが出るが
        # クリック+ドラッグ両対応のため 'floating' を採用。
        self._use_mac_style = False
        if IS_MAC:
            try:
                tk_patch = self.root.tk.eval("info patchlevel")
                tk_minor = int(tk_patch.split(".")[2]) if tk_patch.count(".") >= 2 else 0
                if tk_minor >= 12:
                    self.root.title("")  # タイトルバーの "tk" テキストを消す
                    self.root.call(
                        "::tk::unsupported::MacWindowStyle", "style",
                        self.root._w, "floating", "none",
                    )
                    self._use_mac_style = True
                else:
                    self.root.overrideredirect(True)
            except (tk.TclError, ValueError):
                self.root.overrideredirect(True)
        else:
            self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)
        self.root.configure(bg=WIN_BG)

        # 初期位置は画面中央に固定（_move_to_bottom_right で後から移動）
        self.root.geometry(f"{PET_WIDTH}x{PET_HEIGHT}+600+400")
        self._win_start_x = 600
        self._win_start_y = 400
        self._dragging = False
        self._drag_ready = False  # _on_press〜_on_release の間 True
        # 初期位置（_move_to_bottom_right が上書きする）
        self._base_x = 600
        self._base_y = 400
        # after() id 管理（クリーンアップ用）
        self._anim_after_id: str | None = None
        self._tick_after_id: str | None = None

    def _move_to_bottom_right(self):
        """mainloop 開始後に正確な画面サイズで右下に配置します"""
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        # 画面サイズが取れなかった場合のフォールバック
        if sw < 400:
            sw = 1440
        if sh < 400:
            sh = 900
        x = max(0, sw - PET_WIDTH - 40)
        y = max(0, sh - PET_HEIGHT - 80)
        self._base_x = x
        self._base_y = y
        self.root.geometry(f"{PET_WIDTH}x{PET_HEIGHT}+{x}+{y}")
        self.root.update_idletasks()
        # macOS Sequoia: フォーカスを強制してイベント受付を有効化
        if IS_MAC:
            self.root.focus_force()
            self.root.lift()
        self._request_mic_permission_in_app()

    def _request_mic_permission_in_app(self):
        """アプリ起動後にマイク権限ダイアログをサブプロセスで表示"""
        status = _check_microphone_status()
        if status == 3:
            print("[Mic] ✅ マイク権限あり", flush=True)
            return
        if status == 0:
            print("[Mic] マイク権限を要求します...", flush=True)
            threading.Thread(target=_request_mic_in_subprocess, daemon=True).start()

    def _load_sprite(self):
        self.sprite_photo = None
        self.sprite_frames = []
        custom = ""
        if self.ai_chan and hasattr(self.ai_chan, "settings"):
            custom = self.ai_chan.settings.get("ui", {}).get("pet_image", "")
        img_path = find_character_image(custom)

        if not PILLOW_AVAILABLE:
            print("[Pet] Pillow が見つかりません。pip install Pillow で追加してください", flush=True)
            return
        if img_path is None:
            print("[Pet] 画像ファイルが見つかりません", flush=True)
            return

        try:
            img = Image.open(img_path).convert("RGBA")
            # アスペクト比を保ちつつリサイズ
            target_size = (PET_WIDTH - 10, PET_HEIGHT - 20)
            img.thumbnail(target_size, Image.LANCZOS)

            # PNG透過部分を背景色(RGB tuple)と合成
            r = int(WIN_BG[1:3], 16)
            g = int(WIN_BG[3:5], 16)
            b = int(WIN_BG[5:7], 16)
            bg = Image.new("RGBA", img.size, (r, g, b, 255))
            composite = Image.alpha_composite(bg, img)
            display_img = composite.convert("RGB")

            self._base_image    = img          # アニメ用（RGBA保持）
            self._display_base  = display_img  # 表示用（合成済み）
            self.sprite_photo   = ImageTk.PhotoImage(display_img)
            print(f"[Pet] ✓ 画像読み込み完了: {img.size}", flush=True)
        except Exception as e:
            import traceback
            print(f"[Pet] 画像読み込みエラー: {e}", flush=True)
            traceback.print_exc()

        # #26 表情差分画像のプリロード
        self._expression_images: dict[str, object] = {}
        self._load_expression_images()

    def _load_expression_images(self) -> None:
        """表情差分画像を読み込む (#26)。ファイルがなくても安全にスキップする。"""
        if not PILLOW_AVAILABLE:
            return
        emotions = ("happy", "sad", "excited", "calm", "anxious", "tired", "angry")
        for emotion in emotions:
            for template in EXPRESSION_CANDIDATES:
                path = Path(str(template).replace("{emotion}", emotion))
                if path.exists():
                    try:
                        img = Image.open(path).convert("RGBA")
                        target_size = (PET_WIDTH - 10, PET_HEIGHT - 20)
                        img.thumbnail(target_size, Image.LANCZOS)
                        r = int(WIN_BG[1:3], 16)
                        g = int(WIN_BG[3:5], 16)
                        b = int(WIN_BG[5:7], 16)
                        bg_img = Image.new("RGBA", img.size, (r, g, b, 255))
                        composite = Image.alpha_composite(bg_img, img)
                        self._expression_images[emotion] = ImageTk.PhotoImage(
                            composite.convert("RGB")
                        )
                        logger.info("表情画像読み込み: %s (%s)", emotion, path)
                    except Exception as exc:
                        logger.warning("表情画像読み込みエラー %s: %s", emotion, exc)
                    break

    def _update_expression(self, emotion: str) -> None:
        """表情差分画像があればスプライトを切り替える (#26)。"""
        if not self.sprite_id:
            return
        photo = self._expression_images.get(emotion)
        if photo:
            try:
                self.canvas.itemconfig(self.sprite_id, image=photo)
                self._current_photo = photo
            except tk.TclError:
                pass

    def _build_ui(self):
        self.canvas = tk.Canvas(
            self.root,
            width=PET_WIDTH, height=PET_HEIGHT,
            bg=WIN_BG, highlightthickness=0
        )
        self.canvas.pack()

        # キャラクター画像
        if self.sprite_photo:
            self.sprite_id = self.canvas.create_image(
                PET_WIDTH // 2, PET_HEIGHT // 2,
                image=self.sprite_photo, anchor="center"
            )
        else:
            # 画像がない場合はプレースホルダー
            self.canvas.create_oval(
                60, 40, 160, 200, fill=COLOR_PANEL, outline=COLOR_ACCENT, width=2
            )
            self.canvas.create_text(
                PET_WIDTH // 2, 130,
                text="💎\nアイ", fill=COLOR_ACCENT,
                font=("Hiragino Sans", 14, "bold"), justify="center"
            )
            self.sprite_id = None

        # ─── イベントバインド ───
        self._last_click_time = 0.0
        self._press_x = 0
        self._press_y = 0
        self._long_press_id = None  # 長押し判定用 after ID

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # 右クリック: macOS + floating ウィンドウでは Button-2/3 が
        # 個別シーケンスで canvas に到達しないことがある。
        # 汎用 <ButtonPress> で全ボタンを受け取り、num で判別する方式に変更。
        # Press/Release 両方 + 500ms デバウンスで二重発火を防止。
        self._ctx_last_time = 0.0
        if IS_MAC:
            # 汎用 ButtonPress/Release — _on_any_button 内で num を判別
            for seq in ("<ButtonPress>", "<ButtonRelease>"):
                self.canvas.bind(seq, self._on_any_button, add="+")
                self.root.bind(seq, self._on_any_button, add="+")
            # Control+Click は別途明示バインド（num=1 なので汎用では拾えない）
            for seq in ("<Control-ButtonPress-1>", "<Control-ButtonRelease-1>"):
                self.canvas.bind(seq, self._show_context_menu)
                self.root.bind(seq, self._show_context_menu)
        else:
            ctx_seqs = ("<ButtonPress-3>", "<ButtonRelease-3>")
            for seq in ctx_seqs:
                self.canvas.bind(seq, self._show_context_menu)
                self.root.bind(seq, self._show_context_menu)

        # コンテキストメニュー（クリーンスタイル）
        self.context_menu = tk.Menu(self.root, tearoff=0,
                                     bg=COLOR_BG, fg=COLOR_TEXT,
                                     activebackground=COLOR_ACCENT,
                                     activeforeground="#FFFFFF",
                                     font=("Hiragino Sans", 12),
                                     borderwidth=1,
                                     relief="flat")
        self.context_menu.add_command(label="  💬  チャットを開く",    command=self._open_chat)
        self.context_menu.add_command(label="  😊  アイの気分",  command=self._show_emotion)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="  📊  成長記録を見る",    command=self._open_graph)
        self.context_menu.add_command(label="  📝  議事録アプリ",      command=self._open_minutes)
        self.context_menu.add_command(label="  📸  スクリーンショット", command=self._on_screenshot)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="  💾  会話ログを保存",    command=self._open_export)
        self.context_menu.add_command(label="  ⚙️  設定",              command=self._open_settings)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="  ✕   終了",              command=self.root.quit)

    def _on_press(self, event):
        """マウス押下：ドラッグ起点を記録。長押し (600ms) で右クリックメニュー。"""
        self._press_x = event.x_root
        self._press_y = event.y_root
        # アニメの geometry() がドラッグと競合しないよう即座に停止
        self._drag_ready = True
        self._dragging = False
        # winfo ではなく _base_x/_base_y を信頼（macOS floating で winfo が不正確なため）
        self._win_start_x = self._base_x
        self._win_start_y = self._base_y
        # 長押し判定: 400ms 動かなければ右クリックメニューを表示
        if self._long_press_id is not None:
            self.root.after_cancel(self._long_press_id)
        self._long_press_id = self.root.after(
            400, lambda: self._on_long_press(event)
        )

    def _on_long_press(self, event):
        """長押し判定コールバック。ドラッグ開始していなければメニューを表示。"""
        self._long_press_id = None
        if not self._dragging:
            self._show_context_menu(event)

    def _drag_motion(self, event):
        """5px以上動いたらドラッグと判定（delta方式）"""
        dx = event.x_root - self._press_x
        dy = event.y_root - self._press_y
        if abs(dx) > 5 or abs(dy) > 5:
            self._dragging = True
            # ドラッグ開始 → 長押し判定をキャンセル
            if self._long_press_id is not None:
                self.root.after_cancel(self._long_press_id)
                self._long_press_id = None
        if self._dragging:
            x = self._win_start_x + dx
            y = self._win_start_y + dy
            self.root.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        """マウス離し：ドラッグ完了 or クリック判定"""
        # 長押し判定をキャンセル
        if self._long_press_id is not None:
            self.root.after_cancel(self._long_press_id)
            self._long_press_id = None
        self._drag_ready = False
        if self._dragging:
            # ドラッグ後の位置を delta から計算（winfo_x/y は macOS で不正確なため使わない）
            dx = event.x_root - self._press_x
            dy = event.y_root - self._press_y
            self._base_x = self._win_start_x + dx
            self._base_y = self._win_start_y + dy
            self._dragging = False
            return
        # ユーザー操作でアイドルタイマーをリセット
        self._last_interaction = time.time()
        # シングルクリックでチャットを開く
        self._open_chat()

    def _open_chat(self, event=None):
        if self.chat_window is None or not self.chat_window.winfo_exists():
            self.chat_window = ChatWindow(self.root, self.ai_chan, pet=self)
        else:
            self.chat_window.deiconify()
            self.chat_window.lift()
            self.chat_window.after(50, self.chat_window._focus_input)

    def _on_any_button(self, event):
        """macOS 汎用ボタンハンドラ: num=2 or 3 なら右クリックメニューを表示。"""
        if getattr(event, "num", 1) in (2, 3):
            self._show_context_menu(event)

    def _show_context_menu(self, event):
        """
        macOS + overrideredirect / floating 対応の右クリックメニュー表示。
        Press / Release が連続発火するため、500ms のデバウンスで抑止する。
        """
        now = time.time()
        last = getattr(self, "_ctx_last_time", 0.0)
        if now - last < 0.5:
            return
        self._ctx_last_time = now

        # ドラッグ中なら無視
        if getattr(self, "_dragging", False):
            return

        x, y = event.x_root, event.y_root

        def _popup():
            try:
                self.root.update_idletasks()
                self.root.focus_force()
                self.root.lift()
                self.context_menu.tk_popup(x, y, 0)
            except Exception as e:
                print(f"[Menu] popup failed: {e}", flush=True)
            finally:
                try:
                    self.context_menu.grab_release()
                except Exception:
                    pass

        # 80ms遅延でmacOSのフォーカス遷移を待つ（50msでは不足な場合がある）
        self.root.after(80, _popup)

    def _show_emotion(self):
        if self.ai_chan:
            text = self.ai_chan.emotion.get_display_string()
        else:
            text = "😊 元気だよ！"
        self._show_bubble(text)

    def _show_bubble(self, text: str):
        if self.bubble:
            try:
                self.bubble.destroy()
            except Exception:
                pass
        # モードインジケータを付与（familyモード以外）
        _mode_icons = {"family": "\U0001f497", "agent": "\U0001f4bc", "learning": "\U0001f4da", "creative": "\U0001f3a8"}
        _mm = getattr(self.ai_chan, "mode_manager", None) if self.ai_chan else None
        if _mm and _mm.current_mode != "family":
            _icon = _mode_icons.get(_mm.current_mode, "")
            text = f"{_icon} {text}"
        x = self.root.winfo_x() + PET_WIDTH // 2
        y = self.root.winfo_y() + 30
        self.bubble = SpeechBubble(self.root, text, x, y)

    def _greet(self):
        if self.ai_chan:
            def _gen():
                try:
                    prompt = self.ai_chan.build_greeting_prompt("startup")
                    resp = self.ai_chan.chat(prompt)
                except Exception:
                    resp = "起きたよ"
                self.root.after(0, lambda: self._show_bubble(resp))
            threading.Thread(target=_gen, daemon=True).start()
        else:
            self._show_bubble("起きたよ")

    def _open_graph(self):
        """成長記録ウィンドウを開く"""
        if not self.ai_chan:
            self._show_bubble("まだ読み込み中だよ、少し待ってからもう一回試してね！")
            return
        try:
            from ui.graph_window import GraphWindow
            GraphWindow(self.root, self.ai_chan)
        except Exception as e:
            print(f"[Pet] graph window error: {e}", flush=True)

    def _open_minutes(self):
        """議事録アプリを開く"""
        try:
            from ui.minutes_window import MinutesWindow
            MinutesWindow(self.root, self.ai_chan)
        except Exception as e:
            print(f"[Pet] minutes window error: {e}", flush=True)
            self._show_bubble("議事録アプリを開けなかったよ")

    def _open_export(self):
        """会話ログエクスポートウィンドウを開く"""
        if not (self.ai_chan and hasattr(self.ai_chan, "memory")):
            self._show_bubble("まだ読み込み中だよ、少し待ってからもう一回試してね！")
            return
        from ui.export_window import ExportWindow
        ExportWindow(self.root, self.ai_chan.memory, BASE_DIR)

    def _open_settings(self):
        """設定ウィンドウを開く"""
        from ui.settings_window import SettingsWindow
        win = SettingsWindow(self.root, self.ai_chan, BASE_DIR)
        # クリップボード監視の再起動は保存後に反映
        # <Destroy> は子ウィジェットでも発火するため、win 本体かチェック
        win.bind(
            "<Destroy>",
            lambda e, w=win: (e.widget is w) and self._restart_clipboard_watcher(),
        )

    def _restart_clipboard_watcher(self):
        """設定変更後にクリップボード監視を再起動"""
        if hasattr(self, "_clipboard_watcher") and self._clipboard_watcher:
            self._clipboard_watcher.stop()
            self._clipboard_watcher = None
        self._start_clipboard_watcher()

    def _start_clipboard_watcher(self):
        """クリップボード監視を開始（設定が有効な場合のみ）"""
        if not IS_MAC:
            return
        enabled = False
        if self.ai_chan:
            try:
                enabled = self.ai_chan.settings.get(
                    "autonomous", {}
                ).get("clipboard_watch", False)
            except Exception:
                pass
        if enabled:
            from core.clipboard_watcher import ClipboardWatcher
            self._clipboard_watcher = ClipboardWatcher(
                callback=self._on_clipboard_change
            )
            self._clipboard_watcher.start()
            print("[Pet] クリップボード監視を開始", flush=True)

    def _start_battery_monitor(self):
        """バッテリー低下時に吹き出しで通知する"""
        try:
            from core.battery_monitor import BatteryMonitor
            def _on_low(pct: int):
                msg = f"バッテリーが{pct}%になったよ！充電してね⚡"
                self.root.after(0, lambda: self._show_bubble(msg))
            self._battery_monitor = BatteryMonitor(
                callback=_on_low,
                warn_thresholds=[20, 10],
                check_interval=120,
            )
            self._battery_monitor.start()
        except Exception as e:
            print(f"[Battery] 監視開始エラー: {e}", flush=True)

    def _on_clipboard_change(self, text: str):
        """クリップボード変化時のコールバック（バックグラウンドスレッドから呼ばれる）"""
        if not (self.ai_chan and self.ai_chan.llm_loaded):
            return
        def _gen():
            try:
                resp = self.ai_chan.respond_to_clipboard(text)
                if resp:
                    self.root.after(0, lambda: self._show_bubble(resp))
            except Exception:
                pass
        threading.Thread(target=_gen, daemon=True).start()

    def _on_screenshot(self):
        """スクリーンショットを撮ってアイにコメントさせる"""
        if not IS_MAC:
            self._show_bubble("スクリーンショットは macOS 専用だよ")
            return
        def _gen():
            try:
                # VisionEngine が初期化されていれば優先使用（OCR/Moondream）
                if self.ai_chan and hasattr(self.ai_chan, "vision"):
                    desc = self.ai_chan.vision.capture_and_describe()
                else:
                    from core.screenshot_reader import capture_screen, read_and_cleanup
                    path = capture_screen()
                    if path is None:
                        self.root.after(0, lambda: self._show_bubble("うまく撮れなかった…"))
                        return
                    desc = read_and_cleanup(path)

                if self.ai_chan and self.ai_chan.llm_loaded:
                    resp = self.ai_chan.respond_to_screenshot(desc)
                else:
                    resp = desc
                self.root.after(0, lambda: self._show_bubble(resp))
            except Exception as e:
                print(f"[Screenshot] エラー: {e}", flush=True)
        threading.Thread(target=_gen, daemon=True).start()

    # ─── 自律行動 ────────────────────────────────────────────────

    def _autonomous_tick(self):
        """J・K: 1分ごとにアイドル確認とスケジュールチェック"""
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if self.ai_chan and self.ai_chan.llm_loaded:
            idle_secs = time.time() - self._last_interaction
            idle_mins = getattr(self.ai_chan, "_idle_minutes", 30)

            # J: 放置中の独り言
            if idle_secs >= idle_mins * 60:
                self._last_interaction = time.time()  # 連発防止
                def _gen_solo():
                    try:
                        text = self.ai_chan.generate_soliloquy()
                        if text:
                            self.root.after(0, lambda: self._show_bubble(text))
                    except Exception:
                        pass
                threading.Thread(target=_gen_solo, daemon=True).start()

            # K: 日課スケジュール
            else:
                def _gen_sched():
                    try:
                        text = self.ai_chan.check_schedule()
                        if text:
                            self._last_interaction = time.time()
                            self.root.after(0, lambda: self._show_bubble(text))
                            # macOS 通知センターにも送る
                            try:
                                from core.notifier import notify_schedule
                                notify_schedule(text[:80])
                            except Exception:
                                pass
                    except Exception:
                        pass
                threading.Thread(target=_gen_sched, daemon=True).start()

        # 次のチェックをスケジュール（1分後）
        self._tick_after_id = self.root.after(60000, self._autonomous_tick)

    # ─── アニメーション ──────────────────────────────────────────

    def _start_animation(self):
        self._anim_tick = 0
        self._idle_anim()

    def _build_breath_frames(self, base_image):
        """ブリージングアニメのフレームを事前計算（メインスレッドの毎フレームLANCZOS廃止）"""
        n_frames = 64  # sin 周期を64分割
        iw, ih = base_image.size
        frames = []
        for i in range(n_frames):
            scale = 1.0 + math.sin(i * (2 * math.pi / n_frames)) * 0.012
            w = max(1, int(iw * scale))
            h = max(1, int(ih * scale))
            resized = base_image.resize((w, h), Image.LANCZOS)
            frames.append(ImageTk.PhotoImage(resized))
        self._breath_frames = frames
        self._breath_dirty = False

    def _idle_anim(self):
        """浮遊アニメーション（上下にゆっくり揺れる）"""
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        self._anim_tick += 1
        offset = int(math.sin(self._anim_tick * 0.05) * 6)
        # base_x/y を一度ローカルに取得（ドラッグ中の更新との race 回避）
        bx = self._base_x
        by = self._base_y

        if self.sprite_id and PILLOW_AVAILABLE and hasattr(self, "_display_base"):
            # Sprint 3.0-D: 感情に応じて表情を変化させる（10フレームに1回更新）
            display = self._display_base
            if self._anim_tick % 10 == 0:
                try:
                    if self.ai_chan and hasattr(self.ai_chan, "emotion"):
                        emotion_dict = self.ai_chan.emotion.state.to_dict()
                        # 感情を分類
                        from core.expression_engine import classify_emotion
                        emotion_label = classify_emotion(emotion_dict)

                        # 優先1: 表情差分画像があればそちらを使う
                        expr_photo = self._expression_images.get(emotion_label)
                        if expr_photo:
                            self._update_expression(emotion_label)
                            self._emotion_display = None  # 差分画像使用中はスキップ
                        # 優先2: ExpressionEngine で色調変化
                        elif (hasattr(self.ai_chan, "expression")
                                and self.ai_chan.expression
                                and hasattr(self, "_base_image")):
                            modified = self.ai_chan.expression.apply_emotion(
                                self._base_image, emotion_dict
                            )
                            r = int(WIN_BG[1:3], 16)
                            g = int(WIN_BG[3:5], 16)
                            b = int(WIN_BG[5:7], 16)
                            bg = Image.new("RGBA", modified.size, (r, g, b, 255))
                            composite = Image.alpha_composite(bg, modified.convert("RGBA"))
                            self._emotion_display = composite.convert("RGB")
                except Exception:
                    pass
            if getattr(self, "_emotion_display", None) is not None:
                display = self._emotion_display
                self._breath_dirty = True  # 感情変化時にフレーム再構築

            # わずかに拡縮するブリージングエフェクト（プリコンピュート済みフレームを使用）
            try:
                if not hasattr(self, "_breath_frames") or self._breath_dirty:
                    self._build_breath_frames(display)
                    self._breath_dirty = False
                frame_idx = self._anim_tick % len(self._breath_frames)
                self._current_photo = self._breath_frames[frame_idx]
                self.canvas.itemconfig(self.sprite_id, image=self._current_photo)
            except Exception as e:
                if self._anim_tick <= 2:
                    print(f"[Pet] アニメエラー: {e}", flush=True)

        # ドラッグ準備中〜ドラッグ中は geometry() を呼ばない
        # （_drag_ready は _on_press で即座に True になるので 5px 閾値前も防御）
        if by is not None and bx is not None and not self._drag_ready:
            try:
                self.root.geometry(f"+{bx}+{by + offset}")
            except tk.TclError:
                return

        self._anim_after_id = self.root.after(50, self._idle_anim)  # 20fps

    def update_expression_from_entropy(self, text: str) -> str:
        """
        テキストのエントロピーからデスクトップペットの表情を更新。
        高エントロピー(複雑な思考) → 考え込んだ表情
        低エントロピー(シンプルな感情) → はっきりした表情
        最適ゾーン(0.6-0.8) → 活発で生き生きした表情
        """
        try:
            from core.akashic.entropy_engine import EntropyEngine
            profile = EntropyEngine().profile(text)
            entropy = profile.domain_diversity * 0.6 + profile.domain_diversity * 0.4
            if 0.6 <= entropy <= 0.8:
                return "active"      # カオスの縁: 最も生き生き
            elif entropy > 0.8:
                return "thinking"    # 高エントロピー: 考え込み
            elif entropy > 0.4:
                return "normal"      # 中程度
            else:
                return "sleepy"      # 低エントロピー: 眠そう
        except Exception:
            return "normal"

    def run(self):
        self.root.mainloop()


def _request_mic_in_subprocess():
    """
    子プロセスで AVFoundation requestAccess を実行。
    クラッシュしても親プロセスには影響しない。
    """
    import subprocess, sys, os
    script = """
import sys, signal, time
signal.signal(signal.SIGABRT, lambda s,f: sys.exit(1))
try:
    from AppKit import NSApplication
    from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
    from Foundation import NSRunLoop, NSDate
    NSApplication.sharedApplication()
    status = int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
    if status != 0:
        sys.exit(0)
    result = [None]
    def cb(g): result[0] = g
    AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, cb)
    deadline = time.time() + 60
    while result[0] is None and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
except Exception:
    pass
"""
    try:
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        print(f"[Mic] subprocess launch error: {e}")


def _check_microphone_status() -> int:
    """
    macOS マイク権限のステータスを返します（クラッシュしない安全版）。
    0=未決定, 2=拒否, 3=許可済み, -1=確認不可
    """
    if platform.system() != "Darwin":
        return -1
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio  # type: ignore
        return int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
    except Exception:
        return -1


def run_desktop_pet(base_dir: str | Path = "."):
    """
    デスクトップペットを起動します。
    ウィンドウをすぐに表示し、LLMはバックグラウンドで読み込みます。
    """
    base_dir = Path(base_dir)

    # まず画面にウィンドウを出す（LLM読み込み前）
    print("アイを起動しています...")
    pet = DesktopPet(ai_chan_instance=None)

    # ウィンドウが出たらすぐに「起動中」バブルを見せて、待ちを視覚化する
    def _initial_bubble():
        try:
            pet._show_bubble("起動したよ！今モデルを読み込んでるから少しだけ待っててね✨")
        except Exception:
            pass
    pet.root.after(200, _initial_bubble)

    # LLMをバックグラウンドスレッドで読み込む
    def _load_ai():
        try:
            from core.ai_chan import AiChan
            ai = AiChan(base_dir=base_dir)
            # 読み込み完了後にペットにセット（メインスレッドで）
            def _apply():
                # 最優先：ai_chan を先に差し込むことで、以降何が失敗しても
                # 会話機能だけは生き残るようにする
                pet.ai_chan = ai
                try:
                    pet._idle_minutes = getattr(ai, "_idle_minutes", 30)
                except Exception as e:
                    print(f"[Pet] _idle_minutes 設定失敗: {e}", flush=True)
                    pet._idle_minutes = 30
                # 既に開いている ChatWindow があれば ai_chan を更新し、
                # マイクボタンを再表示する
                try:
                    cw = pet.chat_window
                    if cw is not None and cw.winfo_exists():
                        cw.ai_chan = ai
                        cw._update_mic_button_visibility()
                        print("[Pet] ✓ ChatWindow に ai_chan を反映", flush=True)
                except Exception as e:
                    print(f"[Pet] ChatWindow 更新失敗: {e}", flush=True)
                try:
                    pet._show_bubble("準備できたよ！何でも話しかけてね💕")
                except Exception as e:
                    print(f"[Pet] 初期バブル表示失敗: {e}", flush=True)
                try:
                    pet._start_clipboard_watcher()
                except Exception as e:
                    print(f"[Pet] クリップボード監視開始失敗: {e}", flush=True)
                try:
                    pet._start_battery_monitor()
                except Exception as e:
                    print(f"[Pet] バッテリ監視開始失敗: {e}", flush=True)
            pet.root.after(0, _apply)
            # 自動学習スレッドを開始
            def _on_learn_complete(text: str):
                pet.root.after(0, lambda: pet._show_bubble(text))
            ai.auto_learner.start(ai, on_complete=_on_learn_complete)
            # Sprint 1.2: 自律エンジン（階層ジョブ）を起動
            try:
                if ai.start_autonomous():
                    print("[Pet] ✓ 自律エンジン起動")
            except Exception as e:
                print(f"[Pet] 自律エンジン起動失敗: {e}")
            print("[Pet] ✓ アイ準備完了")
        except Exception as e:
            import traceback
            print(f"[警告] AiChan 読み込み失敗: {e}")
            traceback.print_exc()

    threading.Thread(target=_load_ai, daemon=True).start()
    pet.run()

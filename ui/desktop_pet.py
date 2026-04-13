"""
デスクトップペット UI
アイがデスクトップ上に表示され、アニメーションし、
クリックで会話できるウィンドウを提供します。
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import threading
import math
import time
import sys
import platform
from pathlib import Path

IS_MAC = platform.system() == "Darwin"
# ウィンドウ背景色（PNG の透明部分と馴染む深い紫）
WIN_BG = "#1A0A2E"

try:
    from PIL import Image, ImageTk, ImageFilter, ImageEnhance
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))


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

# カラーパレット（アイのテーマカラー）
COLOR_BG       = "#2D1B3D"   # ダークパープル
COLOR_PANEL    = "#3D2255"   # パネル背景
COLOR_INPUT    = "#1A0F2E"   # 入力欄
COLOR_ACCENT   = "#E8A5C8"   # ピンクアクセント
COLOR_ACCENT2  = "#B57BDC"   # パープルアクセント
COLOR_TEXT     = "#F5E6FF"   # 明るいテキスト
COLOR_SUBTEXT  = "#C9A8E8"   # サブテキスト
COLOR_BUBBLE   = "#4A2870"   # 吹き出し背景
COLOR_USER_BUB = "#2A1545"   # ユーザー吹き出し

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
    """アイの台詞吹き出し"""

    def __init__(self, parent, text: str, x: int, y: int):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(bg=COLOR_BUBBLE)

        # 角丸風フレーム
        frame = tk.Frame(self, bg=COLOR_BUBBLE, padx=14, pady=10)
        frame.pack()

        label = tk.Label(
            frame, text=text, bg=COLOR_BUBBLE, fg=COLOR_TEXT,
            font=("Hiragino Sans", 12), wraplength=260, justify="left"
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


class ChatWindow(tk.Toplevel):
    """チャットウィンドウ"""

    def __init__(self, parent, ai_chan_instance, pet=None):
        super().__init__(parent)
        self.ai_chan = ai_chan_instance
        self._pet   = pet  # DesktopPet インスタンス（アイドルタイマーリセット用）

        # アイコン・名前設定を読み込む
        ui_cfg = {}
        if ai_chan_instance and hasattr(ai_chan_instance, "settings"):
            ui_cfg = ai_chan_instance.settings.get("ui", {})
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
                    resp = self.ai_chan.chat("チャットを開いてくれた。自然に一言だけ話しかけて。")
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
        # タイトルバー
        title_bar = tk.Frame(self, bg=COLOR_PANEL, height=44)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        # タイトルバー用の頭部アイコン（少し大きめ）
        self._title_head_photo = None
        if PILLOW_AVAILABLE and self.ai_chan and hasattr(self.ai_chan, "settings"):
            pet_img_path = self.ai_chan.settings.get("ui", {}).get("pet_image", "")
            self._title_head_photo = self._load_head_icon_from_pet_image(
                pet_img_path, size=28
            )

        if self._title_head_photo is not None:
            title_icon = tk.Label(
                title_bar, image=self._title_head_photo, bg=COLOR_PANEL
            )
            title_icon.image = self._title_head_photo  # GC 防止
            title_icon.pack(side="left", padx=(16, 6), pady=8)
            tk.Label(
                title_bar, text="アイ",
                bg=COLOR_PANEL, fg=COLOR_ACCENT,
                font=("Hiragino Sans", 14, "bold")
            ).pack(side="left", pady=8)
        else:
            tk.Label(
                title_bar, text="アイ",
                bg=COLOR_PANEL, fg=COLOR_ACCENT,
                font=("Hiragino Sans", 14, "bold")
            ).pack(side="left", padx=16, pady=8)

        # 閉じるボタン
        close_btn = tk.Label(
            title_bar, text="✕", bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
            font=("Arial", 14), cursor="hand2"
        )
        close_btn.pack(side="right", padx=16)
        close_btn.bind("<Button-1>", lambda e: self.withdraw())

        # チャット履歴エリア
        chat_frame = tk.Frame(self, bg=COLOR_BG)
        chat_frame.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        self.chat_canvas = tk.Canvas(
            chat_frame, bg=COLOR_BG, highlightthickness=0
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

        # 感情表示バー
        self.emotion_var = tk.StringVar(value="😊 元気")
        emotion_bar = tk.Frame(self, bg=COLOR_PANEL, height=28)
        emotion_bar.pack(fill="x")
        emotion_bar.pack_propagate(False)
        tk.Label(
            emotion_bar, textvariable=self.emotion_var,
            bg=COLOR_PANEL, fg=COLOR_SUBTEXT,
            font=("Hiragino Sans", 10)
        ).pack(side="left", padx=12)

        # 入力エリア
        input_frame = tk.Frame(self, bg=COLOR_PANEL, pady=10)
        input_frame.pack(fill="x", side="bottom")

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            input_frame, textvariable=self.input_var,
            bg=COLOR_INPUT, fg=COLOR_TEXT, insertbackground=COLOR_ACCENT,
            font=("Hiragino Sans", 13), relief="flat",
            highlightbackground=COLOR_ACCENT2, highlightthickness=1
        )
        self.input_entry.pack(side="left", fill="x", expand=True,
                               padx=(12, 6), ipady=8)
        self.input_entry.bind("<Return>", self._on_send)

        send_btn = tk.Button(
            input_frame, text="送信 ➤",
            bg=COLOR_ACCENT, fg=COLOR_BG,
            font=("Hiragino Sans", 12, "bold"),
            relief="flat", cursor="hand2",
            command=self._on_send,
            padx=10, pady=6
        )
        send_btn.pack(side="right", padx=(0, 12))

        # マイクボタン（STT が有効な場合のみ表示）
        self._mic_btn = tk.Button(
            input_frame, text="🎤",
            bg=COLOR_PANEL, fg=COLOR_TEXT,
            font=("Hiragino Sans", 14),
            relief="flat", cursor="hand2",
            command=self._toggle_mic,
            padx=6, pady=4
        )
        self._mic_btn.pack(side="right", padx=(0, 4))
        self._mic_recording = False
        self._update_mic_button_visibility()

    def _focus_input(self):
        """入力欄にフォーカスを確実にセットする（macOS 対策）"""
        try:
            self.lift()
            self.focus_force()
            self.input_entry.focus_set()
        except (tk.TclError, AttributeError):
            pass

    def _update_mic_button_visibility(self):
        """STT が有効な場合のみマイクボタンを表示する"""
        stt_enabled = False
        if self.ai_chan and hasattr(self.ai_chan, "settings"):
            stt_enabled = self.ai_chan.settings.get("stt", {}).get("enabled", False)
        if stt_enabled:
            self._mic_btn.pack(side="right", padx=(0, 4))
        else:
            self._mic_btn.pack_forget()

    def _toggle_mic(self):
        """マイク録音を開始/停止してテキストを入力欄に入れる"""
        if not (self.ai_chan and hasattr(self.ai_chan, "settings")):
            return
        stt_enabled = self.ai_chan.settings.get("stt", {}).get("enabled", False)
        if not stt_enabled:
            return

        if not self._mic_recording:
            # 録音開始
            self._mic_recording = True
            self._mic_btn.configure(bg="#E84040", text="■")
            from core.stt import STTEngine
            model_size = self.ai_chan.settings.get("stt", {}).get("model_size", "small")
            if not hasattr(self, "_stt_engine"):
                self._stt_engine = STTEngine(model_size=model_size)
                self._stt_engine.load_model_async()
            self._stt_engine.start_recording()
        else:
            # 録音停止・変換
            self._mic_recording = False
            self._mic_btn.configure(bg=COLOR_PANEL, text="🎤")

            def _transcribe():
                if hasattr(self, "_stt_engine"):
                    text = self._stt_engine.stop_recording_and_transcribe()
                    if text:
                        self.after(0, lambda: self.input_var.set(text))
                        self.after(0, lambda: self.input_entry.icursor("end"))
            threading.Thread(target=_transcribe, daemon=True).start()

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
        row = tk.Frame(self.msg_frame, bg=COLOR_BG, pady=4)
        row.pack(fill="x", padx=8)

        # アイコン（画像優先、なければ絵文字）
        icon_photo = self._ai_icon_photo if is_ai else self._user_icon_photo
        if icon_photo:
            icon = tk.Label(row, image=icon_photo, bg=COLOR_BG)
            icon.image = icon_photo  # GC防止
        else:
            icon_text = self._ai_icon if is_ai else self._user_icon
            icon = tk.Label(row, text=icon_text, bg=COLOR_BG, font=("Arial", 16))

        # 吹き出し
        bubble_color = COLOR_BUBBLE if is_ai else COLOR_USER_BUB
        name_color   = COLOR_ACCENT if is_ai else COLOR_ACCENT2
        bubble = tk.Frame(row, bg=bubble_color, padx=12, pady=8)

        name_label = tk.Label(
            bubble, text=sender,
            bg=bubble_color, fg=name_color,
            font=("Hiragino Sans", 10, "bold")
        )
        name_label.pack(anchor="w")

        wrap = max(200, self.winfo_width() - 120) if self.winfo_width() > 1 else 300
        msg_label = tk.Label(
            bubble, text=text,
            bg=bubble_color, fg=COLOR_TEXT,
            font=("Hiragino Sans", 12),
            wraplength=wrap, justify="left"
        )
        msg_label.pack(anchor="w")

        if is_ai:
            icon.pack(side="left", anchor="n", padx=(0, 6))
            bubble.pack(side="left", anchor="w")
        else:
            bubble.pack(side="right", anchor="e")
            icon.pack(side="right", anchor="n", padx=(6, 0))

        # 最下部へスクロール
        self.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

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
                    # 特定のプレースホルダーだけを削除（最後の子ではなく）
                    if placeholder is not None:
                        try:
                            placeholder.destroy()
                        except tk.TclError:
                            pass
                    self._add_message("アイ", response, is_ai=True)
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
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)
        self.root.configure(bg=WIN_BG)

        # 初期位置は画面中央に固定（_move_to_bottom_right で後から移動）
        self.root.geometry(f"{PET_WIDTH}x{PET_HEIGHT}+600+400")
        self._drag_x = 0
        self._drag_y = 0
        self._dragging = False
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
                60, 40, 160, 200, fill="#E8A5C8", outline="#B57BDC", width=3
            )
            self.canvas.create_text(
                PET_WIDTH // 2, 130,
                text="💗\nアイ", fill="#2D1B3D",
                font=("Hiragino Sans", 14, "bold"), justify="center"
            )
            self.sprite_id = None

        # ─── イベントバインド ───
        self._last_click_time = 0.0
        self._press_x = 0
        self._press_y = 0

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # 右クリック: macOS では Button-2 が右クリック、Button-3 はミドル
        # overrideredirect 環境では Release で拾う方が確実
        # 500ms デバウンスで Press/Release 二重発火を防止
        self._ctx_last_time = 0.0
        if IS_MAC:
            # macOS: Button-2 = 右クリック, Control+Button-1 = 右クリック代替
            ctx_seqs = ("<ButtonPress-2>", "<ButtonRelease-2>",
                        "<Control-ButtonPress-1>", "<Control-ButtonRelease-1>")
        else:
            # Windows/Linux: Button-3 = 右クリック
            ctx_seqs = ("<ButtonPress-3>", "<ButtonRelease-3>")
        for seq in ctx_seqs:
            self.canvas.bind(seq, self._show_context_menu)
            self.root.bind(seq, self._show_context_menu)

        # コンテキストメニュー
        self.context_menu = tk.Menu(self.root, tearoff=0,
                                     bg=COLOR_PANEL, fg=COLOR_TEXT,
                                     activebackground=COLOR_ACCENT,
                                     activeforeground=COLOR_BG)
        self.context_menu.add_command(label="チャットを開く",    command=self._open_chat)
        self.context_menu.add_command(label="アイの気分",  command=self._show_emotion)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="成長記録を見る",    command=self._open_graph)
        self.context_menu.add_command(label="議事録アプリ",      command=self._open_minutes)
        self.context_menu.add_command(label="スクリーンショット", command=self._on_screenshot)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="会話ログを保存",    command=self._open_export)
        self.context_menu.add_command(label="設定",              command=self._open_settings)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="終了",              command=self.root.quit)

    def _on_press(self, event):
        """マウス押下：ドラッグ起点を記録"""
        self._press_x = event.x_root
        self._press_y = event.y_root
        self._drag_x  = event.x_root - self.root.winfo_x()
        self._drag_y  = event.y_root - self.root.winfo_y()
        self._dragging = False

    def _drag_motion(self, event):
        """5px以上動いたらドラッグと判定"""
        if abs(event.x_root - self._press_x) > 5 or abs(event.y_root - self._press_y) > 5:
            self._dragging = True
        if self._dragging:
            x = event.x_root - self._drag_x
            y = event.y_root - self._drag_y
            self.root.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        """マウス離し：ドラッグ完了 or クリック判定"""
        if self._dragging:
            # ドラッグ後の位置をアニメ基準に確定
            # update_idletasks で compositor に反映を促してから winfo_x/y を読む
            self.root.update_idletasks()
            self._base_x = self.root.winfo_x()
            self._base_y = self.root.winfo_y()
            self._dragging = False
            return
        # ユーザー操作でアイドルタイマーをリセット
        self._last_interaction = time.time()
        # シングルクリックでチャットを開く
        self._open_chat()

    def _on_single_click(self):
        import random
        phrases = ["なあに？😊", "何かあった？", "一緒にいるよ💕",
                   "呼んだ？✨", "えへへ〜", "どうしたの？"]
        self._show_bubble(random.choice(phrases))

    def _open_chat(self, event=None):
        if self.chat_window is None or not self.chat_window.winfo_exists():
            self.chat_window = ChatWindow(self.root, self.ai_chan, pet=self)
        else:
            self.chat_window.deiconify()
            self.chat_window.lift()
            self.chat_window.after(50, self.chat_window._focus_input)

    def _show_context_menu(self, event):
        """
        macOS + overrideredirect 対応の右クリックメニュー表示。
        Press / Release が連続発火するため、500ms のデバウンスで抑止する。
        Release イベントのみで発火させ、Press は無視する。
        """
        # Release イベントのみ処理（Press で出すと Release で二重発火する）
        evt_type = str(event.type)
        if "Press" in evt_type or evt_type == "4":
            return

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
                # macOS overrideredirect: フォーカスを確実に奪う
                self.root.focus_force()
                self.root.lift()
                self.root.update_idletasks()
                self.context_menu.tk_popup(x, y, 0)
            except Exception as e:
                print(f"[Menu] popup failed: {e}", flush=True)
            finally:
                try:
                    self.context_menu.grab_release()
                except Exception:
                    pass

        # 50ms遅延でmacOSのフォーカス遷移を待つ（10msでは不足な場合がある）
        self.root.after(50, _popup)

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
        x = self.root.winfo_x() + PET_WIDTH // 2
        y = self.root.winfo_y() + 30
        self.bubble = SpeechBubble(self.root, text, x, y)

    def _greet(self):
        if self.ai_chan:
            def _gen():
                try:
                    resp = self.ai_chan.chat("起動した。一言だけ自然に話しかけて。")
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
            # Sprint 3.0-D: 感情に応じて色調を変化させる（10フレームに1回更新）
            display = self._display_base
            if self._anim_tick % 10 == 0:
                try:
                    if (self.ai_chan and hasattr(self.ai_chan, "expression")
                            and self.ai_chan.expression
                            and hasattr(self, "_base_image")):
                        emotion_dict = self.ai_chan.emotion.state.to_dict()
                        modified = self.ai_chan.expression.apply_emotion(
                            self._base_image, emotion_dict
                        )
                        # RGBA → RGB（背景色と合成）
                        r = int(WIN_BG[1:3], 16)
                        g = int(WIN_BG[3:5], 16)
                        b = int(WIN_BG[5:7], 16)
                        bg = Image.new("RGBA", modified.size, (r, g, b, 255))
                        composite = Image.alpha_composite(bg, modified.convert("RGBA"))
                        self._emotion_display = composite.convert("RGB")
                except Exception:
                    pass
            if hasattr(self, "_emotion_display"):
                display = self._emotion_display

            # わずかに拡縮するブリージングエフェクト
            scale = 1.0 + math.sin(self._anim_tick * 0.03) * 0.012
            iw, ih = display.size
            w = max(1, int(iw * scale))
            h = max(1, int(ih * scale))
            try:
                resized = display.resize((w, h), Image.LANCZOS)
                self._current_photo = ImageTk.PhotoImage(resized)
                self.canvas.itemconfig(self.sprite_id, image=self._current_photo)
            except Exception as e:
                if self._anim_tick <= 2:
                    print(f"[Pet] アニメエラー: {e}", flush=True)

        # ドラッグ中はアニメを停止
        # base_x を使うことで winfo_x() が 0 を返す macOS のタイミング問題を回避
        if by is not None and bx is not None and not self._dragging:
            try:
                self.root.geometry(f"+{bx}+{by + offset}")
            except tk.TclError:
                return

        self._anim_after_id = self.root.after(50, self._idle_anim)  # 20fps

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

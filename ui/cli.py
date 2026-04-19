"""
CLIインターフェース
rich ライブラリを使用した美しいターミナルUIを提供します
"""
from __future__ import annotations
import sys
import threading
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.spinner import Spinner
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from core.ai_chan import AiChan


console = Console() if RICH_AVAILABLE else None

HELP_TEXT = """
╭─────────────────────────────────────────────╮
│            アイ コマンド一覧             │
├─────────────────────────────────────────────┤
│ これを覚えて: ○○    記憶に保存               │
│ 絶対に覚えて: ○○    保護記憶に保存           │
│ これを忘れて: ○○    記憶を削除               │
│ 記憶を見せて        記憶の一覧を表示          │
│ 私の○○は△△だよ    プロファイル登録          │
│ /code [sub] <コード>  コードエンジン          │
│   sub: analyze / review / fix / run /        │
│        test / explain                        │
│ /review /fix /run /test /explain (省略形)    │
│ /status             現在の状態を表示          │
│ /stream on|off      ストリーミング表示の切替  │
│ モード              現在のモードを表示        │
│ 家族モード/お仕事モード/学習モード/創作モード │
│ 声紋登録 <名前>     声紋を登録                │
│ 声紋認証            声で本人確認              │
│ 声紋状態            声紋認証の状態を確認      │
│ 音声確認 / /voice   音声エンジンの状態確認    │
│ 音声テスト          テストフレーズを読み上げ  │
│ 音声切替 neural     ニューラル自然音声に切替  │
│ 音声切替 say        macOS say 音声に切替      │
│ 音声一覧            利用可能な音声の一覧      │
│ イントネーション学習 声を聞いて抑揚を学習    │
│ イントネーション確認 学習状態を確認          │
│ /help               このヘルプを表示          │
│ /quit               終了                     │
╰─────────────────────────────────────────────╯
""".strip()

# モードアイコンマッピング
MODE_ICONS = {"family": "\U0001f497", "agent": "\U0001f4bc", "learning": "\U0001f4da", "creative": "\U0001f3a8"}
MODE_NAMES = {"family": "ファミリー", "agent": "エージェント", "learning": "学習", "creative": "クリエイティブ"}


def print_header(ai_chan: AiChan):
    if RICH_AVAILABLE:
        status = "✓ LLM稼働中" if ai_chan.llm_loaded else "⚠ フォールバックモード（モデル未設定）"
        emotion_str = ai_chan.emotion.get_display_string()
        header = Text()
        header.append("💗 アイ ", style="bold magenta")
        header.append(f"v{ai_chan.persona['version']}\n", style="dim")
        header.append(f"   {status}\n", style="green" if ai_chan.llm_loaded else "yellow")
        header.append(f"   {emotion_str}", style="cyan")
        console.print(Panel(header, border_style="magenta"))
    else:
        print(f"=== アイ ===")
        print(f"LLM: {'稼働中' if ai_chan.llm_loaded else 'フォールバックモード'}")


def _prepend_mode_indicator(response: str, ai_chan) -> str:
    """familyモード以外の場合、レスポンスにモードアイコンを付与する"""
    mode_mgr = getattr(ai_chan, "mode_manager", None)
    if mode_mgr and mode_mgr.current_mode != "family":
        icon = MODE_ICONS.get(mode_mgr.current_mode, "")
        return f"{icon} {response}"
    return response


def print_ai_response(name: str, response: str):
    if RICH_AVAILABLE:
        console.print(f"\n[bold magenta]{name}:[/bold magenta]", end=" ")
        console.print(response)
    else:
        print(f"\n{name}: {response}")


def print_ai_stream_header(name: str, mode_prefix: str = ""):
    """ストリーミング表示用: 名前部分だけ先に出力"""
    prefix = f"{mode_prefix} " if mode_prefix else ""
    if RICH_AVAILABLE:
        console.print(f"\n[bold magenta]{name}:[/bold magenta] {prefix}", end="")
    else:
        print(f"\n{name}: {prefix}", end="", flush=True)


def _get_mode_prefix(ai_chan) -> str:
    """familyモード以外ならモードアイコンを返す"""
    mode_mgr = getattr(ai_chan, "mode_manager", None)
    if mode_mgr and mode_mgr.current_mode != "family":
        return MODE_ICONS.get(mode_mgr.current_mode, "")
    return ""


def chat_with_stream(ai_chan: AiChan, user_input: str) -> str:
    """
    E-05: ストリーミングモードでアイちゃんの応答を表示する。

    llm.generate_chat の stream_cb コールバックを使い、
    トークンが届くたびに即座にターミナルへ書き出す。
    コマンド系（cmd_response が存在する場合）はストリーミングをスキップし
    全文を返す従来動作にフォールバックする。
    """
    print_ai_stream_header(ai_chan.name, _get_mode_prefix(ai_chan))

    # ストリーミング中に文字を蓄積するバッファ
    _buf: list[str] = []
    _stream_done = threading.Event()

    def _on_token(token: str) -> None:
        _buf.append(token)
        if RICH_AVAILABLE:
            # richのコンソールでインライン出力
            console.print(token, end="", highlight=False)
        else:
            sys.stdout.write(token)
            sys.stdout.flush()

    # chat() を呼び出す（stream_cb が有効なときのみLLMがストリーミングする）
    response = ai_chan.chat(user_input, stream_cb=_on_token)

    # ストリーミングトークンが全く届かなかった場合（コマンド系など）は
    # response をそのまま表示する
    if not _buf:
        if RICH_AVAILABLE:
            console.print(response)
        else:
            print(response)
    else:
        # 改行だけ付けて完了
        if RICH_AVAILABLE:
            console.print()
        else:
            print()

    return response


def print_user_prompt():
    if RICH_AVAILABLE:
        return console.input("\n[bold cyan]あなた:[/bold cyan] ")
    else:
        return input("\nあなた: ")


def run_cli(base_dir: str | Path = "."):
    """CLIメインループ"""
    base_dir = Path(base_dir)

    if RICH_AVAILABLE:
        with console.status("[magenta]アイを起動しています...[/magenta]", spinner="hearts"):
            ai_chan = AiChan(base_dir=base_dir)
    else:
        print("アイを起動しています...")
        ai_chan = AiChan(base_dir=base_dir)

    print_header(ai_chan)

    if not ai_chan.llm_loaded:
        if RICH_AVAILABLE:
            console.print(
                "[yellow]⚠ モデルファイルが見つかりません。\n"
                "  [bold]python scripts/setup_model.py[/bold] を実行してモデルをダウンロードしてください。\n"
                "  フォールバックモードで起動します。[/yellow]"
            )
        else:
            print("⚠ モデルファイルが見つかりません。scripts/setup_model.py を実行してください。")

    # E-05: ストリーミングモード（デフォルト有効）
    streaming_enabled: bool = True

    # 声紋IDによるパーソナライズ挨拶
    voice_id = getattr(ai_chan, "voice_id", None)
    if voice_id:
        vid_greeting = voice_id.get_greeting()
        if RICH_AVAILABLE:
            console.print(f"  [dim]{vid_greeting}[/dim]")
        else:
            print(f"  {vid_greeting}")

    # 起動挨拶（ストリーミングなし — スピナーと重複するため）
    greeting = ai_chan.chat("起動しました。挨拶して。")
    print_ai_response(ai_chan.name, greeting)

    # メインループ
    while True:
        try:
            user_input = print_user_prompt()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # ─── システムコマンド ───────────────────────────────────

        if user_input.lower() in ("/quit", "/exit", "終了", "さようなら"):
            farewell = ai_chan.chat("さようならの挨拶をして。")
            print_ai_response(ai_chan.name, farewell)
            break

        if user_input.lower() in ("/help", "ヘルプ"):
            print(HELP_TEXT)
            continue

        if user_input.lower() == "/status":
            status = ai_chan.get_status()
            import json
            if RICH_AVAILABLE:
                console.print_json(json.dumps(status, ensure_ascii=False, indent=2))
            else:
                print(json.dumps(status, ensure_ascii=False, indent=2))
            continue

        # モード表示コマンド
        if user_input in ("モード", "/mode"):
            mode_mgr = getattr(ai_chan, "mode_manager", None)
            if mode_mgr:
                cur = mode_mgr.current_mode
                icon = MODE_ICONS.get(cur, "")
                name = MODE_NAMES.get(cur, cur)
                if RICH_AVAILABLE:
                    console.print(f"  [bold]{icon} 現在のモード: {name}[/bold]")
                else:
                    print(f"  {icon} 現在のモード: {name}")
            else:
                print("  モード管理は利用できません")
            continue

        # E-05: ストリーミング切替コマンド
        if user_input.lower() in ("/stream on", "/stream オン"):
            streaming_enabled = True
            print("✅ ストリーミング表示: ON")
            continue
        if user_input.lower() in ("/stream off", "/stream オフ"):
            streaming_enabled = False
            print("⏸ ストリーミング表示: OFF")
            continue

        # ─── 通常の対話 ─────────────────────────────────────────

        if streaming_enabled and ai_chan.llm_loaded:
            # ストリーミングモード
            # NOTE: console.status (Live renderer) はスレッドセーフではないため、
            #       別スレッドでスピナーを回しながら console.print すると
            #       デッドロックする。代わりにシンプルなテキスト表示を使う。
            if RICH_AVAILABLE:
                # 「考えています…」を表示し、最初のトークンで上書き
                _thinking_msg = f"  [dim magenta]{ai_chan.name}が考えています…[/dim magenta]"
                console.print(_thinking_msg, end="\r")

                _first = [True]
                _buf: list[str] = []

                def _stream_cb_rich(token: str) -> None:
                    if _first[0]:
                        _first[0] = False
                        # 「考えています…」行を空白で消去
                        sys.stdout.write("\r" + " " * 60 + "\r")
                        sys.stdout.flush()
                        print_ai_stream_header(ai_chan.name, _get_mode_prefix(ai_chan))
                    _buf.append(token)
                    console.print(token, end="", highlight=False)

                response = ai_chan.chat(user_input, stream_cb=_stream_cb_rich)
                if _buf:
                    console.print()  # 改行
                else:
                    # コマンド系でトークンが届かなかった場合
                    sys.stdout.write("\r" + " " * 60 + "\r")
                    sys.stdout.flush()
                    response = _prepend_mode_indicator(response, ai_chan)
                    print_ai_response(ai_chan.name, response)
            else:
                # richなし: 単純なストリーミング
                response = chat_with_stream(ai_chan, user_input)
        else:
            # 従来モード（ストリーミングOFF、またはLLM未ロード）
            if RICH_AVAILABLE:
                with console.status(
                    f"[magenta]{ai_chan.name}が考えています...[/magenta]",
                    spinner="hearts",
                ):
                    response = ai_chan.chat(user_input)
            else:
                response = ai_chan.chat(user_input)
            response = _prepend_mode_indicator(response, ai_chan)
            print_ai_response(ai_chan.name, response)

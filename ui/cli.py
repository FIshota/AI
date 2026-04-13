"""
CLIインターフェース
rich ライブラリを使用した美しいターミナルUIを提供します
"""
from __future__ import annotations
import sys
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
╭─────────────────────────────────────╮
│         アイ コマンド一覧        │
├─────────────────────────────────────┤
│ これを覚えて: ○○    記憶に保存        │
│ 絶対に覚えて: ○○    保護記憶に保存    │
│ これを忘れて: ○○    記憶を削除        │
│ 記憶を見せて        記憶の一覧を表示   │
│ 私の○○は△△だよ    プロファイル登録   │
│ /status             現在の状態を表示  │
│ /help               このヘルプを表示  │
│ /quit               終了              │
╰─────────────────────────────────────╯
""".strip()


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


def print_ai_response(name: str, response: str):
    if RICH_AVAILABLE:
        console.print(f"\n[bold magenta]{name}:[/bold magenta]", end=" ")
        console.print(response)
    else:
        print(f"\n{name}: {response}")


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

    # 起動挨拶
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

        # システムコマンド
        if user_input.lower() in ("/quit", "/exit", "終了", "さようなら"):
            farewell = ai_chan.chat("さようならの挨拶をして。")
            print_ai_response(ai_chan.name, farewell)
            break

        if user_input.lower() in ("/help", "ヘルプ"):
            print(HELP_TEXT)
            continue

        if user_input.lower() == "/status":
            status = ai_chan.get_status()
            if RICH_AVAILABLE:
                import json
                console.print_json(json.dumps(status, ensure_ascii=False, indent=2))
            else:
                import json
                print(json.dumps(status, ensure_ascii=False, indent=2))
            continue

        # 通常の対話
        if RICH_AVAILABLE:
            with console.status(f"[magenta]{ai_chan.name}が考えています...[/magenta]", spinner="hearts"):
                response = ai_chan.chat(user_input)
        else:
            response = ai_chan.chat(user_input)

        print_ai_response(ai_chan.name, response)

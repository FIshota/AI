"""
カレンダー連携エンジン（機能④）
AppleScript で macOS Calendar.app のイベントを読みます。
追加インストール不要・完全ローカル。
"""
from __future__ import annotations
import subprocess
import json
import re
import platform
from datetime import datetime, timedelta

IS_MAC = platform.system() == "Darwin"

# 取得する日数の範囲
_LOOKAHEAD_DAYS = 3   # 今日から3日先まで


def _run_applescript(script: str) -> str | None:
    """AppleScript を実行して stdout を返す"""
    if not IS_MAC:
        return None
    try:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        return res.stdout.strip() if res.returncode == 0 else None
    except Exception:
        return None


def get_upcoming_events(days: int = _LOOKAHEAD_DAYS) -> list[dict]:
    """
    今日から days 日以内のカレンダーイベントを取得する。
    戻り値: [{"title": str, "start": str, "calendar": str}, ...]
    """
    if not IS_MAC:
        return []

    today   = datetime.now().date()
    end_day = today + timedelta(days=days)

    script = f"""
    set startDate to date "{today.strftime('%Y/%m/%d')} 00:00:00"
    set endDate to date "{end_day.strftime('%Y/%m/%d')} 23:59:59"
    set output to ""
    tell application "Calendar"
        set allCals to every calendar
        repeat with aCal in allCals
            set calName to name of aCal
            set theEvents to (every event of aCal whose start date >= startDate and start date <= endDate)
            repeat with anEvent in theEvents
                set evTitle to summary of anEvent
                set evStart to start date of anEvent as string
                set output to output & calName & "|||" & evTitle & "|||" & evStart & "###"
            end repeat
        end repeat
    end tell
    return output
    """

    raw = _run_applescript(script)
    if not raw:
        return []

    events = []
    for chunk in raw.split("###"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("|||")
        if len(parts) >= 3:
            events.append({
                "calendar": parts[0].strip(),
                "title":    parts[1].strip(),
                "start":    parts[2].strip(),
            })
    return events


def build_calendar_hint(days: int = _LOOKAHEAD_DAYS) -> str | None:
    """
    近日中のイベントを会話ヒント文字列として返す。
    イベントがなければ None。
    """
    events = get_upcoming_events(days)
    if not events:
        return None
    if len(events) == 1:
        ev = events[0]
        return f"近日中の予定「{ev['title']}」がカレンダーにあるよ"
    titles = "、".join(f"「{e['title']}」" for e in events[:3])
    return f"近日中の予定が{len(events)}件あるよ（{titles}など）"


def format_events_for_chat(days: int = _LOOKAHEAD_DAYS) -> str:
    """チャットに表示するイベント一覧テキストを返す"""
    events = get_upcoming_events(days)
    if not events:
        return f"今後{days}日以内の予定は見つからなかったよ。"
    lines = [f"今後{days}日以内の予定だよ："]
    for ev in events[:10]:
        # 日付部分だけ抽出
        start = ev["start"]
        m = re.search(r'\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2}', start)
        date_str = m.group(0) if m else start[:10]
        lines.append(f"・{date_str}  {ev['title']}（{ev['calendar']}）")
    return "\n".join(lines)

"""
Google Calendar API 連携
アクションアイテムの期日・次回会議を Google Calendar に登録する。

事前準備:
  1. Google Cloud Console でプロジェクト作成 → Calendar API 有効化
  2. OAuth 2.0 クライアントID (デスクトップアプリ) を作成してJSONをダウンロード
  3. config/integrations.json の google.credentials_file にパスを設定
  4. 初回起動時にブラウザで認証 → token.json が自動生成される
"""
from __future__ import annotations
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GCAL_OK = True
except ImportError:
    GCAL_OK = False

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GCalConnector:
    """Google Calendar への書き出しを担当"""

    def __init__(
        self,
        credentials_file: str = "",
        token_file: str = "",
        calendar_id: str = "primary",
    ):
        self.credentials_file = credentials_file
        self.token_file       = token_file or str(
            Path(credentials_file).parent / "gcal_token.json"
            if credentials_file else ""
        )
        self.calendar_id = calendar_id
        self._service    = None

    def is_configured(self) -> bool:
        return bool(self.credentials_file and GCAL_OK
                    and Path(self.credentials_file).exists())

    def _get_service(self):
        if self._service:
            return self._service
        if not GCAL_OK:
            raise RuntimeError("google-api-python-client が未インストールです")
        creds = None
        token_path = Path(self.token_file)
        creds_path = Path(self.credentials_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow  = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    # ─── 接続テスト ──────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        if not GCAL_OK:
            return False, "google-api-python-client が未インストールです"
        if not self.credentials_file:
            return False, "credentials ファイルが未設定です"
        if not Path(self.credentials_file).exists():
            return False, f"credentials ファイルが見つかりません: {self.credentials_file}"
        try:
            svc = self._get_service()
            cal = svc.calendars().get(calendarId=self.calendar_id).execute()
            return True, f"接続成功: カレンダー「{cal.get('summary', self.calendar_id)}」"
        except Exception as e:
            return False, f"接続失敗: {e}"

    # ─── 次回会議をカレンダーに追加 ─────────────────────────────

    def push_meeting(
        self,
        title:       str,
        start_date:  str,        # YYYY-MM-DD
        start_time:  str = "10:00",
        duration_h:  float = 1.0,
        description: str = "",
        location:    str = "",
    ) -> tuple[bool, str]:
        """会議予定をGoogleカレンダーに追加"""
        if not self.is_configured():
            return False, "Google Calendar が設定されていません"
        try:
            svc = self._get_service()
            start_dt = datetime.strptime(
                f"{start_date} {start_time}", "%Y-%m-%d %H:%M"
            )
            end_dt = start_dt + timedelta(hours=duration_h)

            event = {
                "summary":     title,
                "location":    location,
                "description": description,
                "start": {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": "Asia/Tokyo",
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": "Asia/Tokyo",
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 30},
                        {"method": "email", "minutes": 60 * 24},
                    ],
                },
            }
            created = svc.events().insert(
                calendarId=self.calendar_id, body=event
            ).execute()
            return True, created.get("htmlLink", "")

        except Exception as e:
            return False, f"カレンダー登録失敗: {e}"

    # ─── アクションアイテムの期日をカレンダーに追加 ─────────────

    def push_action_item(
        self,
        item:          dict,
        meeting_title: str = "",
    ) -> tuple[bool, str]:
        """
        アクションアイテムを終日イベントとしてカレンダーに追加。
        due_date がない場合は登録しない。
        """
        if not item.get("due_date"):
            return False, "期日が未設定のため登録しませんでした"
        if not self.is_configured():
            return False, "Google Calendar が設定されていません"

        task    = item.get("task", "タスク")
        owner   = item.get("owner", "")
        due     = item["due_date"]
        summary = f"[TODO] {task}"
        if owner:
            summary += f"（{owner}）"
        if meeting_title:
            summary = f"[{meeting_title}] {summary}"

        desc = f"会議「{meeting_title}」のアクションアイテム\n" if meeting_title else ""
        if owner:
            desc += f"担当: {owner}\n"
        desc += f"タスク: {task}\n"
        desc += f"by アイ議事録アプリ"

        try:
            svc = self._get_service()
            event = {
                "summary":     summary,
                "description": desc,
                "start":       {"date": due},
                "end":         {"date": due},
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 60 * 9}],
                },
                "colorId": "6",  # タンジェリン
            }
            created = svc.events().insert(
                calendarId=self.calendar_id, body=event
            ).execute()
            return True, created.get("htmlLink", "")
        except Exception as e:
            return False, f"失敗: {e}"

    # ─── アクションアイテム一括登録 ─────────────────────────────

    def push_all_action_items(
        self, items: list[dict], meeting_title: str = ""
    ) -> dict:
        """複数アクションアイテムを一括登録。結果サマリを返す"""
        ok, fail, skip = 0, 0, 0
        for item in items:
            if not item.get("due_date"):
                skip += 1
                continue
            success, _ = self.push_action_item(item, meeting_title)
            if success:
                ok += 1
            else:
                fail += 1
        return {"ok": ok, "fail": fail, "skip": skip}

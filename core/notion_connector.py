"""
Notion API 連携
議事録・アクションアイテムを Notion データベースに書き出す。

事前準備:
  1. https://www.notion.so/my-integrations でインテグレーション作成
  2. 対象データベースをインテグレーションと共有
  3. config/integrations.json に api_key と database_id を設定
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

try:
    from notion_client import Client as NotionClient
    NOTION_OK = True
except ImportError:
    NOTION_OK = False


class NotionConnector:
    """Notion API への書き出しを担当"""

    def __init__(self, api_key: str = "", database_id: str = ""):
        self.api_key      = api_key
        self.database_id  = database_id
        self._client: NotionClient | None = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.database_id and NOTION_OK)

    def _get_client(self) -> NotionClient:
        if not self._client:
            if not NOTION_OK:
                raise RuntimeError("notion-client が未インストールです")
            self._client = NotionClient(auth=self.api_key)
        return self._client

    # ─── 接続テスト ──────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """接続テスト。(成功可否, メッセージ) を返す"""
        if not NOTION_OK:
            return False, "notion-client が未インストールです（pip install notion-client）"
        if not self.api_key:
            return False, "Notion API キーが未設定です"
        if not self.database_id:
            return False, "Notion データベース ID が未設定です"
        try:
            client = self._get_client()
            db = client.databases.retrieve(database_id=self.database_id)
            title = ""
            for t in db.get("title", []):
                title += t.get("plain_text", "")
            return True, f"接続成功: データベース「{title or self.database_id[:8]}…」"
        except Exception as e:
            return False, f"接続失敗: {e}"

    # ─── 議事録をページとして追加 ────────────────────────────────

    def push_minutes(self, entry: dict, structured: dict | None = None) -> tuple[bool, str]:
        """
        議事録1件を Notion データベースのページとして追加。
        structured: MinutesExtractor の抽出結果（オプション）
        戻り値: (成功可否, Notion ページ URL または エラーメッセージ)
        """
        if not self.is_configured():
            return False, "Notion が設定されていません"
        try:
            client = self._get_client()

            # ── ページプロパティ ──
            props = {
                "名前": {
                    "title": [{"text": {"content": entry.get("title", "無題の会議")}}]
                },
                "日付": {
                    "date": {"start": entry.get("date", date.today().isoformat())}
                },
            }

            # 参加者プロパティ（テキスト型）
            if entry.get("attendees"):
                props["参加者"] = {
                    "rich_text": [{"text": {"content": entry["attendees"]}}]
                }

            # ステータスプロパティ（存在する場合）
            props["ステータス"] = {
                "select": {"name": "完了"}
            }

            # ── ページ本文（ブロック） ──
            children = []

            # 議事録本文
            formatted = entry.get("formatted") or entry.get("transcript", "")
            for line in formatted.splitlines():
                line = line.strip()
                if not line:
                    children.append({"object": "block", "type": "paragraph",
                                     "paragraph": {"rich_text": []}})
                    continue
                if line.startswith("## "):
                    children.append({
                        "object": "block", "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text",
                                           "text": {"content": line.lstrip("# ")}}]
                        }
                    })
                elif line.startswith(("・", "•", "-")):
                    children.append({
                        "object": "block", "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text",
                                           "text": {"content": line.lstrip("・•- ")}}]
                        }
                    })
                else:
                    children.append({
                        "object": "block", "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text",
                                           "text": {"content": line}}]
                        }
                    })

            # アクションアイテムをデータベース埋め込みリスト
            if structured and structured.get("action_items"):
                children.append({"object": "block", "type": "divider",
                                  "divider": {}})
                children.append({
                    "object": "block", "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": "📋 アクションアイテム一覧"}}]
                    }
                })
                for item in structured["action_items"]:
                    task     = item.get("task", "")
                    owner    = item.get("owner", "")
                    due      = item.get("due_label") or item.get("due_date", "")
                    content  = f"{task}"
                    if owner:
                        content += f"  ［担当: {owner}］"
                    if due:
                        content += f"  ［期限: {due}］"
                    children.append({
                        "object": "block", "type": "to_do",
                        "to_do": {
                            "rich_text": [{"text": {"content": content}}],
                            "checked": False,
                        }
                    })

            # メタ情報フッター
            children.append({"object": "block", "type": "divider", "divider": {}})
            children.append({
                "object": "block", "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {
                        "content": f"議事録ID: {entry.get('id', '')}  "
                                   f"作成: {entry.get('created_at', '')}  "
                                   f"by アイ",
                    }}],
                    "color": "gray",
                }
            })

            # Notion にページを作成
            page = client.pages.create(
                parent={"database_id": self.database_id},
                properties=props,
                children=children[:100],  # Notion API の1回上限
            )
            page_url = page.get("url", "")
            return True, page_url

        except Exception as e:
            return False, f"Notion 書き出し失敗: {e}"

    # ─── アクションアイテム単体を TODO ページとして追加 ────────────

    def push_action_item(
        self, item: dict, meeting_title: str = "", database_id: str = ""
    ) -> tuple[bool, str]:
        """アクションアイテム1件を Notion に追加"""
        if not self.is_configured():
            return False, "Notion が設定されていません"
        db_id = database_id or self.database_id
        try:
            client = self._get_client()
            title  = item.get("task", "タスク")
            if meeting_title:
                title = f"[{meeting_title}] {title}"

            props: dict = {
                "名前": {"title": [{"text": {"content": title}}]},
                "ステータス": {"select": {"name": "未完了"}},
            }
            if item.get("due_date"):
                props["期日"] = {"date": {"start": item["due_date"]}}
            if item.get("owner"):
                props["担当者"] = {
                    "rich_text": [{"text": {"content": item["owner"]}}]
                }

            page = client.pages.create(
                parent={"database_id": db_id},
                properties=props,
            )
            return True, page.get("url", "")
        except Exception as e:
            return False, f"失敗: {e}"

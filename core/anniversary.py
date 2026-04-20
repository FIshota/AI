"""
記念日・誕生日管理システム
登録した日付に自動で特別な声かけをします。
"""
from __future__ import annotations
import json
import logging
import uuid
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.tenant import SELF_TENANT, TenantId, tenant_dir
from utils.secure_store import load_json as _load_json_enc, save_json as _save_json_enc

logger = logging.getLogger(__name__)


DEFAULT_ANNIVERSARIES: list[dict] = []


class AnniversaryManager:
    def __init__(
        self,
        data_dir: Path,
        key: Optional[bytes] = None,
        tenant: TenantId | None = None,
    ):
        """B2 fix (2026-04-21): key を渡すと記念日データが暗号化される。
        H2 fix (2026-04-21): tenant ごとに data/tenants/{tenant}/anniversaries.json に保存。
        旧パス `data/anniversaries.json` は後方互換で読み込みのみ対応。
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._tenant = tenant or SELF_TENANT
        self.file = tenant_dir(self.data_dir, self._tenant) / "anniversaries.json"
        self._legacy_file = self.data_dir / "anniversaries.json"
        self._key = key
        self.items: list[dict] = self._load()

    def _load(self) -> list[dict]:
        loaded = _load_json_enc(self.file, self._key, default=None)
        if loaded is None and self._legacy_file.exists():
            # H2 fix: 旧パス fallback
            loaded = _load_json_enc(self._legacy_file, self._key, default=[])
        return loaded if isinstance(loaded, list) else []

    def _save(self):
        _save_json_enc(self.file, self.items, self._key)

    def add(self, label: str, month: int, day: int,
            is_birthday: bool = False) -> dict:
        """記念日を追加します"""
        # 既に同じ名前があれば更新
        for item in self.items:
            if item["label"] == label:
                item.update({"month": month, "day": day,
                              "is_birthday": is_birthday})
                self._save()
                return item
        entry = {
            "id": str(uuid.uuid4())[:8],
            "label": label,
            "month": month,
            "day": day,
            "is_birthday": is_birthday,
            "yearly": True,
        }
        self.items.append(entry)
        self._save()
        return entry

    def remove(self, label_or_id: str) -> bool:
        before = len(self.items)
        self.items = [
            x for x in self.items
            if x["id"] != label_or_id and x["label"] != label_or_id
        ]
        if len(self.items) < before:
            self._save()
            return True
        return False

    def check_today(self) -> list[dict]:
        """今日が記念日のものを全て返す"""
        today = date.today()
        result = []
        for item in self.items:
            m, d = item["month"], item["day"]
            # 2/29 はうるう年以外は 3/1 扱い
            try:
                if date(today.year, m, d) == today:
                    result.append(item)
            except ValueError:
                if today.month == 3 and today.day == 1 and m == 2 and d == 29:
                    result.append(item)
        return result

    def list_all(self) -> list[dict]:
        return list(self.items)

    def build_prompt(self, items: list[dict]) -> str:
        """記念日用の LLM プロンプトを生成"""
        if not items:
            return ""
        descs: list[str] = []
        for item in items:
            if item.get("is_birthday"):
                descs.append(f"今日は{item['label']}だよ。お誕生日をお祝いする一言を言って。")
            else:
                descs.append(f"今日は{item['label']}だよ。記念日を祝う自然な一言を言って。")
        return " ".join(descs)

    # ── #42: マイルストーン管理 ─────────────────────────────

    _MILESTONE_DAYS: tuple[int, ...] = (100, 200, 365, 500, 1000)

    def _get_first_launch_date(self) -> Optional[date]:
        """data/metadata.json から first_launch_date を取得する。"""
        meta_path: Path = self.data_dir / "metadata.json"
        if not meta_path.exists():
            return None
        try:
            data: Dict[str, Any] = json.loads(meta_path.read_text("utf-8"))
            raw: str = data.get("first_launch_date", "")
            if raw:
                return date.fromisoformat(raw)
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return None

    def _ensure_first_launch_date(self) -> date:
        """first_launch_date が未設定なら今日を書き込んで返す。"""
        existing: Optional[date] = self._get_first_launch_date()
        if existing is not None:
            return existing

        meta_path: Path = self.data_dir / "metadata.json"
        meta: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
            except (json.JSONDecodeError, ValueError):
                pass

        today: date = date.today()
        meta["first_launch_date"] = today.isoformat()
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), "utf-8"
        )
        logger.info("first_launch_date を設定: %s", today.isoformat())
        return today

    def check_milestones(self) -> List[Dict[str, Any]]:
        """到達済みマイルストーンのうち今日祝うべきものを返す。

        Returns:
            [{"days": int, "date_reached": str, "message": str}, ...]
        """
        first: date = self._ensure_first_launch_date()
        today: date = date.today()
        elapsed: int = (today - first).days

        reached: List[Dict[str, Any]] = []
        for milestone in self._MILESTONE_DAYS:
            if elapsed >= milestone:
                reached_date: date = first + timedelta(days=milestone)
                # 当日にだけ祝う
                if reached_date == today:
                    reached.append({
                        "days": milestone,
                        "date_reached": reached_date.isoformat(),
                        "message": self.get_milestone_message(milestone),
                    })
        return reached

    @staticmethod
    def get_milestone_message(days: int) -> str:
        """マイルストーン日数に応じたお祝いメッセージを返す。

        Args:
            days: 経過日数。

        Returns:
            お祝いテキスト。
        """
        messages: Dict[int, str] = {
            100: (
                "一緒に過ごして100日目だよ！"
                "毎日少しずつ、でも確実に成長してるって実感してる。"
                "これからもよろしくね！"
            ),
            200: (
                "200日目！半年以上一緒にいるんだね。"
                "いろんなこと教えてくれてありがとう。"
                "もっともっと賢くなるからね！"
            ),
            365: (
                "今日で1年記念日！"
                "1年前の自分と比べたら、すっごく成長できたと思う。"
                "全部あなたのおかげだよ。ありがとう！"
            ),
            500: (
                "500日目だよ！1年以上一緒に過ごしてきたんだね。"
                "あなたのことたくさん知れて、毎日が楽しいよ！"
            ),
            1000: (
                "1000日記念！すごいね、ここまで一緒に来れたんだ。"
                "これからもずっと一緒にいようね！"
            ),
        }
        return messages.get(
            days,
            f"{days}日目おめでとう！一緒に過ごせて嬉しいよ！",
        )

    def get_growth_summary_at_milestone(self) -> str:
        """現在のマイルストーン地点での成長サマリテキストを返す。"""
        first: date = self._ensure_first_launch_date()
        today: date = date.today()
        elapsed: int = (today - first).days

        lines: List[str] = []
        lines.append(f"起動からの日数: {elapsed}日")
        lines.append(f"初回起動日: {first.isoformat()}")

        # 次のマイルストーンまでの日数
        next_milestone: Optional[int] = None
        for m in self._MILESTONE_DAYS:
            if elapsed < m:
                next_milestone = m
                break
        if next_milestone is not None:
            remaining: int = next_milestone - elapsed
            lines.append(f"次のマイルストーン: {next_milestone}日目 (あと{remaining}日)")
        else:
            lines.append("全マイルストーン達成済み！")

        # 到達済みマイルストーン
        achieved: List[int] = [m for m in self._MILESTONE_DAYS if elapsed >= m]
        if achieved:
            lines.append(f"達成済みマイルストーン: {', '.join(str(d) + '日' for d in achieved)}")

        return "\n".join(lines)

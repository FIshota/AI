"""
自動学習エンジン
定期スケジュールに従って YouTube・Web・ファイルを自律的に学習します。

スケジュール例:
  - 毎日 9:00〜9:30: 登録済み YouTube チャンネルから新着を学習
  - 毎日 14:00〜14:30: 登録済み Web URL を再読み込み
  - 毎週月曜 10:00: 学習データを振り返り・要約

オフラインファースト:
  - URL は事前登録しておきローカルキャッシュを優先参照
  - ネットワーク不可時はキャッシュ済みコンテンツで代替
"""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path
from datetime import datetime, date, timedelta


# ─── デフォルトスケジュール ──────────────────────────────────────

DEFAULT_SCHEDULE = [
    {
        "id": "morning_web",
        "name": "午前の Web 学習",
        "enabled": False,
        "hour": 9,
        "minute": 0,
        "days": [0, 1, 2, 3, 4],   # 月〜金
        "type": "web_list",         # 登録 URL を順番に学習
        "max_items": 2,
        "note": "平日朝に登録 URL を最大2件学習",
    },
    {
        "id": "afternoon_youtube",
        "name": "午後の YouTube 学習",
        "enabled": False,
        "hour": 14,
        "minute": 0,
        "days": [0, 1, 2, 3, 4, 5, 6],
        "type": "youtube_list",
        "max_items": 1,
        "note": "毎日昼に YouTube を最大1件学習",
    },
    {
        "id": "weekly_review",
        "name": "週次振り返り",
        "enabled": False,
        "hour": 10,
        "minute": 0,
        "days": [0],                # 月曜のみ
        "type": "review",
        "max_items": 0,
        "note": "月曜朝に学習データを振り返り要約",
    },
    {
        "id": "evening_memo",
        "name": "夜のメモ復習",
        "enabled": False,
        "hour": 21,
        "minute": 0,
        "days": [0, 1, 2, 3, 4, 5, 6],
        "type": "memo_review",
        "max_items": 3,
        "note": "毎晩21時に登録メモをランダムに復習",
    },
]


class AutoLearner:
    """
    定期自動学習エンジン。
    バックグラウンドスレッドでスケジュールを監視し、
    条件一致時に学習を実行してコールバックで結果を通知します。
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._schedule_path  = self.data_dir / "auto_learn_schedule.json"
        self._log_path       = self.data_dir / "auto_learn_log.jsonl"
        self._sources_path   = self.data_dir / "auto_learn_sources.json"
        self._fired_path     = self.data_dir / "auto_learn_fired.json"

        self._schedule: list[dict] = self._load_schedule()
        self._sources:  dict       = self._load_sources()
        self._fired:    dict       = self._load_fired()   # {id: "YYYY-MM-DD"}

        self._on_complete = None   # callback(result_text: str)
        self._ai_chan     = None
        self._stop_event  = threading.Event()
        self._thread: threading.Thread | None = None

    # ─── 設定 ────────────────────────────────────────────────────

    def _load_schedule(self) -> list[dict]:
        if self._schedule_path.exists():
            try:
                return json.loads(self._schedule_path.read_text("utf-8"))
            except Exception:
                pass
        self._schedule_path.write_text(
            json.dumps(DEFAULT_SCHEDULE, ensure_ascii=False, indent=2), "utf-8"
        )
        return [dict(s) for s in DEFAULT_SCHEDULE]

    def _save_schedule(self):
        self._schedule_path.write_text(
            json.dumps(self._schedule, ensure_ascii=False, indent=2), "utf-8"
        )

    def _load_sources(self) -> dict:
        """学習ソース一覧 {"youtube": [...urls], "web": [...urls], "files": [...paths]}"""
        if self._sources_path.exists():
            try:
                return json.loads(self._sources_path.read_text("utf-8"))
            except Exception:
                pass
        default = {"youtube": [], "web": [], "files": []}
        self._sources_path.write_text(
            json.dumps(default, ensure_ascii=False, indent=2), "utf-8"
        )
        return default

    def _save_sources(self):
        self._sources_path.write_text(
            json.dumps(self._sources, ensure_ascii=False, indent=2), "utf-8"
        )

    def _load_fired(self) -> dict:
        if self._fired_path.exists():
            try:
                return json.loads(self._fired_path.read_text("utf-8"))
            except Exception:
                pass
        return {}

    def _save_fired(self):
        self._fired_path.write_text(
            json.dumps(self._fired, ensure_ascii=False), "utf-8"
        )

    # ─── ソース管理 ──────────────────────────────────────────────

    def add_source(self, kind: str, value: str) -> bool:
        """youtube / web / files にソースを追加"""
        if kind not in self._sources:
            return False
        if value not in self._sources[kind]:
            self._sources[kind].append(value)
            self._save_sources()
        return True

    def remove_source(self, kind: str, value: str) -> bool:
        if kind not in self._sources:
            return False
        if value in self._sources[kind]:
            self._sources[kind].remove(value)
            self._save_sources()
            return True
        return False

    def get_sources(self, kind: str) -> list[str]:
        return list(self._sources.get(kind, []))

    # ─── スケジュール管理 ────────────────────────────────────────

    def get_schedule(self) -> list[dict]:
        return list(self._schedule)

    def set_schedule_enabled(self, schedule_id: str, enabled: bool):
        for s in self._schedule:
            if s["id"] == schedule_id:
                s["enabled"] = enabled
        self._save_schedule()

    def update_schedule(self, schedule_id: str, hour: int, minute: int, days: list[int]):
        for s in self._schedule:
            if s["id"] == schedule_id:
                s["hour"]   = hour
                s["minute"] = minute
                s["days"]   = days
        self._save_schedule()

    # ─── スケジュールチェック ────────────────────────────────────

    def _should_fire(self, sched: dict) -> bool:
        """このスケジュールを今実行すべきか判定（当日1回のみ）"""
        if not sched.get("enabled", False):
            return False
        now  = datetime.now()
        wday = now.weekday()   # 0=月曜
        if wday not in sched.get("days", []):
            return False
        if now.hour != sched["hour"]:
            return False
        if abs(now.minute - sched["minute"]) > 5:   # ±5分以内
            return False
        # 当日すでに発火済みか
        today = date.today().isoformat()
        if self._fired.get(sched["id"]) == today:
            return False
        return True

    def check_and_fire(self) -> list[str]:
        """
        スケジュールをチェックし、条件を満たすものを実行。
        実行した結果テキストのリストを返す。
        """
        results = []
        for sched in self._schedule:
            if self._should_fire(sched):
                today = date.today().isoformat()
                self._fired[sched["id"]] = today
                self._save_fired()
                result = self._execute(sched)
                if result:
                    results.append(result)
        return results

    # ─── 実行 ────────────────────────────────────────────────────

    def _execute(self, sched: dict) -> str | None:
        """スケジュールを実行して結果テキストを返す"""
        kind = sched.get("type", "")
        try:
            if kind == "youtube_list":
                return self._learn_youtube_batch(sched.get("max_items", 1))
            if kind == "web_list":
                return self._learn_web_batch(sched.get("max_items", 2))
            if kind == "review":
                return self._review_learned()
            if kind == "memo_review":
                return self._review_memos(sched.get("max_items", 3))
        except Exception as e:
            print(f"[AutoLearn] 実行エラー ({sched['id']}): {e}", flush=True)
        return None

    def _learn_youtube_batch(self, max_items: int) -> str | None:
        if not self._ai_chan:
            return None
        urls = self.get_sources("youtube")
        if not urls:
            return None

        # 未学習 or 古い順に並べる
        pending = self._pick_pending(urls, "youtube", max_items)
        if not pending:
            return None

        learned = []
        for url in pending:
            try:
                result = self._ai_chan._learn_youtube(url)
                if "失敗" not in result and "エラー" not in result:
                    learned.append(url)
                    self._log("youtube", url, "ok")
                else:
                    self._log("youtube", url, "fail")
            except Exception as e:
                self._log("youtube", url, f"error:{e}")

        if not learned:
            return None
        count = len(learned)
        self._notify(f"YouTube を {count} 件自動学習したよ！")
        return f"自動学習完了：YouTube {count} 件学習したよ。"

    def _learn_web_batch(self, max_items: int) -> str | None:
        if not self._ai_chan:
            return None
        urls = self.get_sources("web")
        if not urls:
            return None

        pending = self._pick_pending(urls, "web", max_items)
        if not pending:
            return None

        learned = []
        for url in pending:
            try:
                result = self._ai_chan._learn_web(url)
                if "失敗" not in result and "エラー" not in result:
                    learned.append(url)
                    self._log("web", url, "ok")
                else:
                    self._log("web", url, "fail")
            except Exception as e:
                self._log("web", url, f"error:{e}")

        if not learned:
            return None
        count = len(learned)
        self._notify(f"Web ページを {count} 件自動学習したよ！")
        return f"自動学習完了：Web {count} 件学習したよ。"

    def _review_learned(self) -> str | None:
        """学習済みコンテンツの振り返り要約を生成"""
        if not self._ai_chan:
            return None
        yt_list  = self._ai_chan.youtube.list_learned()
        web_list = self._ai_chan.web_learner.list_learned()
        file_list = self._ai_chan.file_learner.list_learned()

        total = len(yt_list) + len(web_list) + len(file_list)
        if total == 0:
            return None

        # 直近1週間分だけ対象
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        recent_yt  = [x for x in yt_list  if x.get("learned_at","") >= week_ago]
        recent_web = [x for x in web_list if x.get("learned_at","") >= week_ago]

        items = [x.get("title","") for x in (recent_yt + recent_web) if x.get("title")]
        if not items:
            return None

        summary_items = "、".join(items[:5])
        msg = f"今週の学習振り返り：「{summary_items}」など {len(items)} 件を学習したよ！"
        self._notify(msg)
        self._log("review", "", "ok")
        return msg

    # ─── メモ学習 ────────────────────────────────────────────────

    def add_memo(self, text: str, tags: list[str] | None = None) -> dict:
        """
        短いテキストメモを学習データとして登録する。
        チャットで「メモを覚えて: ○○」と入力した時などに呼ぶ。
        """
        import json, hashlib
        memo_path = self.data_dir / "auto_learn_memos.jsonl"
        entry = {
            "id":      hashlib.md5(text.encode()).hexdigest()[:8],
            "text":    text,
            "tags":    tags or [],
            "ts":      datetime.now().isoformat()[:16],
            "reviews": 0,
            "last_review": "",
        }
        with open(memo_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def get_memos(self, tag: str | None = None) -> list[dict]:
        """登録済みメモを取得する（重複は最新のみ）"""
        memo_path = self.data_dir / "auto_learn_memos.jsonl"
        if not memo_path.exists():
            return []
        seen: dict[str, dict] = {}
        try:
            for line in memo_path.read_text("utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    seen[e["id"]] = e
        except Exception:
            return []
        items = list(seen.values())
        if tag:
            items = [m for m in items if tag in m.get("tags", [])]
        items.sort(key=lambda x: x.get("ts", ""))
        return items

    def _review_memos(self, n: int = 3) -> str | None:
        """登録メモをランダムに選んで復習通知を出す"""
        import random
        memos = self.get_memos()
        if not memos:
            return None
        # 復習回数が少ない / 古いもの優先
        memos.sort(key=lambda m: (m.get("reviews", 0), m.get("last_review", "")))
        sample = memos[:min(n * 2, len(memos))]
        chosen = random.sample(sample, min(n, len(sample)))

        # 復習カウント更新
        memo_path = self.data_dir / "auto_learn_memos.jsonl"
        updated_ids = {m["id"] for m in chosen}
        lines = []
        try:
            for line in memo_path.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                e = json.loads(line)
                if e["id"] in updated_ids:
                    e["reviews"]     = e.get("reviews", 0) + 1
                    e["last_review"] = datetime.now().isoformat()[:16]
                lines.append(json.dumps(e, ensure_ascii=False))
            memo_path.write_text("\n".join(lines) + "\n", "utf-8")
        except Exception:
            pass

        texts = [m["text"][:40] for m in chosen]
        msg = "夜の復習タイム！\n" + "\n".join(f"・{t}" for t in texts)
        self._notify(msg)
        self._log("memo_review", "", "ok")
        return msg

    def _pick_pending(self, urls: list[str], kind: str, n: int) -> list[str]:
        """ログを参照して未学習 or 最も古いものを優先選択"""
        # 直近の学習日時マップを作成
        log_dates: dict[str, str] = {}
        if self._log_path.exists():
            for line in self._log_path.read_text("utf-8").splitlines():
                try:
                    entry = json.loads(line)
                    if entry.get("kind") == kind and entry.get("status") == "ok":
                        url = entry.get("url", "")
                        ts  = entry.get("ts", "")
                        if url and (url not in log_dates or ts > log_dates[url]):
                            log_dates[url] = ts
                except Exception:
                    pass

        # 学習日時が古い順 or 未学習を優先
        sorted_urls = sorted(urls, key=lambda u: log_dates.get(u, "0000"))
        return sorted_urls[:n]

    def _log(self, kind: str, url: str, status: str):
        entry = {
            "ts":     datetime.now().isoformat()[:16],
            "kind":   kind,
            "url":    url,
            "status": status,
        }
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _notify(self, message: str):
        """macOS 通知センターに送る（失敗しても無視）"""
        try:
            from core.notifier import notify_ai
            notify_ai(message)
        except Exception:
            pass

    # ─── バックグラウンドスレッド ────────────────────────────────

    def start(self, ai_chan, on_complete=None):
        """バックグラウンド監視を開始"""
        self._ai_chan     = ai_chan
        self._on_complete = on_complete
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="AutoLearner"
        )
        self._thread.start()
        print("[AutoLearn] バックグラウンド学習スレッド起動", flush=True)

    def stop(self):
        self._stop_event.set()

    def _loop(self):
        """60秒ごとにスケジュールチェック"""
        while not self._stop_event.is_set():
            try:
                results = self.check_and_fire()
                for r in results:
                    print(f"[AutoLearn] {r}", flush=True)
                    if self._on_complete:
                        self._on_complete(r)
            except Exception as e:
                print(f"[AutoLearn] ループエラー: {e}", flush=True)
            self._stop_event.wait(60)   # 1分待機

    # ─── 即時実行（手動トリガー）────────────────────────────────

    def run_now(self, kind: str, max_items: int = 3) -> str:
        """
        即時学習を実行（設定画面やコマンドから呼ぶ）
        kind: "youtube" / "web" / "review"
        """
        if kind == "youtube":
            return self._learn_youtube_batch(max_items) or "学習するYouTube URLが登録されていないよ。"
        if kind == "web":
            return self._learn_web_batch(max_items) or "学習するWebURLが登録されていないよ。"
        if kind == "review":
            return self._review_learned() or "まだ振り返れる学習データがないよ。"
        if kind == "memo":
            return self._review_memos(max_items) or "登録メモがまだないよ。"
        return "不明な種類だよ。"

    # ─── 統計 ────────────────────────────────────────────────────

    def stats(self) -> dict:
        log_count = 0
        ok_count  = 0
        if self._log_path.exists():
            for line in self._log_path.read_text("utf-8").splitlines():
                if line.strip():
                    log_count += 1
                    try:
                        if json.loads(line).get("status") == "ok":
                            ok_count += 1
                    except Exception:
                        pass
        return {
            "total_runs":      log_count,
            "success_runs":    ok_count,
            "youtube_sources": len(self._sources.get("youtube", [])),
            "web_sources":     len(self._sources.get("web", [])),
            "enabled_schedules": sum(1 for s in self._schedule if s.get("enabled")),
        }

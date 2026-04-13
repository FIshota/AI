"""
Autonomous Engine — アイの自律生命維持エンジン（階層型スケジューラ）

設計方針:
  - **既存の AutoLearner._loop は一切変更しない**。このエンジンは
    別スレッドとして共存する上位ラッパーです。
  - APScheduler などの外部依存は導入せず、内部スレッド + 時刻判定で
    4層ジョブ (hourly / every_6h / daily / weekly) を実行します。
  - 各ジョブは純粋な callable として登録でき、失敗しても他ジョブに
    影響しないよう例外隔離されています。
  - 実行履歴は `data/autonomous_fired.json` に永続化され、再起動後も
    「今日の daily はもう走ったか」を判定できます。
  - 各ジョブ完了時は `data/health.jsonl` に1行JSON追記（監査可能）。

ジョブ種別:
  - hourly      : 毎時0分前後にヘルスチェック
  - every_6h    : 0,6,12,18 時に興味マップ更新やネット学習
  - daily       : 毎日指定時刻（既定: 02:00）に日次振り返り
  - weekly      : 毎週日曜の指定時刻（既定: 02:30）に週次レポート

Sprint 1.2 の時点では hourly (health check) のみ標準ジョブとして
登録し、daily / weekly は Sprint 1.3 で成長レポートと接続します。
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable


JobFn = Callable[[], Any]


# ─── データモデル ─────────────────────────────────────────────

@dataclass
class Job:
    """登録された自律ジョブ。"""
    name: str
    cadence: str                       # "hourly" / "every_6h" / "daily" / "weekly"
    fn: JobFn
    hour: int | None = None            # daily / weekly で使用
    minute: int = 0
    weekday: int | None = None         # weekly で使用 (Mon=0, Sun=6)
    description: str = ""


@dataclass
class JobResult:
    name: str
    cadence: str
    started_at: str
    finished_at: str
    ok: bool
    message: str = ""
    detail: dict = field(default_factory=dict)


# ─── コア：AutonomousEngine ──────────────────────────────────

class AutonomousEngine:
    """
    階層ジョブスケジューラ。

    Usage:
        engine = AutonomousEngine(base_dir=Path("."))
        engine.register_job(Job("health", "hourly", my_health_fn))
        engine.start()       # 内部スレッドでループ開始
        ...
        engine.stop()

    テスト時は `tick(now)` を直接呼ぶことでスレッドを起こさず決定論的に
    検証できます。
    """

    # 実行中のジョブ名を記録するロック
    def __init__(
        self,
        base_dir: Path | str,
        *,
        check_interval_sec: int = 60,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._jobs: list[Job] = []
        self._fired_path = self.data_dir / "autonomous_fired.json"
        self._health_log = self.data_dir / "health.jsonl"
        self._fired: dict[str, str] = self._load_fired()

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._check_interval_sec = check_interval_sec

    # ─── 永続化 ────────────────────────────────────────────────

    def _load_fired(self) -> dict[str, str]:
        if not self._fired_path.exists():
            return {}
        try:
            return json.loads(self._fired_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[Autonomous] fired JSON 読み込み失敗: {e}", flush=True)
            return {}

    def _save_fired(self) -> None:
        try:
            tmp = self._fired_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._fired, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._fired_path)
        except OSError as e:
            print(f"[Autonomous] fired JSON 書き込み失敗: {e}", flush=True)

    def _append_health(self, result: JobResult) -> None:
        """health.jsonl に実行結果を1行追記する。"""
        try:
            row = {
                "name": result.name,
                "cadence": result.cadence,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "ok": result.ok,
                "message": result.message,
                "detail": result.detail,
            }
            with self._health_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"[Autonomous] health.jsonl 書き込み失敗: {e}", flush=True)

    # ─── ジョブ登録 ────────────────────────────────────────────

    def register_job(self, job: Job) -> None:
        """ジョブを登録。同名は上書き。"""
        with self._lock:
            self._jobs = [j for j in self._jobs if j.name != job.name]
            self._jobs.append(job)

    def register(
        self,
        name: str,
        cadence: str,
        fn: JobFn,
        *,
        hour: int | None = None,
        minute: int = 0,
        weekday: int | None = None,
        description: str = "",
    ) -> None:
        """Convenience: Job を直接組み立てずに登録する。"""
        self.register_job(
            Job(
                name=name,
                cadence=cadence,
                fn=fn,
                hour=hour,
                minute=minute,
                weekday=weekday,
                description=description,
            )
        )

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs)

    # ─── 発火判定 ───────────────────────────────────────────────

    @staticmethod
    def _fire_key(job: Job, now: datetime) -> str:
        """ジョブが『この瞬間に1度だけ走るべき』ことを表す一意キー。"""
        if job.cadence == "hourly":
            return f"{job.name}:{now.strftime('%Y%m%d%H')}"
        if job.cadence == "every_6h":
            bucket = (now.hour // 6) * 6
            return f"{job.name}:{now.strftime('%Y%m%d')}-{bucket:02d}"
        if job.cadence == "daily":
            return f"{job.name}:{now.strftime('%Y%m%d')}"
        if job.cadence == "weekly":
            iso_year, iso_week, _ = now.isocalendar()
            return f"{job.name}:{iso_year}W{iso_week:02d}"
        return f"{job.name}:{now.strftime('%Y%m%d%H%M')}"

    def _should_fire(self, job: Job, now: datetime) -> bool:
        """このジョブを now のタイミングで走らせるべきか。"""
        key = self._fire_key(job, now)
        if self._fired.get(job.name) == key:
            return False  # この周期ではすでに実行済み

        if job.cadence == "hourly":
            # 毎時 0 分〜10 分以内に1回
            return now.minute < 10
        if job.cadence == "every_6h":
            # 0,6,12,18 時台の 0〜10 分
            return now.hour % 6 == 0 and now.minute < 10
        if job.cadence == "daily":
            target_hour = job.hour if job.hour is not None else 2
            return now.hour == target_hour and abs(now.minute - job.minute) <= 5
        if job.cadence == "weekly":
            target_weekday = job.weekday if job.weekday is not None else 6  # Sun
            target_hour = job.hour if job.hour is not None else 2
            return (
                now.weekday() == target_weekday
                and now.hour == target_hour
                and abs(now.minute - job.minute) <= 5
            )
        return False

    # ─── 実行 ──────────────────────────────────────────────────

    def _run_job(self, job: Job, now: datetime) -> JobResult:
        started = now.isoformat(timespec="seconds")
        try:
            output = job.fn()
            finished = datetime.now().isoformat(timespec="seconds")
            detail: dict = {}
            if isinstance(output, dict):
                detail = output
                msg = output.get("summary", "ok")
            else:
                msg = str(output) if output is not None else "ok"
            return JobResult(
                name=job.name,
                cadence=job.cadence,
                started_at=started,
                finished_at=finished,
                ok=True,
                message=msg,
                detail=detail,
            )
        except Exception as e:
            finished = datetime.now().isoformat(timespec="seconds")
            return JobResult(
                name=job.name,
                cadence=job.cadence,
                started_at=started,
                finished_at=finished,
                ok=False,
                message=f"{type(e).__name__}: {e}",
                detail={"traceback": traceback.format_exc(limit=3)},
            )

    def tick(self, now: datetime | None = None) -> list[JobResult]:
        """
        ジョブの1回分判定 + 実行。
        ループから呼ばれるが、テストでは直接呼べる。
        """
        now = now or datetime.now()
        results: list[JobResult] = []
        with self._lock:
            jobs_snapshot = list(self._jobs)
        for job in jobs_snapshot:
            if not self._should_fire(job, now):
                continue
            result = self._run_job(job, now)
            # 発火済みキーを記録
            with self._lock:
                self._fired[job.name] = self._fire_key(job, now)
            self._save_fired()
            self._append_health(result)
            results.append(result)
            if result.ok:
                print(f"[Autonomous] ✓ {job.name} ({job.cadence}): {result.message}", flush=True)
            else:
                print(f"[Autonomous] ✗ {job.name} ({job.cadence}): {result.message}", flush=True)
        return results

    # ─── バックグラウンドスレッド ────────────────────────────────

    def start(self) -> None:
        """内部スレッドを起動してポーリングを開始。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="AutonomousEngine", daemon=True
        )
        self._thread.start()
        print("[Autonomous] 自律エンジン起動", flush=True)

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        # 起動直後に1度走らせて、すぐに health.jsonl が書かれることを保証
        try:
            self.tick()
        except Exception as e:
            print(f"[Autonomous] 初回 tick エラー: {e}", flush=True)
        while not self._stop_event.is_set():
            self._stop_event.wait(self._check_interval_sec)
            if self._stop_event.is_set():
                break
            try:
                self.tick()
            except Exception as e:
                print(f"[Autonomous] ループエラー: {e}", flush=True)

    # ─── 健康状態の読み出し ─────────────────────────────────────

    def read_recent_health(self, limit: int = 20) -> list[dict]:
        """最近の health.jsonl エントリを新しい順で返す。"""
        if not self._health_log.exists():
            return []
        try:
            lines = self._health_log.read_text("utf-8").splitlines()
        except OSError:
            return []
        rows: list[dict] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(rows) >= limit:
                break
        return rows


# ─── 標準ジョブ：ヘルスチェック ───────────────────────────────

def build_health_check(ai_chan) -> JobFn:
    """
    AiChan 本体を渡して hourly ヘルスチェック用 callable を生成する。

    取得する情報:
      - memory stats (short/mid/long 件数、core件数)
      - DB ファイルサイズ
      - app.log の直近エラー件数（あれば）
      - 現在時刻
    """
    base_dir = Path(ai_chan.base_dir)
    db_path = base_dir / ai_chan.settings["memory"]["db_path"]
    log_path = base_dir / "data" / "app.log"

    def _check() -> dict:
        out: dict[str, Any] = {"timestamp": datetime.now().isoformat(timespec="seconds")}
        try:
            out["memory_stats"] = ai_chan.memory.stats()
        except Exception as e:
            out["memory_stats_error"] = str(e)

        try:
            if db_path.exists():
                out["db_size_bytes"] = db_path.stat().st_size
        except OSError as e:
            out["db_size_error"] = str(e)

        # app.log の末尾から ERROR 行数だけ軽くカウント
        try:
            if log_path.exists():
                size = log_path.stat().st_size
                tail_bytes = 64 * 1024
                with log_path.open("rb") as f:
                    if size > tail_bytes:
                        f.seek(-tail_bytes, 2)
                    data = f.read().decode("utf-8", errors="replace")
                err_count = sum(1 for line in data.splitlines() if "ERROR" in line)
                out["recent_errors_in_log_tail"] = err_count
        except OSError as e:
            out["log_read_error"] = str(e)

        out["summary"] = (
            f"db={out.get('memory_stats', {}).get('db_total', '?')} "
            f"core={out.get('memory_stats', {}).get('core', '?')} "
            f"errors={out.get('recent_errors_in_log_tail', 0)}"
        )
        return out

    return _check


__all__ = [
    "AutonomousEngine",
    "Job",
    "JobResult",
    "build_health_check",
]

"""
監査ログ (Audit Log)
Sprint 2.1: セキュリティイベントの改ざん耐性付き追記ログ。

各エントリは前行のハッシュを含むチェーンで、改ざん検知が可能。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# イベント重要度
Severity = Literal["INFO", "WARN", "CRITICAL"]

_LOCK = threading.Lock()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _hash_line(line: str) -> str:
    """SHA-256 の先頭16文字を返す"""
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]


class AuditLog:
    """
    改ざん検知付きの追記専用監査ログ。

    各行: JSON {"ts","sev","event","detail","prev_hash","hash"}
    hash = SHA-256(ts+sev+event+detail+prev_hash)[:16]
    """

    def __init__(self, log_dir: str | Path):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "audit.jsonl"
        self._prev_hash = self._load_last_hash()

    # ─── public ──────────────────────────────────────────────

    def log(
        self,
        event: str,
        detail: str = "",
        severity: Severity = "INFO",
    ) -> dict:
        """監査イベントを追記する。返り値はログエントリ dict。"""
        entry = self._build_entry(event, detail, severity)
        with _LOCK:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._prev_hash = entry["hash"]
        return entry

    def info(self, event: str, detail: str = "") -> dict:
        return self.log(event, detail, "INFO")

    def warn(self, event: str, detail: str = "") -> dict:
        return self.log(event, detail, "WARN")

    def critical(self, event: str, detail: str = "") -> dict:
        return self.log(event, detail, "CRITICAL")

    def verify_chain(self) -> dict:
        """
        ログチェーン全体を検証する。
        戻り値: {"valid": bool, "total": int, "broken_at": int | None}
        """
        if not self._path.exists():
            return {"valid": True, "total": 0, "broken_at": None}

        prev = "0" * 16
        total = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return {"valid": False, "total": total, "broken_at": i}

                if entry.get("prev_hash") != prev:
                    return {"valid": False, "total": total, "broken_at": i}

                expected = self._compute_hash(entry, prev)
                if entry.get("hash") != expected:
                    return {"valid": False, "total": total, "broken_at": i}

                prev = entry["hash"]

        return {"valid": True, "total": total, "broken_at": None}

    def get_recent(self, limit: int = 20, severity: Severity | None = None) -> list[dict]:
        """直近のログエントリを取得する。"""
        if not self._path.exists():
            return []
        entries: list[dict] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if severity is None or entry.get("sev") == severity:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries[-limit:]

    # ─── private ─────────────────────────────────────────────

    def _build_entry(self, event: str, detail: str, severity: Severity) -> dict:
        ts = _utcnow_iso()
        prev = self._prev_hash
        entry = {
            "ts": ts,
            "sev": severity,
            "event": event,
            "detail": detail,
            "prev_hash": prev,
            "hash": "",
        }
        entry["hash"] = self._compute_hash(entry, prev)
        return entry

    @staticmethod
    def _compute_hash(entry: dict, prev_hash: str) -> str:
        raw = f"{entry['ts']}{entry['sev']}{entry['event']}{entry['detail']}{prev_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _load_last_hash(self) -> str:
        """既存ログの最終行からハッシュを読み込む"""
        if not self._path.exists():
            return "0" * 16
        last_hash = "0" * 16
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    last_hash = entry.get("hash", last_hash)
                except json.JSONDecodeError:
                    continue
        return last_hash

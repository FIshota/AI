"""
プロセスモニター (Process Monitor)
Sprint 3.0-E: 実行中のプロセスを監視し、不審なプロセスを検出する。

機能:
- 新規プロセス検出
- 不審なプロセス名パターン検出
- CPU/メモリ異常使用検出
- ベースラインからの逸脱検出

倫理規定: 監視は自PCのみ。外部への介入は行わない。
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.audit_log import AuditLog

IS_MAC = platform.system() == "Darwin"

# 不審なプロセス名パターン
_SUSPICIOUS_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)xmr|monero|coinhive|minergate|cryptonight", "暗号通貨マイナー"),
    (r"(?i)reverse.?shell|bind.?shell|netcat|ncat|socat", "リバースシェル"),
    (r"(?i)metasploit|meterpreter|cobalt.?strike|empire", "攻撃ツール"),
    (r"(?i)keylog|key.?logger|hook.?key", "キーロガー"),
    (r"(?i)(?<![a-z])rat(?![a-z])|dark.?comet|njrat|poison.?ivy", "RAT"),
    (r"(?i)mimikatz|lazagne|credential.?dump", "資格情報窃取"),
    (r"(?i)ransom|encrypt.?files|lock.?screen", "ランサムウェア"),
]

# 高CPU/メモリの閾値
CPU_THRESHOLD = 90.0
MEM_THRESHOLD = 50.0


@dataclass(frozen=True)
class ProcessInfo:
    """プロセス情報"""
    pid: str
    user: str
    cpu: float
    mem: float
    command: str


@dataclass(frozen=True)
class ProcessAlert:
    """プロセスアラート"""
    severity: str
    category: str
    message: str
    detail: str = ""


class ProcessMonitor:
    """
    プロセス監視・異常検出。

    使い方:
      monitor = ProcessMonitor(base_dir)
      alerts = monitor.detect_suspicious_processes()
      summary = monitor.get_summary()
    """

    def __init__(self, base_dir: str | Path, audit: AuditLog | None = None):
        self._base = Path(base_dir)
        self._baseline_path = self._base / "data" / ".process_baseline.json"
        self._audit = audit
        self._lock = threading.Lock()
        self._reported_alerts: set[str] = set()  # 重複ログ抑制

    # ─── public ──────────────────────────────────────────────

    def scan_processes(self) -> list[ProcessInfo]:
        """実行中のプロセスを取得する"""
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=5,
            )
            return self._parse_ps(result.stdout)
        except Exception:
            return []

    def detect_suspicious_processes(self) -> list[ProcessAlert]:
        """不審なプロセスを検出する"""
        alerts: list[ProcessAlert] = []
        processes = self.scan_processes()

        if not processes:
            return alerts

        for proc in processes:
            # 1. 不審な名前パターン
            for pattern, desc in _SUSPICIOUS_PATTERNS:
                if re.search(pattern, proc.command):
                    alerts.append(ProcessAlert(
                        severity="CRITICAL",
                        category="suspicious_process",
                        message=f"{desc}の疑い: {proc.command[:60]}",
                        detail=f"PID:{proc.pid} USER:{proc.user}",
                    ))
                    break

            # 2. 隠しプロセス（ドットで始まるコマンド）
            cmd_parts = proc.command.split("/")[-1].split() if proc.command else []
            cmd_base = cmd_parts[0] if cmd_parts else ""
            if cmd_base.startswith(".") and len(cmd_base) > 1:
                alerts.append(ProcessAlert(
                    severity="WARN",
                    category="hidden_process",
                    message=f"隠しプロセス検出: {cmd_base}",
                    detail=f"PID:{proc.pid} USER:{proc.user}",
                ))

            # 3. CPU/メモリ異常
            if proc.cpu > CPU_THRESHOLD:
                alerts.append(ProcessAlert(
                    severity="WARN",
                    category="high_cpu",
                    message=f"高CPU使用: {proc.command[:40]} ({proc.cpu}%)",
                    detail=f"PID:{proc.pid}",
                ))
            if proc.mem > MEM_THRESHOLD:
                alerts.append(ProcessAlert(
                    severity="WARN",
                    category="high_memory",
                    message=f"高メモリ使用: {proc.command[:40]} ({proc.mem}%)",
                    detail=f"PID:{proc.pid}",
                ))

        # 4. ベースラインとの比較
        baseline_alerts = self._compare_to_baseline(processes)
        alerts.extend(baseline_alerts)

        # 監査ログ（同一アラート群の重複記録を抑制）
        if self._audit and alerts:
            critical = [a for a in alerts if a.severity == "CRITICAL"]
            if critical:
                dedup_key = ";".join(sorted(a.message for a in critical))
                if dedup_key not in self._reported_alerts:
                    self._reported_alerts.add(dedup_key)
                    self._audit.critical(
                        "process_alert",
                        f"不審プロセス {len(critical)}件: "
                        + "; ".join(a.message for a in critical[:3]),
                    )

        return alerts

    def build_baseline(self) -> dict:
        """現在のプロセス一覧をベースラインとして記録する"""
        processes = self.scan_processes()
        process_names = sorted(set(
            parts[0]
            for p in processes if p.command
            for parts in [p.command.split("/")[-1].split()]
            if parts
        ))
        baseline = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "process_count": len(processes),
            "process_names": process_names,
        }
        with self._lock:
            self._baseline_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._baseline_path, "w", encoding="utf-8") as f:
                json.dump(baseline, f, ensure_ascii=False, indent=2)
        return baseline

    def get_summary(self) -> str:
        """プロセス状況の日本語サマリーを返す"""
        processes = self.scan_processes()
        alerts = self.detect_suspicious_processes()

        lines: list[str] = ["⚙️ プロセス監視状況："]
        lines.append(f"  実行中プロセス: {len(processes)} 件")

        # CPU/メモリ上位
        top_cpu = sorted(processes, key=lambda p: p.cpu, reverse=True)[:3]
        if top_cpu:
            lines.append("\n  📊 CPU使用率トップ:")
            for p in top_cpu:
                cmd_parts = p.command.split("/")[-1].split()
                name = (cmd_parts[0] if cmd_parts else "unknown")[:30]
                lines.append(f"    {name}: CPU {p.cpu}% / MEM {p.mem}%")

        if alerts:
            critical = [a for a in alerts if a.severity == "CRITICAL"]
            warn = [a for a in alerts if a.severity == "WARN"]
            if critical:
                lines.append(f"\n  🔴 重大アラート: {len(critical)} 件")
                for a in critical[:3]:
                    lines.append(f"    → {a.message}")
            if warn:
                lines.append(f"  ⚠ 警告: {len(warn)} 件")
                for a in warn[:2]:
                    lines.append(f"    → {a.message}")
        else:
            lines.append("\n  ✅ 不審なプロセスは見つからなかったよ！")

        return "\n".join(lines)

    def get_health_score(self) -> int:
        """プロセス健全性スコア（0-100）"""
        alerts = self.detect_suspicious_processes()
        score = 100
        for a in alerts:
            if a.severity == "CRITICAL":
                score -= 25
            elif a.severity == "WARN":
                score -= 5
        return max(0, score)

    def hourly_job(self) -> dict:
        """自律エンジン用の毎時ジョブ"""
        alerts = self.detect_suspicious_processes()
        return {
            "action": "process_check",
            "alerts": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == "CRITICAL"),
            "warn": sum(1 for a in alerts if a.severity == "WARN"),
        }

    # ─── private ─────────────────────────────────────────────

    def _parse_ps(self, output: str) -> list[ProcessInfo]:
        """ps aux の出力をパースする"""
        processes: list[ProcessInfo] = []
        for line in output.splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            try:
                processes.append(ProcessInfo(
                    pid=parts[1],
                    user=parts[0],
                    cpu=float(parts[2]),
                    mem=float(parts[3]),
                    command=parts[10],
                ))
            except (ValueError, IndexError):
                continue
        return processes

    def _compare_to_baseline(self, current: list[ProcessInfo]) -> list[ProcessAlert]:
        """ベースラインとの差異を検出する"""
        alerts: list[ProcessAlert] = []

        if not self._baseline_path.exists():
            # 初回はベースラインを作成
            self.build_baseline()
            return alerts

        try:
            with open(self._baseline_path, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        except (json.JSONDecodeError, OSError):
            return alerts

        baseline_names = set(baseline.get("process_names", []))
        current_names = set(
            parts[0]
            for p in current if p.command
            for parts in [p.command.split("/")[-1].split()]
            if parts
        )

        # 新しいプロセス（ベースラインにないもの）
        new_processes = current_names - baseline_names
        # システムプロセスやよくあるものは除外
        safe_prefixes = {
            "python", "node", "ruby", "java", "git", "ssh",
            "bash", "zsh", "sh", "fish", "vim", "nano",
            "grep", "awk", "sed", "find", "ls", "cat",
            "com.apple", "mdworker", "spotlight", "kernel",
        }
        suspicious_new = [
            n for n in new_processes
            if not any(n.lower().startswith(s) for s in safe_prefixes)
            and len(n) > 2
        ]

        if len(suspicious_new) > 10:
            alerts.append(ProcessAlert(
                severity="WARN",
                category="new_processes",
                message=f"ベースラインにない新規プロセスが {len(suspicious_new)} 個",
                detail=", ".join(list(suspicious_new)[:5]),
            ))

        return alerts

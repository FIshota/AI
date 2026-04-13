"""
ネットワークモニター (Network Monitor)
Sprint 3.0-E: リアルタイムでネットワーク接続を監視し、不審な通信を検出する。

機能:
- アクティブ接続の監視
- 不審なポート/IPへの接続検出
- DNS変更検出
- 通信量の異常検出

倫理規定: 外部への不正アクセスは絶対に行わない。受動的検知と通知のみ。
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.audit_log import AuditLog

IS_MAC = platform.system() == "Darwin"

# 不審なポート一覧（RAT / バックドア / マルウェアでよく使われる）
SUSPICIOUS_PORTS = {
    4444, 5555, 1337, 6666, 6667, 31337, 12345, 54321,
    4443, 8888, 9999, 1234, 6660, 6669, 7777, 13337,
}

# 正常に使われることが多いポート
KNOWN_SAFE_PORTS = {
    22, 53, 80, 443, 993, 995, 587, 465, 8080, 8443,
    5353, 123,  # mDNS, NTP
}


@dataclass(frozen=True)
class ConnectionInfo:
    """ネットワーク接続情報"""
    process: str
    pid: str
    protocol: str
    local_addr: str
    remote_addr: str
    state: str = ""


@dataclass(frozen=True)
class NetworkAlert:
    """ネットワークアラート"""
    severity: str        # CRITICAL / WARN / INFO
    category: str
    message: str
    detail: str = ""


class NetworkMonitor:
    """
    リアルタイムネットワーク監視。

    使い方:
      monitor = NetworkMonitor(base_dir)
      alerts = monitor.detect_suspicious()
      summary = monitor.get_connection_summary()
    """

    def __init__(self, base_dir: str | Path, audit: AuditLog | None = None):
        self._base = Path(base_dir)
        self._state_path = self._base / "data" / ".network_state.json"
        self._audit = audit
        self._lock = threading.Lock()
        self._prev_state = self._load_state()

    # ─── public ──────────────────────────────────────────────

    def scan_connections(self) -> list[ConnectionInfo]:
        """アクティブなネットワーク接続をスキャンする"""
        if not IS_MAC:
            return []
        try:
            result = subprocess.run(
                ["lsof", "-i", "-n", "-P"],
                capture_output=True, text=True, timeout=5,
            )
            return self._parse_lsof(result.stdout)
        except Exception:
            return []

    def detect_suspicious(self) -> list[NetworkAlert]:
        """不審な接続を検出する"""
        alerts: list[NetworkAlert] = []
        connections = self.scan_connections()

        if not connections:
            return alerts

        # 1. 不審なポートへの接続
        for conn in connections:
            remote_port = self._extract_port(conn.remote_addr)
            if remote_port and remote_port in SUSPICIOUS_PORTS:
                alerts.append(NetworkAlert(
                    severity="CRITICAL",
                    category="suspicious_port",
                    message=f"不審なポート {remote_port} への接続を検出",
                    detail=f"プロセス: {conn.process} (PID:{conn.pid}) → {conn.remote_addr}",
                ))

        # 2. 異常な接続数
        established = [c for c in connections if "ESTABLISHED" in c.state.upper()]
        if len(established) > 100:
            alerts.append(NetworkAlert(
                severity="WARN",
                category="connection_flood",
                message=f"異常な接続数: {len(established)} 件",
                detail="通常の範囲を超えています",
            ))

        # 3. LISTENしているポートのチェック
        listening = [c for c in connections if "LISTEN" in c.state.upper()]
        for conn in listening:
            local_port = self._extract_port(conn.local_addr)
            if local_port and local_port not in KNOWN_SAFE_PORTS and local_port > 1024:
                # 高ポートでLISTENしている不明なプロセス
                if conn.process.lower() not in (
                    "python3", "python", "node", "ruby", "java",
                    "rapportd", "sharingd", "identityservicesd",
                    "controlce", "spotify", "discord",
                ):
                    alerts.append(NetworkAlert(
                        severity="WARN",
                        category="unknown_listener",
                        message=f"不明なプロセスがポート {local_port} で待受中",
                        detail=f"プロセス: {conn.process} (PID:{conn.pid})",
                    ))

        # 4. 前回からの変化を検出
        prev_count = self._prev_state.get("connection_count", 0)
        current_count = len(established)
        if prev_count > 0 and current_count > prev_count * 3:
            alerts.append(NetworkAlert(
                severity="WARN",
                category="connection_spike",
                message=f"接続数が急増: {prev_count} → {current_count}",
            ))

        # 状態を保存
        self._save_state({
            "connection_count": current_count,
            "listening_count": len(listening),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "alert_count": len(alerts),
        })

        # 監査ログに記録
        if self._audit and alerts:
            critical = [a for a in alerts if a.severity == "CRITICAL"]
            if critical:
                self._audit.critical(
                    "network_alert",
                    f"重大ネットワーク異常 {len(critical)}件: "
                    + "; ".join(a.message for a in critical[:3]),
                )
            else:
                self._audit.warn(
                    "network_alert",
                    f"ネットワーク警告 {len(alerts)}件",
                )

        return alerts

    def check_dns_integrity(self) -> dict:
        """DNS設定の整合性を確認する"""
        result = {"status": "ok", "servers": [], "alerts": []}
        if not IS_MAC:
            result["status"] = "skip"
            return result

        try:
            proc = subprocess.run(
                ["scutil", "--dns"],
                capture_output=True, text=True, timeout=5,
            )
            # DNSサーバーを抽出
            servers: list[str] = []
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("nameserver["):
                    match = re.search(r':\s*(.+)', line)
                    if match:
                        servers.append(match.group(1).strip())
            result["servers"] = list(set(servers))

            # 疑わしいDNSサーバーチェック
            for server in servers:
                # ローカルIP以外の非標準DNS
                if not server.startswith(("192.168.", "10.", "172.", "127.", "fe80:")):
                    # 既知の安全なDNS
                    safe_dns = {
                        "8.8.8.8", "8.8.4.4",     # Google
                        "1.1.1.1", "1.0.0.1",     # Cloudflare
                        "9.9.9.9",                  # Quad9
                        "208.67.222.222",            # OpenDNS
                    }
                    if server not in safe_dns:
                        result["alerts"].append(f"不明なDNSサーバー: {server}")
                        result["status"] = "warn"

        except Exception as e:
            result["status"] = "error"
            result["alerts"].append(str(e))

        return result

    def get_connection_summary(self) -> str:
        """ネットワーク接続の日本語サマリーを返す"""
        connections = self.scan_connections()
        alerts = self.detect_suspicious()

        established = [c for c in connections if "ESTABLISHED" in c.state.upper()]
        listening = [c for c in connections if "LISTEN" in c.state.upper()]

        lines: list[str] = ["🌐 ネットワーク接続状況："]
        lines.append(f"  接続中: {len(established)} 件")
        lines.append(f"  待受中: {len(listening)} 件")

        if alerts:
            critical = [a for a in alerts if a.severity == "CRITICAL"]
            warn = [a for a in alerts if a.severity == "WARN"]
            if critical:
                lines.append(f"\n  🔴 重大アラート: {len(critical)} 件")
                for a in critical[:3]:
                    lines.append(f"    → {a.message}")
            if warn:
                lines.append(f"  ⚠ 警告: {len(warn)} 件")
                for a in warn[:3]:
                    lines.append(f"    → {a.message}")
        else:
            lines.append("\n  ✅ 不審な接続は見つからなかったよ！")

        # DNS状況
        dns = self.check_dns_integrity()
        if dns["alerts"]:
            lines.append(f"\n  ⚠ DNS: {', '.join(dns['alerts'])}")
        elif dns["servers"]:
            lines.append(f"\n  DNS: {', '.join(dns['servers'][:3])}")

        return "\n".join(lines)

    def get_health_score(self) -> int:
        """ネットワーク健全性スコア（0-100）"""
        alerts = self.detect_suspicious()
        score = 100
        for a in alerts:
            if a.severity == "CRITICAL":
                score -= 25
            elif a.severity == "WARN":
                score -= 10
        dns = self.check_dns_integrity()
        if dns["status"] == "warn":
            score -= 10
        return max(0, score)

    def hourly_job(self) -> dict:
        """自律エンジン用の毎時ジョブ"""
        alerts = self.detect_suspicious()
        return {
            "action": "network_check",
            "alerts": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == "CRITICAL"),
            "warn": sum(1 for a in alerts if a.severity == "WARN"),
        }

    # ─── private ─────────────────────────────────────────────

    def _parse_lsof(self, output: str) -> list[ConnectionInfo]:
        """lsof -i の出力をパースする"""
        connections: list[ConnectionInfo] = []
        for line in output.splitlines()[1:]:  # ヘッダーをスキップ
            parts = line.split()
            if len(parts) < 9:
                continue
            try:
                conn = ConnectionInfo(
                    process=parts[0],
                    pid=parts[1],
                    protocol=parts[7] if len(parts) > 7 else "",
                    local_addr=parts[8] if len(parts) > 8 else "",
                    remote_addr=parts[8] if len(parts) > 8 and "->" in parts[8] else "",
                    state=parts[9] if len(parts) > 9 else "",
                )
                # remote_addr を抽出（"local->remote" 形式）
                if "->" in conn.local_addr:
                    local_part, remote_part = conn.local_addr.split("->", 1)
                    conn = ConnectionInfo(
                        process=conn.process,
                        pid=conn.pid,
                        protocol=conn.protocol,
                        local_addr=local_part,
                        remote_addr=remote_part,
                        state=conn.state,
                    )
                connections.append(conn)
            except (IndexError, ValueError):
                continue
        return connections

    @staticmethod
    def _extract_port(addr: str) -> int | None:
        """アドレス文字列からポート番号を抽出する"""
        if not addr:
            return None
        # "host:port" or "[ipv6]:port"
        if ":" in addr:
            try:
                return int(addr.rsplit(":", 1)[-1])
            except ValueError:
                return None
        return None

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self, state: dict) -> None:
        with self._lock:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

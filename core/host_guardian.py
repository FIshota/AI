"""
ホストガーディアン (Host Guardian)
Sprint 2.1: アイがいるPC全体のセキュリティを監視・保護する。

倫理規定: 外部システムへの不正アクセスは絶対に行わない。
全ての防御は受動的検知と通知のみ。

監視項目:
- macOS ファイアウォール状態
- 不審なネットワーク接続の検出
- ディスク暗号化（FileVault）状態
- macOS セキュリティアップデート確認
- 不審なプロセスの検出
- SSH/リモートアクセスの監視
- 重要ファイルの権限チェック
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


@dataclass(frozen=True)
class HostAlert:
    """ホスト防御アラート"""
    category: str
    severity: str
    message: str
    recommendation: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
        }


def _run_cmd(cmd: list[str], timeout: int = 10) -> str:
    """コマンド実行のヘルパー（失敗時は空文字）"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


class HostGuardian:
    """
    ホストPC全体のセキュリティを受動的に監視する。

    重要: 外部への攻撃・侵入は絶対に行わない（倫理規定準拠）。
    全ての機能は検知→通知→推奨のみ。
    """

    def __init__(
        self,
        base_dir: str | Path,
        audit: AuditLog | None = None,
    ):
        self._base = Path(base_dir)
        self._audit = audit
        self._state_path = self._base / "data" / ".host_guardian_state.json"
        self._reported_alerts: set[str] = set()  # 同一アラートの重複ログ抑制

    # ─── public ──────────────────────────────────────────────

    def run_all_checks(self) -> list[HostAlert]:
        """全てのホストセキュリティチェックを実行する"""
        if not IS_MAC:
            return [HostAlert(
                category="system",
                severity="INFO",
                message="macOS以外の環境です。ホスト監視は制限されます。",
            )]

        alerts: list[HostAlert] = []
        alerts.extend(self._check_firewall())
        alerts.extend(self._check_filevault())
        alerts.extend(self._check_sip())
        alerts.extend(self._check_gatekeeper())
        alerts.extend(self._check_ssh_status())
        alerts.extend(self._check_remote_login())
        alerts.extend(self._check_suspicious_connections())
        alerts.extend(self._check_software_update())
        alerts.extend(self._check_key_file_permissions())

        # 監査ログに記録
        for alert in alerts:
            self._log(alert)

        # 状態を保存
        self._save_summary(alerts)
        return alerts

    def get_security_score(self) -> dict:
        """
        ホストのセキュリティスコアを0-100で返す。
        """
        alerts = self.run_all_checks()
        score = 100
        for a in alerts:
            if a.severity == "CRITICAL":
                score -= 20
            elif a.severity == "WARN":
                score -= 10
            elif a.severity == "INFO":
                score -= 2
        return {
            "score": max(0, score),
            "total_alerts": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == "CRITICAL"),
            "warn": sum(1 for a in alerts if a.severity == "WARN"),
            "alerts": [a.to_dict() for a in alerts],
        }

    def get_summary_text(self) -> str:
        """チャット向けの日本語サマリーを返す"""
        result = self.get_security_score()
        score = result["score"]
        c = result["critical"]
        w = result["warn"]

        if score >= 90:
            emoji = "🛡️"
            status = "とても安全"
        elif score >= 70:
            emoji = "⚠️"
            status = "注意が必要"
        elif score >= 50:
            emoji = "🚨"
            status = "危険な状態"
        else:
            emoji = "💀"
            status = "非常に危険"

        lines = [f"{emoji} PCセキュリティスコア: {score}/100 ({status})"]
        if c > 0:
            lines.append(f"🔴 重大な問題: {c}件")
        if w > 0:
            lines.append(f"🟡 注意事項: {w}件")

        # 上位3件の推奨事項
        recs = [a for a in result["alerts"] if a.get("recommendation")]
        for r in recs[:3]:
            lines.append(f"→ {r['recommendation']}")

        return "\n".join(lines)

    # ─── ジョブ登録用 ────────────────────────────────────────

    def hourly_job(self) -> dict:
        """AutonomousEngine の hourly ジョブとして登録用"""
        result = self.get_security_score()
        return {"action": "host_guardian", "score": result["score"]}

    # ─── 個別チェック ────────────────────────────────────────

    def _check_firewall(self) -> list[HostAlert]:
        """macOS ファイアウォールの状態を確認"""
        output = _run_cmd(
            ["sudo", "-n", "/usr/libexec/ApplicationFirewall/socketfilterfw",
             "--getglobalstate"]
        )
        # sudo なしでも試す
        if not output:
            output = _run_cmd(["defaults", "read",
                               "/Library/Preferences/com.apple.alf", "globalstate"])

        if not output:
            return []  # 確認不能は無視

        # globalstate: 0=off, 1=on, 2=on+stealth
        if "disabled" in output.lower() or output.strip() == "0":
            return [HostAlert(
                category="firewall",
                severity="CRITICAL",
                message="macOS ファイアウォールが無効です",
                recommendation="システム設定 → ネットワーク → ファイアウォール を有効にしてください",
            )]
        return []

    def _check_filevault(self) -> list[HostAlert]:
        """FileVault（ディスク暗号化）の状態を確認"""
        output = _run_cmd(["fdesetup", "status"])
        if not output:
            return []

        if "Off" in output or "FileVault is Off" in output:
            return [HostAlert(
                category="encryption",
                severity="CRITICAL",
                message="FileVault（ディスク暗号化）が無効です",
                recommendation="システム設定 → プライバシーとセキュリティ → FileVault を有効にしてください",
            )]
        return []

    def _check_sip(self) -> list[HostAlert]:
        """System Integrity Protection の状態を確認"""
        output = _run_cmd(["csrutil", "status"])
        if not output:
            return []

        if "disabled" in output.lower():
            return [HostAlert(
                category="system",
                severity="CRITICAL",
                message="System Integrity Protection (SIP) が無効です",
                recommendation="リカバリモードで csrutil enable を実行してください",
            )]
        return []

    def _check_gatekeeper(self) -> list[HostAlert]:
        """Gatekeeper の状態を確認"""
        output = _run_cmd(["spctl", "--status"])
        if not output:
            return []

        if "disabled" in output.lower():
            return [HostAlert(
                category="system",
                severity="WARN",
                message="Gatekeeper が無効です",
                recommendation="ターミナルで sudo spctl --master-enable を実行してください",
            )]
        return []

    def _check_ssh_status(self) -> list[HostAlert]:
        """SSH（リモートログイン）が有効でないか確認"""
        output = _run_cmd(["systemsetup", "-getremotelogin"])
        if not output:
            return []

        if "On" in output or "on" in output.lower():
            return [HostAlert(
                category="remote_access",
                severity="WARN",
                message="SSH リモートログインが有効です",
                recommendation="不要であれば システム設定 → 一般 → 共有 → リモートログイン を無効にしてください",
            )]
        return []

    def _check_remote_login(self) -> list[HostAlert]:
        """画面共有・リモートマネジメントが有効でないか確認"""
        alerts: list[HostAlert] = []

        # 画面共有
        screen_sharing = _run_cmd(
            ["launchctl", "list", "com.apple.screensharing"]
        )
        if screen_sharing and "Could not find" not in screen_sharing:
            alerts.append(HostAlert(
                category="remote_access",
                severity="WARN",
                message="画面共有が有効です",
                recommendation="不要であれば システム設定 → 一般 → 共有 → 画面共有 を無効に",
            ))

        return alerts

    def _check_suspicious_connections(self) -> list[HostAlert]:
        """不審な外部接続を検出（既知の危険ポートへの接続）"""
        alerts: list[HostAlert] = []
        output = _run_cmd(["lsof", "-i", "-P", "-n"])
        if not output:
            return alerts

        # 危険なポートへの ESTABLISHED 接続を検出
        suspicious_ports = {
            "4444", "5555", "6666", "1337",  # RAT/バックドア系
            "31337", "12345", "54321",        # 古典的トロイ
        }

        for line in output.splitlines():
            if "ESTABLISHED" not in line:
                continue
            # ポート番号を抽出
            parts = line.split()
            for part in parts:
                if "->" in part:
                    port_match = re.search(r":(\d+)$", part)
                    if port_match and port_match.group(1) in suspicious_ports:
                        alerts.append(HostAlert(
                            category="network",
                            severity="CRITICAL",
                            message=f"不審なポートへの接続を検出: {part}（プロセス: {parts[0]}）",
                            recommendation="該当プロセスを確認し、不要であれば終了してください",
                        ))

        return alerts

    def _check_software_update(self) -> list[HostAlert]:
        """保留中のセキュリティアップデートを確認"""
        output = _run_cmd(
            ["softwareupdate", "--list", "--no-scan"], timeout=5
        )
        if not output:
            return []

        if "Security" in output or "セキュリティ" in output:
            return [HostAlert(
                category="update",
                severity="WARN",
                message="セキュリティアップデートが保留中です",
                recommendation="softwareupdate --install --all でアップデートを適用してください",
            )]
        return []

    def _check_key_file_permissions(self) -> list[HostAlert]:
        """暗号鍵ファイルの権限を確認"""
        alerts: list[HostAlert] = []
        key_file = self._base / "data" / ".key"
        if not key_file.exists():
            return alerts

        try:
            mode = key_file.stat().st_mode & 0o777
            if mode != 0o400:
                alerts.append(HostAlert(
                    category="permissions",
                    severity="WARN",
                    message=f"暗号鍵ファイルの権限が {oct(mode)} です（推奨: 0o400）",
                    recommendation=f"chmod 400 {key_file} を実行してください",
                ))
        except OSError:
            pass

        return alerts

    # ─── private ─────────────────────────────────────────────

    def _save_summary(self, alerts: list[HostAlert]) -> None:
        summary = {
            "last_check": datetime.now(timezone.utc).isoformat(),
            "total_alerts": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == "CRITICAL"),
            "alerts": [a.to_dict() for a in alerts],
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(summary, ensure_ascii=False, indent=2, fp=f)

    def _log(self, alert: HostAlert) -> None:
        if self._audit is None:
            return
        # 同一カテゴリ+メッセージの重複ログを抑制（初回のみ記録）
        dedup_key = f"{alert.category}:{alert.message}"
        if dedup_key in self._reported_alerts:
            return
        self._reported_alerts.add(dedup_key)
        try:
            method = {
                "INFO": self._audit.info,
                "WARN": self._audit.warn,
                "CRITICAL": self._audit.critical,
            }.get(alert.severity, self._audit.info)
            method(f"host_{alert.category}", alert.message)
        except Exception:
            pass

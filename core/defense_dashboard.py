"""
防御ダッシュボード (Defense Dashboard)
Sprint 3.0-E: 全防御システムの統合レポートを生成する。

機能:
- 全防御モジュールの状態統合
- 総合セキュリティスコア算出
- 推奨アクション生成
- 日次サマリー
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DefenseDashboard:
    """
    全防御システムの統合ダッシュボード。

    使い方:
      dashboard = DefenseDashboard(base_dir, ...)
      report = dashboard.get_full_report()
      score = dashboard.get_overall_score()
    """

    def __init__(
        self,
        base_dir: str | Path,
        audit_log: Any | None = None,
        integrity_monitor: Any | None = None,
        backup_rotator: Any | None = None,
        anomaly_detector: Any | None = None,
        host_guardian: Any | None = None,
        network_monitor: Any | None = None,
        process_monitor: Any | None = None,
    ):
        self._base = Path(base_dir)
        self._state_path = self._base / "data" / ".defense_dashboard.json"
        self._audit = audit_log
        self._integrity = integrity_monitor
        self._backup = backup_rotator
        self._anomaly = anomaly_detector
        self._host_guardian = host_guardian
        self._network = network_monitor
        self._process = process_monitor
        self._lock = threading.Lock()

    # ─── public ──────────────────────────────────────────────

    def get_overall_score(self) -> int:
        """
        総合セキュリティスコア（0-100）を算出する。

        重み付け:
          ホストPC: 30%, ネットワーク: 20%, プロセス: 15%,
          整合性: 20%, バックアップ: 15%
        """
        scores: dict[str, tuple[int, float]] = {}  # name: (score, weight)

        # ホストPC
        if self._host_guardian:
            try:
                result = self._host_guardian.get_security_score()
                scores["host"] = (result.get("score", 50), 0.30)
            except Exception:
                scores["host"] = (50, 0.30)
        else:
            scores["host"] = (50, 0.30)

        # ネットワーク
        if self._network:
            try:
                scores["network"] = (self._network.get_health_score(), 0.20)
            except Exception:
                scores["network"] = (50, 0.20)
        else:
            scores["network"] = (50, 0.20)

        # プロセス
        if self._process:
            try:
                scores["process"] = (self._process.get_health_score(), 0.15)
            except Exception:
                scores["process"] = (50, 0.15)
        else:
            scores["process"] = (50, 0.15)

        # 整合性
        if self._integrity:
            try:
                result = self._integrity.verify()
                if result["status"] == "ok":
                    scores["integrity"] = (100, 0.20)
                else:
                    modified = len(result.get("modified", []))
                    missing = len(result.get("missing", []))
                    penalty = (modified + missing) * 15
                    scores["integrity"] = (max(0, 100 - penalty), 0.20)
            except Exception:
                scores["integrity"] = (50, 0.20)
        else:
            scores["integrity"] = (50, 0.20)

        # バックアップ
        if self._backup:
            try:
                backups = self._backup.list_backups()
                if backups:
                    scores["backup"] = (100, 0.15)
                else:
                    scores["backup"] = (30, 0.15)
            except Exception:
                scores["backup"] = (30, 0.15)
        else:
            scores["backup"] = (30, 0.15)

        # 重み付き平均
        total_score = sum(s * w for s, w in scores.values())
        total_weight = sum(w for _, w in scores.values())
        return round(total_score / total_weight) if total_weight > 0 else 50

    def get_full_report(self) -> str:
        """全防御モジュールの統合レポートを生成する"""
        lines: list[str] = []
        score = self.get_overall_score()

        # ヘッダー
        emoji = self._score_emoji(score)
        lines.append(f"{emoji} セキュリティ総合レポート")
        lines.append(f"総合スコア: {score}/100\n")

        # 各モジュールの状態
        lines.append("━" * 30)

        # 1. ホストPC
        lines.append("\n🖥️ ホストPCセキュリティ:")
        if self._host_guardian:
            try:
                summary = self._host_guardian.get_summary_text()
                lines.append(f"  {summary}")
            except Exception:
                lines.append("  状態を取得できませんでした")
        else:
            lines.append("  未設定")

        # 2. ネットワーク
        lines.append("\n🌐 ネットワーク:")
        if self._network:
            try:
                net_score = self._network.get_health_score()
                lines.append(f"  健全性: {net_score}/100")
                alerts = self._network.detect_suspicious()
                if alerts:
                    for a in alerts[:3]:
                        severity_mark = "🔴" if a.severity == "CRITICAL" else "⚠"
                        lines.append(f"  {severity_mark} {a.message}")
                else:
                    lines.append("  ✅ 異常なし")
            except Exception:
                lines.append("  確認できませんでした")
        else:
            lines.append("  未設定")

        # 3. プロセス
        lines.append("\n⚙️ プロセス:")
        if self._process:
            try:
                proc_score = self._process.get_health_score()
                lines.append(f"  健全性: {proc_score}/100")
                alerts = self._process.detect_suspicious_processes()
                critical = [a for a in alerts if a.severity == "CRITICAL"]
                if critical:
                    for a in critical[:2]:
                        lines.append(f"  🔴 {a.message}")
                else:
                    lines.append("  ✅ 不審なプロセスなし")
            except Exception:
                lines.append("  確認できませんでした")
        else:
            lines.append("  未設定")

        # 4. データ整合性
        lines.append("\n📁 データ整合性:")
        if self._integrity:
            try:
                result = self._integrity.verify()
                if result["status"] == "ok":
                    lines.append("  ✅ 全ファイル正常")
                else:
                    modified = len(result.get("modified", []))
                    missing = len(result.get("missing", []))
                    lines.append(f"  ⚠ 変更:{modified}件 消失:{missing}件")
            except Exception:
                lines.append("  確認できませんでした")
        else:
            lines.append("  未設定")

        # 5. バックアップ
        lines.append("\n💾 バックアップ:")
        if self._backup:
            try:
                backups = self._backup.list_backups()
                if backups:
                    latest = backups[-1]
                    lines.append(f"  最新: {latest.get('filename', '不明')}")
                    lines.append(f"  世代数: {len(backups)}")
                else:
                    lines.append("  ⚠ バックアップがありません")
            except Exception:
                lines.append("  確認できませんでした")
        else:
            lines.append("  未設定")

        # 6. 監査ログ
        lines.append("\n📋 監査ログ:")
        if self._audit:
            try:
                chain = self._audit.verify_chain()
                if chain["valid"]:
                    lines.append(f"  ✅ チェーン正常 ({chain['total']}件)")
                else:
                    lines.append(f"  🔴 チェーン破損 (行{chain['broken_at']})")
            except Exception:
                lines.append("  確認できませんでした")
        else:
            lines.append("  未設定")

        # 推奨アクション
        recommendations = self.get_recommendations()
        if recommendations:
            lines.append(f"\n{'━' * 30}")
            lines.append("\n💡 推奨アクション:")
            for i, rec in enumerate(recommendations[:5], 1):
                lines.append(f"  {i}. {rec}")

        return "\n".join(lines)

    def get_quick_status(self) -> str:
        """ワンラインのクイックステータス"""
        score = self.get_overall_score()
        emoji = self._score_emoji(score)
        return f"{emoji} セキュリティ: {self._score_label(score)} ({score}点)"

    def get_recommendations(self) -> list[str]:
        """優先順位付き推奨アクションリスト"""
        recs: list[str] = []

        # バックアップ確認
        if self._backup:
            try:
                backups = self._backup.list_backups()
                if not backups:
                    recs.append("バックアップを作成してください（「バックアップ作成」）")
            except Exception:
                pass
        else:
            recs.append("バックアップ機能を有効にしてください")

        # ホストPC
        if self._host_guardian:
            try:
                result = self._host_guardian.get_security_score()
                if result.get("score", 100) < 70:
                    alerts = result.get("alerts", [])
                    critical = [a for a in alerts if a.get("severity") == "CRITICAL"]
                    for a in critical[:2]:
                        rec = a.get("recommendation", a.get("message", ""))
                        if rec:
                            recs.append(rec)
            except Exception:
                pass

        # ネットワーク
        if self._network:
            try:
                alerts = self._network.detect_suspicious()
                critical = [a for a in alerts if a.severity == "CRITICAL"]
                if critical:
                    recs.append("不審なネットワーク接続を確認してください")
            except Exception:
                pass

        # プロセス
        if self._process:
            try:
                alerts = self._process.detect_suspicious_processes()
                critical = [a for a in alerts if a.severity == "CRITICAL"]
                if critical:
                    recs.append("不審なプロセスを確認してください（アクティビティモニタ）")
            except Exception:
                pass

        # 整合性
        if self._integrity:
            try:
                result = self._integrity.verify()
                if result["status"] != "ok":
                    recs.append("データ整合性に問題があります。整合性チェックを実行してください")
            except Exception:
                pass

        if not recs:
            recs.append("現在特に対応が必要な項目はありません。良好な状態です！")

        return recs

    def daily_job(self) -> dict:
        """自律エンジン用の日次ジョブ"""
        score = self.get_overall_score()
        recommendations = self.get_recommendations()

        # 状態を保存
        state = {
            "score": score,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "recommendations": recommendations[:5],
        }
        with self._lock:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

        # 監査ログ
        if self._audit:
            if score >= 80:
                self._audit.info("defense_report", f"日次防御レポート: スコア {score}/100")
            else:
                self._audit.warn("defense_report", f"日次防御レポート: スコア {score}/100 — 対応推奨")

        return {
            "action": "defense_report",
            "score": score,
            "recommendations": len(recommendations),
        }

    # ─── private ─────────────────────────────────────────────

    # ── #100: セキュリティスコア詳細 ─────────────────────────

    def get_security_score(self) -> Dict[str, Any]:
        """セキュリティスコアの詳細内訳を返す。

        Returns:
            {
                "overall_score": int (0-100),
                "key_age_days": int | None,
                "integrity_status": str,
                "last_backup_date": str | None,
                "pii_detections": int,
                "injection_attempts": int,
                "checked_at": str,
            }
        """
        overall: int = self.get_overall_score()

        # 鍵の経過日数（audit_log の作成日を代理指標にする）
        key_age_days: Optional[int] = None
        if self._audit:
            try:
                chain_info: Dict[str, Any] = self._audit.verify_chain()
                if chain_info.get("first_timestamp"):
                    first_ts: str = chain_info["first_timestamp"]
                    first_dt: datetime = datetime.fromisoformat(
                        first_ts.replace("Z", "+00:00")
                    )
                    key_age_days = (datetime.now(timezone.utc) - first_dt).days
            except Exception:
                pass

        # 整合性ステータス
        integrity_status: str = "unknown"
        if self._integrity:
            try:
                result: Dict[str, Any] = self._integrity.verify()
                integrity_status = result.get("status", "unknown")
            except Exception:
                integrity_status = "error"

        # 最新バックアップ日
        last_backup_date: Optional[str] = None
        if self._backup:
            try:
                backups: List[Dict[str, Any]] = self._backup.list_backups()
                if backups:
                    last_backup_date = backups[-1].get("created_at", backups[-1].get("filename", ""))
            except Exception:
                pass

        # PII 検出数・インジェクション試行数（anomaly_detector から取得を試みる）
        pii_detections: int = 0
        injection_attempts: int = 0
        if self._anomaly:
            try:
                stats: Dict[str, Any] = self._anomaly.get_stats()
                pii_detections = int(stats.get("pii_detections", 0))
                injection_attempts = int(stats.get("injection_attempts", 0))
            except Exception:
                pass

        return {
            "overall_score": overall,
            "key_age_days": key_age_days,
            "integrity_status": integrity_status,
            "last_backup_date": last_backup_date,
            "pii_detections": pii_detections,
            "injection_attempts": injection_attempts,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def format_security_dashboard(self) -> str:
        """セキュリティダッシュボードのフォーマット済みテキストを返す。"""
        info: Dict[str, Any] = self.get_security_score()
        score: int = info["overall_score"]
        emoji: str = self._score_emoji(score)
        label: str = self._score_label(score)

        lines: List[str] = []
        lines.append("=" * 50)
        lines.append(f"  {emoji} セキュリティダッシュボード")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"  総合スコア: {score}/100 ({label})")
        lines.append("")

        lines.append("■ 詳細")
        lines.append("-" * 30)

        if info["key_age_days"] is not None:
            lines.append(f"  鍵の経過日数: {info['key_age_days']}日")
        else:
            lines.append("  鍵の経過日数: 不明")

        lines.append(f"  整合性ステータス: {info['integrity_status']}")

        if info["last_backup_date"]:
            lines.append(f"  最終バックアップ: {info['last_backup_date']}")
        else:
            lines.append("  最終バックアップ: なし")

        lines.append(f"  PII 検出数: {info['pii_detections']}")
        lines.append(f"  インジェクション試行: {info['injection_attempts']}")
        lines.append("")

        # 推奨アクション
        recs: List[str] = self.get_recommendations()
        if recs:
            lines.append("■ 推奨アクション")
            lines.append("-" * 30)
            for i, rec in enumerate(recs[:5], 1):
                lines.append(f"  {i}. {rec}")
            lines.append("")

        lines.append(f"  確認日時: {info['checked_at']}")
        lines.append("=" * 50)
        return "\n".join(lines)

    # ─── private ─────────────────────────────────────────────

    @staticmethod
    def _score_emoji(score: int) -> str:
        if score >= 90:
            return "🛡️"
        if score >= 70:
            return "⚠️"
        if score >= 50:
            return "🚨"
        return "💀"

    @staticmethod
    def _score_label(score: int) -> str:
        if score >= 90:
            return "良好"
        if score >= 70:
            return "注意"
        if score >= 50:
            return "警告"
        return "危険"

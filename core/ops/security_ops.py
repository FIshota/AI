"""
core.ops.security_ops — セキュリティ診断・バックアップ・ロックダウン系オペレーション

AiChan インスタンスを第一引数に取り、ユーザー向けの応答文字列を返す
純粋関数群。AiChan 側の attributes (host_guardian / integrity /
anomaly_detector / audit / backup / kill_switch) に依存する。

M2 (2026-04-21): core/ai_chan.py:_run_* から切り出し。
"""
from __future__ import annotations

from typing import Any


def run_security_check(ai: Any) -> str:
    """セキュリティ統合診断（PC/データ整合性/異常検知/監査ログチェーン）。"""
    lines: list[str] = ["\U0001f6e1\ufe0f セキュリティ診断を実行するね！\n"]

    host_guardian = getattr(ai, "host_guardian", None)
    if host_guardian is not None:
        try:
            summary = host_guardian.get_summary_text()
            lines.append("【PCセキュリティ】")
            lines.append(summary)
        except Exception as e:
            lines.append(f"【PCセキュリティ】確認できなかったよ: {e}")

    integrity = getattr(ai, "integrity", None)
    if integrity is not None:
        try:
            result = integrity.verify()
            if result["status"] == "ok":
                lines.append("\n【データ整合性】\u2705 異常なし")
            else:
                lines.append(
                    f"\n【データ整合性】\u26a0 問題あり: "
                    f"変更{len(result['modified'])}件、消失{len(result['missing'])}件"
                )
        except Exception:
            pass

    anomaly_detector = getattr(ai, "anomaly_detector", None)
    if anomaly_detector is not None:
        try:
            alerts = anomaly_detector.run_checks()
            critical = [a for a in alerts if a.severity == "CRITICAL"]
            if critical:
                lines.append(f"\n【異常検知】\U0001f534 重大アラート {len(critical)}件")
                for a in critical[:3]:
                    lines.append(f"  → {a.message}")
            else:
                lines.append("\n【異常検知】\u2705 異常なし")
        except Exception:
            pass

    audit = getattr(ai, "audit", None)
    if audit is not None:
        try:
            chain = audit.verify_chain()
            if chain["valid"]:
                lines.append(f"\n【監査ログ】\u2705 チェーン正常 ({chain['total']}件)")
            else:
                lines.append(f"\n【監査ログ】\U0001f534 チェーン破損 (行{chain['broken_at']})")
        except Exception:
            pass

    return "\n".join(lines)


def run_backup(ai: Any) -> str:
    """手動バックアップを作成。"""
    backup = getattr(ai, "backup", None)
    if backup is None:
        return "バックアップ機能が初期化されていないよ。"
    try:
        result = backup.create_backup(label="manual")
        return (
            f"\u2705 バックアップ完了！\n"
            f"サイズ: {result['size_mb']}MB、ファイル数: {result['files']}"
        )
    except Exception as e:
        return f"バックアップに失敗したよ: {e}"


def show_backup_list(ai: Any) -> str:
    """既存バックアップの一覧表示（直近 5 件）。"""
    backup = getattr(ai, "backup", None)
    if backup is None:
        return "バックアップ機能が初期化されていないよ。"
    backups = backup.list_backups()
    if not backups:
        return "まだバックアップはないよ。「バックアップ作成」で作れるよ！"
    lines = ["\U0001f4e6 バックアップ一覧："]
    for b in backups[-5:]:
        lines.append(f"  \u2022 {b['filename']} ({b['size_mb']}MB)")
    return "\n".join(lines)


def run_lockdown(ai: Any, reason: str) -> str:
    """緊急ロックダウン（外部通信遮断＋バックアップ）。"""
    kill_switch = getattr(ai, "kill_switch", None)
    if kill_switch is None:
        return "キルスイッチが初期化されていないよ。"
    try:
        kill_switch.backup_and_halt(reason)
        return (
            f"\U0001f512 緊急ロックダウンを実行したよ！\n"
            f"理由: {reason}\n"
            f"外部通信を遮断し、バックアップを作成しました。\n"
            f"解除するには「アイ解除」と話しかけてね。"
        )
    except Exception as e:
        return f"ロックダウンに失敗: {e}"


def run_unlock(ai: Any) -> str:
    """ロックダウン解除（合言葉『アイ解除』必須）。"""
    kill_switch = getattr(ai, "kill_switch", None)
    if kill_switch is None:
        return "キルスイッチが初期化されていないよ。"
    result = kill_switch.unlock(confirm="アイ解除")
    if result["unlocked"]:
        return "\U0001f513 ロックダウンを解除したよ！通常モードに戻るね。"
    return f"解除できなかったよ: {result['reason']}"

"""
core.ops.server_ops — サーバー（アイの家）系オペレーション

AiChan の server_home / server_ai_env / prometheus / knowledge_sync
属性に依存する。M2 (2026-04-21): core/ai_chan.py:_server_* から切り出し。
"""
from __future__ import annotations

from typing import Any


def server_status(ai: Any) -> str:
    """サーバー（アイの家）の状態を整形して返す。"""
    sh = getattr(ai, "server_home", None)
    if sh is None or not sh.enabled:
        return (
            "\U0001f3e0 サーバー（アイの家）はまだ設定されていないよ。\n"
            "「サーバー設定」で接続先を登録してね！"
        )
    lines: list[str] = ["\U0001f3e0 アイの家（サーバー）の状態だよ：\n"]
    reachable = sh.is_reachable()
    if not reachable:
        lines.append("\u274c サーバーに接続できないよ…。電源やLANケーブルを確認してね。")
        return "\n".join(lines)
    lines.append("\u2705 サーバーに接続できたよ！")
    try:
        health = sh.health_check()
        if health.get("ok"):
            if health.get("uptime"):
                lines.append(f"\u23f1 稼働時間: {health['uptime'].strip()}")
            if health.get("disk_usage"):
                lines.append(f"\U0001f4be ディスク: {health['disk_usage'].strip()}")
            if health.get("memory"):
                lines.append(f"\U0001f9e0 メモリ: {health['memory'].strip()}")
    except Exception:
        pass
    ai_env = getattr(ai, "server_ai_env", None)
    if ai_env is not None:
        lines.append(f"\n{ai_env.get_status_text()}")
    prom = getattr(ai, "prometheus", None)
    if prom is not None:
        lines.append(f"\n{prom.get_summary_text()}")
    ks = getattr(ai, "knowledge_sync", None)
    if ks is not None:
        lines.append(f"\n{ks.get_sync_status()}")
    return "\n".join(lines)


def server_docker(ai: Any) -> str:
    """サーバー上の Docker コンテナ一覧を取得。"""
    sh = getattr(ai, "server_home", None)
    if sh is None or not sh.enabled:
        return "\U0001f3e0 サーバーがまだ設定されていないよ。「サーバー設定」で登録してね！"
    try:
        containers = sh.docker_ps()
    except Exception as e:
        return f"Docker情報を取得できなかったよ: {e}"
    if not containers:
        return "\U0001f433 サーバーにDockerコンテナはないみたい。"
    lines = [f"\U0001f433 Dockerコンテナ一覧（{len(containers)}件）："]
    for c in containers:
        status_icon = "\U0001f7e2" if "Up" in c.get("status", "") else "\U0001f534"
        lines.append(f"  {status_icon} {c.get('name', '?')} - {c.get('status', '?')}")
    return "\n".join(lines)


def server_sync(ai: Any) -> str:
    """サーバーとの双方向知識同期（push + pull）。"""
    ks = getattr(ai, "knowledge_sync", None)
    if ks is None:
        return "\U0001f3e0 サーバーがまだ設定されていないよ。「サーバー設定」で登録してね！"
    lines = ["\U0001f4e1 サーバーとの知識同期を開始するね…\n"]

    push_result = ks.push_knowledge()
    if push_result.get("ok"):
        action = push_result.get("action", "")
        if action == "no_changes":
            lines.append("\u2b06 アップロード: 変更なし（最新状態）")
        else:
            lines.append("\u2b06 アップロード: \u2705 完了！")
    else:
        lines.append(f"\u2b06 アップロード: \u274c {push_result.get('error', '失敗')}")

    pull_result = ks.pull_knowledge()
    if pull_result.get("ok"):
        pulled = pull_result.get("pulled", 0)
        if pull_result.get("action") == "nothing_to_pull":
            lines.append("\u2b07 ダウンロード: 新しいデータなし")
        else:
            lines.append(f"\u2b07 ダウンロード: \u2705 {pulled}件取得！")
    else:
        lines.append(f"\u2b07 ダウンロード: \u274c {pull_result.get('error', '失敗')}")
    return "\n".join(lines)


def server_setup_guide() -> str:
    """サーバー設定の手順ガイド。AiChan 状態に依存しないため ai 引数なし。"""
    return (
        "\U0001f3e0 サーバー（アイの家）の設定方法だよ：\n\n"
        "config/settings.json の「server_home」セクションを編集してね：\n"
        "  - enabled: true にする\n"
        "  - host: サーバーのIPアドレス（例: 192.168.3.86）\n"
        "  - port: SSHポート（通常22）\n"
        "  - username: SSHユーザー名\n"
        "  - password: SSHパスワード（暗号化して保存されるよ）\n\n"
        "設定後、「サーバー状態」で接続テストできるよ！"
    )

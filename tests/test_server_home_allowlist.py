"""server_home.py の _is_allowed() regression tests.

背景: 2026-04-21 の security triage で以下の脆弱性が発見された:
  - "rm -rf /home" が allowlist に含まれ、path traversal で全破壊可能
  - "cat" / "ls" / "pwd" / "mkdir" が単体で allowlist に含まれ、
    "cat /etc/shadow" 等が通過していた

本テストはそれらが再発しないことを保証する.
"""
from __future__ import annotations

import pytest

from core.server_home import DEFAULT_ALLOWED_PREFIXES, ServerHome


@pytest.fixture
def allowlist_checker():
    """_is_allowed を単体で叩けるよう、paramiko 不要の lightweight fixture."""
    # ServerHome は paramiko 依存が大きいので _is_allowed だけをローカルクラスで再現
    from core.server_home import _DANGEROUS_PATTERNS

    class _Probe:
        _allowed = DEFAULT_ALLOWED_PREFIXES

        def _is_allowed(self, cmd: str) -> bool:
            return ServerHome._is_allowed(self, cmd)  # type: ignore[arg-type]

    return _Probe()


# ─── 危険パターン: path traversal ─────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "ls /home/../etc",
    "cd /home/user/../..",
    "mkdir -p /home/../tmp",
    "cat /home/user/../../etc/passwd",
])
def test_path_traversal_rejected(allowlist_checker, cmd):
    assert allowlist_checker._is_allowed(cmd) is False, (
        f"path traversal should be rejected: {cmd!r}"
    )


# ─── 危険パターン: command substitution ──────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "ls /home/$(whoami)",
    "mkdir -p /home/`id`",
    "docker ps $(cat /etc/hostname)",
])
def test_command_substitution_rejected(allowlist_checker, cmd):
    assert allowlist_checker._is_allowed(cmd) is False


# ─── 危険パターン: rm 系は全て拒否 ────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "rm -rf /home",
    "rm -rf /home/",
    "rm -rf /home/../",
    "rm -rf /",
    "rm -r /home/user",
    "rm /tmp/foo",
])
def test_rm_always_rejected(allowlist_checker, cmd):
    assert allowlist_checker._is_allowed(cmd) is False, (
        f"rm 系は常に拒否されるべき: {cmd!r}"
    )


# ─── 機密ファイル直接参照は拒否 ─────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "docker exec container cat /etc/shadow",
    "docker exec c1 cat /etc/passwd",
    "docker exec c1 cat /etc/sudoers",
])
def test_sensitive_file_references_rejected(allowlist_checker, cmd):
    assert allowlist_checker._is_allowed(cmd) is False


# ─── 改行・null バイトによるチェーンは拒否 ───────────────────────────────

@pytest.mark.parametrize("cmd", [
    "uptime\nrm -rf /home",
    "whoami\rrm -rf /",
    "docker ps\x00cat /etc/passwd",
])
def test_control_char_chaining_rejected(allowlist_checker, cmd):
    assert allowlist_checker._is_allowed(cmd) is False


# ─── 旧 allowlist にあった曖昧プレフィックスは拒否 ───────────────────────

@pytest.mark.parametrize("cmd", [
    "cat /etc/shadow",
    "cat /etc/passwd",
    "ls /root",
    "ls /root/.ssh/",
    "pwd",
    "mkdir /tmp/evil",
])
def test_old_broad_prefixes_rejected(allowlist_checker, cmd):
    """以前は cat/ls/pwd/mkdir 単体 allowlist で通っていたコマンドが拒否されること."""
    assert allowlist_checker._is_allowed(cmd) is False, (
        f"曖昧 allowlist 問題の再発: {cmd!r}"
    )


# ─── 正常な呼び出しは通る (回帰防止) ────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "docker ps",
    "docker inspect --format '{{.State.Status}}' container_name",
    "docker exec container python /workspace/script.py",
    "mkdir -p /home/user/ai-chan/knowledge",
    "ls /home/user/ai-chan/",
    "ls -1 /home/user/output/",
    "uptime",
    "whoami",
    "hostname",
    "df -h",
    "free -h",
    "curl -s 'localhost:9090/api/v1/query?query=node_cpu'",
    "systemctl status nginx",
])
def test_legitimate_commands_still_allowed(allowlist_checker, cmd):
    assert allowlist_checker._is_allowed(cmd) is True, (
        f"正常な呼び出しが拒否された (regression): {cmd!r}"
    )


# ─── 空文字・空白のみは拒否 ─────────────────────────────────────────────

@pytest.mark.parametrize("cmd", ["", "   ", "\n", "\t"])
def test_empty_command_rejected(allowlist_checker, cmd):
    assert allowlist_checker._is_allowed(cmd) is False

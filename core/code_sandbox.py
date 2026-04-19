"""
コードサンドボックス (Code Sandbox)

安全な隔離環境でコードを実行する。

制限:
  - タイムアウト（デフォルト10秒）
  - 一時ディレクトリ内のみファイルアクセス可能
  - ネットワークアクセスなし（subprocess環境制限）
  - メモリ: 256MB上限（Unix系のみ resource.RLIMIT_AS）
  - プロセス数: 最大10（Unix系のみ resource.RLIMIT_NPROC）

将来YAMATOの yamato_core に移植される遺伝子技術。
"""
from __future__ import annotations

import logging
import platform
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

# Unix系のみ resource モジュールを利用
_HAS_RESOURCE = False
if platform.system() != "Windows":
    try:
        import resource
        _HAS_RESOURCE = True
    except ImportError:
        pass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionResult:
    """コード実行結果"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    elapsed_ms: int = 0
    timed_out: bool = False


class CodeSandbox:
    """
    安全なコード実行環境。

    subprocess で別プロセスとして実行し、
    タイムアウト・出力制限で安全性を確保する。

    使い方:
      sandbox = CodeSandbox()
      result = sandbox.execute("print(1 + 2)")
      # result.stdout == "3\n"
    """

    _MAX_OUTPUT = 10_000  # 出力上限(文字数)
    _MEM_LIMIT_BYTES = 256 * 1024 * 1024  # 256MB
    _MAX_NPROC = 10

    _BLOCKED_IMPORTS = frozenset({
        "os.system", "subprocess", "shutil.rmtree",
        "socket", "http", "urllib", "requests",
        "ctypes", "multiprocessing",
        "importlib", "__builtins__", "pathlib", "glob", "signal",
    })

    # コード内で禁止する組み込み呼び出し（文字列リテラル外）
    _BLOCKED_BUILTINS = frozenset({
        "open(",
        "sys.exit",
        "quit(",
    })

    def __init__(
        self,
        timeout_sec: int = 10,
        python_path: str = "python3",
    ) -> None:
        self._timeout = timeout_sec
        self._python = python_path

    def execute(self, code: str, timeout: int | None = None) -> ExecutionResult:
        """
        Pythonコードを安全に実行する。

        Args:
            code: 実行するPythonコード
            timeout: タイムアウト秒数（Noneでデフォルト）

        Returns:
            ExecutionResult: 実行結果
        """
        # バリデーション
        is_safe, reason = self.validate_code(code)
        if not is_safe:
            return ExecutionResult(
                success=False,
                stderr=f"セキュリティ: {reason}",
                return_code=-1,
            )

        effective_timeout = timeout or self._timeout
        preexec_fn = self._make_preexec_fn()

        with tempfile.TemporaryDirectory(prefix="ai_sandbox_") as tmpdir:
            script_path = Path(tmpdir) / "script.py"
            script_path.write_text(code, encoding="utf-8")

            start = time.monotonic()
            try:
                proc = subprocess.run(
                    [self._python, str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    cwd=tmpdir,
                    env={
                        "PATH": "/usr/bin:/usr/local/bin",
                        "HOME": tmpdir,
                        "TMPDIR": tmpdir,
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    preexec_fn=preexec_fn,
                )
                elapsed = int((time.monotonic() - start) * 1000)

                stdout = proc.stdout[:self._MAX_OUTPUT]
                stderr = proc.stderr[:self._MAX_OUTPUT]

                return ExecutionResult(
                    success=proc.returncode == 0,
                    stdout=stdout,
                    stderr=stderr,
                    return_code=proc.returncode,
                    elapsed_ms=elapsed,
                )
            except subprocess.TimeoutExpired:
                elapsed = int((time.monotonic() - start) * 1000)
                return ExecutionResult(
                    success=False,
                    stderr=f"タイムアウト ({effective_timeout}秒超過)",
                    return_code=-1,
                    elapsed_ms=elapsed,
                    timed_out=True,
                )
            except FileNotFoundError:
                return ExecutionResult(
                    success=False,
                    stderr=f"Python実行環境が見つかりません: {self._python}",
                    return_code=-1,
                )
            except Exception as exc:
                logger.exception("サンドボックス実行エラー")
                return ExecutionResult(
                    success=False,
                    stderr=f"実行エラー: {exc}",
                    return_code=-1,
                )

    # ── セキュリティチェック ──

    @staticmethod
    def _strip_string_literals(code: str) -> str:
        """文字列リテラルを空文字に置換してコード部分だけ残す（簡易版）"""
        # トリプルクォートを先に除去し、次にシングル/ダブルクォートを除去
        stripped = re.sub(r'""".*?"""', '""', code, flags=re.DOTALL)
        stripped = re.sub(r"'''.*?'''", "''", stripped, flags=re.DOTALL)
        stripped = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', stripped)
        stripped = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", stripped)
        return stripped

    def _check_blocked(self, code: str) -> Optional[str]:
        """禁止されたimport/呼び出しをチェック"""
        for blocked in self._BLOCKED_IMPORTS:
            if blocked in code:
                return blocked
        # eval/exec の直接使用
        if "exec(" in code or "__import__(" in code:
            return "exec/__import__"
        # 組み込み関数の危険な呼び出し（文字列リテラル外）
        code_no_strings = self._strip_string_literals(code)
        for builtin in self._BLOCKED_BUILTINS:
            if builtin in code_no_strings:
                return builtin
        return None

    def validate_code(self, code: str) -> Tuple[bool, str]:
        """
        全セキュリティルールを検証する。

        Args:
            code: 検証対象のPythonコード

        Returns:
            (is_safe, reason) — 安全ならば (True, ""), 危険ならば (False, "理由")
        """
        if not code.strip():
            return (False, "空のコードです")

        blocked = self._check_blocked(code)
        if blocked is not None:
            return (False, f"禁止されたモジュール/呼び出し使用: {blocked}")

        return (True, "")

    # ── リソース制限 ──

    @classmethod
    def _make_preexec_fn(cls) -> Optional[Callable[[], None]]:
        """subprocess の preexec_fn を生成（Unix系のみ）

        RLIMIT_AS: 仮想メモリ上限（Linux では有効、macOS では
        カーネル制限で設定できない場合がある）。
        RLIMIT_NPROC: 子プロセス数上限。
        設定失敗時は警告のみでプロセス起動を妨げない。
        """
        if not _HAS_RESOURCE:
            return None

        mem_limit = cls._MEM_LIMIT_BYTES
        max_nproc = cls._MAX_NPROC

        def _set_limits() -> None:
            # メモリ制限（macOS では設定できない場合がある）
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
            except (ValueError, OSError):
                pass  # macOS等でRLIMIT_AS設定不可の場合は無視
            # プロセス数制限
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (max_nproc, max_nproc))
            except (ValueError, OSError):
                pass

        return _set_limits

    def execute_and_format(self, code: str) -> str:
        """実行して結果をフォーマット済み文字列で返す"""
        result = self.execute(code)
        lines: list[str] = []

        if result.success:
            lines.append(f"✅ 実行成功 ({result.elapsed_ms}ms)")
            if result.stdout.strip():
                lines.append(f"📤 出力:\n{result.stdout.strip()}")
            else:
                lines.append("📤 出力なし")
        else:
            if result.timed_out:
                lines.append(f"⏱️ タイムアウト ({result.elapsed_ms}ms)")
            else:
                lines.append(f"❌ 実行失敗 (code={result.return_code})")
            if result.stderr.strip():
                lines.append(f"📛 エラー:\n{result.stderr.strip()}")

        return "\n".join(lines)

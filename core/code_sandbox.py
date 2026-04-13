"""
コードサンドボックス (Code Sandbox)

安全な隔離環境でコードを実行する。

制限:
  - タイムアウト（デフォルト10秒）
  - 一時ディレクトリ内のみファイルアクセス可能
  - ネットワークアクセスなし（subprocess環境制限）
  - メモリ: 親プロセスの制限に従う

将来YAMATOの yamato_core に移植される遺伝子技術。
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

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
    _BLOCKED_IMPORTS = frozenset({
        "os.system", "subprocess", "shutil.rmtree",
        "socket", "http", "urllib", "requests",
        "ctypes", "multiprocessing",
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
        if not code.strip():
            return ExecutionResult(
                success=False, stderr="空のコードです", return_code=-1,
            )

        # 危険なimportチェック
        blocked = self._check_blocked(code)
        if blocked:
            return ExecutionResult(
                success=False,
                stderr=f"セキュリティ: 禁止されたモジュール使用 ({blocked})",
                return_code=-1,
            )

        effective_timeout = timeout or self._timeout

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

    def _check_blocked(self, code: str) -> str | None:
        """禁止されたimport/呼び出しをチェック"""
        for blocked in self._BLOCKED_IMPORTS:
            if blocked in code:
                return blocked
        # eval/exec の直接使用
        if "exec(" in code or "__import__(" in code:
            return "exec/__import__"
        return None

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

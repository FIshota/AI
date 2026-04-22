"""
Phase 2 テスト — CodeSandbox / run_and_fix / CMD_CODE_RUN

2-A: CodeSandbox 単体テスト
2-B: CodeEngine.run / run_and_fix テスト
2-C: CMD_CODE_RUN パターン + ハンドラ テスト
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────
# 2-A: CodeSandbox 単体テスト
# ──────────────────────────────────────────────

class TestExecutionResult:
    """ExecutionResult frozen dataclass"""

    def test_frozen(self) -> None:
        from core.code_sandbox import ExecutionResult
        r = ExecutionResult(success=True, stdout="ok")
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]

    def test_defaults(self) -> None:
        from core.code_sandbox import ExecutionResult
        r = ExecutionResult(success=False)
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.return_code == -1
        assert r.elapsed_ms == 0
        assert r.timed_out is False


class TestCodeSandbox:
    """CodeSandbox 実行テスト"""

    def test_execute_simple(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox(timeout_sec=5)
        result = sb.execute("print(1 + 2)")
        assert result.success is True
        assert result.stdout.strip() == "3"
        assert result.return_code == 0
        assert result.elapsed_ms > 0

    def test_execute_empty_code(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("")
        assert result.success is False
        assert "空" in result.stderr

    def test_execute_whitespace_only(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("   \n  ")
        assert result.success is False

    def test_execute_syntax_error(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("def foo(:")
        assert result.success is False
        assert result.return_code != 0

    def test_execute_runtime_error(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("1 / 0")
        assert result.success is False
        assert "ZeroDivision" in result.stderr

    def test_blocked_subprocess(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("import subprocess; subprocess.run(['ls'])")
        assert result.success is False
        assert "セキュリティ" in result.stderr or "禁止" in result.stderr

    def test_blocked_socket(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("import socket")
        assert result.success is False
        assert "セキュリティ" in result.stderr or "禁止" in result.stderr

    def test_blocked_os_system(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("import os; os.system('ls')")
        assert result.success is False

    def test_blocked_exec(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("exec('print(1)')")
        assert result.success is False
        assert "exec" in result.stderr

    def test_blocked_import(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        result = sb.execute("__import__('os')")
        assert result.success is False

    def test_timeout(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox(timeout_sec=1)
        result = sb.execute("import time; time.sleep(5)", timeout=1)
        assert result.success is False
        assert result.timed_out is True
        assert "タイムアウト" in result.stderr

    def test_output_truncation(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        # 大量出力を生成
        result = sb.execute("print('A' * 20000)")
        assert result.success is True
        assert len(result.stdout) <= 10_000

    def test_execute_and_format_success(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        text = sb.execute_and_format("print('hello')")
        assert "✅" in text
        assert "hello" in text

    def test_execute_and_format_failure(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        text = sb.execute_and_format("raise ValueError('oops')")
        assert "❌" in text
        assert "oops" in text or "ValueError" in text

    def test_execute_and_format_timeout(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox(timeout_sec=1)
        text = sb.execute_and_format("import time; time.sleep(5)")
        assert "⏱️" in text

    def test_multiline_code(self) -> None:
        from core.code_sandbox import CodeSandbox
        sb = CodeSandbox()
        code = "x = 10\ny = 20\nprint(x + y)"
        result = sb.execute(code)
        assert result.success is True
        assert result.stdout.strip() == "30"


# ──────────────────────────────────────────────
# 2-B: CodeEngine.run / run_and_fix テスト
# ──────────────────────────────────────────────

class TestCodeEngineRun:
    """CodeEngine.run() テスト"""

    def _make_engine(self, tmp_path: Path) -> "CodeEngine":
        from core.code_engine import CodeEngine
        return CodeEngine(data_dir=tmp_path)

    def test_run_simple(self, tmp_path: Path) -> None:
        engine = self._make_engine(tmp_path)
        result = engine.run("print('test')")
        assert "✅" in result
        assert "test" in result

    def test_run_failure(self, tmp_path: Path) -> None:
        engine = self._make_engine(tmp_path)
        result = engine.run("raise RuntimeError('boom')")
        assert "❌" in result


class TestCodeEngineRunAndFix:
    """CodeEngine.run_and_fix() テスト"""

    def _make_engine(self, tmp_path: Path) -> "CodeEngine":
        from core.code_engine import CodeEngine
        return CodeEngine(data_dir=tmp_path)

    def test_run_and_fix_success_first_try(self, tmp_path: Path) -> None:
        engine = self._make_engine(tmp_path)
        result = engine.run_and_fix("print('works')")
        assert "✅" in result
        assert "初回" in result
        assert "works" in result

    def test_run_and_fix_all_failures(self, tmp_path: Path) -> None:
        engine = self._make_engine(tmp_path)
        # undefinedな変数を使う — suggest_fixでは自動修正されない
        result = engine.run_and_fix(
            "undefined_var_xyz_999",
            max_retries=1,
        )
        assert "❌" in result
        assert "試行" in result

    def test_run_and_fix_timeout_breaks(self, tmp_path: Path) -> None:
        """タイムアウトではリトライしない"""
        from core.code_engine import CodeEngine
        engine = CodeEngine(data_dir=tmp_path)
        # sandbox default is 10s; patch to make fast
        with patch("core.code_sandbox.CodeSandbox") as MockSandbox:
            from core.code_sandbox import ExecutionResult
            mock_sb = MockSandbox.return_value
            mock_sb.execute.return_value = ExecutionResult(
                success=False,
                stderr="タイムアウト (10秒超過)",
                return_code=-1,
                timed_out=True,
                elapsed_ms=10000,
            )
            result = engine.run_and_fix("import time; time.sleep(999)")
            assert "タイムアウト" in result
            # execute は1回だけ（リトライしない）
            assert mock_sb.execute.call_count == 1

    def test_run_and_fix_records_pattern(self, tmp_path: Path) -> None:
        engine = self._make_engine(tmp_path)
        engine.run_and_fix("print(42)")
        stats = engine.get_stats()
        assert stats["pattern_memory"]["total"] >= 1


# ──────────────────────────────────────────────
# 2-C: CMD_CODE_RUN パターン + ハンドラ テスト
# ──────────────────────────────────────────────

class TestCmdCodeRunPattern:
    """CMD_CODE_RUN パターンマッチテスト"""

    def _pattern(self):
        from core.cmd_handlers import CMD_CODE_RUN
        return CMD_CODE_RUN

    def test_basic_match(self) -> None:
        p = self._pattern()
        assert p.match("コード実行: print('hello')")

    def test_kono_prefix(self) -> None:
        p = self._pattern()
        assert p.match("このコード実行: 1+1")

    def test_wo_particle(self) -> None:
        p = self._pattern()
        assert p.match("コードを実行: x=1")

    def test_hashirasete(self) -> None:
        p = self._pattern()
        assert p.match("コード走らせて: print('go')")

    def test_ugokashite(self) -> None:
        p = self._pattern()
        assert p.match("コード動かして: print('move')")

    def test_no_match(self) -> None:
        p = self._pattern()
        assert p.match("こんにちは") is None

    def test_capture_group(self) -> None:
        p = self._pattern()
        m = p.match("コード実行: print('test')")
        assert m is not None
        assert m.group(4).strip() == "print('test')"


class TestHandleCodeRun:
    """_handle_code_run ハンドラテスト"""

    def test_no_engine(self) -> None:
        """code_engine未初期化の場合"""
        ai = MagicMock()
        ai.code_engine = None
        # _handle_code_run は AiChan のメソッドなので直接呼ぶ
        from core.ai_chan import AiChan
        handler = AiChan._handle_code_run
        # selfの属性をmockで模倣
        mock_self = MagicMock()
        mock_self.code_engine = None
        # getattr(self, "code_engine", None) を動作させる
        del mock_self.code_engine  # getattrがNoneを返すように
        result = handler(mock_self, "print(1)")
        assert "初期化されていない" in result

    def test_with_engine(self, tmp_path: Path) -> None:
        """code_engine初期化済みの場合"""
        from core.code_engine import CodeEngine
        mock_self = MagicMock()
        mock_self.code_engine = CodeEngine(data_dir=tmp_path)
        from core.ai_chan import AiChan
        result = AiChan._handle_code_run(mock_self, "print('hello from handler')")
        assert "✅" in result
        assert "hello from handler" in result

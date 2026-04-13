"""
Tests for core.code_engine module.

Covers PythonAnalyzer, CodeEngine, PatternMemory, detect_language,
and frozen dataclasses (CodeIssue, CodeAnalysis, CodePattern).
"""
from __future__ import annotations

import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from core.code_engine import (
    CodeAnalysis,
    CodeEngine,
    CodeIssue,
    CodePattern,
    PatternMemory,
    PythonAnalyzer,
    detect_language,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

SAMPLE_PYTHON = '''\
import os
from pathlib import Path


class FileManager:
    """ファイル管理クラス"""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def read_file(self, name: str) -> str:
        """ファイルを読み込む"""
        path = self._base / name
        return path.read_text()

    def list_files(self) -> list[str]:
        """ファイル一覧"""
        return [f.name for f in self._base.iterdir() if f.is_file()]
'''

BAD_PYTHON = '''\
def process(data=[]):
    try:
        result = eval(data[0])
    except:
        pass
    return result
'''

JAVASCRIPT_CODE = '''\
const express = require('express');
const app = express();

function handleRequest(req, res) {
    res.json({ status: 'ok' });
}

app.get('/', handleRequest);
'''


@pytest.fixture()
def engine() -> CodeEngine:
    return CodeEngine()


@pytest.fixture()
def engine_with_storage(tmp_path: Path) -> CodeEngine:
    return CodeEngine(data_dir=tmp_path)


@pytest.fixture()
def analyzer() -> PythonAnalyzer:
    return PythonAnalyzer()


# ──────────────────────────────────────────────
# Frozen dataclass tests
# ──────────────────────────────────────────────

class TestCodeIssueFrozen:
    def test_frozen(self) -> None:
        issue = CodeIssue(severity="high", line=1, message="test")
        with pytest.raises(FrozenInstanceError):
            issue.severity = "low"  # type: ignore[misc]

    def test_defaults(self) -> None:
        issue = CodeIssue(severity="low", line=0, message="msg")
        assert issue.suggestion == ""


class TestCodeAnalysisFrozen:
    def test_frozen(self) -> None:
        analysis = CodeAnalysis(language="python", lines=10)
        with pytest.raises(FrozenInstanceError):
            analysis.language = "rust"  # type: ignore[misc]

    def test_defaults(self) -> None:
        analysis = CodeAnalysis(language="go", lines=5)
        assert analysis.functions == ()
        assert analysis.classes == ()
        assert analysis.imports == ()
        assert analysis.complexity == 0
        assert analysis.issues == ()


class TestCodePatternFrozen:
    def test_frozen(self) -> None:
        p = CodePattern(
            pattern_type="fix", language="python",
            input_signature="sig", success=True,
        )
        with pytest.raises(FrozenInstanceError):
            p.success = False  # type: ignore[misc]


# ──────────────────────────────────────────────
# Language detection tests
# ──────────────────────────────────────────────

class TestDetectLanguage:
    def test_python(self) -> None:
        assert detect_language("import os\ndef hello():\n    pass") == "python"

    def test_javascript(self) -> None:
        assert detect_language(JAVASCRIPT_CODE) == "javascript"

    def test_rust(self) -> None:
        code = "fn main() {\n    let mut x = 5;\n}"
        assert detect_language(code) == "rust"

    def test_go(self) -> None:
        code = "package main\n\nfunc main() {\n}"
        assert detect_language(code) == "go"

    def test_sql(self) -> None:
        assert detect_language("SELECT * FROM users") == "sql"

    def test_unknown(self) -> None:
        assert detect_language("hello world") == "unknown"

    def test_html(self) -> None:
        assert detect_language("<html><div>Hello</div></html>") == "html"


# ──────────────────────────────────────────────
# PythonAnalyzer tests
# ──────────────────────────────────────────────

class TestPythonAnalyzer:
    def test_analyze_functions(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(SAMPLE_PYTHON)
        assert "read_file" in result.functions
        assert "list_files" in result.functions
        assert "__init__" in result.functions

    def test_analyze_classes(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(SAMPLE_PYTHON)
        assert "FileManager" in result.classes

    def test_analyze_imports(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(SAMPLE_PYTHON)
        assert "os" in result.imports
        assert "pathlib" in result.imports

    def test_analyze_lines(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(SAMPLE_PYTHON)
        assert result.lines > 10

    def test_analyze_language(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(SAMPLE_PYTHON)
        assert result.language == "python"

    def test_syntax_error(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze("def bad(\n")
        assert len(result.issues) > 0
        assert result.issues[0].severity == "critical"
        assert "構文エラー" in result.issues[0].message

    def test_bare_except_detected(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(BAD_PYTHON)
        severities = [i.severity for i in result.issues]
        assert "high" in severities

    def test_mutable_default_detected(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(BAD_PYTHON)
        messages = [i.message for i in result.issues]
        assert any("ミュータブル" in m for m in messages)

    def test_summary_present(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze(SAMPLE_PYTHON)
        assert result.summary
        assert "クラス" in result.summary or "関数" in result.summary

    def test_empty_code(self, analyzer: PythonAnalyzer) -> None:
        result = analyzer.analyze("")
        assert result.lines == 1
        assert result.functions == ()


# ──────────────────────────────────────────────
# CodeEngine tests
# ──────────────────────────────────────────────

class TestCodeEngine:
    def test_analyze_python(self, engine: CodeEngine) -> None:
        result = engine.analyze(SAMPLE_PYTHON)
        assert result.language == "python"
        assert len(result.functions) >= 2

    def test_analyze_auto_detect(self, engine: CodeEngine) -> None:
        result = engine.analyze(JAVASCRIPT_CODE)
        assert result.language == "javascript"

    def test_analyze_empty(self, engine: CodeEngine) -> None:
        result = engine.analyze("")
        assert result.summary == "空のコード"

    def test_analyze_explicit_language(self, engine: CodeEngine) -> None:
        result = engine.analyze("some code", language="rust")
        assert result.language == "rust"

    def test_review_finds_issues(self, engine: CodeEngine) -> None:
        issues = engine.review(BAD_PYTHON)
        assert len(issues) > 0

    def test_review_security_eval(self, engine: CodeEngine) -> None:
        issues = engine.review("result = eval(user_input)")
        critical = [i for i in issues if i.severity == "critical"]
        assert len(critical) > 0
        assert any("eval" in i.message for i in critical)

    def test_review_security_password(self, engine: CodeEngine) -> None:
        issues = engine.review('password = "secret123"')
        assert any("パスワード" in i.message for i in issues)

    def test_review_security_api_key(self, engine: CodeEngine) -> None:
        issues = engine.review('api_key = "sk-1234567890"')
        assert any("秘密情報" in i.message for i in issues)

    def test_review_sorted_by_severity(self, engine: CodeEngine) -> None:
        issues = engine.review(BAD_PYTHON)
        if len(issues) >= 2:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            for i in range(len(issues) - 1):
                current = severity_order.get(issues[i].severity, 99)
                next_val = severity_order.get(issues[i + 1].severity, 99)
                assert current <= next_val

    def test_suggest_fix_name_error(self, engine: CodeEngine) -> None:
        result = engine.suggest_fix("x = foo", "NameError: name 'foo' is not defined")
        assert "foo" in result
        assert "未定義" in result

    def test_suggest_fix_import_error(self, engine: CodeEngine) -> None:
        result = engine.suggest_fix("import foobar", "ImportError: No module named 'foobar'")
        assert "foobar" in result
        assert "pip install" in result

    def test_suggest_fix_key_error(self, engine: CodeEngine) -> None:
        result = engine.suggest_fix("d['x']", "KeyError: 'x'")
        assert "dict.get" in result

    def test_suggest_fix_unknown(self, engine: CodeEngine) -> None:
        result = engine.suggest_fix("code", "SomeWeirdError: xyz")
        assert "エラー内容" in result

    def test_generate_test_skeleton(self, engine: CodeEngine) -> None:
        skeleton = engine.generate_test_skeleton(SAMPLE_PYTHON)
        assert "import pytest" in skeleton
        assert "TestFilemanager" in skeleton or "TestFileManager" in skeleton

    def test_generate_test_skeleton_skip_private(self, engine: CodeEngine) -> None:
        code = "def _private(): pass\ndef public(): pass"
        skeleton = engine.generate_test_skeleton(code)
        assert "test_public" in skeleton
        assert "_private" not in skeleton

    def test_generate_test_non_python(self, engine: CodeEngine) -> None:
        skeleton = engine.generate_test_skeleton(JAVASCRIPT_CODE)
        assert "Python のみ" in skeleton

    def test_explain(self, engine: CodeEngine) -> None:
        explanation = engine.explain(SAMPLE_PYTHON)
        assert "python" in explanation.lower() or "Python" in explanation
        assert "FileManager" in explanation

    def test_explain_empty(self, engine: CodeEngine) -> None:
        explanation = engine.explain("")
        assert "0" in explanation

    def test_get_stats(self, engine: CodeEngine) -> None:
        stats = engine.get_stats()
        assert "pattern_memory" in stats
        assert "supported_languages" in stats
        assert "python" in stats["supported_languages"]

    def test_get_status_text(self, engine: CodeEngine) -> None:
        status = engine.get_status_text()
        assert "コードエンジン" in status


# ──────────────────────────────────────────────
# PatternMemory tests
# ──────────────────────────────────────────────

class TestPatternMemory:
    def test_record_and_stats(self) -> None:
        mem = PatternMemory()
        mem.record("fix", "python", "sig1", True)
        mem.record("fix", "python", "sig2", False)
        stats = mem.get_stats()
        assert stats["total"] == 2
        assert stats["success_rate"] == 0.5

    def test_success_rate_by_type(self) -> None:
        mem = PatternMemory()
        mem.record("fix", "python", "s1", True)
        mem.record("fix", "python", "s2", True)
        mem.record("generate", "python", "s3", False)
        assert mem.get_success_rate("fix") == 1.0
        assert mem.get_success_rate("generate") == 0.0

    def test_success_rate_by_language(self) -> None:
        mem = PatternMemory()
        mem.record("fix", "python", "s1", True)
        mem.record("fix", "rust", "s2", False)
        assert mem.get_success_rate(language="python") == 1.0
        assert mem.get_success_rate(language="rust") == 0.0

    def test_success_rate_empty(self) -> None:
        mem = PatternMemory()
        assert mem.get_success_rate() == 0.0

    def test_persistence(self, tmp_path: Path) -> None:
        storage = tmp_path / "patterns.json"
        mem1 = PatternMemory(storage_path=storage)
        mem1.record("fix", "python", "sig1", True)
        mem1.record("generate", "rust", "sig2", False)

        # 新しいインスタンスで読み込み
        mem2 = PatternMemory(storage_path=storage)
        stats = mem2.get_stats()
        assert stats["total"] == 2

    def test_max_patterns_cap(self) -> None:
        mem = PatternMemory()
        for i in range(1050):
            mem.record("fix", "python", f"sig{i}", True)
        stats = mem.get_stats()
        assert stats["total"] == 1000

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        storage = tmp_path / "bad.json"
        storage.write_text("not valid json{{{")
        mem = PatternMemory(storage_path=storage)
        assert mem.get_stats()["total"] == 0

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        storage = tmp_path / "nope.json"
        mem = PatternMemory(storage_path=storage)
        assert mem.get_stats()["total"] == 0


# ──────────────────────────────────────────────
# Basic analysis (non-Python) tests
# ──────────────────────────────────────────────

class TestBasicAnalysis:
    def test_todo_detection(self, engine: CodeEngine) -> None:
        code = "// TODO: fix this\nconst x = 1;"
        result = engine.analyze(code, language="javascript")
        assert any("TODO" in i.message for i in result.issues)

    def test_fixme_detection(self, engine: CodeEngine) -> None:
        code = "# FIXME: broken\nx = 1"
        result = engine.analyze(code, language="shell")
        assert any("FIXME" in i.message for i in result.issues)

    def test_long_file_warning(self, engine: CodeEngine) -> None:
        code = "x = 1\n" * 900
        result = engine.analyze(code, language="javascript")
        assert any("800行" in i.message for i in result.issues)

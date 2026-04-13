"""
コードエンジン (Code Engine)

アイのコード理解・生成・修正の特化エンジン。
「コードを制すればいくらでもアップデートしていける」

将来的にYAMATOの核（yamato_core）として移植される遺伝子技術。

機能:
  - コード解析（構造理解・依存関係・複雑度）
  - コード生成（仕様→実装）
  - コードレビュー（問題検知・改善提案）
  - 自動修正（エラー→修正コード）
  - テスト生成（コード→テストコード）
  - リファクタリング（目的に沿った改善）
  - パターン学習（成功/失敗パターンの蓄積）
"""
from __future__ import annotations

import ast
import json
import logging
import re
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# データ構造（frozen: 不変）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)
class CodeIssue:
    """コードの問題点"""
    severity: str           # critical / high / medium / low
    line: int               # 行番号 (0 = 不明)
    message: str            # 問題の説明
    suggestion: str = ""    # 修正案


@dataclass(frozen=True)
class CodeAnalysis:
    """コード解析結果"""
    language: str
    lines: int
    functions: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    complexity: int = 0           # 循環的複雑度（概算）
    issues: tuple[CodeIssue, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class CodePattern:
    """学習済みコードパターン"""
    pattern_type: str       # fix / generate / refactor
    language: str
    input_signature: str    # 入力の特徴（ハッシュ的）
    success: bool
    timestamp: float = 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Python AST 解析器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PythonAnalyzer:
    """Python コードの静的解析"""

    def analyze(self, code: str) -> CodeAnalysis:
        """Python コードを解析する"""
        lines = code.count("\n") + 1
        functions: list[str] = []
        classes: list[str] = []
        imports: list[str] = []
        issues: list[CodeIssue] = []
        complexity = 0

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return CodeAnalysis(
                language="python",
                lines=lines,
                issues=(CodeIssue(
                    severity="critical",
                    line=e.lineno or 0,
                    message=f"構文エラー: {e.msg}",
                    suggestion="構文を修正してください",
                ),),
                summary="構文エラーあり — パース不可",
            )

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
                # 複雑度: 分岐の数を数える
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While,
                                  ast.ExceptHandler, ast.BoolOp)):
                        complexity += 1

            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        # 品質チェック
        issues.extend(self._check_quality(code, tree))

        summary_parts = []
        if classes:
            summary_parts.append(f"クラス{len(classes)}個")
        if functions:
            summary_parts.append(f"関数{len(functions)}個")
        summary_parts.append(f"{lines}行")
        if complexity > 10:
            summary_parts.append(f"複雑度{complexity}(高)")
        elif complexity > 5:
            summary_parts.append(f"複雑度{complexity}(中)")

        return CodeAnalysis(
            language="python",
            lines=lines,
            functions=tuple(functions),
            classes=tuple(classes),
            imports=tuple(imports),
            complexity=complexity,
            issues=tuple(issues),
            summary=" / ".join(summary_parts),
        )

    def _check_quality(
        self, code: str, tree: ast.Module
    ) -> list[CodeIssue]:
        """品質問題を検出する"""
        issues: list[CodeIssue] = []

        for node in ast.walk(tree):
            # 長すぎる関数
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if hasattr(node, "end_lineno") and node.end_lineno:
                    func_lines = node.end_lineno - node.lineno
                    if func_lines > 50:
                        issues.append(CodeIssue(
                            severity="medium",
                            line=node.lineno,
                            message=f"関数 '{node.name}' が{func_lines}行 — 50行以下推奨",
                            suggestion="小さな関数に分割してください",
                        ))

                # 型アノテーションなし
                if not node.returns:
                    issues.append(CodeIssue(
                        severity="low",
                        line=node.lineno,
                        message=f"関数 '{node.name}' に戻り値の型アノテーションがありません",
                        suggestion="-> ReturnType を追加してください",
                    ))

            # bare except
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append(CodeIssue(
                        severity="high",
                        line=node.lineno,
                        message="bare except（型指定なし）は非推奨",
                        suggestion="except Exception as e: を使ってください",
                    ))

            # mutable default argument
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        issues.append(CodeIssue(
                            severity="high",
                            line=node.lineno,
                            message=f"関数 '{node.name}' にミュータブルなデフォルト引数",
                            suggestion="None をデフォルトにし、関数内で初期化してください",
                        ))

        # ファイル全体の長さ
        total_lines = code.count("\n") + 1
        if total_lines > 800:
            issues.append(CodeIssue(
                severity="medium",
                line=0,
                message=f"ファイルが{total_lines}行 — 800行以下推奨",
                suggestion="モジュールを分割してください",
            ))

        return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 汎用コード解析（言語判定 + ルーティング）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_LANGUAGE_PATTERNS: dict[str, list[str]] = {
    "python": [r"^import\s+", r"^from\s+\w+\s+import", r"def\s+\w+\(", r"class\s+\w+:"],
    "javascript": [r"const\s+\w+\s*=", r"function\s+\w+\(", r"=>\s*\{", r"require\("],
    "typescript": [r"interface\s+\w+", r":\s*(string|number|boolean)", r"import\s+.*from\s+"],
    "rust": [r"fn\s+\w+\(", r"let\s+mut\s+", r"impl\s+\w+", r"use\s+\w+::"],
    "go": [r"func\s+\w+\(", r"package\s+\w+", r"import\s+\("],
    "java": [r"public\s+class\s+", r"private\s+\w+\s+\w+", r"System\.out\."],
    "html": [r"<html", r"<div\s", r"<!DOCTYPE"],
    "css": [r"\{[\s\S]*?}", r"@media\s+", r"\.[\w-]+\s*\{"],
    "sql": [r"SELECT\s+", r"FROM\s+", r"CREATE\s+TABLE", r"INSERT\s+INTO"],
    "shell": [r"#!/bin/(ba)?sh", r"echo\s+", r"\$\{?\w+\}?"],
}


def detect_language(code: str) -> str:
    """コードの言語を推定する"""
    scores: dict[str, int] = {}
    for lang, patterns in _LANGUAGE_PATTERNS.items():
        score = 0
        for pattern in patterns:
            if re.search(pattern, code, re.MULTILINE):
                score += 1
        if score > 0:
            scores[lang] = score

    if not scores:
        return "unknown"
    return max(scores, key=scores.get)  # type: ignore[arg-type]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# パターン記憶（成功/失敗から学習）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PatternMemory:
    """コードパターンの学習記憶"""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._patterns: list[CodePattern] = []
        self._storage_path = storage_path
        if storage_path and storage_path.exists():
            self._load()

    def record(
        self,
        pattern_type: str,
        language: str,
        input_signature: str,
        success: bool,
    ) -> None:
        """パターンを記録する"""
        pattern = CodePattern(
            pattern_type=pattern_type,
            language=language,
            input_signature=input_signature,
            success=success,
            timestamp=time.time(),
        )
        self._patterns.append(pattern)

        # 最大1000件保持
        if len(self._patterns) > 1000:
            self._patterns = self._patterns[-1000:]

        if self._storage_path:
            self._save()

    def get_success_rate(
        self, pattern_type: str | None = None, language: str | None = None
    ) -> float:
        """成功率を計算する"""
        filtered = self._patterns
        if pattern_type:
            filtered = [p for p in filtered if p.pattern_type == pattern_type]
        if language:
            filtered = [p for p in filtered if p.language == language]

        if not filtered:
            return 0.0
        successes = sum(1 for p in filtered if p.success)
        return successes / len(filtered)

    def get_stats(self) -> dict[str, Any]:
        """統計を返す"""
        if not self._patterns:
            return {"total": 0, "success_rate": 0.0}

        by_type: dict[str, int] = {}
        by_lang: dict[str, int] = {}
        for p in self._patterns:
            by_type[p.pattern_type] = by_type.get(p.pattern_type, 0) + 1
            by_lang[p.language] = by_lang.get(p.language, 0) + 1

        return {
            "total": len(self._patterns),
            "success_rate": self.get_success_rate(),
            "by_type": by_type,
            "by_language": by_lang,
        }

    def _save(self) -> None:
        """ファイルに保存"""
        if not self._storage_path:
            return
        data = [
            {
                "pattern_type": p.pattern_type,
                "language": p.language,
                "input_signature": p.input_signature,
                "success": p.success,
                "timestamp": p.timestamp,
            }
            for p in self._patterns
        ]
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        """ファイルから読み込み"""
        if not self._storage_path or not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            self._patterns = [
                CodePattern(
                    pattern_type=d["pattern_type"],
                    language=d["language"],
                    input_signature=d["input_signature"],
                    success=d["success"],
                    timestamp=d.get("timestamp", 0.0),
                )
                for d in data
            ]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("パターン記憶の読み込み失敗: %s", exc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# コードエンジン本体
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CodeEngine:
    """
    コード理解・生成・修正の統合エンジン。

    アイのコード能力の中核。将来YAMATOの yamato_core に移植される。

    使い方:
      engine = CodeEngine(data_dir=Path("data"))
      analysis = engine.analyze("def hello(): print('hi')")
      review = engine.review("def f(x=[]): ...")
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        llm_fn: Any | None = None,
    ) -> None:
        """
        Args:
            data_dir: パターン記憶の保存先
            llm_fn: LLM推論関数（将来のコード生成用）
                     signature: (prompt: str) -> str
        """
        self._python_analyzer = PythonAnalyzer()
        self._llm_fn = llm_fn

        storage = data_dir / "code_patterns.json" if data_dir else None
        self._memory = PatternMemory(storage_path=storage)

        logger.info("CodeEngine 初期化完了")

    # ─── 解析 ─────────────────────────────────────────

    def analyze(self, code: str, language: str | None = None) -> CodeAnalysis:
        """
        コードを解析し、構造・品質情報を返す。

        Args:
            code: ソースコード文字列
            language: 言語指定（None で自動判定）

        Returns:
            CodeAnalysis: 解析結果
        """
        if not code.strip():
            return CodeAnalysis(
                language=language or "unknown",
                lines=0,
                summary="空のコード",
            )

        lang = language or detect_language(code)

        if lang == "python":
            return self._python_analyzer.analyze(code)

        # Python以外は基本解析のみ（将来拡張）
        return self._basic_analyze(code, lang)

    def _basic_analyze(self, code: str, language: str) -> CodeAnalysis:
        """Python以外の基本解析"""
        lines = code.count("\n") + 1
        issues: list[CodeIssue] = []

        if lines > 800:
            issues.append(CodeIssue(
                severity="medium",
                line=0,
                message=f"ファイルが{lines}行 — 800行以下推奨",
                suggestion="モジュールを分割してください",
            ))

        # TODO / FIXME / HACK 検出
        for i, line in enumerate(code.splitlines(), 1):
            for marker in ("TODO", "FIXME", "HACK", "XXX"):
                if marker in line:
                    issues.append(CodeIssue(
                        severity="low",
                        line=i,
                        message=f"{marker} コメントが残っています",
                        suggestion="対応するか削除してください",
                    ))

        return CodeAnalysis(
            language=language,
            lines=lines,
            issues=tuple(issues),
            summary=f"{language} / {lines}行",
        )

    # ─── レビュー ─────────────────────────────────────

    def review(self, code: str, language: str | None = None) -> list[CodeIssue]:
        """
        コードをレビューし、問題点のリストを返す。

        Args:
            code: レビュー対象コード
            language: 言語指定

        Returns:
            問題リスト（severity順）
        """
        analysis = self.analyze(code, language)
        issues = list(analysis.issues)

        # 追加チェック: セキュリティ
        issues.extend(self._security_check(code))

        # severity でソート（critical > high > medium > low）
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        issues.sort(key=lambda i: severity_order.get(i.severity, 99))

        return issues

    def _security_check(self, code: str) -> list[CodeIssue]:
        """セキュリティ問題を検出する"""
        issues: list[CodeIssue] = []

        security_patterns = [
            (r"eval\s*\(", "eval() の使用", "ast.literal_eval() を使ってください"),
            (r"exec\s*\(", "exec() の使用", "安全な代替手段を検討してください"),
            (r"subprocess\.\w+\(.*shell\s*=\s*True", "shell=True の使用",
             "shell=False にしてコマンドをリストで渡してください"),
            (r"os\.system\s*\(", "os.system() の使用",
             "subprocess.run() を使ってください"),
            (r"pickle\.load", "pickle.load の使用",
             "信頼できないデータには json を使ってください"),
            (r"__import__\s*\(", "__import__() の使用",
             "通常の import 文を使ってください"),
            (r"password\s*=\s*['\"]", "ハードコードされたパスワード",
             "環境変数または秘密管理を使ってください"),
            (r"(api_key|secret|token)\s*=\s*['\"]", "ハードコードされた秘密情報",
             "環境変数を使ってください"),
        ]

        for i, line in enumerate(code.splitlines(), 1):
            for pattern, message, suggestion in security_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append(CodeIssue(
                        severity="critical",
                        line=i,
                        message=f"セキュリティ: {message}",
                        suggestion=suggestion,
                    ))

        return issues

    # ─── 修正提案 ──────────────────────────────────────

    def suggest_fix(self, code: str, error_message: str) -> str:
        """
        エラーメッセージに基づいて修正方法を提案する。

        Args:
            code: エラーが発生したコード
            error_message: エラーメッセージ

        Returns:
            修正提案テキスト
        """
        suggestions: list[str] = []

        # よくあるPythonエラーのパターンマッチ
        error_fixes = [
            (r"IndentationError", "インデントを確認してください。スペース4つで統一してください。"),
            (r"NameError: name '(\w+)' is not defined",
             "変数 '{0}' が未定義です。スペルミスか、importの不足を確認してください。"),
            (r"TypeError: .+ takes (\d+) .+ (\d+) .+ given",
             "引数の数が一致しません。関数定義と呼び出しを確認してください。"),
            (r"ImportError: No module named '(\w+)'",
             "モジュール '{0}' がインストールされていません。pip install {0} を実行してください。"),
            (r"KeyError: '?(\w+)'?",
             "キー '{0}' が辞書に存在しません。dict.get('{0}', default) を使ってください。"),
            (r"AttributeError: .+ has no attribute '(\w+)'",
             "属性 '{0}' が存在しません。クラス定義またはスペルを確認してください。"),
            (r"FileNotFoundError",
             "ファイルが見つかりません。パスとファイル名を確認してください。"),
            (r"ZeroDivisionError",
             "ゼロ除算です。除算前にゼロチェックを追加してください。"),
            (r"RecursionError",
             "再帰が深すぎます。終了条件を確認してください。"),
            (r"SyntaxError: invalid syntax",
             "構文エラーです。括弧の対応、コロン、クォートを確認してください。"),
        ]

        for pattern, fix_template in error_fixes:
            match = re.search(pattern, error_message)
            if match:
                # テンプレート内の {0}, {1} をマッチグループで置換
                fix = fix_template
                for i, group in enumerate(match.groups()):
                    fix = fix.replace(f"{{{i}}}", group)
                suggestions.append(fix)

        if not suggestions:
            suggestions.append(
                f"エラー内容: {error_message}\n"
                "コードを確認し、エラー箇所を特定してください。"
            )

        # 記録
        self._memory.record(
            pattern_type="fix",
            language=detect_language(code),
            input_signature=error_message[:100],
            success=True,
        )

        return "\n".join(f"💡 {s}" for s in suggestions)

    # ─── テスト生成 ────────────────────────────────────

    def generate_test_skeleton(
        self, code: str, language: str | None = None
    ) -> str:
        """
        コードに対するテストの骨格を生成する（Python限定）。

        Args:
            code: テスト対象コード
            language: 言語指定（None で自動判定）

        Returns:
            pytest テストコードの骨格
        """
        lang = language or detect_language(code)
        if lang != "python":
            return "# 現在 Python のみ対応しています"

        analysis = self.analyze(code, language="python")

        test_lines = [
            '"""自動生成テスト骨格"""',
            "import pytest",
            "",
        ]

        # 関数ごとにテスト骨格を生成
        for func_name in analysis.functions:
            if func_name.startswith("_"):
                continue  # プライベート関数はスキップ

            test_lines.extend([
                "",
                f"class Test{func_name.title().replace('_', '')}:",
                f'    """Tests for {func_name}"""',
                "",
                f"    def test_{func_name}_basic(self) -> None:",
                f'        """基本動作テスト"""',
                f"        # TODO: {func_name} の基本テストを書く",
                f"        pass",
                "",
                f"    def test_{func_name}_edge_case(self) -> None:",
                f'        """エッジケーステスト"""',
                f"        # TODO: エッジケースのテストを書く",
                f"        pass",
                "",
            ])

        # クラスごとにテスト骨格を生成
        for class_name in analysis.classes:
            test_lines.extend([
                "",
                f"class Test{class_name}:",
                f'    """Tests for {class_name}"""',
                "",
                f"    @pytest.fixture()",
                f"    def instance(self) -> {class_name}:",
                f'        """テスト用インスタンス"""',
                f"        # TODO: 適切な引数でインスタンスを生成",
                f"        pass",
                "",
                f"    def test_init(self, instance) -> None:",
                f'        """初期化テスト"""',
                f"        assert instance is not None",
                "",
            ])

        self._memory.record(
            pattern_type="generate",
            language="python",
            input_signature=f"test_skeleton:{len(analysis.functions)}funcs",
            success=True,
        )

        return "\n".join(test_lines)

    # ─── コード説明 ────────────────────────────────────

    def explain(self, code: str) -> str:
        """
        コードを解析して日本語で説明する。

        Args:
            code: 説明対象コード

        Returns:
            日本語の説明テキスト
        """
        analysis = self.analyze(code)
        parts: list[str] = []

        parts.append(f"📝 言語: {analysis.language}")
        parts.append(f"📏 行数: {analysis.lines}")

        if analysis.classes:
            parts.append(f"🏗️ クラス: {', '.join(analysis.classes)}")
        if analysis.functions:
            parts.append(f"🔧 関数: {', '.join(analysis.functions)}")
        if analysis.imports:
            parts.append(f"📦 依存: {', '.join(analysis.imports[:10])}")
        if analysis.complexity > 0:
            level = "高" if analysis.complexity > 10 else "中" if analysis.complexity > 5 else "低"
            parts.append(f"🧩 複雑度: {analysis.complexity} ({level})")

        if analysis.issues:
            critical = sum(1 for i in analysis.issues if i.severity == "critical")
            high = sum(1 for i in analysis.issues if i.severity == "high")
            medium = sum(1 for i in analysis.issues if i.severity == "medium")
            low = sum(1 for i in analysis.issues if i.severity == "low")
            issue_parts = []
            if critical:
                issue_parts.append(f"🔴 重大{critical}件")
            if high:
                issue_parts.append(f"🟠 高{high}件")
            if medium:
                issue_parts.append(f"🟡 中{medium}件")
            if low:
                issue_parts.append(f"🔵 低{low}件")
            parts.append(f"⚠️ 問題: {' '.join(issue_parts)}")

        return "\n".join(parts)

    # ─── 実行 ──────────────────────────────────────────

    def run(self, code: str) -> str:
        """
        コードをサンドボックスで実行し、結果を返す。

        Returns:
            フォーマット済みの実行結果テキスト
        """
        from core.code_sandbox import CodeSandbox
        sandbox = CodeSandbox(timeout_sec=10)
        return sandbox.execute_and_format(code)

    def run_and_fix(self, code: str, max_retries: int = 2) -> str:
        """
        コードを実行し、エラーなら修正提案→再試行するループ。

        「コードを制する」の核心：生成→実行→修正→再実行

        Args:
            code: 実行するPythonコード
            max_retries: 最大リトライ回数

        Returns:
            実行結果のフォーマット済みテキスト
        """
        from core.code_sandbox import CodeSandbox, ExecutionResult
        sandbox = CodeSandbox(timeout_sec=10)

        current_code = code
        lines: list[str] = []

        for attempt in range(max_retries + 1):
            result = sandbox.execute(current_code)

            if result.success:
                label = "初回" if attempt == 0 else f"修正{attempt}回目"
                lines.append(f"✅ {label}で実行成功 ({result.elapsed_ms}ms)")
                if result.stdout.strip():
                    lines.append(f"📤 出力:\n{result.stdout.strip()}")
                self._memory.record(
                    "run", "python",
                    f"success_attempt_{attempt}", True,
                )
                return "\n".join(lines)

            # 失敗
            lines.append(f"❌ 試行{attempt + 1}: 失敗")

            # タイムアウトはリトライ不可（先に判定）
            if result.timed_out:
                lines.append("⏱️ タイムアウト — リトライ不可")
                if result.stderr.strip():
                    lines.append(f"📛 {result.stderr.strip()[:200]}")
                break

            if result.stderr.strip():
                error_msg = result.stderr.strip()
                lines.append(f"📛 {error_msg[:200]}")

                # リトライ上限でなければ修正提案
                if attempt < max_retries:
                    fix = self.suggest_fix(current_code, error_msg)
                    lines.append(f"🔧 修正提案: {fix[:150]}")

        self._memory.record(
            "run", "python",
            f"failed_after_{max_retries + 1}", False,
        )
        lines.append(f"\n⚠️ {max_retries + 1}回試行しましたが成功しませんでした")
        return "\n".join(lines)

    # ─── 統計 ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """エンジンの統計を返す"""
        return {
            "pattern_memory": self._memory.get_stats(),
            "supported_languages": list(_LANGUAGE_PATTERNS.keys()),
            "analyzers": ["python (AST)", "generic (pattern)"],
        }

    def get_status_text(self) -> str:
        """ステータステキスト"""
        stats = self._memory.get_stats()
        total = stats["total"]
        rate = stats["success_rate"]
        return (
            f"💻 コードエンジン: "
            f"パターン{total}件 / 成功率{rate:.0%}"
        )

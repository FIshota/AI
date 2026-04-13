"""
Phase 1 統合テスト

1-A: CodeEngine接続（コマンドパターン + ハンドラ）
1-B: 自意志アクション拡充
1-C: Web検索機能
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────
# 1-A: コードエンジン コマンドパターンテスト
# ──────────────────────────────────────────────

class TestCodeCommandPatterns:
    """コードエンジンのコマンドパターンが正しくマッチするか"""

    def _import_patterns(self):
        from core.ai_chan import (
            CMD_CODE_ANALYZE,
            CMD_CODE_REVIEW,
            CMD_CODE_FIX,
            CMD_CODE_TEST,
            CMD_CODE_EXPLAIN,
            CMD_CODE_FILE,
        )
        return {
            "analyze": CMD_CODE_ANALYZE,
            "review": CMD_CODE_REVIEW,
            "fix": CMD_CODE_FIX,
            "test": CMD_CODE_TEST,
            "explain": CMD_CODE_EXPLAIN,
            "file": CMD_CODE_FILE,
        }

    def test_code_analyze_patterns(self) -> None:
        p = self._import_patterns()["analyze"]
        assert p.match("コード見て: def hello(): pass")
        assert p.match("コードを解析: x = 1")
        assert p.match("このコードチェック: import os")
        assert p.match("コード確認: print('hi')")

    def test_code_review_patterns(self) -> None:
        p = self._import_patterns()["review"]
        assert p.match("コードレビュー: def f(): pass")
        assert p.match("このコードをレビューして: x = eval(y)")

    def test_code_fix_patterns(self) -> None:
        p = self._import_patterns()["fix"]
        assert p.match("エラー直して: NameError: name 'x' is not defined")
        assert p.match("このバグ修正して: TypeError")

    def test_code_test_patterns(self) -> None:
        p = self._import_patterns()["test"]
        assert p.match("コードテスト書いて: class Foo: pass")
        assert p.match("コードのテスト生成: def bar(): return 1")

    def test_code_explain_patterns(self) -> None:
        p = self._import_patterns()["explain"]
        assert p.match("コード説明して: for i in range(10): print(i)")
        assert p.match("このコードを解説: lambda x: x**2")

    def test_code_file_patterns(self) -> None:
        p = self._import_patterns()["file"]
        assert p.match("ファイルを見て: core/llm.py")
        assert p.match("ファイル解析: test.py")

    def test_no_false_match(self) -> None:
        """通常の会話がコードコマンドにマッチしないこと"""
        patterns = self._import_patterns()
        normal_inputs = [
            "今日の天気は？",
            "こんにちは",
            "お父さんについて教えて",
        ]
        for text in normal_inputs:
            for name, p in patterns.items():
                assert not p.match(text), f"'{text}' が {name} にマッチしてしまった"


# ──────────────────────────────────────────────
# 1-A: コードエンジン ハンドラテスト（モック使用）
# ──────────────────────────────────────────────

class TestCodeHandlers:
    """ai_chanのコードハンドラが正しく動作するか"""

    @pytest.fixture()
    def mock_ai(self):
        """最小限のai_chanモック"""
        ai = MagicMock()
        from core.code_engine import CodeEngine
        ai.code_engine = CodeEngine()
        ai.base_dir = Path(__file__).parent.parent
        # 実際のメソッドをバインド
        from core.ai_chan import AiChan
        ai._handle_code_analyze = AiChan._handle_code_analyze.__get__(ai)
        ai._handle_code_review = AiChan._handle_code_review.__get__(ai)
        ai._handle_code_fix = AiChan._handle_code_fix.__get__(ai)
        ai._handle_code_test = AiChan._handle_code_test.__get__(ai)
        ai._handle_code_explain = AiChan._handle_code_explain.__get__(ai)
        ai._handle_code_file = AiChan._handle_code_file.__get__(ai)
        return ai

    def test_analyze_python(self, mock_ai) -> None:
        result = mock_ai._handle_code_analyze("def hello():\n    print('hi')")
        assert "コード解析結果" in result
        assert "python" in result.lower()
        assert "hello" in result

    def test_analyze_empty(self, mock_ai) -> None:
        result = mock_ai._handle_code_analyze("")
        assert "空のコード" in result or "解析結果" in result

    def test_review_finds_issues(self, mock_ai) -> None:
        bad_code = "def f(x=[]):\n    result = eval(x[0])\n    return result"
        result = mock_ai._handle_code_review(bad_code)
        assert "レビュー結果" in result
        assert "🔴" in result  # critical issue (eval)

    def test_review_clean_code(self, mock_ai) -> None:
        result = mock_ai._handle_code_review("x = 1")
        # 短いコードなら少なくとも実行できること
        assert isinstance(result, str)

    def test_fix_name_error(self, mock_ai) -> None:
        result = mock_ai._handle_code_fix("NameError: name 'foo' is not defined")
        assert "foo" in result

    def test_fix_with_code_separator(self, mock_ai) -> None:
        result = mock_ai._handle_code_fix("x = foo---NameError: name 'foo' is not defined")
        assert "foo" in result

    def test_test_generation(self, mock_ai) -> None:
        code = "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b"
        result = mock_ai._handle_code_test(code)
        assert "テスト骨格" in result or "pytest" in result

    def test_explain(self, mock_ai) -> None:
        result = mock_ai._handle_code_explain("import os\nfor f in os.listdir('.'): print(f)")
        assert "python" in result.lower() or "言語" in result

    def test_file_nonexistent(self, mock_ai) -> None:
        result = mock_ai._handle_code_file("nonexistent_file_xyz.py")
        assert "見つからない" in result

    def test_file_real(self, mock_ai) -> None:
        # 自分自身のテストファイルを解析
        result = mock_ai._handle_code_file("tests/test_phase1_integration.py")
        assert "解析結果" in result
        assert "python" in result.lower()

    def test_file_outside_project(self, mock_ai) -> None:
        result = mock_ai._handle_code_file("/etc/passwd")
        assert "プロジェクト外" in result or "セキュリティ" in result

    def test_no_code_engine(self) -> None:
        """code_engineが無い場合のエラーハンドリング"""
        ai = MagicMock()
        ai.code_engine = None
        from core.ai_chan import AiChan
        ai._handle_code_analyze = AiChan._handle_code_analyze.__get__(ai)
        result = ai._handle_code_analyze("some code")
        assert "初期化されていない" in result


# ──────────────────────────────────────────────
# 1-B: 自意志アクション拡充テスト
# ──────────────────────────────────────────────

class TestWillActionsExpanded:
    """拡充された自意志アクションが登録されるか"""

    def test_will_actions_registered(self) -> None:
        """_register_will_actions で新しいアクションが登録されること"""
        from core.self_will import SelfWillEngine
        sw = SelfWillEngine(data_dir=None)

        # 登録前
        old_count = len(sw.executor._actions)

        # モックのaiオブジェクトを作ってアクション登録
        ai = MagicMock()
        ai.self_will = sw
        ai.base_dir = Path(__file__).parent.parent
        ai.auto_learner = MagicMock()
        ai.memory_compressor = MagicMock()
        ai.memory_compressor.compress_old_memories.return_value = 3
        ai.memory = MagicMock()
        ai.memory.get_recent.return_value = [1, 2, 3]
        ai.self_correction = MagicMock()
        ai.self_correction.get_health_report.return_value = {"active_symptoms": []}
        ai.self_correction.force_check.return_value = []
        ai.bio_nervous = MagicMock()
        ai.bio_nervous.get_stats.return_value = {"bypass_rate": 0.7}
        ai.bio_nervous.immune = MagicMock()
        ai.bio_nervous.immune.health_check.return_value = {"status": "ok"}
        ai.code_engine = MagicMock()
        ai.code_engine.get_status_text.return_value = "💻 テスト"
        ai.code_engine.review.return_value = []
        ai.self_dev = MagicMock()

        from core.ai_chan import AiChan
        ai._register_will_actions = AiChan._register_will_actions.__get__(ai)
        ai._register_will_actions()

        # 新しいアクションが追加されたことを確認
        handlers = sw.executor._actions
        assert "review_code" in handlers
        assert "organize_memory" in handlers
        assert "check_health" in handlers
        assert "learn_topic" in handlers
        assert "self_improve" in handlers
        assert "play" in handlers

    def test_organize_memory_action(self) -> None:
        """organize_memory アクションが動作すること"""
        from core.self_will import SelfWillEngine, Desire
        sw = SelfWillEngine(data_dir=None)

        ai = MagicMock()
        ai.self_will = sw
        ai.base_dir = Path(__file__).parent.parent
        ai.auto_learner = MagicMock()
        ai.memory_compressor = MagicMock()
        ai.memory_compressor.compress_old_memories.return_value = 5
        ai.memory = MagicMock()
        ai.memory.get_recent.return_value = list(range(42))
        ai.self_correction = MagicMock()
        ai.self_correction.get_health_report.return_value = {"active_symptoms": []}
        ai.self_correction.force_check.return_value = []
        ai.bio_nervous = MagicMock()
        ai.bio_nervous.get_stats.return_value = {"bypass_rate": 0.8}
        ai.bio_nervous.immune = MagicMock()
        ai.bio_nervous.immune.health_check.return_value = {"status": "ok"}
        ai.code_engine = MagicMock()
        ai.code_engine.get_status_text.return_value = "💻 テスト"
        ai.code_engine.review.return_value = []
        ai.self_dev = MagicMock()

        from core.ai_chan import AiChan
        ai._register_will_actions = AiChan._register_will_actions.__get__(ai)
        ai._register_will_actions()

        # アクション実行
        desire = Desire(
            desire_type="maintenance",
            intensity=0.8,
            description="記憶整理テスト",
            trigger="test",
            action_key="organize_memory",
            params={},
        )
        result = sw.executor.execute(desire)
        assert result["ok"]
        assert "圧縮" in result["result"]
        assert "記憶数" in result["result"]

    def test_check_health_action(self) -> None:
        """check_health アクションが動作すること"""
        from core.self_will import SelfWillEngine, Desire
        sw = SelfWillEngine(data_dir=None)

        ai = MagicMock()
        ai.self_will = sw
        ai.base_dir = Path(__file__).parent.parent
        ai.auto_learner = MagicMock()
        ai.memory_compressor = MagicMock()
        ai.memory_compressor.compress_old_memories.return_value = 0
        ai.memory = MagicMock()
        ai.memory.get_recent.return_value = []
        ai.self_correction = MagicMock()
        ai.self_correction.get_health_report.return_value = {"active_symptoms": []}
        ai.self_correction.force_check.return_value = []
        ai.bio_nervous = MagicMock()
        ai.bio_nervous.get_stats.return_value = {"bypass_rate": 0.75}
        ai.bio_nervous.immune = MagicMock()
        ai.bio_nervous.immune.health_check.return_value = {"status": "ok"}
        ai.code_engine = MagicMock()
        ai.code_engine.get_status_text.return_value = "💻 パターン10件"
        ai.code_engine.review.return_value = []
        ai.self_dev = MagicMock()

        from core.ai_chan import AiChan
        ai._register_will_actions = AiChan._register_will_actions.__get__(ai)
        ai._register_will_actions()

        desire = Desire(
            desire_type="maintenance",
            intensity=0.5,
            description="ヘルスチェックテスト",
            trigger="test",
            action_key="check_health",
            params={},
        )
        result = sw.executor.execute(desire)
        assert result["ok"]
        assert "良好" in result["result"]
        assert "バイパス率" in result["result"]


# ──────────────────────────────────────────────
# 1-C: Web検索機能テスト
# ──────────────────────────────────────────────

class TestWebSearchPatterns:
    """Web検索コマンドパターンのマッチテスト"""

    def _import_patterns(self):
        from core.ai_chan import CMD_WEB_SEARCH, CMD_WEB_FETCH
        return CMD_WEB_SEARCH, CMD_WEB_FETCH

    def test_search_patterns(self) -> None:
        search, _ = self._import_patterns()
        m = search.match("Python asyncioについて調べて")
        assert m
        assert m.group(1).strip() == "Python asyncio"

        m = search.match("最新のAIニュースを検索して")
        assert m

        m = search.match("量子コンピュータ調べて")
        assert m

    def test_fetch_patterns(self) -> None:
        _, fetch = self._import_patterns()
        m = fetch.match("URL読んで: https://example.com")
        assert m
        assert m.group(4).strip() == "https://example.com"

        m = fetch.match("サイトを取得: https://news.ycombinator.com")
        assert m

    def test_no_false_search_match(self) -> None:
        search, _ = self._import_patterns()
        assert not search.match("こんにちは")
        assert not search.match("コードを見て: def f(): pass")


class TestWebFetcherFunctions:
    """web_fetcher の新関数テスト"""

    def test_web_search_import(self) -> None:
        """web_search関数がインポートできること"""
        from core.web_fetcher import web_search
        assert callable(web_search)

    def test_web_fetch_text_import(self) -> None:
        """web_fetch_text関数がインポートできること"""
        from core.web_fetcher import web_fetch_text
        assert callable(web_fetch_text)

    def test_web_search_with_mock(self) -> None:
        """モックでweb_searchの戻り値を検証"""
        sample_html = '''
        <a rel="nofollow" href="https://example.com/1" class="result-link">Result One</a>
        <td class="result-snippet">This is snippet one</td>
        <a rel="nofollow" href="https://example.com/2" class="result-link">Result Two</a>
        <td class="result-snippet">This is snippet two</td>
        '''
        import urllib.request
        import core.web_fetcher as wf
        wf._CACHE.clear()

        with patch.object(urllib.request, "urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = sample_html.encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            results = wf.web_search("test query")
            assert results is not None
            assert len(results) == 2
            assert results[0]["title"] == "Result One"
            assert results[0]["url"] == "https://example.com/1"
            assert "snippet one" in results[0]["snippet"]

    def test_web_fetch_text_with_mock(self) -> None:
        """モックでweb_fetch_textの戻り値を検証"""
        sample_html = '''
        <html><head><title>Test</title>
        <script>var x = 1;</script>
        <style>body{color:red}</style>
        </head><body>
        <p>Hello World</p>
        <p>This is content</p>
        </body></html>
        '''
        import urllib.request
        import core.web_fetcher as wf
        wf._CACHE.clear()

        with patch.object(urllib.request, "urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = sample_html.encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            text = wf.web_fetch_text("https://example.com")
            assert text is not None
            assert "Hello World" in text
            assert "This is content" in text
            # script/style は除去されている
            assert "var x = 1" not in text
            assert "color:red" not in text


class TestWebHandlers:
    """Web検索ハンドラのテスト"""

    @pytest.fixture()
    def mock_ai(self):
        ai = MagicMock()
        ai.llm = MagicMock()
        ai.llm.is_loaded.return_value = False
        from core.ai_chan import AiChan
        ai._handle_web_search = AiChan._handle_web_search.__get__(ai)
        ai._handle_web_fetch = AiChan._handle_web_fetch.__get__(ai)
        return ai

    def test_search_success(self, mock_ai) -> None:
        with patch("core.web_fetcher.web_search") as mock_search:
            mock_search.return_value = [
                {"title": "Result 1", "url": "https://a.com", "snippet": "Snippet 1"},
                {"title": "Result 2", "url": "https://b.com", "snippet": "Snippet 2"},
            ]
            result = mock_ai._handle_web_search("テスト検索")
            assert "検索結果" in result
            assert "Result 1" in result
            assert "https://a.com" in result

    def test_search_no_results(self, mock_ai) -> None:
        with patch("core.web_fetcher.web_search") as mock_search:
            mock_search.return_value = None
            result = mock_ai._handle_web_search("存在しないもの")
            assert "見つからなかった" in result

    def test_fetch_invalid_url(self, mock_ai) -> None:
        result = mock_ai._handle_web_fetch("not-a-url")
        assert "http" in result

    def test_fetch_success(self, mock_ai) -> None:
        with patch("core.web_fetcher.web_fetch_text") as mock_fetch:
            mock_fetch.return_value = "This is the page content about AI"
            result = mock_ai._handle_web_fetch("https://example.com")
            assert "example.com" in result
            assert "page content" in result

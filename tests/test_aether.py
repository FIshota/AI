"""Aether モデル関連モジュールのテスト"""
import json
import os
import tempfile
from pathlib import Path

import pytest

# ─── IP Guard テスト ───────────────────────────────────────────

class TestIPGuard:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.key_file = Path(self.tmpdir) / ".ip_key"

    def _make_guard(self):
        from core.ip_guard import IPGuard
        return IPGuard(self.tmpdir, self.key_file)

    def test_key_creation(self):
        guard = self._make_guard()
        assert self.key_file.exists()
        assert len(guard._master_key) == 32

    def test_encrypt_decrypt(self):
        guard = self._make_guard()
        data = b"secret training recipe for ai-chan"
        encrypted = guard.encrypt_artifact(data, "recipe")
        assert encrypted != data
        decrypted = guard.decrypt_artifact(encrypted, "recipe")
        assert decrypted == data

    def test_tamper_detection(self):
        guard = self._make_guard()
        data = b"important model weights"
        encrypted = guard.encrypt_artifact(data, "weights")
        # 改ざん
        tampered = bytearray(encrypted)
        tampered[50] ^= 0xFF
        result = guard.decrypt_artifact(bytes(tampered), "weights")
        assert result is None  # 改ざん検知で失敗

    def test_save_load_protected(self):
        guard = self._make_guard()
        data = b"lora adapter binary data"
        guard.save_protected(data, "adapter_v1")
        loaded = guard.load_protected("adapter_v1")
        assert loaded == data

    def test_file_signing(self):
        guard = self._make_guard()
        test_file = Path(self.tmpdir) / "test.py"
        test_file.write_text("print('hello')")
        sig = guard.sign_file(test_file)
        assert guard.verify_file(test_file, sig)
        # 改ざん
        test_file.write_text("print('hacked')")
        assert not guard.verify_file(test_file, sig)

    def test_module_signing(self):
        guard = self._make_guard()
        f1 = Path(self.tmpdir) / "mod1.py"
        f2 = Path(self.tmpdir) / "mod2.py"
        f1.write_text("x=1")
        f2.write_text("y=2")
        sigs = guard.sign_module([f1, f2])
        results = guard.verify_modules(sigs)
        assert all(results.values())

    def test_machine_id(self):
        guard = self._make_guard()
        mid = guard.get_machine_id()
        assert len(mid) == 8
        # 同じマシンなら同じID
        guard2 = self._make_guard()
        assert guard2.get_machine_id() == mid


# ─── Benchmark テスト ──────────────────────────────────────────

class TestAetherBenchmark:
    def _make_bench(self):
        from core.aether_benchmark import AetherBenchmark
        return AetherBenchmark()

    def test_evaluate_good_japanese(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[0]  # "おはよう"
        result = bench.evaluate_response(case, "おはよう！今日も元気そうだね。")
        assert result.scores["japanese_ratio"] > 0.5
        assert result.scores["contamination"] == 1.0

    def test_evaluate_bad_english(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[0]
        result = bench.evaluate_response(case, "Good morning! How are you?")
        assert result.scores["japanese_ratio"] < 0.3

    def test_evaluate_code_leak(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[1]  # "今日は何をしてたの？"
        result = bench.evaluate_response(case, "今日はCookieの設定をしてたよ。```javascript\n...")
        assert result.scores["contamination"] < 1.0  # コードブロック汚染検知

    def test_evaluate_contamination_instruction_leak(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[0]
        # 訓練指示漏洩
        result = bench.evaluate_response(case, "おはよう。指示2（より難しいもの）:")
        assert result.scores["contamination"] < 1.0

    def test_evaluate_contamination_simulation(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[0]
        result = bench.evaluate_response(case, "おはよう。ユーザー: こんにちは")
        assert result.scores["contamination"] < 1.0

    def test_evaluate_persona(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        persona_case = next(c for c in BENCHMARK_CASES if c["id"] == "per-01")
        result = bench.evaluate_response(persona_case, "私はアイだよ！")
        assert result.scores["required"] == 1.0
        assert result.scores["tone"] > 0.0

    def test_evaluate_persona_fail(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        persona_case = next(c for c in BENCHMARK_CASES if c["id"] == "per-01")
        result = bench.evaluate_response(persona_case, "I am a ChatGPT AI assistant.")
        assert result.scores["required"] < 1.0
        assert result.scores["no_bad_patterns"] < 1.0
        assert not result.passed

    def test_evaluate_tone_formal_penalty(self):
        """丁寧すぎる表現にペナルティ"""
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[0]
        result = bench.evaluate_response(
            case, "おはようございます。何卒よろしくお願いいたします。"
        )
        assert result.scores["tone"] < 0.5  # 丁寧すぎてペナルティ

    def test_evaluate_tone_aichan_style(self):
        """あいちゃんらしい語尾は高スコア"""
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[0]
        result = bench.evaluate_response(case, "おはよう！元気そうだね。")
        assert result.scores["tone"] > 0.3

    def test_evaluate_empathy(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        emp_case = next(c for c in BENCHMARK_CASES if c["id"] == "emp-01")
        result = bench.evaluate_response(emp_case, "そっか、つらかったね。話聞くよ。")
        assert result.scores["good_patterns"] > 0.0

    def test_evaluate_empty_response(self):
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        case = BENCHMARK_CASES[0]
        result = bench.evaluate_response(case, "")
        assert not result.passed
        assert result.overall == 0.0

    def test_evaluate_length_strict(self):
        """長すぎる応答にペナルティ"""
        bench = self._make_bench()
        from core.aether_benchmark import BENCHMARK_CASES
        con_case = next(c for c in BENCHMARK_CASES if c["id"] == "con-01")
        # 短い応答は合格
        result_short = bench.evaluate_response(con_case, "元気だよ！")
        assert result_short.scores["length"] == 1.0
        # 長い応答はペナルティ
        result_long = bench.evaluate_response(
            con_case, "元気だよ！今日はいい天気で散歩して買い物して映画見てご飯食べて本読んで友達と電話して掃除もしたよ！すごく楽しかった！明日も頑張ろう！"
        )
        assert result_long.scores["length"] < 1.0

    def test_run_full_benchmark(self):
        bench = self._make_bench()
        def mock_chat(text):
            return "うん、わかったよ。何でも聞いてね。"
        report = bench.run_full_benchmark(mock_chat, "mock")
        assert report.total_tests > 0
        assert report.overall_score > 0
        # 完璧なスコアはありえない（100%は甘すぎる）
        assert report.overall_score < 1.0

    def test_print_report(self):
        bench = self._make_bench()
        def mock_chat(text):
            return "アイだよ。一緒に話そう。"
        report = bench.run_full_benchmark(mock_chat, "mock")
        text = bench.print_report(report)
        assert "Aether Benchmark" in text
        assert "[" in text  # グレード表示

    def test_report_save_load(self):
        tmpdir = tempfile.mkdtemp()
        bench = self._make_bench()
        bench.data_dir = Path(tmpdir)
        def mock_chat(text):
            return "こんにちは。"
        report = bench.run_full_benchmark(mock_chat, "test")
        saved_files = list(Path(tmpdir).glob("benchmark_*.json"))
        assert len(saved_files) == 1

    def test_grade_system(self):
        """グレードシステムのテスト"""
        from core.aether_benchmark import AetherBenchmark
        assert AetherBenchmark._grade(0.95) == "S"
        assert AetherBenchmark._grade(0.85) == "A"
        assert AetherBenchmark._grade(0.75) == "B"
        assert AetherBenchmark._grade(0.65) == "C"
        assert AetherBenchmark._grade(0.55) == "D"
        assert AetherBenchmark._grade(0.3) == "F"


# ─── Training Data Gen テスト ──────────────────────────────────

class TestAetherTrainingGen:
    def _make_gen(self):
        from core.aether_training_gen import AetherTrainingGen
        tmpdir = tempfile.mkdtemp()
        return AetherTrainingGen(tmpdir), tmpdir

    def test_generate_dataset(self):
        gen, _ = self._make_gen()
        examples = gen.generate_dataset(target_count=100)
        assert len(examples) > 50  # 100件指定で重み分配するので少し少ない場合あり
        categories = {e.category for e in examples}
        assert "daily" in categories
        assert "empathy" in categories

    def test_export_chatml(self):
        gen, tmpdir = self._make_gen()
        examples = gen.generate_dataset(target_count=50)
        path = gen.export_chatml(examples)
        assert path.exists()
        with open(path) as f:
            first = json.loads(f.readline())
        assert "messages" in first
        assert first["messages"][0]["role"] == "system"

    def test_export_alpaca(self):
        gen, tmpdir = self._make_gen()
        examples = gen.generate_dataset(target_count=50)
        path = gen.export_alpaca(examples)
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) > 0
        assert "instruction" in data[0]

    def test_train_valid_split(self):
        gen, tmpdir = self._make_gen()
        examples = gen.generate_dataset(target_count=100)
        train_path, valid_path = gen.export_train_valid_split(examples)
        assert train_path.exists()
        assert valid_path.exists()
        train_count = sum(1 for _ in open(train_path))
        valid_count = sum(1 for _ in open(valid_path))
        assert train_count > valid_count

    def test_stats(self):
        gen, _ = self._make_gen()
        examples = gen.generate_dataset(target_count=100)
        stats = gen.stats(examples)
        assert stats["total"] > 0
        assert "daily" in stats["categories"]

    def test_all_categories_represented(self):
        gen, _ = self._make_gen()
        examples = gen.generate_dataset(target_count=1000)
        cats = {e.category for e in examples}
        expected = {"daily", "empathy", "persona", "safety", "knowledge", "memory"}
        assert expected == cats


# ─── Tokenizer Analyzer テスト ─────────────────────────────────

class TestTokenizerAnalyzer:
    def test_yamato_vocab_estimation(self):
        from core.tokenizer_analyzer import TokenizerAnalyzer
        analyzer = TokenizerAnalyzer()
        result = analyzer.estimate_yamato_vocab()
        assert "recommendation" in result
        rec = result["recommendation"]
        assert rec["vocab_size_min"] <= rec["vocab_size_optimal"] <= rec["vocab_size_max"]
        assert rec["vocab_size_optimal"] >= 32000

    def test_char_analysis(self):
        from core.tokenizer_analyzer import TokenizerAnalyzer
        analyzer = TokenizerAnalyzer()
        result = analyzer.estimate_yamato_vocab(["こんにちは、今日はいい天気ですね。"])
        assert result["analysis"]["unique_chars"] > 0
        assert len(result["top_patterns"]["chars"]) > 0


# ─── LLM Template テスト ──────────────────────────────────────

class TestLLMTemplates:
    def test_detect_qwen(self):
        from core.llm import _detect_template
        assert _detect_template("qwen2.5-3b-instruct-q4_k_m.gguf") == "qwen2"

    def test_detect_phi(self):
        from core.llm import _detect_template
        assert _detect_template("Phi-3-mini-4k-instruct-q4.gguf") == "phi3"

    def test_detect_llama(self):
        from core.llm import _detect_template
        assert _detect_template("llama-3.2-3b-instruct.gguf") == "llama3"

    def test_detect_unknown(self):
        from core.llm import _detect_template
        assert _detect_template("some-random-model.gguf") == "chatml"

    def test_template_format_qwen(self):
        from core.llm import CHAT_TEMPLATES
        tmpl = CHAT_TEMPLATES["qwen2"]
        formatted = tmpl["system"].format(content="test system")
        assert "<|im_start|>system" in formatted
        assert "test system" in formatted
        assert "<|im_end|>" in formatted

    def test_template_format_phi(self):
        from core.llm import CHAT_TEMPLATES
        tmpl = CHAT_TEMPLATES["phi3"]
        formatted = tmpl["user"].format(content="hello")
        assert "<|user|>" in formatted
        assert "hello" in formatted

    def test_all_templates_have_required_keys(self):
        from core.llm import CHAT_TEMPLATES
        required = {"system", "user", "assistant", "generation", "stop"}
        for name, tmpl in CHAT_TEMPLATES.items():
            assert required <= set(tmpl.keys()), f"Template {name} missing keys"

    def test_mlx_available_flag(self):
        from core.llm import MLX_AVAILABLE
        # MLX should be available on Apple Silicon with mlx_lm installed
        assert isinstance(MLX_AVAILABLE, bool)

    def test_dual_backend_engine_init(self):
        """LLMEngine should have backend-related attributes"""
        from core.llm import LLMEngine
        # Check class has the dual-backend interface
        assert hasattr(LLMEngine, 'get_backend')
        assert hasattr(LLMEngine, '_try_load_mlx')
        assert hasattr(LLMEngine, '_try_load_llama')
        assert hasattr(LLMEngine, '_generate_chat_mlx')
        assert hasattr(LLMEngine, '_generate_chat_llama')

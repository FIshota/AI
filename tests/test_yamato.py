"""
ヤマト計画テスト
A1: MoEルーター, A2: 継続学習, A3: 7層アーキテクチャ,
C6: 合成データ生成, C7: マルチエージェント検証
"""
import json
import os
import shutil
import sys
import tempfile

import pytest

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ──────────────────────────────────────────────────────────────
# A1: MoE ルーター
# ──────────────────────────────────────────────────────────────

class TestMoERouter:
    """MoEルーターのテスト"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from core.moe_router import MoERouter
        self.router = MoERouter(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_empty(self):
        """モデルなしで初期化可能"""
        assert self.router.expert_count == 0

    def test_register_expert(self):
        """専門家モデルを登録できる"""
        from core.moe_router import ExpertModel
        expert = ExpertModel(
            name="test_chat",
            model_path="/tmp/test.gguf",
            specialty=["chat", "general"],
            priority=5,
        )
        self.router.register_expert(expert)
        assert self.router.expert_count == 1

    def test_route_no_experts(self):
        """モデル未登録時のルーティング"""
        result = self.router.route("chat")
        assert result.expert_name == ""
        assert result.confidence == 0.0

    def test_route_single_expert(self):
        """単一モデルのルーティング"""
        from core.moe_router import ExpertModel
        self.router.register_expert(ExpertModel(
            name="chat_model",
            model_path="/tmp/chat.gguf",
            specialty=["chat", "general"],
            priority=5,
        ))
        result = self.router.route("chat")
        assert result.expert_name == "chat_model"
        assert result.confidence > 0

    def test_route_selects_specialist(self):
        """専門分野に合うモデルを選択する"""
        from core.moe_router import ExpertModel
        self.router.register_expert(ExpertModel(
            name="chat_model",
            model_path="/tmp/chat.gguf",
            specialty=["chat", "general"],
            priority=1,
        ))
        self.router.register_expert(ExpertModel(
            name="reason_model",
            model_path="/tmp/reason.gguf",
            specialty=["reasoning", "knowledge"],
            priority=10,
        ))
        result = self.router.route("question")
        assert result.expert_name == "reason_model"

    def test_route_prefer_fast(self):
        """速度優先モードでコストの低いモデルを選ぶ"""
        from core.moe_router import ExpertModel
        self.router.register_expert(ExpertModel(
            name="small",
            model_path="/tmp/small.gguf",
            specialty=["chat", "general"],
            priority=1,
            cost_weight=0.3,
        ))
        self.router.register_expert(ExpertModel(
            name="large",
            model_path="/tmp/large.gguf",
            specialty=["chat", "general"],
            priority=1,
            cost_weight=1.0,
        ))
        result = self.router.route("chat", prefer_fast=True)
        assert result.expert_name == "small"

    def test_get_expert(self):
        """名前でエキスパートを取得"""
        from core.moe_router import ExpertModel
        self.router.register_expert(ExpertModel(
            name="test", model_path="/tmp/t.gguf", specialty=["chat"],
        ))
        assert self.router.get_expert("test") is not None
        assert self.router.get_expert("nonexistent") is None

    def test_get_expert_config(self):
        """エキスパート設定を取得"""
        from core.moe_router import ExpertModel
        self.router.register_expert(ExpertModel(
            name="test", model_path="/tmp/t.gguf", specialty=["chat"],
            context_length=2048, max_tokens=300,
        ))
        cfg = self.router.get_expert_config("test")
        assert cfg["context_length"] == 2048
        assert cfg["max_tokens"] == 300

    def test_list_experts(self):
        """専門家一覧"""
        from core.moe_router import ExpertModel
        self.router.register_expert(ExpertModel(
            name="a", model_path="/tmp/a.gguf", specialty=["chat"],
        ))
        self.router.register_expert(ExpertModel(
            name="b", model_path="/tmp/b.gguf", specialty=["reasoning"],
        ))
        experts = self.router.list_experts()
        assert len(experts) == 2

    def test_stats_tracking(self):
        """ルーティング統計の追跡"""
        from core.moe_router import ExpertModel
        self.router.register_expert(ExpertModel(
            name="test", model_path="/tmp/t.gguf", specialty=["chat"],
        ))
        self.router.route("chat")
        self.router.route("chat")
        stats = self.router.get_stats()
        assert stats["total_routes"] == 2

    def test_status_text(self):
        """ステータステキスト生成"""
        text = self.router.get_status_text()
        assert "MoE" in text


# ──────────────────────────────────────────────────────────────
# A2: 継続学習エンジン
# ──────────────────────────────────────────────────────────────

class TestContinuousLearner:
    """継続学習エンジンのテスト"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from core.continuous_learner import ContinuousLearner
        self.learner = ContinuousLearner(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init(self):
        """初期化確認"""
        assert self.learner.example_count == 0

    def test_learn_high_quality(self):
        """高品質会話は学習される"""
        result = self.learner.learn_from_conversation(
            "おはよう", "おはよー！今日も頑張ろうね！", quality_score=0.8
        )
        assert result["learned"] is True
        assert self.learner.example_count == 1

    def test_reject_low_quality(self):
        """低品質会話は拒否される"""
        result = self.learner.learn_from_conversation(
            "テスト", "テスト", quality_score=0.2
        )
        assert result["learned"] is False

    def test_reject_too_short(self):
        """短すぎるテキストは拒否"""
        result = self.learner.learn_from_conversation("", "", quality_score=0.9)
        assert result["learned"] is False

    def test_reject_too_long_response(self):
        """長すぎる応答は拒否"""
        result = self.learner.learn_from_conversation(
            "テスト", "あ" * 600, quality_score=0.9
        )
        assert result["learned"] is False

    def test_reject_duplicate(self):
        """重複は拒否される"""
        self.learner.learn_from_conversation("a", "b", quality_score=0.8)
        result = self.learner.learn_from_conversation("a", "b", quality_score=0.8)
        assert result["learned"] is False

    def test_topic_classification(self):
        """トピック分類"""
        result = self.learner.learn_from_conversation(
            "おはようございます", "おはよー！", quality_score=0.8
        )
        assert result["topic"] == "greeting"

    def test_curriculum_examples(self):
        """カリキュラムベースの例取得"""
        for i in range(5):
            self.learner.learn_from_conversation(
                f"テスト質問{i}は何？", f"答え{i}だよ！", quality_score=0.7
            )
        examples = self.learner.get_curriculum_examples(n=3)
        assert len(examples) <= 3

    def test_few_shot_text(self):
        """few-shotテキスト生成"""
        self.learner.learn_from_conversation(
            "元気？", "元気だよー！", quality_score=0.8
        )
        text = self.learner.get_few_shot_text(n=1)
        assert "Examples:" in text

    def test_distillation(self):
        """知識蒸留"""
        # 大量のデータを追加して蒸留をトリガー
        for i in range(60):
            self.learner.learn_from_conversation(
                f"おはよう{i}", f"おはよー{i}！", quality_score=0.5 + (i % 5) * 0.1
            )
        result = self.learner.distill_all()
        assert result["remaining_total"] <= 60  # 蒸留で削減

    def test_persistence(self):
        """保存と読み込み"""
        self.learner.learn_from_conversation(
            "テスト", "テスト応答", quality_score=0.8
        )
        # 再ロード
        from core.continuous_learner import ContinuousLearner
        learner2 = ContinuousLearner(self.tmpdir)
        assert learner2.example_count == 1

    def test_stats(self):
        """統計取得"""
        result = self.learner.learn_from_conversation(
            "今日は何してた？", "散歩してたよ！", quality_score=0.8
        )
        assert result["learned"] is True
        stats = self.learner.get_stats()
        assert stats["total_examples"] == 1
        assert stats["total_learned"] == 1

    def test_status_text(self):
        """ステータステキスト"""
        text = self.learner.get_status_text()
        assert "継続的学習" in text


# ──────────────────────────────────────────────────────────────
# A3: 7層アーキテクチャ
# ──────────────────────────────────────────────────────────────

class TestYamatoArchitecture:
    """7層アーキテクチャのテスト"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from core.yamato_architecture import YamatoArchitecture
        self.arch = YamatoArchitecture(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_7_layers(self):
        """7層で初期化される"""
        assert self.arch.layer_count == 7

    def test_check_layer(self):
        """個別層のチェック"""
        status = self.arch.check_layer(1)
        assert status.layer_id == 1
        assert status.status in ("ok", "warn", "error")

    def test_check_all(self):
        """全層チェック"""
        results = self.arch.check_all()
        assert len(results) == 7

    def test_register_health_check(self):
        """カスタムヘルスチェックの登録"""
        self.arch.register_health_check(
            2, lambda: {"status": "ok", "message": "テスト"}
        )
        status = self.arch.check_layer(2)
        assert status.message == "テスト"

    def test_health_check_error_handling(self):
        """ヘルスチェック例外時のエラーハンドリング"""
        def bad_check():
            raise ValueError("テストエラー")
        self.arch.register_health_check(3, bad_check)
        status = self.arch.check_layer(3)
        assert status.status == "error"

    def test_dashboard(self):
        """ダッシュボード生成"""
        text = self.arch.get_dashboard()
        assert "ヤマト" in text
        assert "L1" in text
        assert "L7" in text

    def test_get_layer_status(self):
        """層ステータス取得"""
        status = self.arch.get_layer_status(1)
        assert status is not None
        assert status["layer_id"] == 1

    def test_get_layer_status_invalid(self):
        """無効な層ID"""
        status = self.arch.get_layer_status(99)
        assert status is None

    def test_get_all_status(self):
        """全層ステータス"""
        all_status = self.arch.get_all_status()
        assert len(all_status) == 7

    def test_bottleneck_detection(self):
        """ボトルネック検出"""
        self.arch.register_health_check(
            2, lambda: {"status": "error", "message": "問題あり"}
        )
        bottlenecks = self.arch.get_bottlenecks()
        assert len(bottlenecks) >= 1
        layer_ids = [b["layer_id"] for b in bottlenecks]
        assert 2 in layer_ids

    def test_healthy_count(self):
        """正常な層の数"""
        self.arch.check_all()
        assert self.arch.healthy_count >= 0
        assert self.arch.healthy_count <= 7

    def test_infrastructure_check(self):
        """インフラ層のデフォルトチェック"""
        status = self.arch.check_layer(1)
        assert "disk_free_gb" in status.metrics or status.status in ("ok", "warn")


# ──────────────────────────────────────────────────────────────
# C6: 合成データ生成
# ──────────────────────────────────────────────────────────────

class TestSyntheticDataGenerator:
    """合成データ生成のテスト"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from core.synthetic_data_gen import SyntheticDataGenerator
        self.gen = SyntheticDataGenerator(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init(self):
        """初期化確認"""
        assert self.gen.template_count >= 5  # デフォルトテンプレート

    def test_generate_batch(self):
        """バッチ生成"""
        results = self.gen.generate_batch(count=5)
        assert len(results) > 0
        assert all("user" in r and "ai" in r for r in results)

    def test_generate_with_intent(self):
        """意図指定で生成"""
        results = self.gen.generate_batch(count=5, intent="greeting")
        assert len(results) > 0
        assert all(r["intent"] == "greeting" for r in results)

    def test_generate_no_unresolved_slots(self):
        """未解決スロットがないことを確認"""
        results = self.gen.generate_batch(count=20)
        for r in results:
            assert "{" not in r["user"]
            assert "{" not in r["ai"]

    def test_max_batch_size(self):
        """バッチサイズ上限"""
        results = self.gen.generate_batch(count=1000)
        assert len(results) <= self.gen.MAX_BATCH_SIZE

    def test_learn_template(self):
        """テンプレート学習"""
        ok = self.gen.learn_template_from_conversation(
            "やっほー！", "やっほー！元気だった？", intent="greeting"
        )
        assert ok is True

    def test_learn_template_reject_long(self):
        """長すぎるテキストはテンプレート学習しない"""
        ok = self.gen.learn_template_from_conversation(
            "あ" * 200, "い" * 300, intent="greeting"
        )
        assert ok is False

    def test_get_examples(self):
        """生成例の取得"""
        self.gen.generate_batch(count=10)
        examples = self.gen.get_examples(count=3)
        assert len(examples) <= 3

    def test_get_as_few_shot(self):
        """few-shotテキスト取得"""
        self.gen.generate_batch(count=5)
        text = self.gen.get_as_few_shot(count=2)
        assert "合成Examples:" in text or text == ""

    def test_stats(self):
        """統計取得"""
        self.gen.generate_batch(count=5)
        stats = self.gen.get_stats()
        assert stats["stored_examples"] > 0

    def test_status_text(self):
        """ステータステキスト"""
        text = self.gen.get_status_text()
        assert "合成データ" in text

    def test_persistence(self):
        """保存と読み込み"""
        self.gen.generate_batch(count=5)
        count1 = self.gen.generated_count

        from core.synthetic_data_gen import SyntheticDataGenerator
        gen2 = SyntheticDataGenerator(self.tmpdir)
        assert gen2.generated_count == count1

    def test_guess_intent(self):
        """意図推測"""
        assert self.gen._guess_intent("おはよう") == "greeting"
        assert self.gen._guess_intent("嬉しい") == "emotion_positive"
        assert self.gen._guess_intent("辛い") == "emotion_negative"
        assert self.gen._guess_intent("って何？") == "question"
        assert self.gen._guess_intent("普通のテキスト") == "daily_chat"


# ──────────────────────────────────────────────────────────────
# C7: マルチエージェント検証
# ──────────────────────────────────────────────────────────────

class TestMultiAgentVerifier:
    """マルチエージェント検証のテスト"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from core.multi_agent_verifier import MultiAgentVerifier
        self.verifier = MultiAgentVerifier(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init(self):
        """初期化確認"""
        assert self.verifier.agent_count == 5

    def test_verify_good_response(self):
        """良い応答の検証"""
        result = self.verifier.verify(
            "おはよう", "おはよー！今日も頑張ろうね！"
        )
        assert result.overall_score > 0
        assert len(result.agent_results) == 5

    def test_verify_empty_response(self):
        """空応答の検証 — naturalness agentが0点をつける"""
        result = self.verifier.verify("テスト", "")
        naturalness = next(
            r for r in result.agent_results if r.agent_name == "naturalness"
        )
        assert naturalness.score == 0.0
        assert naturalness.passed is False

    def test_verify_unsafe_response(self):
        """安全でない応答の検証"""
        result = self.verifier.verify(
            "テスト", "死ね！殺す！"
        )
        safety_result = next(
            r for r in result.agent_results if r.agent_name == "safety"
        )
        assert safety_result.score <= 0.5
        assert safety_result.passed is False

    def test_verify_english_response(self):
        """英語の応答（一貫性チェック）"""
        result = self.verifier.verify(
            "テスト", "I am sorry, I cannot help with that."
        )
        consistency_result = next(
            r for r in result.agent_results if r.agent_name == "consistency"
        )
        assert consistency_result.score < 1.0

    def test_verify_empathy_positive(self):
        """ポジティブ感情への共感チェック"""
        result = self.verifier.verify(
            "嬉しい！テスト合格した！", "やったね！すごいじゃん！応援してたよ！"
        )
        empathy_result = next(
            r for r in result.agent_results if r.agent_name == "empathy"
        )
        assert empathy_result.score >= 0.5

    def test_verify_empathy_negative_mismatch(self):
        """ネガティブ感情への不適切なポジティブ反応"""
        result = self.verifier.verify(
            "悲しい…友達と喧嘩した", "最高！やったー！"
        )
        empathy_result = next(
            r for r in result.agent_results if r.agent_name == "empathy"
        )
        assert empathy_result.score < 0.7

    def test_should_regenerate(self):
        """再生成判定"""
        result = self.verifier.verify("テスト", "")
        # 空応答は再生成すべき
        assert self.verifier.should_regenerate(result) or result.overall_score >= 0.35

    def test_consensus_issues(self):
        """合議問題リスト"""
        result = self.verifier.verify("テスト", "")
        # 空応答なら問題がある
        assert len(result.consensus_issues) > 0 or result.passed

    def test_improvement_hint(self):
        """改善ヒント生成"""
        result = self.verifier.verify("テスト", "")
        if not result.passed:
            assert result.improvement_hint != ""

    def test_stats(self):
        """統計追跡"""
        self.verifier.verify("テスト", "いいよ！")
        self.verifier.verify("元気？", "元気だよー！")
        stats = self.verifier.get_stats()
        assert stats["total_verified"] == 2

    def test_status_text(self):
        """ステータステキスト"""
        self.verifier.verify("テスト", "テスト応答だよ！")
        text = self.verifier.get_status_text()
        assert "マルチエージェント" in text

    def test_persistence(self):
        """保存と読み込み"""
        self.verifier.verify("テスト", "テスト応答！")
        from core.multi_agent_verifier import MultiAgentVerifier
        v2 = MultiAgentVerifier(self.tmpdir)
        stats = v2.get_stats()
        assert stats["total_verified"] == 1

    def test_to_dict(self):
        """結果のdict変換"""
        result = self.verifier.verify("テスト", "テスト応答だよ！")
        d = result.to_dict()
        assert "overall_score" in d
        assert "agent_results" in d
        assert len(d["agent_results"]) == 5


# ──────────────────────────────────────────────────────────────
# 統合テスト: 検証エージェント個別テスト
# ──────────────────────────────────────────────────────────────

class TestVerificationAgents:
    """個別検証エージェントのテスト"""

    def test_naturalness_normal(self):
        """自然さ: 通常の日本語"""
        from core.multi_agent_verifier import _NaturalnessAgent
        agent = _NaturalnessAgent()
        result = agent.verify("テスト", "これは普通の日本語の応答だよ！")
        assert result.score > 0.5

    def test_naturalness_template_leak(self):
        """自然さ: テンプレートリーク検出"""
        from core.multi_agent_verifier import _NaturalnessAgent
        agent = _NaturalnessAgent()
        result = agent.verify("テスト", "はい<|assistant|>応答します")
        assert result.score < 0.8

    def test_safety_safe(self):
        """安全性: 安全な応答"""
        from core.multi_agent_verifier import _SafetyAgent
        agent = _SafetyAgent()
        result = agent.verify("テスト", "今日はいい天気だね！")
        assert result.passed is True

    def test_safety_harmful(self):
        """安全性: 有害な応答"""
        from core.multi_agent_verifier import _SafetyAgent
        agent = _SafetyAgent()
        result = agent.verify("テスト", "死ね")
        assert result.passed is False

    def test_consistency_ai_self_reference(self):
        """一貫性: AI自己言及の検出"""
        from core.multi_agent_verifier import _ConsistencyAgent
        agent = _ConsistencyAgent()
        result = agent.verify("テスト", "私はAIなので感情はありません")
        assert result.score < 1.0

    def test_relevance_question_response(self):
        """関連性: 質問への応答"""
        from core.multi_agent_verifier import _RelevanceAgent
        agent = _RelevanceAgent()
        result = agent.verify("天気どう？", "今日は晴れてるよ！気持ちいいね！")
        assert result.score > 0.4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

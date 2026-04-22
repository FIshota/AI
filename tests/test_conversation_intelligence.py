"""
会話知能 / 知識グラフ / 性格進化 / 応答品質評価のテスト.

(元: test_sprint_k.py — 2026-04-21 M7 でドメイン命名へリネーム)

対象:
    会話知能 (K1) — IntentClassification / ResponseStrategy / ContextChain /
                    ConversationDepthManager / JapaneseQualityFilter /
                    ConversationIntelligence
    知識グラフ (K2) — KnowledgeGraph
    性格進化 (K3) — PersonalityEvolution
    応答品質評価 (K4) — ResponseEvaluator
    コマンドパターン — TestSprintKCommandPatterns (将来改名候補)
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ─── K1: 会話知能テスト ──────────────────────────────────────

class TestIntentClassification:
    """意図分類テスト"""

    def test_greeting_morning(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("おはよう！")
        assert intent.intent_type == "greeting"

    def test_greeting_evening(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("おつかれさま〜")
        assert intent.intent_type == "greeting"

    def test_emotion_positive(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("今日すごく嬉しいことがあった！")
        assert intent.intent_type == "emotion"
        assert intent.sub_type == "positive"

    def test_emotion_negative(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("悲しくて泣きそう…")
        assert intent.intent_type == "emotion"
        assert intent.sub_type == "negative"

    def test_question_factual(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("AIって何？教えて")
        assert intent.intent_type == "question"

    def test_consultation(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("ちょっと相談があるんだけど…")
        assert intent.intent_type == "consultation"

    def test_request(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("これ覚えてほしいんだけど")
        assert intent.intent_type == "request"

    def test_chat_bored(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("暇だなー")
        assert intent.intent_type == "chat"
        assert intent.sub_type == "bored"

    def test_question_mark_fallback(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("明日の天気は？")
        assert intent.intent_type == "question"

    def test_default_chat(self):
        from core.conversation_intelligence import classify_intent
        intent = classify_intent("ふーん")
        assert intent.intent_type == "chat"


class TestResponseStrategy:
    """応答戦略テスト"""

    def test_strategy_for_greeting(self):
        from core.conversation_intelligence import classify_intent, get_response_strategy
        intent = classify_intent("おはよう！")
        strategy = get_response_strategy(intent)
        assert strategy.tone != ""
        assert strategy.approach != ""

    def test_strategy_for_emotion(self):
        from core.conversation_intelligence import classify_intent, get_response_strategy
        intent = classify_intent("悲しくて辛い")
        strategy = get_response_strategy(intent)
        assert "寄り添" in strategy.tone or "優しく" in strategy.tone

    def test_strategy_for_question(self):
        from core.conversation_intelligence import classify_intent, get_response_strategy
        intent = classify_intent("これって何？教えて")
        strategy = get_response_strategy(intent)
        assert strategy.max_sentences >= 1


class TestContextChain:
    """文脈チェーンテスト"""

    def test_empty_history(self):
        from core.conversation_intelligence import ContextChain
        hint = ContextChain.build_chain_hint([])
        assert hint == ""

    def test_with_history(self):
        from core.conversation_intelligence import ContextChain
        history = [
            {"role": "user", "content": "仕事で疲れた"},
            {"role": "assistant", "content": "お疲れさま！"},
            {"role": "user", "content": "今日は残業だったんだ"},
            {"role": "assistant", "content": "大変だったね"},
        ]
        hint = ContextChain.build_chain_hint(history)
        assert isinstance(hint, str)

    def test_reference_detection(self):
        from core.conversation_intelligence import ContextChain
        history = [
            {"role": "user", "content": "昨日映画を見た"},
            {"role": "assistant", "content": "何の映画？"},
            {"role": "user", "content": "それが面白くてさ"},
        ]
        hint = ContextChain.build_chain_hint(history)
        assert "指示語" in hint or "前の話題" in hint


class TestConversationDepthManager:
    """会話深度管理テスト"""

    def test_depth_starts_at_zero(self):
        from core.conversation_intelligence import ConversationDepthManager
        mgr = ConversationDepthManager()
        assert mgr.depth == 0

    def test_depth_increases_on_emotion(self):
        from core.conversation_intelligence import (
            ConversationDepthManager, ConversationIntent
        )
        mgr = ConversationDepthManager()
        intent = ConversationIntent("emotion", 0.8, "negative")
        mgr.update_depth(intent, 5)
        assert mgr.depth >= 2

    def test_depth_increases_on_consultation(self):
        from core.conversation_intelligence import (
            ConversationDepthManager, ConversationIntent
        )
        mgr = ConversationDepthManager()
        intent = ConversationIntent("consultation", 0.8, "worry")
        mgr.update_depth(intent, 5)
        assert mgr.depth >= 3


class TestJapaneseQualityFilter:
    """日本語品質フィルタテスト"""

    def test_auto_fix_desu_masu(self):
        from core.conversation_intelligence import JapaneseQualityFilter
        fixed = JapaneseQualityFilter.auto_fix("それは素敵です。ありがとうございます。")
        assert "だよ" in fixed or "あるよ" in fixed
        # ございます→あるよ が先にマッチする
        assert "ございます" not in fixed

    def test_detect_english(self):
        from core.conversation_intelligence import JapaneseQualityFilter
        issues = JapaneseQualityFilter.check_quality("This is a test. Hello world.")
        assert "英語が混入" in issues

    def test_clean_text_passes(self):
        from core.conversation_intelligence import JapaneseQualityFilter
        issues = JapaneseQualityFilter.check_quality("今日はいい天気だね！散歩しない？")
        assert len(issues) == 0


class TestConversationIntelligence:
    """統合テスト"""

    def test_analyze_input(self):
        from core.conversation_intelligence import ConversationIntelligence
        ci = ConversationIntelligence()
        result = ci.analyze_input("おはよう！今日も頑張ろう！", [], 1)
        assert "intent" in result
        assert "strategy" in result
        assert "instruction_text" in result

    def test_post_process(self):
        from core.conversation_intelligence import ConversationIntelligence
        ci = ConversationIntelligence()
        result = ci.post_process("それは素晴らしいです。")
        assert "だよ" in result


# ─── K2: 知識グラフテスト ────────────────────────────────────

class TestKnowledgeGraph:
    """知識グラフテスト"""

    def test_extract_person_relation(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        result = kg.extract_from_conversation("田中さんは私の上司だよ")
        assert result["relations_added"] >= 1

    def test_extract_preference(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        result = kg.extract_from_conversation("猫が好きなんだよね")
        assert result["relations_added"] >= 1

    def test_extract_activity(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        result = kg.extract_from_conversation("プログラミングを勉強しているんだ")
        assert result["relations_added"] >= 1

    def test_no_duplicate_relations(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        kg.extract_from_conversation("猫が好きなんだよね")
        kg.extract_from_conversation("猫が好きなんだよね")
        assert kg.relation_count == 1

    def test_search_related(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        kg.extract_from_conversation("田中さんは私の上司だよ")
        results = kg.search_related("田中")
        assert len(results) > 0

    def test_context_for_chat(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        kg.extract_from_conversation("田中さんは私の上司だよ")
        ctx = kg.get_context_for_chat("田中さんに")
        assert "田中" in ctx

    def test_persistence(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg1 = KnowledgeGraph(tmp_path)
        kg1.extract_from_conversation("猫が大好きなんだ")
        kg1._save()

        kg2 = KnowledgeGraph(tmp_path)
        assert kg2.relation_count >= 1

    def test_user_world_summary_empty(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        summary = kg.get_user_world_summary()
        assert "まだ" in summary

    def test_place_extraction(self, tmp_path):
        from core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(tmp_path)
        result = kg.extract_from_conversation("東京に住んでるよ")
        assert kg.entity_count >= 1


# ─── K3: 性格進化テスト ──────────────────────────────────────

class TestPersonalityEvolution:
    """性格進化テスト"""

    def test_initial_traits(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo = PersonalityEvolution(tmp_path)
        d = evo.traits.to_dict()
        assert 0.0 <= d["warmth"] <= 1.0
        assert 0.0 <= d["empathy"] <= 1.0

    def test_on_conversation_evolves(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo = PersonalityEvolution(tmp_path)
        initial_empathy = evo.traits.empathy
        for _ in range(20):
            evo.on_conversation("悲しいことがあったんだ…", intent_type="emotion")
        assert evo.traits.empathy > initial_empathy

    def test_relationship_grows(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo = PersonalityEvolution(tmp_path)
        initial = evo.relationship.familiarity
        for _ in range(10):
            evo.on_conversation("今日も楽しかった！", intent_type="chat")
        assert evo.relationship.familiarity > initial

    def test_relationship_level_label(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo = PersonalityEvolution(tmp_path)
        label = evo.relationship.level_label()
        assert isinstance(label, str)
        assert len(label) > 0

    def test_personality_prompt_hint(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo = PersonalityEvolution(tmp_path)
        # 十分な会話をして性格を形成
        for _ in range(50):
            evo.on_conversation("面白い話を教えて！", intent_type="question")
        hint = evo.get_personality_prompt_hint()
        assert isinstance(hint, str)

    def test_persistence(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo1 = PersonalityEvolution(tmp_path)
        for _ in range(20):
            evo1.on_conversation("テスト", intent_type="chat")
        evo1.force_save()

        evo2 = PersonalityEvolution(tmp_path)
        assert evo2.relationship.total_conversations == 20

    def test_growth_summary(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo = PersonalityEvolution(tmp_path)
        summary = evo.get_growth_summary()
        assert "成長" in summary

    def test_tendency_tracker(self, tmp_path):
        from core.personality_evolution import PersonalityEvolution
        evo = PersonalityEvolution(tmp_path)
        for _ in range(5):
            evo.on_conversation("質問だよ", intent_type="question", hour=14)
        topics = evo.tendency.get_dominant_topics(1)
        assert len(topics) > 0
        assert topics[0][0] == "question"


# ─── K4: 応答品質評価テスト ──────────────────────────────────

class TestResponseEvaluator:
    """応答品質自己評価テスト"""

    def test_evaluate_good_response(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator
        ev = ResponseEvaluator(tmp_path)
        score = ev.evaluate("こんにちは", "やっほー！元気だよ。今日はどうだった？")
        assert score.overall > 0.3
        assert score.naturalness > 0.5

    def test_evaluate_empty_response(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator
        ev = ResponseEvaluator(tmp_path)
        score = ev.evaluate("こんにちは", "")
        assert score.naturalness == 0.0

    def test_evaluate_english_response(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator
        ev = ResponseEvaluator(tmp_path)
        score = ev.evaluate("こんにちは", "Hello, how are you? I am fine thank you.")
        assert score.naturalness < 0.7  # 英語混入で減点

    def test_evaluate_formal_response(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator
        ev = ResponseEvaluator(tmp_path)
        score = ev.evaluate("こんにちは", "こんにちは。お元気でしょうか。よろしくお願いいたします。")
        assert score.naturalness <= 0.8  # 敬語混入で減点

    def test_diversity_decreases_on_repeat(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator
        ev = ResponseEvaluator(tmp_path)
        same_response = "うん、そうだね！"
        scores = []
        for _ in range(5):
            score = ev.evaluate("なんか話して", same_response)
            scores.append(score.diversity)
        # 繰り返すと多様性スコアが下がる
        assert scores[-1] < scores[0]

    def test_should_regenerate(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator, QualityScore
        ev = ResponseEvaluator(tmp_path)
        bad_score = QualityScore(naturalness=0.1, relevance=0.1, diversity=0.1, consistency=0.1, overall=0.1)
        assert ev.should_regenerate(bad_score) is True
        good_score = QualityScore(naturalness=0.8, relevance=0.8, diversity=0.8, consistency=0.8, overall=0.8)
        assert ev.should_regenerate(good_score) is False

    def test_improvement_hint(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator, QualityScore
        ev = ResponseEvaluator(tmp_path)
        bad_score = QualityScore(naturalness=0.3, relevance=0.3, diversity=0.3, consistency=0.3, overall=0.3)
        hint = ev.get_improvement_hint(bad_score)
        assert len(hint) > 0

    def test_quality_summary(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator
        ev = ResponseEvaluator(tmp_path)
        ev.evaluate("テスト", "テスト応答だよ！")
        summary = ev.get_quality_summary()
        assert "品質" in summary

    def test_persistence(self, tmp_path):
        from core.response_evaluator import ResponseEvaluator
        ev1 = ResponseEvaluator(tmp_path)
        for i in range(25):
            ev1.evaluate(f"質問{i}", f"応答{i}だよ！")

        ev2 = ResponseEvaluator(tmp_path)
        assert len(ev2._recent_scores) > 0


# ─── Sprint K コマンドパターンテスト ─────────────────────────

class TestSprintKCommandPatterns:
    """Sprint K コマンドの正規表現マッチテスト"""

    def test_knowledge_patterns(self):
        from core.cmd_handlers import CMD_KNOWLEDGE
        assert CMD_KNOWLEDGE.match("知識グラフ")
        assert CMD_KNOWLEDGE.match("知ってることを見せて")
        assert CMD_KNOWLEDGE.match("ナレッジ一覧")

    def test_relationship_patterns(self):
        from core.cmd_handlers import CMD_RELATIONSHIP
        assert CMD_RELATIONSHIP.match("関係性を見せて")
        assert CMD_RELATIONSHIP.match("親密度確認")
        assert CMD_RELATIONSHIP.match("仲良し度どのくらい")

    def test_growth_patterns(self):
        from core.cmd_handlers import CMD_GROWTH
        assert CMD_GROWTH.match("成長レポート")
        assert CMD_GROWTH.match("アイの成長")
        assert CMD_GROWTH.match("進化状況")

    def test_quality_patterns(self):
        from core.cmd_handlers import CMD_QUALITY
        assert CMD_QUALITY.match("応答品質レポート")
        assert CMD_QUALITY.match("会話品質スコア")
        assert CMD_QUALITY.match("品質確認")

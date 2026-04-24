# CODEMAP: core/

> Auto-generated 2026-04-24 — Cat 5 codemap (C5)

Total modules: **155**

Core engine modules: emotion, memory, voice, safety, tenants, search.

| File | Summary | Public API (excerpt) | Lines |
|------|---------|----------------------|-------|
| `__init__.py` | アイちゃん コアパッケージ | — | 9 |
| `a11y_announcer.py` | Screen reader announcer for state changes in the desktop pet. | class _Sink, class FileSink, class _MacVoiceOverSink, class _LinuxSpeakSink, class A11yAnnouncer | 184 |
| `action_cycle.py` | 自律行動サイクル (Autonomous Action Cycle) | class CyclePhase, class Goal, class CycleRecord, class GoalGenerator, class ActionCycleEngine | 380 |
| `aether_benchmark.py` | B5: 自動評価ベンチマーク - Aether Quality Benchmark | class BenchmarkResult, class BenchmarkReport, class AetherBenchmark | 709 |
| `aether_training_gen.py` | D9: あいちゃん専用訓練データ生成パイプライン | class TrainingExample, class AetherTrainingGen | 314 |
| `ai_chan.py` | アイ メインクラス | class AiChan | 3761 |
| `akashic_core.py` | — | class AkashicResponse, class AkashicCore | 974 |
| `alerts.py` | Local-only monitoring alerts for ai-chan. | class Alert, make_alert_id(), class AlertSink, class MacOsNotificationSink, class FileSink | 197 |
| `anniversary.py` | 記念日・誕生日管理システム | class AnniversaryManager | 278 |
| `anniversary_ical_bridge.py` | Bridge between `core.anniversary` records and `core.ical_export`. | anniversary_to_ical_event() | 95 |
| `anniversary_importance.py` | 記念日の自動重要度推定。 | class AnniversaryFeatures, class ImportanceBucket, estimate_importance(), bucket_of(), score_and_bucket() | 181 |
| `anomaly_detector.py` | 異常検知 (Anomaly Detector) | class AnomalyAlert, class AnomalyDetector | 260 |
| `audio_fx.py` | 音声エフェクト・変換ユーティリティ | class AudioChunk, pitch_shift(), time_stretch(), apply_volume(), apply_breathiness() | 223 |
| `audit_chain.py` | Tamper-evident hash chain for security audit logs. | class ChainViolation, append_entry(), verify_chain() | 197 |
| `audit_log.py` | 監査ログ (Audit Log) | class AuditLog | 166 |
| `auto_learner.py` | 自動学習エンジン | class AutoLearner | 506 |
| `autonomous_actions.py` | 自律行動アクション (Autonomous Actions) | class GreetingEngine, class IdleLearner, class ProactiveStarter, class DiaryEnricher, class AnomalyEscalator | 389 |
| `autonomous_engine.py` | Autonomous Engine — アイの自律生命維持エンジン（階層型スケジューラ） | class Job, class JobResult, class AutonomousEngine, build_health_check() | 393 |
| `backup_rotator.py` | バックアップローテーター (Backup Rotator) | class BackupRotator | 220 |
| `battery_monitor.py` | バッテリー監視エンジン（機能⑥） | get_battery_info(), get_battery_hint(), class BatteryMonitor | 94 |
| `bgm_suggester.py` | BGM 提案エンジン（Sprint 4-C） | class BGMSuggestion, class BGMSuggester | 146 |
| `bio_nervous_system.py` | 生物神経系アーキテクチャ (Bio-Nervous System Architecture) | class ReflexRule, class ReflexLayer, class MusclePattern, class MuscleMemoryLayer, class AutonomicTask | 1096 |
| `calendar_reader.py` | カレンダー連携エンジン（機能④） | get_upcoming_events(), build_calendar_hint(), format_events_for_chat() | 110 |
| `clipboard_assistant.py` | クリップボードアシスタント（Sprint 3-A） | class ClipboardAssistant | 150 |
| `clipboard_image.py` | クリップボード画像キャプチャ (Clipboard Image) | class ClipboardImageCapture | 169 |
| `clipboard_watcher.py` | クリップボード監視システム（macOS専用） | contains_pii(), class ClipboardWatcher | 161 |
| `cmd_handlers.py` | コマンドハンドラ | class CommandHandler | 1364 |
| `code_engine.py` | コードエンジン (Code Engine) | class CodeIssue, class CodeAnalysis, class CodePattern, class PythonAnalyzer, detect_language() | 921 |
| `code_reviewer.py` | CodeReviewer — コードレビュー & 修正 | class ReviewResult, class CodeReviewer | 185 |
| `code_sandbox.py` | コードサンドボックス (Code Sandbox) | class ExecutionResult, class CodeSandbox | 264 |
| `competitor_analyzer.py` | 競合調査レポートエンジン（Sprint 4-F） | class CompetitorReport, class CompetitorAnalyzer | 227 |
| `config_model.py` | アプリケーション設定モデル | class MLXConfig, class LLMConfig, class MemoryConfig, class SecurityConfig, class UIConfig | 302 |
| `config_watcher.py` | 設定ファイルのホットリロード＋自動バックアップ | class ConfigWatcher | 125 |
| `consent.py` | consent — ai-chan 利用同意（consent string）管理。 | class ConsentRecord, class ConsentError, class UnknownConsentItem, class ConsentStore, load_consent_items() | 422 |
| `continuous_learner.py` | 継続的学習エンジン (Continuous Learning Engine) | class LearningExample, class TopicCluster, class ContinuousLearner | 491 |
| `conversation_intelligence.py` | 会話知能エンジン (Conversation Intelligence) | class ConversationIntent, classify_intent(), class ResponseStrategy, get_response_strategy(), class ContextChain | 701 |
| `conversation_search.py` | Conversation history search (Sprint 5.7 UX). | class SearchQuery, class SearchHit, to_bigrams(), class ConversationSearchIndex | 458 |
| `correction_learning.py` | ユーザー訂正学習モジュール | class CorrectionEntry, class CorrectionLearning | 291 |
| `data_exporter.py` | 会話・記憶データのエクスポート | class DataExporter | 199 |
| `defense_dashboard.py` | 防御ダッシュボード (Defense Dashboard) | class DefenseDashboard | 485 |
| `deps.py` | AiChanDeps — 依存注入コンテナ (H1, 2026-04-21)。 | class AiChanDeps | 62 |
| `diary.py` | アイの日記システム | class DiaryManager | 161 |
| `doc_agent.py` | DocAgent — 書類作成エージェント（提案書・企画書・報告書など） | class DocResult, class DocAgent | 253 |
| `document_exporter.py` | ドキュメントエクスポーター (Document Exporter) | class DocumentSection, class DocumentContent, class ContentParser, class WordExporter, class PowerPointExporter | 512 |
| `emotion.py` | 感情モデル | class EmotionState, class EmotionEngine, class MoodAnalyzer | 225 |
| `emotion_drift.py` | 感情状態長期ドリフト可視化「心の健康診断」の集計ロジック。 | class EmotionAggregate, class EmotionDriftAnalyzer, ascii_sparkline(), sparkline_for_aggregates() | 277 |
| `emotion_history.py` | 感情履歴管理 | class EmotionHistory | 160 |
| `emotional_tts.py` | 感情豊かな音声合成エンジン | class EmotionalTTSConfig, class EmotionalTTSEngine, class NeuralTTSBackend, create_tts_engine() | 722 |
| `errors.py` | アイちゃん例外階層 | class AiChanError, class LLMError, class MemoryError_, class SecurityError_, class ConfigError | 77 |
| `event_bus.py` | イベント駆動コンポーネント間通信 | class EventBus | 143 |
| `expression_engine.py` | 表情エンジン (Expression Engine) | classify_emotion(), class ExpressionEngine | 162 |
| `file_learner.py` | ファイル学習エンジン（機能③） | is_file_path(), class FileLearner | 161 |
| `file_ops.py` | ファイル操作機能 — アイのファイルシステムアクセス | class FileOperations | 403 |
| `gcal_connector.py` | Google Calendar API 連携 | class GCalConnector | 208 |
| `github_learner.py` | github_learner.py | class GithubPattern, class GithubLearner | 355 |
| `goal_tracker.py` | ユーザー目標トラッキング | class GoalTracker | 142 |
| `growth_report.py` | Growth Report — アイの成長記録レポート生成 | class DailySnapshot, class WeeklySnapshot, class GrowthReporter | 618 |
| `growth_stage.py` | 成長段階システム (Growth Stage System) | class Stage, class GrowthMetrics, class GrowthStageSystem | 442 |
| `habit_tracker.py` | 習慣トラッカー (Habit Tracker) | class HabitRecord, class Habit, class HabitTracker | 203 |
| `health_check.py` | システムヘルスチェック | class HealthStatus, check_model_files(), check_database(), check_key_file(), check_disk_space() | 229 |
| `hinomoto_bridge.py` | ai-chan ← HinoMoto 統合ブリッジ (PoC, Phase 2 kickoff). | class HinoMotoBridge | 152 |
| `host_guardian.py` | ホストガーディアン (Host Guardian) | class HostAlert, class HostGuardian | 379 |
| `ical_export.py` | iCalendar (RFC 5545) serializer for ai-chan anniversaries. | class ICalEvent, stable_uid(), escape_text(), fold_line(), serialize_calendar() | 240 |
| `image_analyzer.py` | 画像解析エンジン (Image Analyzer) | class ImageAnalyzer | 267 |
| `image_gen.py` | 画像生成モジュール（Pollinations.ai） | class ImageResult, class ImageGenerator | 236 |
| `initiative_channels.py` | 自発性メッセージ配信チャネル（Initiative Channels） | class InitiativeMessage, class InitiativeChannel, class CLIChannel, class DesktopChannel, class WebChannel | 234 |
| `initiative_driver.py` | 自発性ドライバー (Initiative Driver) | class InitiativeConfig, class _DriverState, class InitiativeDriver | 365 |
| `injection_guard.py` | プロンプトインジェクション検出 | check(), check_strict(), detect_patterns(), is_safe() | 165 |
| `integrity_monitor.py` | 整合性監視 (Integrity Monitor) | class IntegrityMonitor | 179 |
| `interest_map.py` | 好み・関心マップ | class InterestMap | 107 |
| `ip_guard.py` | IP保護モジュール - 独自開発の知的財産を保護する | class IPGuard | 168 |
| `kill_switch.py` | キルスイッチ (Kill Switch) | class KillSwitch | 182 |
| `knowledge_graph.py` | 知識グラフ (Knowledge Graph) | class Entity, class Relation, class KnowledgeGraph | 496 |
| `learning.py` | 擬似学習システム | is_safe_learning_example(), class LearningEngine | 115 |
| `lifelong_memory.py` | Lifelong Memory Module (LMM) — PoC skeleton. | class MemoryEvent, new_event(), class MemoryStore, with_importance() | 348 |
| `lifelong_memory_policy.py` | Retention policy for the Lifelong Memory Module. | class RetentionPolicy, should_retain(), filter_retainable() | 84 |
| `llm.py` | LLMエンジン | get_model_family(), default_model_family(), check_model_policy(), class LLMEngine | 1475 |
| `llm_ipc_protocol.py` | M8: LLM IPC Protocol — JSON-lines over Unix Domain Socket. | class ProtocolError, class WorkerError, encode_frame(), decode_frame(), new_request_id() | 187 |
| `llm_proxy.py` | M8: LLMProxy — client-side IPC wrapper for LLMEngine. | class LLMProxyError, class LLMProxy | 594 |
| `llm_worker_logger.py` | M8 Phase 2: LLM worker JSONL event logger. | class LLMWorkerLogger | 100 |
| `memory.py` | 三層記憶管理システム | class Memory, class MemoryManager | 1173 |
| `memory_compressor.py` | 記憶圧縮 + 重要度自動調整システム | class MemoryCompressor | 154 |
| `memory_context.py` | メモリコンテキストビルダー | class MemoryContextBuilder | 255 |
| `memory_forgetting.py` | Ebbinghaus 忘却曲線 + pin 永続化ポリシー. | class ForgettingCurveParams, retention_score(), class MemoryEntry, class ForgettingPolicy | 142 |
| `memory_phrasing.py` | Memory Honesty Phrasing (Q6, kindness-first). | band_from_confidence(), class PhrasingConfig, pick_phrase() | 195 |
| `memory_summarizer.py` | 記憶要約チェーン (Memory Summarizer) | class MemorySummarizer | 175 |
| `middleware.py` | 会話パイプラインのミドルウェアチェーン | class ConversationContext, class MiddlewareChain | 121 |
| `migration.py` | データベースマイグレーション管理 | class MigrationManager | 238 |
| `minutes_engine.py` | 議事録エンジン | class MinutesEngine | 974 |
| `minutes_extractor.py` | 議事録 構造化抽出エンジン | class MinutesExtractor | 331 |
| `mlx_engine.py` | MLX ネイティブ推論エンジン (Apple Silicon 専用) | class MLXEngine | 502 |
| `mode_manager.py` | インテリジェントモード切替システム | class ModeState, class ModeManager | 227 |
| `moe_router.py` | MoE ルーター (Mixture of Experts Router) | class ExpertModel, class RoutingDecision, class MoERouter | 326 |
| `multi_agent.py` | マルチエージェント協調エンジン（Sprint 4-M） | class MultiAgent | 164 |
| `multi_agent_verifier.py` | マルチエージェント検証 (Multi-Agent Verifier) | class VerificationResult, class ConsensusResult, class _NaturalnessAgent, class _SafetyAgent, class _ConsistencyAgent | 502 |
| `multimodal_chat.py` | マルチモーダルチャットハンドラ (Multimodal Chat Handler) | class MultimodalChatHandler | 182 |
| `network_monitor.py` | ネットワークモニター (Network Monitor) | class ConnectionInfo, class NetworkAlert, class NetworkMonitor | 340 |
| `neural_tts.py` | ニューラル音声合成バックエンド v2 | class VoiceProsody, class _AsyncRunner, class NeuralTTSEngine, create_neural_tts() | 843 |
| `news_briefing.py` | ニュースブリーフィングエンジン（Sprint 3-G） | class NewsBriefing | 121 |
| `notifier.py` | macOS 通知エンジン（機能⑤） | notify(), notify_ai(), notify_battery(), notify_schedule() | 56 |
| `notion_connector.py` | Notion API 連携 | class NotionConnector | 216 |
| `observability.py` | ai-chan Observability スケルトン (OpenTelemetry 最小ラッパ) | class SpanContext, class MetricSample, class _NoopTracer, is_enabled(), get_tracer() | 203 |
| `personality_card.py` | パーソナリティダッシュボードデータ | class PersonalityCard, generate(), summarize() | 184 |
| `personality_evolution.py` | 性格進化システム (Personality Evolution) | class PersonalityTraits, class RelationshipState, class ConversationTendencyTracker, class PersonalityEvolution | 407 |
| `pii_masker.py` | PII（個人情報）マスキング | class PIIMatch, mask(), detect(), has_pii(), mask_with_report() | 184 |
| `process_monitor.py` | プロセスモニター (Process Monitor) | class ProcessInfo, class ProcessAlert, class ProcessMonitor | 303 |
| `prompt_ab_test.py` | プロンプト A/B テスト | class PromptVariant, class ABTestState, class PromptABTest | 251 |
| `prosody_learner.py` | プロソディ学習エンジン | class ProsodyProfile, extract_pitch_contour(), extract_energy_contour(), detect_pauses(), analyze_intonation_pattern() | 630 |
| `protocols.py` | プロトコルインターフェース定義 | class LLMProtocol, class MemoryProtocol, class EmotionProtocol, class TTSProtocol, class STTProtocol | 176 |
| `quality_benchmark.py` | 自動品質ベンチマーク | is_japanese(), is_not_empty(), no_role_prefix(), appropriate_length(), no_repetition() | 442 |
| `rag_engine.py` | RAG エンジン (Retrieval-Augmented Generation) | class DocumentChunk, class RAGEngine | 273 |
| `research_agent.py` | Web リサーチエージェント | class ResearchResult, class ResearchAgent | 301 |
| `response_evaluator.py` | 応答品質自己評価 (Response Evaluator) | class QualityScore, class ResponseEvaluator | 309 |
| `response_pipeline.py` | レスポンスパイプライン | get_friendly_error(), sanitize_input(), class ResponsePipeline, compute_phi_quality() | 317 |
| `safety_bridge.py` | Safety bridge to hinomoto-model's deny-list. | is_denied(), is_available() | 111 |
| `schedule_announcer.py` | スケジュール読み上げエンジン（Sprint 3-B） | class ScheduleAnnouncer | 109 |
| `scheduler.py` | K. 日課・リマインダーシステム | class ScheduleManager, class _MaintenanceTask, class MaintenanceScheduler, register_maintenance_tasks() | 292 |
| `screenshot_blur.py` | スクリーンショット用ブラー / REDACT フィルタ。 | apply_blur() | 151 |
| `screenshot_reader.py` | スクリーンショット読み取りシステム（macOS専用） | capture_screen(), extract_text(), describe_screenshot(), read_and_cleanup() | 120 |
| `screenshot_sensitive.py` | スクリーンショット機密画面検出器。 | class SensitiveAction, class SensitivePattern, class SensitiveClassifier | 237 |
| `self_correction.py` | 自己修正システム (Self-Correction System) | class Symptom, class DiagnosisResult, class Prescription, class TreatmentRecord, class QualityMonitor | 700 |
| `self_development.py` | 自己開発パイプライン (Self-Development Pipeline) | class CodeReader, class ErrorPattern, class ErrorAnalyzer, class ProposalType, class Proposal | 786 |
| `self_will.py` | 自己意思エンジン (Self-Will Engine) | class DesireType, class Desire, class WillRecord, class DesireGenerator, class WillDecider | 576 |
| `semantic_search.py` | セマンティック記憶検索エンジン（機能⑧） | tfidf_score(), keyword_search(), class SemanticSearchEngine | 238 |
| `server_ai_env.py` | サーバーAI環境 (Server AI Environment) | class ServerAIEnv, class KnowledgeSync, class PrometheusReader, build_sync_job(), build_server_health_job() | 344 |
| `server_home.py` | サーバーホーム (Server Home) | class ServerCredentials, class CredentialStore, class ServerHome | 496 |
| `silence_emotion_bridge.py` | 沈黙イベントを感情状態に反映させる薄いアダプタ層。 | apply_silence_to_emotion() | 78 |
| `silence_token.py` | 沈黙トークン (Silence-aware) — HinoMoto 四本柱 #4「沈黙を理解する」の ai-chan 側実装。 | class SilenceCategory, class SilenceEvent, class SilenceClassifier, class SilenceDetector | 214 |
| `silence_turn.py` | 沈黙イベントを会話履歴の turn レコードに変換するユーティリティ。 | silence_event_to_turn() | 56 |
| `sound.py` | 通知サウンドマネージャー | class SoundManager | 98 |
| `sprint34_handlers.py` | Sprint 3・4 機能の統合ハンドラ。 | class Sprint34Handler | 224 |
| `stt.py` | 音声入力エンジン（機能⑦） | class SpeakerUtterance, class STTEngine | 720 |
| `subject_rights.py` | subject_rights — GDPR 17 条（忘れられる権利）/ 20 条（データポータビリティ）相当。 | class SubjectRightsManager | 259 |
| `synthetic_data_gen.py` | 合成データ生成 (Synthetic Data Generator) | class ConversationTemplate, class GeneratedExample, class SyntheticDataGenerator | 452 |
| `task_agent.py` | タスク分解エージェント | class SubTask, class TaskResult, class TaskAgent | 252 |
| `task_manager.py` | タスクマネージャー (Task Manager) | class Task, class TaskManager | 276 |
| `telemetry.py` | テレメトリ基盤 -- 匿名品質フィードバック収集 | class TelemetryEvent, class TelemetryCollector | 681 |
| `tenant.py` | tenant — マルチテナント基盤（H2, 2026-04-21）。 | class InvalidTenantId, class TenantId, tenant_dir(), parse_tenant_id() | 93 |
| `tenant_context.py` | tenant_context — マルチテナント物理分離のための root-scoped コンテキスト。 | class InvalidTenantIdError, class TenantIsolationError, class TenantContext, list_tenants(), purge_tenant() | 235 |
| `tokenizer_analyzer.py` | D10準備: トークナイザー分析ツール | class TokenizerProfile, class TokenizerAnalyzer | 283 |
| `topic_tracker.py` | 話題追跡システム | class TopicTracker | 74 |
| `tts.py` | テキスト読み上げエンジン（機能①） | class TTSEngine | 189 |
| `user_profile_mgr.py` | マルチユーザープロファイル管理 | class UserProfileManager | 216 |
| `vector_store.py` | M9 Phase 1: VectorStore Protocol abstraction. | class VectorStore, class FaissVectorStore, class SQLiteVecUnavailable, class SQLiteVecVectorStore, make_vector_store() | 389 |
| `vision_engine.py` | 画面理解エンジン（機能⑨） | class VisionEngine | 177 |
| `voice_id.py` | 声紋認証システム | extract_voice_features(), cosine_similarity(), record_voice(), class VoiceProfile, class VoiceIDManager | 530 |
| `voice_id_fallback.py` | Voice ID fallback: drift detection and challenge-based re-authentication. | class VoiceMatch, class DriftDetector, class ChallengeSet, class _SubjectState, class FallbackPolicy | 526 |
| `voice_loop.py` | ハンズフリー会話ループ（Voice Conversation Loop） | class VoiceLoop | 197 |
| `wake_word.py` | ウェイクワード検出（Wake Word Detection） | class WakeWordBackend, class VoskWakeWord, class OpenWakeWordBackend, create_wake_word_detector() | 348 |
| `web_builder.py` | WebBuilder — HP構成案 → HTML/CSS/JS コード生成 | class WebBuildResult, class WebBuilder | 281 |
| `web_fetcher.py` | L. 天気・ニュース取得モジュール | get_weather(), get_news_headlines(), build_weather_hint(), build_news_hint(), web_search() | 262 |
| `web_learner.py` | Web ページ学習エンジン（機能②） | is_web_url(), class WebLearner | 207 |
| `yamato_architecture.py` | 7層アーキテクチャ基盤 (Yamato 7-Layer Architecture) | class LayerStatus, class YamatoArchitecture | 265 |
| `yamato_shield.py` | YAMATO Shield -- 整合性検証・ライセンスチェック・署名検証・監査ログ | class IntegrityBaseline, class FileIntegrityChecker, class LicenseIssue, class LicenseChecker, class UpdateVerifier | 542 |
| `youtube_learner.py` | YouTube 学習エンジン | extract_youtube_url(), class YouTubeLearner | 276 |

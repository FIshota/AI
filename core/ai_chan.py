"""
アイ メインクラス
全コンポーネントを統合して管理します

リファクタリングにより以下のモジュールに分割:
- core.cmd_handlers    : CMD_* パターンとコマンドディスパッチ
- core.memory_context  : 記憶コンテキスト / システムプロンプト組み立て
- core.response_pipeline: 応答クリーニング / 品質推定 / エラーメッセージ
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# コアコンポーネント（軽量・常時ロード）
# ──────────────────────────────────────────────────────────────
from core.memory import MemoryManager
from core.emotion import EmotionEngine, MoodAnalyzer
from core.llm import LLMEngine
from core.learning import LearningEngine
from core.correction_learning import CorrectionLearning
from core.memory_compressor import MemoryCompressor
from core.topic_tracker import TopicTracker
from core.scheduler import ScheduleManager
from core.anniversary import AnniversaryManager
from core.diary import DiaryManager
from core.emotion_history import EmotionHistory
from core.interest_map import InterestMap
from core.goal_tracker import GoalTracker
from core.tts import TTSEngine  # レガシー互換
# Item #P1: lazy imports — 起動時の import コストを削減するため、以下は使用時にロード
# from core.emotional_tts import create_tts_engine as _create_emotional_tts
# from core.neural_tts import NeuralTTSEngine, create_neural_tts, EDGE_TTS_AVAILABLE
# from core.prosody_learner import ProsodyLearner
# from core.calendar_reader import build_calendar_hint, format_events_for_chat
# from core.semantic_search import SemanticSearchEngine
# from core.auto_learner import AutoLearner
# from core.bio_nervous_system import BioNervousSystem
from core.growth_stage import GrowthStageSystem
from core.self_correction import SelfCorrectionSystem
from core.self_will import SelfWillEngine
# Item #P1: lazy — from core.self_development import SelfDevelopmentEngine
from core.initiative_driver import InitiativeDriver, InitiativeConfig
from core.initiative_channels import (
    BroadcastChannel,
    CLIChannel,
    DesktopChannel,
    VoiceChannel,
    WebChannel,
)
from core.action_cycle import ActionCycleEngine
from core.event_bus import EventBus, CONFIG_CHANGED
from core.config_watcher import ConfigWatcher
from core.mode_manager import ModeManager, FAMILY_MODE, AGENT_MODE
from core.voice_id import VoiceIDManager
from core.federated_stub import FederatedStub

# ──────────────────────────────────────────────────────────────
# 分割モジュール
# ──────────────────────────────────────────────────────────────
from core.cmd_handlers import CommandHandler
from core.memory_context import MemoryContextBuilder
from core.response_pipeline import (
    ResponsePipeline,
    ERROR_MESSAGES,
    get_friendly_error,
    sanitize_input,
    _NARRATION_RE,
)

# ──────────────────────────────────────────────────────────────
# 後方互換: CMD_* パターンを re-export（テストコードが参照している）
# ──────────────────────────────────────────────────────────────
from core.cmd_handlers import (  # noqa: F401
    CMD_REMEMBER, CMD_FORGET, CMD_IMPORTANT, CMD_MEMORY,
    CMD_PROFILE, CMD_SEARCH, CMD_DIARY, CMD_ANNIV_ADD, CMD_ANNIV_LIST,
    CMD_YT_LIST, CMD_WEB_LIST, CMD_FILE_LIST, CMD_CALENDAR, CMD_BATTERY,
    CMD_AUTO_LEARN, CMD_LEARN_ADD, CMD_LEARN_NOW,
    CMD_MEMO_ADD, CMD_MEMO_LIST,
    CMD_PROPOSAL, CMD_PROPOSAL_OK, CMD_PROPOSAL_NO,
    CMD_SELF_AWARE, CMD_MINUTES,
    CMD_SECURITY, CMD_BACKUP, CMD_LOCKDOWN, CMD_UNLOCK,
    CMD_SERVER_STATUS, CMD_SERVER_DOCKER, CMD_SERVER_SYNC,
    CMD_SERVER_SETUP, CMD_PROACTIVE,
    CMD_KNOWLEDGE, CMD_RELATIONSHIP, CMD_GROWTH, CMD_QUALITY,
    CMD_YAMATO_DASH, CMD_MOE_STATUS, CMD_LEARNING_STATUS,
    CMD_SYNTH_GEN, CMD_VERIFY_STATUS,
    CMD_SCREENSHOT, CMD_CLIPBOARD_IMG, CMD_IMAGE_ANALYZE,
    CMD_NETWORK_CHECK, CMD_PROCESS_CHECK, CMD_DEFENSE_REPORT,
    CMD_TASK_ADD, CMD_TASK_DONE, CMD_TASK_LIST,
    CMD_HABIT_ADD, CMD_HABIT_REC, CMD_HABIT_LIST,
    CMD_DOC_ADD, CMD_DOC_LIST, CMD_DOC_SEARCH,
    CMD_WEB_SEARCH, CMD_WEB_SEARCH_PREFIX, CMD_WEB_FETCH,
    CMD_CODE_ANALYZE, CMD_CODE_REVIEW, CMD_CODE_FIX,
    CMD_CODE_TEST, CMD_CODE_EXPLAIN, CMD_CODE_FILE, CMD_CODE_RUN,
    CMD_SLASH_CODE, CMD_SLASH_REVIEW, CMD_SLASH_FIX,
    CMD_SLASH_RUN, CMD_SLASH_EXPLAIN, CMD_SLASH_TEST, CMD_SLASH_CODE_HELP,
    CMD_EXPORT_WORD, CMD_EXPORT_PPTX, CMD_EXPORT_EXCEL, CMD_EXPORT_AUTO,
    CMD_HEALTH,
    CMD_VOICE_REGISTER, CMD_VOICE_IDENTIFY, CMD_VOICE_STATUS,
    # Sprint 2
    CMD_WEB_BUILD, CMD_CODE_REVIEW_S2, CMD_DOC_CREATE,
)

# ──────────────────────────────────────────────────────────────
# プロファイル自動深化パターン（一人称が明確な文のみ）
# ──────────────────────────────────────────────────────────────
_PROFILE_PATTERNS = [
    (re.compile(r'(?:私|俺|うち|自分)の名前は(.+?)(?:だ|だよ|です|。|$)'), '名前'),
    (re.compile(r'(?:私|俺|うち|自分)は(\d+)歳'), '年齢'),
    (re.compile(r'(?:私|俺|うち|自分)の誕生日は(\d{1,2})月(\d{1,2})日'), '誕生日'),
    (re.compile(r'(?:私|俺|うち|自分)の仕事は(.+?)(?:だ|だよ|です)'), '職業'),
    (re.compile(r'(?:私|俺|うち|自分)は(.+?)が好き'), '好きなもの'),
    (re.compile(r'(?:私|俺|うち|自分)の趣味は(.+?)(?:だ|だよ|です)'), '趣味'),
    (re.compile(r'(?:私|俺|うち|自分)のことは?(.+?)(?:と|って)呼んで'), '呼び方'),
    (re.compile(r'(.+?)(?:と|って)呼んで(?:ね|くれ|ください|。|$)'), '呼び方'),
    (re.compile(r'(?:私|俺|うち|自分)の呼び方は(.+?)(?:だ|だよ|です|で|。|$)'), '呼び方'),
    (re.compile(r'ニックネームは(.+?)(?:だ|だよ|です|で|。|$)'), '呼び方'),
]

# ──────────────────────────────────────────────────────────────
# 意図→感情プロンプトマッピング (Item #72)
# ──────────────────────────────────────────────────────────────
_EMOTION_PROMPTS: dict[str, str] = {
    "greeting":    "嬉しそうに挨拶して。",
    "question":    "丁寧に、相手の気持ちに寄り添って答えて。",
    "complaint":   "心配そうに共感して、励まして。",
    "gratitude":   "照れながらも嬉しそうに返して。",
    "farewell":    "少し寂しそうに、でも明るく見送って。",
    "chat":        "リラックスして自然に話して。",
    "request":     "前向きに手伝おうとして。",
    "emotional":   "繊細に、相手の感情を大切にして答えて。",
}

# ──────────────────────────────────────────────────────────────
# 意図→プロンプト重み (Item #82)
# memory_weight: 記憶コンテキストの重要度
# persona_weight: 人格プロンプトの重要度
# ──────────────────────────────────────────────────────────────
_INTENT_WEIGHTS: dict[str, dict[str, float]] = {
    "greeting":  {"memory_weight": 0.3, "persona_weight": 1.0},
    "question":  {"memory_weight": 1.0, "persona_weight": 0.7},
    "complaint": {"memory_weight": 0.8, "persona_weight": 0.9},
    "gratitude": {"memory_weight": 0.5, "persona_weight": 1.0},
    "farewell":  {"memory_weight": 0.4, "persona_weight": 0.8},
    "chat":      {"memory_weight": 0.7, "persona_weight": 0.8},
    "request":   {"memory_weight": 0.9, "persona_weight": 0.6},
    "emotional": {"memory_weight": 0.8, "persona_weight": 1.0},
}


class AiChan:
    """
    アイのメインクラス。
    対話の受け取り・処理・応答生成を担当します。
    """

    def __init__(self, base_dir: str | Path = "."):
        self.base_dir = Path(base_dir)
        self._load_config()

        # E-08: settings.json ホットリロード
        # NOTE: _event_bus は _init_components → _init_heavy_components 内で
        #       PluginLoader が参照するため、_init_components より前に初期化する
        self._event_bus = EventBus()

        self._init_components()
        self.conversation_history: list[dict] = []
        self.turn_count = 0

        # 分割モジュールのインスタンスを保持
        self._cmd_handler = CommandHandler(self)
        self._ctx_builder = MemoryContextBuilder(self)
        self._resp_pipeline = ResponsePipeline(self)

        # Item #19: 並列フェッチ用スレッドプール
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="aichan")

        # Item #22: JSONL 会話ログのパス
        self._conv_log_path = self.base_dir / "data" / "conversation_log.jsonl"
        self._conv_log_path.parent.mkdir(parents=True, exist_ok=True)

        # E-08: ConfigWatcher 起動（_event_bus は上で初期化済み）
        self._config_watcher = ConfigWatcher(
            bus=self._event_bus,
            settings_path=self.base_dir / "config" / "settings.json",
            interval=5.0,
        )
        self._event_bus.subscribe(CONFIG_CHANGED, self._on_config_changed)
        self._config_watcher.start()
        logger.info("設定ホットリロード: 起動完了")

    def _load_config(self):
        settings_path = self.base_dir / "config" / "settings.json"
        persona_path  = self.base_dir / "config" / "persona.json"

        def _load_json(p: Path, label: str) -> dict:
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                raise RuntimeError(
                    f"{label} が見つかりません: {p}\n"
                    f"config/ ディレクトリにデフォルト設定をコピーしてください"
                )
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"{label} の JSON が不正です: {p}\n{e}\n"
                    f"ファイルを修正するか、デフォルトを復元してください"
                )

        self.settings = _load_json(settings_path, "settings.json")
        self.persona  = _load_json(persona_path,  "persona.json")

        # personality/*.yaml が存在すれば優先的に上書き
        try:
            from utils.personality_loader import load_personality
            self._personality = load_personality(self.base_dir)
            if self._personality.source == "yaml":
                self.persona = self._personality.to_dict()
                print(
                    f"[Personality] YAML 人格をロードしました "
                    f"(core_memories={len(self._personality.core_memories)})",
                    flush=True,
                )
            else:
                print(
                    f"[Personality] persona.json (レガシー) を使用しています。"
                    f"personality/core.yaml への移行を推奨します。",
                    flush=True,
                )
        except Exception as e:
            print(f"[Personality] YAML ロード失敗、persona.json を使用: {e}", flush=True)
            self._personality = None

    # ─── E-08: 設定ホットリロードハンドラ ──────────────────────────

    def _on_config_changed(self, path: str = "") -> None:
        """
        CONFIG_CHANGED イベント受信時に settings.json を再読み込みする（E-08）。

        再ロード対象:
        - self.settings （全設定値）
        - llm の generation パラメータ（temperature / max_tokens / top_p）
        - 感情パラメータ（decay_rate / mood_window）
        - ネットワーク許可フラグ
        """
        logger.info("[ConfigWatcher] 設定再ロード: %s", path)
        try:
            settings_path = self.base_dir / "config" / "settings.json"
            import json as _json
            with open(settings_path, encoding="utf-8") as f:
                new_settings = _json.load(f)
        except Exception as e:
            logger.error("[ConfigWatcher] settings.json 読み込み失敗: %s", e)
            return

        old_settings = self.settings
        self.settings = new_settings

        # ── LLM パラメータの反映 ──
        new_gen = new_settings.get("llm", {})
        old_gen = old_settings.get("llm", {})
        if new_gen != old_gen and getattr(self, "llm", None):
            try:
                self.llm.config.update({
                    k: new_gen[k]
                    for k in ("temperature", "max_tokens", "top_p", "repeat_penalty")
                    if k in new_gen
                })
                logger.info("[ConfigWatcher] LLM パラメータ更新: %s", new_gen)
            except Exception as e:
                logger.warning("[ConfigWatcher] LLM パラメータ更新失敗: %s", e)

        # ── ネットワーク許可フラグの反映 ──
        new_allow_network = new_settings.get("network", {}).get("allow", True)
        if new_allow_network != old_settings.get("network", {}).get("allow", True):
            self._allow_network = new_allow_network
            logger.info("[ConfigWatcher] ネットワーク許可: %s", new_allow_network)

        # ── 感情パラメータの反映 ──
        new_emo = new_settings.get("emotion", {})
        old_emo = old_settings.get("emotion", {})
        if new_emo != old_emo and getattr(self, "emotion", None):
            try:
                if "decay_rate" in new_emo:
                    self.emotion.decay_rate = float(new_emo["decay_rate"])
                logger.info("[ConfigWatcher] 感情パラメータ更新: %s", new_emo)
            except Exception as e:
                logger.warning("[ConfigWatcher] 感情パラメータ更新失敗: %s", e)

        print(f"[ConfigWatcher] ✅ 設定をホットリロードしました ({path})", flush=True)

    def _init_components(self):
        cfg = self.settings
        mem_cfg = cfg["memory"]
        sec_cfg = cfg["security"]

        # 記憶管理
        db_path  = self.base_dir / mem_cfg["db_path"]
        key_file = self.base_dir / sec_cfg["key_file"]
        self.memory = MemoryManager(
            db_path=db_path,
            key_file=key_file,
            encrypt=sec_cfg["encrypt_database"],
        )
        self.memory.short_term_max = mem_cfg["short_term_max"]

        # personality/memories.yaml のコア記憶を絶対記憶として投入
        if getattr(self, "_personality", None) is not None and self._personality.core_memories:
            try:
                result = self.memory.bootstrap_core_memories(self._personality.core_memories)
                if result["inserted"] > 0:
                    print(
                        f"[Memory] コア記憶を{result['inserted']}件追加しました "
                        f"(skipped={result['skipped']})",
                        flush=True,
                    )
            except Exception as e:
                print(f"[Memory] コア記憶 bootstrap 失敗: {e}", flush=True)

        # 感情エンジン
        emotion_state_file = self.base_dir / "data" / "emotion_state.json"
        self.emotion = EmotionEngine(state_file=emotion_state_file)

        # LLMエンジン
        model_path = self.base_dir / cfg["llm"]["model_path"]
        self.llm = LLMEngine(model_path=model_path, config=cfg["llm"])

        # 擬似学習エンジン
        learning_dir = self.base_dir / "data" / "learning"
        learning_dir.mkdir(exist_ok=True)
        self.learning = LearningEngine(learning_dir)
        print(f"[Learning] {self.learning.stats()['total_examples']} 件の会話例を読み込みました")

        # ユーザー訂正学習
        correction_dir = self.base_dir / "data" / "corrections"
        self.correction_learning = CorrectionLearning(data_dir=correction_dir)
        _cc = self.correction_learning.stats()["total_corrections"]
        if _cc > 0:
            print(f"[Correction] {_cc} 件の訂正データを読み込みました")

        # 記憶圧縮・話題追跡・スケジューラー・記念日・日記
        self.compressor      = MemoryCompressor(self.memory)
        self.topic_tracker   = TopicTracker(self.base_dir / "data")
        self.scheduler       = ScheduleManager(self.base_dir / "data")
        self.anniversary     = AnniversaryManager(self.base_dir / "data")
        self.diary           = DiaryManager(self.base_dir / "data", self.memory)
        self._last_diary_date = datetime.now().date()

        # 成長記録系
        self.emotion_history = EmotionHistory(self.base_dir / "data")
        self.interest_map    = InterestMap(self.base_dir / "data")
        self.goal_tracker    = GoalTracker(self.base_dir / "data")

        # YouTube / Web / ファイル学習エンジン
        # Item #5: lazy import — 実際の fetch/learn メソッド内でモジュールを使う
        from core.youtube_learner import YouTubeLearner, extract_youtube_url
        from core.web_learner import WebLearner, is_web_url
        from core.file_learner import FileLearner, is_file_path
        learning_data_dir = self.base_dir / "data" / "learning"
        self.youtube = YouTubeLearner(
            data_dir=self.base_dir / "data",
            learning_dir=learning_data_dir,
        )
        self.web_learner  = WebLearner(
            data_dir=self.base_dir / "data",
            learning_dir=learning_data_dir,
        )
        self.file_learner = FileLearner(
            data_dir=self.base_dir / "data",
            learning_dir=learning_data_dir,
        )

        # TTS エンジン: NeuralTTS (edge-tts) > EmotionalTTS (say+FX) > TTSEngine (say)
        tts_cfg = cfg.get("tts", {})
        # Item #P1: lazy import
        from core.neural_tts import create_neural_tts, EDGE_TTS_AVAILABLE
        from core.emotional_tts import create_tts_engine as _create_emotional_tts
        try:
            if EDGE_TTS_AVAILABLE and tts_cfg.get("enabled", False):
                self.tts = create_neural_tts(tts_cfg)
                print(f"[NeuralTTS] ✓ ニューラル音声合成を初期化（mode={self.tts.audio_mode}, voice={self.tts.voice}）", flush=True)
            else:
                self.tts = _create_emotional_tts(tts_cfg)
                print(f"[EmotionalTTS] ✓ 感情音声合成を初期化（mode={self.tts.audio_mode}）", flush=True)
        except Exception as _tts_err:
            logger.warning("TTS 初期化失敗、レガシーTTSにフォールバック: %s", _tts_err)
            self.tts = TTSEngine(
                enabled=tts_cfg.get("enabled", False),
                voice=tts_cfg.get("voice", "Kyoko"),
                rate=tts_cfg.get("rate", 175),
            )

        # プロソディ学習エンジン（人間の声からイントネーション学習）
        # Item #P1: lazy import
        from core.prosody_learner import ProsodyLearner
        from core.neural_tts import NeuralTTSEngine
        self.prosody_learner = ProsodyLearner(self.base_dir / "data")
        if self.prosody_learner.has_learned() and isinstance(self.tts, NeuralTTSEngine):
            overrides = self.prosody_learner.get_tts_overrides()
            self.tts.apply_learned_prosody(overrides)
            print(f"[Prosody] ✓ 学習済みプロソディを適用（{self.prosody_learner.get_profile().sample_count}サンプル）", flush=True)

        # セマンティック検索エンジン
        # Item #P1: lazy import
        from core.semantic_search import SemanticSearchEngine
        self.semantic_search = SemanticSearchEngine(self.base_dir / "data")
        if cfg.get("semantic_search", {}).get("enabled", False):
            import threading
            threading.Thread(
                target=self._init_semantic_search, daemon=True
            ).start()

        # ビジョンエンジン
        from core.vision_engine import VisionEngine
        vision_cfg = cfg.get("vision", {})
        enable_moondream = vision_cfg.get("enable_moondream", False)
        self.vision = VisionEngine(enable_moondream=enable_moondream)
        if enable_moondream:
            import threading
            threading.Thread(
                target=self.vision.load_moondream, daemon=True
            ).start()

        # 自動学習エンジン
        # Item #P1: lazy import
        from core.auto_learner import AutoLearner
        self.auto_learner = AutoLearner(self.base_dir / "data")

        # 生物神経系
        # Item #P1: lazy import
        from core.bio_nervous_system import BioNervousSystem
        self.bio_nervous = BioNervousSystem(
            data_dir=self.base_dir / "data"
        )
        self.bio_nervous.autonomic.register(
            "emotion_decay", interval_turns=5,
            callback=lambda: self.emotion.save_if_changed(),
        )
        self.bio_nervous.autonomic.register(
            "memory_compress", interval_turns=10,
            callback=lambda: self.compressor.compress(),
        )
        self.bio_nervous.autonomic.register(
            "self_will_think", interval_turns=8,
            callback=lambda: self._autonomic_will_think(),
        )
        self.bio_nervous.autonomic.register(
            "action_cycle", interval_turns=15,
            callback=lambda: self._autonomic_action_cycle(),
        )
        self.bio_nervous.autonomic.register(
            "self_development", interval_turns=50,
            callback=lambda: self._autonomic_self_dev(),
        )
        self.bio_nervous.immune.register_healer(
            "FileNotFoundError",
            lambda e, ctx: _immune_file_recovery(self, e, ctx),
        )
        self.bio_nervous.immune.register_healer(
            "JSONDecodeError",
            lambda e, ctx: _immune_json_recovery(self, e, ctx),
        )
        try:
            removed = self.bio_nervous.muscle.periodic_maintenance()
            if removed > 0:
                logger.info("筋肉記憶の定期メンテナンス: %d件のstaleパターンを削除", removed)
        except Exception:
            pass

        # 成長段階システム
        self.growth = GrowthStageSystem(
            data_dir=self.base_dir / "data"
        )
        print(f"[Growth] {self.growth.stage_emoji} {self.growth.stage_name}", flush=True)

        # 自己修正システム
        self.self_correction = SelfCorrectionSystem(
            data_dir=self.base_dir / "data"
        )
        self._register_correction_handlers()

        # 自己意思エンジン
        self.self_will = SelfWillEngine(
            data_dir=self.base_dir / "data"
        )
        self._register_will_actions()

        # ─── 自発性ドライバー (Initiative Driver) ─────────────
        # 起動時点では CLI + Web のみ。Desktop/Voice は後から attach_* で追加。
        self._web_initiative_channel = WebChannel()
        self._broadcast_channel = BroadcastChannel([
            CLIChannel(),
            self._web_initiative_channel,
        ])
        try:
            self.initiative_driver = InitiativeDriver(
                self_will=self.self_will,
                channel=self._broadcast_channel,
                context_provider=self._build_initiative_context,
                config=InitiativeConfig(),
            )
            self.initiative_driver.start()
            logger.info("InitiativeDriver wired and started")
        except Exception as e:
            logger.warning("InitiativeDriver 起動失敗: %s", e)
            self.initiative_driver = None

        # 自律行動サイクル
        self.action_cycle = ActionCycleEngine(
            data_dir=self.base_dir / "data"
        )

        # 自己開発パイプライン
        # Item #P1: lazy import
        from core.self_development import SelfDevelopmentEngine
        self.self_dev = SelfDevelopmentEngine(
            project_root=self.base_dir,
            data_dir=self.base_dir / "data",
        )

        # ─── 次世代ビジョン: モード切替・声紋ID・連合学習 ───────
        self.mode_manager = ModeManager(data_dir=self.base_dir / "data")
        self.voice_id = VoiceIDManager(data_dir=self.base_dir / "data")
        self.federated = FederatedStub(data_dir=self.base_dir / "data")
        print(f"[ModeManager] ✓ モード切替を初期化（現在: {self.mode_manager.current_mode}）", flush=True)
        _trust = self.voice_id.get_trust_level()
        if _trust > 40:
            _user = self.voice_id.get_current_user()
            _name = _user.name if _user else "不明"
            print(f"[VoiceID] ✓ ユーザー識別（{_name}, trust={_trust}）", flush=True)
        else:
            print("[VoiceID] ✓ 声紋認証スタブ初期化（名前ベース識別）", flush=True)
        print("[Federated] ✓ 連合学習スタブ初期化（スタンドアロンモード）", flush=True)

        # Item #5: lazy import — 重いモジュールはメソッド内で遅延ロード
        # document_exporter, code_engine は _init_heavy_components で初期化
        self._heavy_initialized = False
        self.doc_exporter = None
        self.code_engine = None
        self.data_exporter = None
        self.personality_card = None
        self.user_profile_mgr = None
        self.sound = None
        self.health_check = None

        self._init_heavy_components(cfg)

        # 時間帯挨拶のペンディング
        self._pending_greeting: str | None = None

    def _init_heavy_components(self, cfg: dict) -> None:
        """
        重いコンポーネントの初期化。
        Item #5: lazy import — import を関数内に閉じ込めて起動を高速化。
        """
        # ドキュメント出力エンジン
        try:
            from core.document_exporter import DocumentExportEngine
            self.doc_exporter = DocumentExportEngine(
                output_dir=self.base_dir / "data" / "exports",
            )
        except Exception as e:
            print(f"[DocExporter] 初期化失敗: {e}", flush=True)

        # コードエンジン
        try:
            from core.code_engine import CodeEngine
            self.code_engine = CodeEngine(
                data_dir=self.base_dir / "data",
            )
        except Exception as e:
            print(f"[CodeEngine] 初期化失敗: {e}", flush=True)

        # 自律エンジン
        try:
            from core.autonomous_engine import AutonomousEngine, build_health_check
            self.autonomous = AutonomousEngine(self.base_dir)
            self.autonomous.register(
                name="health_check",
                cadence="hourly",
                fn=build_health_check(self),
                description="毎時のヘルスチェック (memory stats, db size, log errors)",
            )
        except Exception as e:
            print(f"[Autonomous] 初期化失敗: {e}", flush=True)
            self.autonomous = None

        # 成長レポート
        try:
            from core.growth_report import GrowthReporter
            self.growth_reporter = GrowthReporter(self)
            if self.autonomous is not None:
                self.autonomous.register(
                    name="daily_growth_report",
                    cadence="daily",
                    fn=self.growth_reporter.daily_job,
                    hour=2, minute=0,
                    description="日次成長レポート (reports/daily/*.md)",
                )
                self.autonomous.register(
                    name="weekly_growth_report",
                    cadence="weekly",
                    fn=self.growth_reporter.weekly_job,
                    hour=2, minute=30, weekday=6,
                    description="週次成長レポート (reports/weekly/*.md)",
                )
        except Exception as e:
            print(f"[GrowthReport] 初期化失敗: {e}", flush=True)
            self.growth_reporter = None

        # ─── Sprint 2.1: 防御システム ───────────────────────────
        try:
            from core.audit_log import AuditLog
            self.audit = AuditLog(self.base_dir / "data")
            self.audit.info("system_start", "アイ起動")
        except Exception as e:
            print(f"[AuditLog] 初期化失敗: {e}", flush=True)
            self.audit = None

        try:
            from core.integrity_monitor import IntegrityMonitor
            self.integrity = IntegrityMonitor(self.base_dir, audit=self.audit)
            result = self.integrity.startup_check()
            if result["status"] == "warn":
                print(f"[Integrity] ⚠ 改ざん検知: {result}", flush=True)
            if self.autonomous is not None:
                self.autonomous.register(
                    name="integrity_check",
                    cadence="hourly",
                    fn=self.integrity.hourly_job,
                    description="毎時のファイル整合性チェック",
                )
        except Exception as e:
            print(f"[Integrity] 初期化失敗: {e}", flush=True)
            self.integrity = None

        try:
            from core.backup_rotator import BackupRotator
            self.backup = BackupRotator(
                self.base_dir, audit=self.audit, max_generations=7
            )
            if self.autonomous is not None:
                self.autonomous.register(
                    name="daily_backup",
                    cadence="daily",
                    fn=self.backup.daily_job,
                    hour=3, minute=0,
                    description="日次自動バックアップ (backups/*.tar.gz)",
                )
        except Exception as e:
            print(f"[Backup] 初期化失敗: {e}", flush=True)
            self.backup = None

        try:
            from core.anomaly_detector import AnomalyDetector
            self.anomaly_detector = AnomalyDetector(
                self.base_dir, audit=self.audit, memory=self.memory
            )
            if self.autonomous is not None:
                self.autonomous.register(
                    name="anomaly_check",
                    cadence="hourly",
                    fn=self.anomaly_detector.hourly_job,
                    description="毎時の異常検知（記憶改ざん/データ汚染/設定変更）",
                )
        except Exception as e:
            print(f"[Anomaly] 初期化失敗: {e}", flush=True)
            self.anomaly_detector = None

        try:
            from core.kill_switch import KillSwitch
            self.kill_switch = KillSwitch(
                self.base_dir,
                audit=self.audit,
                backup=getattr(self, "backup", None),
            )
            if self.kill_switch.is_locked:
                print("[KillSwitch] ⚠ ロックダウン状態です", flush=True)
        except Exception as e:
            print(f"[KillSwitch] 初期化失敗: {e}", flush=True)
            self.kill_switch = None

        try:
            from core.host_guardian import HostGuardian
            self.host_guardian = HostGuardian(self.base_dir, audit=self.audit)
            if self.autonomous is not None:
                self.autonomous.register(
                    name="host_security_check",
                    cadence="hourly",
                    fn=self.host_guardian.hourly_job,
                    description="毎時のホストPCセキュリティ監視",
                )
            print("[HostGuardian] ✓ ホスト防御監視を初期化", flush=True)
        except Exception as e:
            print(f"[HostGuardian] 初期化失敗: {e}", flush=True)
            self.host_guardian = None

        # ネットワーク・レスポンス設定
        auto_cfg = cfg.get("autonomous", {})
        self._allow_network  = auto_cfg.get("allow_network", False)
        self._weather_city   = auto_cfg.get("weather_city", "Tokyo")
        self._idle_minutes   = auto_cfg.get("idle_minutes", 30)
        self._sched_enabled  = auto_cfg.get("schedule_enabled", True)
        self._max_sentences  = cfg.get("llm", {}).get("max_sentences", 6)

        # ─── Sprint 3.0-B: 知識拡張 ──────────────────────────
        try:
            from core.rag_engine import RAGEngine
            self.rag = RAGEngine(self.base_dir)
            print(f"[RAG] ✓ ドキュメント {len(self.rag.list_documents())} 件ロード済", flush=True)
        except Exception as e:
            print(f"[RAG] 初期化失敗: {e}", flush=True)
            self.rag = None

        try:
            from core.memory_summarizer import MemorySummarizer
            self.memory_summarizer = MemorySummarizer(self.base_dir)
        except Exception as e:
            print(f"[Summarizer] 初期化失敗: {e}", flush=True)
            self.memory_summarizer = None

        # ─── Sprint 3.0-C: 生活アシスタント ──────────────────
        try:
            from core.task_manager import TaskManager
            self.task_manager = TaskManager(self.base_dir)
            pending = self.task_manager.list_pending()
            if pending:
                print(f"[Tasks] ✓ 未完了タスク {len(pending)} 件", flush=True)
        except Exception as e:
            print(f"[Tasks] 初期化失敗: {e}", flush=True)
            self.task_manager = None

        try:
            from core.habit_tracker import HabitTracker
            self.habit_tracker = HabitTracker(self.base_dir)
        except Exception as e:
            print(f"[Habits] 初期化失敗: {e}", flush=True)
            self.habit_tracker = None

        # ─── Sprint 3.0-D: 表情エンジン ──────────────────────
        try:
            from core.expression_engine import ExpressionEngine
            self.expression = ExpressionEngine(self.base_dir)
        except Exception as e:
            print(f"[Expression] 初期化失敗: {e}", flush=True)
            self.expression = None

        # ─── Sprint 3.0-A: マルチモーダル ────────────────────
        try:
            from core.image_analyzer import ImageAnalyzer
            self.image_analyzer = ImageAnalyzer(self.base_dir)
            from core.multimodal_chat import MultimodalChatHandler
            self.multimodal = MultimodalChatHandler(
                self.base_dir, self.image_analyzer, self.llm
            )
            print("[Multimodal] ✓ マルチモーダル初期化完了", flush=True)
        except Exception as e:
            print(f"[Multimodal] 初期化失敗: {e}", flush=True)
            self.image_analyzer = None
            self.multimodal = None

        # ─── Sprint 3.0-E: 防御進化 ─────────────────────────
        try:
            from core.network_monitor import NetworkMonitor
            self.network_monitor = NetworkMonitor(
                self.base_dir, audit=self.audit
            )
            if self.autonomous is not None:
                self.autonomous.register(
                    name="network_check",
                    cadence="hourly",
                    fn=self.network_monitor.hourly_job,
                    description="毎時のネットワーク監視",
                )
            print("[NetworkMonitor] ✓ ネットワーク監視を初期化", flush=True)
        except Exception as e:
            print(f"[NetworkMonitor] 初期化失敗: {e}", flush=True)
            self.network_monitor = None

        try:
            from core.process_monitor import ProcessMonitor
            self.process_monitor = ProcessMonitor(
                self.base_dir, audit=self.audit
            )
            if self.autonomous is not None:
                self.autonomous.register(
                    name="process_check",
                    cadence="hourly",
                    fn=self.process_monitor.hourly_job,
                    description="毎時のプロセス監視",
                )
            print("[ProcessMonitor] ✓ プロセス監視を初期化", flush=True)
        except Exception as e:
            print(f"[ProcessMonitor] 初期化失敗: {e}", flush=True)
            self.process_monitor = None

        try:
            from core.defense_dashboard import DefenseDashboard
            self.defense_dashboard = DefenseDashboard(
                self.base_dir,
                audit_log=self.audit,
                integrity_monitor=getattr(self, "integrity", None),
                backup_rotator=getattr(self, "backup", None),
                anomaly_detector=getattr(self, "anomaly_detector", None),
                host_guardian=getattr(self, "host_guardian", None),
                network_monitor=getattr(self, "network_monitor", None),
                process_monitor=getattr(self, "process_monitor", None),
            )
            if self.autonomous is not None:
                self.autonomous.register(
                    name="defense_daily_report",
                    cadence="daily",
                    fn=self.defense_dashboard.daily_job,
                    hour=4, minute=0,
                    description="日次防御レポート生成",
                )
            print("[DefenseDashboard] ✓ 防御ダッシュボード初期化", flush=True)
        except Exception as e:
            print(f"[DefenseDashboard] 初期化失敗: {e}", flush=True)
            self.defense_dashboard = None

        # ─── Sprint J: サーバーホーム ────────────────────────
        try:
            from core.server_home import ServerHome
            self.server_home = ServerHome(self.base_dir, cfg)
            if self.server_home.enabled and self.autonomous is not None:
                self.autonomous.register(
                    name="server_health",
                    cadence="hourly",
                    fn=self.server_home.hourly_job,
                    description="毎時のサーバーヘルスチェック",
                )
            if self.server_home.enabled:
                print("[ServerHome] ✓ サーバーホーム初期化", flush=True)
        except Exception as e:
            print(f"[ServerHome] 初期化失敗: {e}", flush=True)
            self.server_home = None

        # Sprint J: サーバーAI環境
        try:
            if getattr(self, "server_home", None) and self.server_home.enabled:
                from core.server_ai_env import (
                    ServerAIEnv, KnowledgeSync, PrometheusReader,
                    build_sync_job, build_server_health_job,
                )
                self.server_ai_env = ServerAIEnv(self.server_home)
                self.knowledge_sync = KnowledgeSync(self.base_dir, self.server_home)
                self.prometheus = PrometheusReader(self.server_home)
                if self.autonomous is not None:
                    self.autonomous.register(
                        name="knowledge_sync",
                        cadence="every_6h",
                        fn=build_sync_job(self.knowledge_sync),
                        description="6時間ごとの知識同期",
                    )
                    self.autonomous.register(
                        name="server_metrics",
                        cadence="hourly",
                        fn=build_server_health_job(self.prometheus),
                        description="毎時のサーバーメトリクス取得",
                    )
            else:
                self.server_ai_env = None
                self.knowledge_sync = None
                self.prometheus = None
        except Exception as e:
            print(f"[ServerAIEnv] 初期化失敗: {e}", flush=True)
            self.server_ai_env = None
            self.knowledge_sync = None
            self.prometheus = None

        # ─── Sprint J: 自律行動 ─────────────────────────────
        try:
            from core.autonomous_actions import AutonomousActions
            self.autonomous_actions = AutonomousActions(self.base_dir, cfg)
            if self.autonomous is not None:
                diary_enricher = self.autonomous_actions.diary_enricher
                if diary_enricher is not None:
                    self.autonomous.register(
                        name="diary_enrich",
                        cadence="daily",
                        fn=lambda: diary_enricher.enrich_daily_diary(self),
                        hour=3, minute=30,
                        description="日記品質強化",
                    )
            print("[AutonomousActions] ✓ 自律行動を初期化", flush=True)
        except Exception as e:
            print(f"[AutonomousActions] 初期化失敗: {e}", flush=True)
            self.autonomous_actions = None

        # ─── Sprint K: 国産AI進化パック ────────────────────────
        try:
            from core.conversation_intelligence import ConversationIntelligence
            self.conv_intelligence = ConversationIntelligence()
            print("[ConvIntelligence] ✓ 会話知能エンジンを初期化", flush=True)
        except Exception as e:
            print(f"[ConvIntelligence] 初期化失敗: {e}", flush=True)
            self.conv_intelligence = None

        try:
            from core.knowledge_graph import KnowledgeGraph
            self.knowledge_graph = KnowledgeGraph(self.base_dir)
            print(f"[KnowledgeGraph] ✓ 知識グラフを初期化（{self.knowledge_graph.entity_count}エンティティ）", flush=True)
        except Exception as e:
            print(f"[KnowledgeGraph] 初期化失敗: {e}", flush=True)
            self.knowledge_graph = None

        try:
            from core.personality_evolution import PersonalityEvolution
            self.personality_evo = PersonalityEvolution(self.base_dir)
            print(f"[PersonalityEvo] ✓ 性格進化システムを初期化（関係性: {self.personality_evo.relationship.level_label()}）", flush=True)
        except Exception as e:
            print(f"[PersonalityEvo] 初期化失敗: {e}", flush=True)
            self.personality_evo = None

        try:
            from core.response_evaluator import ResponseEvaluator
            self.response_evaluator = ResponseEvaluator(self.base_dir)
            print("[ResponseEval] ✓ 応答品質評価を初期化", flush=True)
        except Exception as e:
            print(f"[ResponseEval] 初期化失敗: {e}", flush=True)
            self.response_evaluator = None

        # ─── ヤマト計画: 国産AI進化基盤 ──────────────────────────
        try:
            from core.moe_router import MoERouter
            models_dir = self.base_dir / "models"
            self.moe_router = MoERouter(models_dir, cfg.get("llm", {}))
            count = self.moe_router.expert_count
            print(f"[MoERouter] ✓ 専門家ルーターを初期化（{count}モデル発見）", flush=True)
        except Exception as e:
            print(f"[MoERouter] 初期化失敗: {e}", flush=True)
            self.moe_router = None

        try:
            from core.continuous_learner import ContinuousLearner
            self.continuous_learner = ContinuousLearner(self.base_dir)
            count = self.continuous_learner.example_count
            print(f"[ContinuousLearner] ✓ 継続学習エンジンを初期化（{count}例）", flush=True)
        except Exception as e:
            print(f"[ContinuousLearner] 初期化失敗: {e}", flush=True)
            self.continuous_learner = None

        try:
            from core.yamato_architecture import YamatoArchitecture
            self.yamato_arch = YamatoArchitecture(self.base_dir)
            self._register_yamato_health_checks()
            print("[YamatoArch] ✓ 7層アーキテクチャ基盤を初期化", flush=True)
        except Exception as e:
            print(f"[YamatoArch] 初期化失敗: {e}", flush=True)
            self.yamato_arch = None

        try:
            from core.synthetic_data_gen import SyntheticDataGenerator
            self.synthetic_gen = SyntheticDataGenerator(self.base_dir)
            print(f"[SyntheticGen] ✓ 合成データ生成を初期化（{self.synthetic_gen.generated_count}例）", flush=True)
        except Exception as e:
            print(f"[SyntheticGen] 初期化失敗: {e}", flush=True)
            self.synthetic_gen = None

        try:
            from core.multi_agent_verifier import MultiAgentVerifier
            self.multi_verifier = MultiAgentVerifier(self.base_dir)
            print(f"[MultiVerifier] ✓ マルチエージェント検証を初期化（{self.multi_verifier.agent_count}エージェント）", flush=True)
        except Exception as e:
            print(f"[MultiVerifier] 初期化失敗: {e}", flush=True)
            self.multi_verifier = None

        # ─── データエクスポーター ────────────────────────────
        try:
            from core.data_exporter import DataExporter
            self.data_exporter = DataExporter(
                db_path=self.base_dir / "data" / "memories.db",
                learning_path=self.base_dir / "data" / "continuous_learning.json",
            )
            print("[DataExporter] ✓ データエクスポーターを初期化", flush=True)
        except Exception as e:
            print(f"[DataExporter] 初期化失敗: {e}", flush=True)
            self.data_exporter = None

        # ─── サウンドマネージャー ──────────────────────────────
        try:
            from core.sound import SoundManager
            sound_enabled = cfg.get("sound", {}).get("enabled", True)
            self.sound = SoundManager(enabled=sound_enabled)
            print(f"[Sound] ✓ サウンドマネージャーを初期化（{'有効' if sound_enabled else '無効'}）", flush=True)
        except Exception as e:
            print(f"[Sound] 初期化失敗: {e}", flush=True)
            self.sound = None

        # ─── システムヘルスチェック ────────────────────────────
        try:
            from core import health_check as health_check_mod
            self.health_check = health_check_mod
            if getattr(self, "autonomous", None) is not None:
                self.autonomous.register(
                    name="system_health_check",
                    cadence="every_6h",
                    fn=health_check_mod.run,
                    description="6時間ごとのシステムヘルスチェック",
                )
            print("[HealthCheck] ✓ システムヘルスチェックを初期化", flush=True)
        except Exception as e:
            print(f"[HealthCheck] 初期化失敗: {e}", flush=True)
            self.health_check = None

        # ─── パーソナリティカード ──────────────────────────────
        try:
            from core import personality_card as personality_card_mod
            self.personality_card = personality_card_mod
            print("[PersonalityCard] ✓ パーソナリティカードを初期化", flush=True)
        except Exception as e:
            print(f"[PersonalityCard] 初期化失敗: {e}", flush=True)
            self.personality_card = None

        # ─── ユーザープロファイル管理 ──────────────────────────
        try:
            from core.user_profile_mgr import UserProfileManager
            self.user_profile_mgr = UserProfileManager(
                profiles_dir=self.base_dir / "data" / "profiles",
            )
            profiles = self.user_profile_mgr.list_profiles()
            if profiles:
                print(f"[UserProfile] ✓ ユーザープロファイル管理を初期化（{len(profiles)}件）", flush=True)
            else:
                print("[UserProfile] ✓ ユーザープロファイル管理を初期化", flush=True)
        except Exception as e:
            print(f"[UserProfile] 初期化失敗: {e}", flush=True)
            self.user_profile_mgr = None

        # ─── ミドルウェアチェーン ────────────────────────────────
        try:
            from core.middleware import MiddlewareChain, ConversationContext  # noqa: F401
            from core import injection_guard as _inj_guard
            self.middleware_chain = MiddlewareChain()

            # pre-processing: インジェクションガードをミドルウェアとして登録
            def _mw_injection_guard(ctx: ConversationContext) -> ConversationContext:
                _safe, sanitized = _inj_guard.check(ctx.input_text)
                return ConversationContext(
                    input_text=sanitized,
                    intent=ctx.intent,
                    memory_context=ctx.memory_context,
                    emotion_state=dict(ctx.emotion_state),
                    llm_params=dict(ctx.llm_params),
                    response=ctx.response,
                    metadata={**ctx.metadata, "injection_safe": _safe},
                    should_skip_llm=ctx.should_skip_llm,
                )
            _mw_injection_guard.__name__ = "injection_guard"
            self.middleware_chain.add(_mw_injection_guard)

            # post-processing: 応答クリーニングをミドルウェアとして登録
            _rp = getattr(self, "response_pipeline", None)
            if _rp is not None:
                def _mw_clean_response(ctx: ConversationContext) -> ConversationContext:
                    return ConversationContext(
                        input_text=ctx.input_text,
                        intent=ctx.intent,
                        memory_context=ctx.memory_context,
                        emotion_state=dict(ctx.emotion_state),
                        llm_params=dict(ctx.llm_params),
                        response=_rp.clean_response(ctx.response),
                        metadata=dict(ctx.metadata),
                        should_skip_llm=ctx.should_skip_llm,
                    )
                _mw_clean_response.__name__ = "clean_response"
                self.middleware_chain.add(_mw_clean_response)

            print(f"[Middleware] ✓ ミドルウェアチェーンを初期化（{self.middleware_chain.count}件登録）", flush=True)
        except Exception as e:
            print(f"[Middleware] 初期化失敗: {e}", flush=True)
            self.middleware_chain = None

        # ─── プラグインローダー ───────────────────────────────
        try:
            from core.plugin_loader import PluginLoader
            self.plugin_loader = PluginLoader(
                bus=self._event_bus,
                plugin_dir=self.base_dir / "core" / "plugins",
            )
            loaded = self.plugin_loader.load_all()
            print(f"[PluginLoader] ✓ プラグインを{len(loaded)}件ロード", flush=True)
        except Exception as e:
            print(f"[PluginLoader] 初期化失敗: {e}", flush=True)
            self.plugin_loader = None

        # ─── プロンプト A/B テスト ────────────────────────────
        try:
            from core.prompt_ab_test import PromptABTest
            self.prompt_ab_test = PromptABTest(
                state_path=self.base_dir / "data" / "ab_test_state.json",
            )
            stats = self.prompt_ab_test.get_stats()
            print(f"[PromptABTest] ✓ A/Bテストを初期化（会話数: {stats['total_conversations']}）", flush=True)
        except Exception as e:
            print(f"[PromptABTest] 初期化失敗: {e}", flush=True)
            self.prompt_ab_test = None

        # ─── Sprint 1: Web リサーチ / 画像生成 / タスク分解 ──────
        try:
            from core.research_agent import ResearchAgent
            self.research_agent = ResearchAgent(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
            )
            print("[ResearchAgent] ✓ Web リサーチエージェントを初期化", flush=True)
        except Exception as e:
            print(f"[ResearchAgent] 初期化失敗: {e}", flush=True)
            self.research_agent = None

        try:
            from core.image_gen import ImageGenerator
            self.image_gen = ImageGenerator(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
            )
            print("[ImageGen] ✓ 画像生成エンジンを初期化", flush=True)
        except Exception as e:
            print(f"[ImageGen] 初期化失敗: {e}", flush=True)
            self.image_gen = None

        try:
            from core.task_agent import TaskAgent
            self.task_agent_sprint1 = TaskAgent(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
                research_agent=getattr(self, "research_agent", None),
                image_gen=getattr(self, "image_gen", None),
            )
            print("[TaskAgent] ✓ タスク分解エージェントを初期化", flush=True)
        except Exception as e:
            print(f"[TaskAgent] 初期化失敗: {e}", flush=True)
            self.task_agent_sprint1 = None

        # ─── Sprint 2: WebBuilder / CodeReviewer / DocAgent ──────
        try:
            from core.web_builder import WebBuilder
            self.web_builder = WebBuilder(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
            )
            print("[WebBuilder] ✓ ウェブ構築エージェントを初期化", flush=True)
        except Exception as e:
            print(f"[WebBuilder] 初期化失敗: {e}", flush=True)
            self.web_builder = None

        try:
            from core.code_reviewer import CodeReviewer
            self.code_reviewer_sprint2 = CodeReviewer(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
            )
            print("[CodeReviewer] ✓ コードレビューエージェントを初期化", flush=True)
        except Exception as e:
            print(f"[CodeReviewer] 初期化失敗: {e}", flush=True)
            self.code_reviewer_sprint2 = None

        try:
            from core.doc_agent import DocAgent
            self.doc_agent = DocAgent(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
            )
            print("[DocAgent] ✓ 書類作成エージェントを初期化", flush=True)
        except Exception as e:
            print(f"[DocAgent] 初期化失敗: {e}", flush=True)
            self.doc_agent = None

        # ─── Sprint 3&4: ニュース / スケジュール / 競合分析 / BGM / クリップボード ──
        try:
            from core.sprint34_handlers import Sprint34Handler
            self.sprint34_handler = Sprint34Handler(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
                emotion_engine=getattr(self, "emotion", None),
                research_agent=getattr(self, "research_agent", None),
            )
            print("[Sprint34] ✓ Sprint 3&4 ハンドラを初期化", flush=True)
        except Exception as e:
            print(f"[Sprint34] 初期化失敗: {e}", flush=True)
            self.sprint34_handler = None

        # ─── Akashic Core: 統一意味場・量子的推論・フレーム破壊 ──
        try:
            from core.akashic_core import AkashicCore
            self.akashic = AkashicCore(
                base_dir=self.base_dir,
                llm_fn=self._llm_call,
                depth=2,  # デフォルト深度2（統一場+量子推論）。設定で変更可
            )
            print("[AkashicCore] ✓ アカシックコアを初期化（深度2）", flush=True)
        except Exception as e:
            print(f"[AkashicCore] 初期化失敗（フォールバックモードで継続）: {e}", flush=True)
            self.akashic = None

        # ─── 起動完了サウンド ──────────────────────────────────
        if getattr(self, "sound", None) is not None:
            try:
                self.sound.play_greeting()
            except Exception:
                pass

        self._heavy_initialized = True

    # ─── ヤマトヘルスチェック ─────────────────────────────────

    def _register_yamato_health_checks(self) -> None:
        """7層アーキテクチャにヘルスチェックを登録する"""
        arch = self.yamato_arch
        if arch is None:
            return

        def check_l2() -> dict:
            moe = getattr(self, "moe_router", None)
            if moe is None:
                return {"status": "offline", "message": "MoEルーター未初期化"}
            count = moe.expert_count
            return {
                "status": "ok" if count > 0 else "warn",
                "message": f"{count}モデル登録済み",
                "expert_count": count,
            }
        arch.register_health_check(2, check_l2)

        def check_l3() -> dict:
            metrics: dict = {}
            kg = getattr(self, "knowledge_graph", None)
            if kg:
                metrics["kg_entities"] = kg.entity_count
                metrics["kg_relations"] = kg.relation_count
            mem = getattr(self, "memory", None)
            if mem:
                try:
                    stats = mem.get_stats()
                    metrics["memories"] = stats.get("total", 0)
                except Exception:
                    pass
            return {"status": "ok", "message": "データ管理正常", **metrics}
        arch.register_health_check(3, check_l3)

        def check_l4() -> dict:
            llm = getattr(self, "llm", None)
            if llm is None:
                return {"status": "error", "message": "LLMエンジン未初期化"}
            loaded = llm.is_loaded() if hasattr(llm, "is_loaded") else False
            return {
                "status": "ok" if loaded else "warn",
                "message": "モデルロード済み" if loaded else "モデル未ロード（テンプレート応答モード）",
            }
        arch.register_health_check(4, check_l4)

        def check_l5() -> dict:
            cl = getattr(self, "continuous_learner", None)
            if cl is None:
                return {"status": "offline", "message": "継続学習エンジン未初期化"}
            stats = cl.get_stats()
            return {
                "status": "ok",
                "message": f"{stats['total_examples']}例学習済み",
                "examples": stats["total_examples"],
            }
        arch.register_health_check(5, check_l5)

        def check_l6() -> dict:
            ev = getattr(self, "response_evaluator", None)
            mv = getattr(self, "multi_verifier", None)
            parts = []
            if ev:
                parts.append("品質評価✓")
            if mv:
                parts.append(f"マルチ検証✓({mv.agent_count})")
            if not parts:
                return {"status": "offline", "message": "推論最適化未初期化"}
            return {"status": "ok", "message": ", ".join(parts)}
        arch.register_health_check(6, check_l6)

        def check_l7() -> dict:
            return {
                "status": "ok",
                "message": f"ターン数: {self.turn_count}",
                "turn_count": self.turn_count,
            }
        arch.register_health_check(7, check_l7)

    # ─── Sprint 1: LLM シンプル呼び出しヘルパー ────────────────

    def _llm_call(self, prompt: str) -> str:
        """単純なプロンプト文字列で LLM を呼び出すヘルパー。

        ResearchAgent / ImageGenerator / TaskAgent から使われる。
        LLM が未ロードの場合は空文字を返す（フォールバック動作は各呼び出し側で処理）。
        """
        if not getattr(self, "llm", None) or not self.llm.is_loaded():
            logger.warning("[_llm_call] LLM が未ロード")
            return ""
        try:
            messages = self.llm.build_prompt(
                system_prompt="あなたは有能なアシスタントです。",
                user_input=prompt,
                conversation_history=[],
            )
            return self.llm.generate_chat(messages)
        except Exception as exc:
            logger.warning("[_llm_call] LLM 呼び出し失敗: %s", exc)
            return ""

    # ─── 自律エンジン制御 ─────────────────────────────────────

    def start_autonomous(self) -> bool:
        if self.autonomous is None:
            return False
        self.autonomous.start()
        return True

    def stop_autonomous(self) -> None:
        if self.autonomous is not None:
            self.autonomous.stop()

    # ──────────────────────────────────────────────────────────
    # Initiative Driver 補助
    # ──────────────────────────────────────────────────────────

    def _build_initiative_context(self) -> dict:
        """InitiativeDriver に渡す現在コンテキスト。"""
        try:
            emotion = getattr(self, "emotion", None)
            current_emotion = emotion.current_emotion if emotion else "calm"
        except Exception:
            current_emotion = "calm"
        return {
            "turn_count": getattr(self, "turn_count", 0),
            "current_emotion": current_emotion,
            "recent_history_len": len(getattr(self, "conversation_history", [])),
            "growth_stage": getattr(getattr(self, "growth", None), "stage_name", ""),
        }

    def attach_desktop_channel(self, show_bubble=None, tts=None, speak_aloud: bool = True) -> None:
        """デスクトップペット起動時に呼ぶ。自発メッセージの吹き出し + TTS 配信を有効化。"""
        try:
            ch = DesktopChannel(show_bubble=show_bubble, tts=tts, speak_aloud=speak_aloud)
            self._broadcast_channel.add(ch)
            logger.info("DesktopChannel attached to InitiativeDriver")
        except Exception as e:
            logger.warning("attach_desktop_channel 失敗: %s", e)

    def attach_voice_channel(self, tts, is_active_fn=None) -> None:
        """ハンズフリー音声モード用 VoiceChannel を追加。"""
        try:
            ch = VoiceChannel(tts=tts, is_active_fn=is_active_fn)
            self._broadcast_channel.add(ch)
            logger.info("VoiceChannel attached to InitiativeDriver")
        except Exception as e:
            logger.warning("attach_voice_channel 失敗: %s", e)

    def poll_initiative_messages(self, max_items: int = 10) -> list:
        """Web UI から呼び出し、キューイング済みの自発メッセージを取り出す。"""
        try:
            return self._web_initiative_channel.drain(max_items=max_items)
        except Exception as e:
            logger.warning("poll_initiative_messages 失敗: %s", e)
            return []

    def shutdown(self) -> None:
        """全体の終了処理。"""
        try:
            if getattr(self, "initiative_driver", None):
                self.initiative_driver.stop()
        except Exception as e:
            logger.warning("InitiativeDriver stop 失敗: %s", e)
        try:
            self.stop_autonomous()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────
    # 対話処理
    # ──────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """システムプロンプト組み立て（MemoryContextBuilder に委譲）"""
        return self._ctx_builder.build_system_prompt()

    def _build_memory_context(self, user_input: str) -> str:
        """記憶コンテキスト組み立て（MemoryContextBuilder に委譲）"""
        return self._ctx_builder.build_memory_context(user_input)

    def _clean_response(self, text: str) -> str:
        """応答クリーニング（ResponsePipeline に委譲）"""
        return self._resp_pipeline.clean_response(text)

    def _estimate_response_quality(self, user_input: str, response: str) -> float:
        """品質推定（ResponsePipeline に委譲）"""
        return self._resp_pipeline.estimate_response_quality(user_input, response)

    def _handle_commands(self, user_input: str) -> str | None:
        """コマンドディスパッチ（CommandHandler に委譲）"""
        return self._cmd_handler.try_handle(user_input)

    # ──────────────────────────────────────────────────────────
    # Item #1: 動的スライディングウィンドウ (5-15 turns)
    # ──────────────────────────────────────────────────────────

    def _select_relevant_history(self, max_turns: int = 10) -> list[dict]:
        """
        重要度に基づく動的スライディングウィンドウ。
        - 短い相槌のターンは重要度が低い → ウィンドウを広げる
        - 長い質問・感情的なターンは重要度が高い → ウィンドウを狭める
        基本は max_turns だが 5~15 の範囲で動的に調整する。
        """
        history = self.conversation_history
        if not history:
            return []

        # 直近ターンの平均メッセージ長で重要度を推定
        recent_user = [
            m for m in history[-10:]
            if m.get("role") == "user"
        ]
        if recent_user:
            avg_len = sum(len(m["content"]) for m in recent_user) / len(recent_user)
        else:
            avg_len = 10.0

        # 短い会話ほどウィンドウを広げる（軽い相槌 → 多くのコンテキストが要る）
        # 長い会話ほどウィンドウを狭める（1つの話題に集中）
        if avg_len < 8:
            dynamic_turns = min(15, max_turns + 3)
        elif avg_len > 40:
            dynamic_turns = max(5, max_turns - 3)
        else:
            dynamic_turns = max_turns

        dynamic_turns = max(5, min(15, dynamic_turns))
        max_messages = dynamic_turns * 2

        if len(history) <= max_messages:
            return list(history)
        return list(history[-max_messages:])

    # ──────────────────────────────────────────────────────────
    # Item #22: JSONL 会話ログ
    # ──────────────────────────────────────────────────────────

    def _log_conversation_jsonl(
        self, user_input: str, response: str, metadata: dict | None = None,
    ) -> None:
        """会話を JSONL 形式でファイルに追記する"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "turn": self.turn_count,
            "user": user_input,
            "ai": response,
        }
        if metadata:
            entry["meta"] = metadata
        try:
            with open(self._conv_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("JSONL会話ログ書き込み失敗")

    # ──────────────────────────────────────────────────────────
    # 起動/チャット開始時の自然な挨拶プロンプト組み立て
    # ──────────────────────────────────────────────────────────

    def build_greeting_prompt(self, trigger: str = "startup") -> str:
        """時間帯と直近の会話文脈から自然な挨拶プロンプトを組み立てる。

        trigger: "startup"(アプリ起動) / "chat_open"(チャット欄を開いた)
        """
        from datetime import datetime
        hour = datetime.now().hour

        # 時間帯に合った挨拶の方向性
        if 5 <= hour < 11:
            time_hint = "朝なので「おはよう」系の軽い挨拶"
        elif 11 <= hour < 17:
            time_hint = "昼間なので「こんにちは」か気軽な声かけ"
        elif 17 <= hour < 22:
            time_hint = "夕方〜夜なので「おかえり」「お疲れさま」系"
        else:
            time_hint = "深夜なので「まだ起きてるの？」的な軽い声かけ"

        # 直近の会話ログから最後の話題を取得
        last_topic_hint = ""
        try:
            log_path = self.base_dir / "data" / "conversation_log.jsonl"
            if log_path.exists():
                lines = log_path.read_text("utf-8").strip().splitlines()
                if lines:
                    last_entry = json.loads(lines[-1])
                    last_user = last_entry.get("user", "")
                    last_ai = last_entry.get("ai", "")
                    # システムコールは除外
                    if last_user and "一言だけ" not in last_user and "挨拶" not in last_user:
                        last_topic_hint = (
                            f"前回の会話:「{last_user[:40]}」→「{last_ai[:40]}」。"
                            "自然に前の話題に触れてもいい。"
                        )
        except Exception:
            pass

        # プロンプト組み立て
        parts = [f"{time_hint}で一言だけ自然に声をかけて。"]
        if last_topic_hint:
            parts.append(last_topic_hint)
        else:
            parts.append("特に前の話題はないので、シンプルな挨拶だけで大丈夫。")
        parts.append("質問攻めにしないで。短く、人間が自然にやる感じで。")

        return "".join(parts)

    # ──────────────────────────────────────────────────────────
    # Item #72: 感情リンクプロンプト
    # ──────────────────────────────────────────────────────────

    def _get_emotion_prompt(self, intent_type: str) -> str:
        """意図に応じた感情プロンプトを返す"""
        return _EMOTION_PROMPTS.get(intent_type, "")

    # ──────────────────────────────────────────────────────────
    # Item #82: 意図によるプロンプト重み付け
    # ──────────────────────────────────────────────────────────

    def _apply_intent_weighting(
        self, memory_context: str, intent_type: str,
    ) -> str:
        """
        意図に基づいて記憶コンテキストの情報量を調整する。
        memory_weight が低い意図では記憶コンテキストを短縮する。
        """
        weights = _INTENT_WEIGHTS.get(intent_type, {"memory_weight": 0.7, "persona_weight": 0.8})
        mw = weights["memory_weight"]
        if mw < 0.5 and len(memory_context) > 50:
            # 記憶の重要度が低い意図 → コンテキストを大幅に短縮
            max_len = int(len(memory_context) * mw)
            return memory_context[:max(30, max_len)]
        return memory_context

    # ──────────────────────────────────────────────────────────
    # D-2 / E-1: Memory Honesty 統合
    # ──────────────────────────────────────────────────────────

    # 「覚えてる?」「〜だっけ?」系クエリ検出
    _HONESTY_QUERY_PATTERNS = (
        "覚えてる", "覚えてない", "覚えてますか",
        "だっけ", "だったっけ", "じゃなかったっけ",
        "何だっけ", "なんだっけ", "どこだっけ", "いつだっけ",
    )

    def _map_growth_to_subjective_stage(self) -> str:
        """GrowthStage (INFANT..MATURE) → memory_phrasing Stage (S0..S3)."""
        try:
            s = int(self.growth.stage)
        except Exception:
            return "S1"
        if s <= 1:
            return "S0"
        if s == 2:
            return "S1"
        if s == 3:
            return "S2"
        return "S3"

    def _is_memory_recall_query(self, text: str) -> bool:
        """入力が記憶想起クエリかどうか。"""
        if not text:
            return False
        # 疑問符が無くてもパターンで判定 (感情タグ込み想定)
        return any(p in text for p in self._HONESTY_QUERY_PATTERNS)

    def _try_memory_honesty_response(self, user_input: str) -> str | None:
        """none-band (低信頼度) のときだけ早期に honest 応答を返す。

        high/mid/low 帯は通常フローで memory_context を充実させて LLM に投げる方が
        家族らしい応答になるため、ここでは介入しない。
        """
        if not self._is_memory_recall_query(user_input):
            return None
        try:
            stage = self._map_growth_to_subjective_stage()
            subject = getattr(self, "_last_speaker_tag", None) or None
            recent = [
                h.get("content", "")
                for h in self.conversation_history[-4:]
                if h.get("role") == "user"
            ]
            phrase, conf = self.memory.respond_about_memory(
                user_input, stage=stage, subject=subject, recent=recent,
            )
        except Exception as exc:
            logger.debug("memory-honesty skip: %s", exc)
            return None
        # 信頼度が "none" 帯 (<0.3) のときだけ早期リターン
        if conf < 0.3:
            logger.info("memory-honesty early-return: conf=%.2f stage=%s", conf, stage)
            return phrase
        return None

    # ──────────────────────────────────────────────────────────
    # メインの chat メソッド
    # ──────────────────────────────────────────────────────────

    def chat(
        self,
        user_input: str,
        stream_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """ユーザーの入力を受け取り、アイの応答を返す。

        Args:
            user_input: ユーザー発話テキスト
            stream_cb:  トークンを受け取るコールバック（E-05ストリーミング用）。
                        Noneの場合は従来通り全文生成後に返す。
        """

        # Item #92: 入力サニタイズ
        user_input = sanitize_input(user_input)
        if not user_input:
            return ""

        # 自発性ドライバー: ユーザー発話を通知（抑制タイマー更新）
        if getattr(self, "initiative_driver", None):
            try:
                self.initiative_driver.notify_user_input()
            except Exception:
                pass

        # Phase D: 話者タグ解析 — "[しょうた] こんにちは" → speaker="しょうた"
        _speaker_tag = ""
        _speaker_match = re.match(r'^\[([^\]]+)\]\s*(.+)$', user_input, re.DOTALL)
        if _speaker_match:
            _speaker_tag = _speaker_match.group(1)
            user_input = _speaker_match.group(2).strip()

        self.turn_count += 1

        # ─── モード切替検出 ───
        if getattr(self, "mode_manager", None):
            self.mode_manager.record_turn()
            detected_mode = self.mode_manager.detect_mode_intent(user_input)
            if detected_mode and detected_mode != self.mode_manager.current_mode:
                switch_msg = self.mode_manager.switch_mode(detected_mode)
                if switch_msg:
                    self.conversation_history.append({"role": "user", "content": user_input})
                    self.conversation_history.append({"role": "assistant", "content": switch_msg})
                    self._log_conversation_jsonl(user_input, switch_msg, {"mode_switch": detected_mode})
                    return switch_msg
            # 成長保護: エージェントモード使いすぎ警告
            growth_warning = self.mode_manager.check_growth_balance()
            if growth_warning:
                self._pending_greeting = growth_warning
            # 30分以上の作業モード自動復帰提案
            auto_return = self.mode_manager.get_auto_return_suggestion()
            if auto_return:
                self._pending_greeting = auto_return

        # Sprint J: ユーザー操作を記録
        if getattr(self, "autonomous_actions", None):
            self.autonomous_actions.on_user_interaction()

        # 挨拶プロンプト（動的生成含む）をシステムコールとして判定
        _system_markers = ("一言だけ自然に", "短く一言", "一言挨拶", "自然に声をかけて")
        is_system_call = any(m in user_input for m in _system_markers)

        # Sprint J: 時間帯挨拶チェック
        if not is_system_call and getattr(self, "autonomous_actions", None):
            aa = self.autonomous_actions
            if aa.greeting and self._pending_greeting is None:
                greeting = aa.greeting.get_time_greeting()
                if greeting:
                    self._pending_greeting = greeting

        # 特殊コマンドを処理
        cmd_response = self._handle_commands(user_input)
        if cmd_response is not None:
            return cmd_response

        # ─── Sprint 1: リサーチ / 画像生成 / タスク分解 ──────────
        if not is_system_call:
            sprint1_response = self._handle_sprint1(user_input)
            if sprint1_response is not None:
                return sprint1_response

        # ─── Sprint 2: WebBuilder / CodeReviewer / DocAgent ──────
        if not is_system_call:
            sprint2_response = self._handle_sprint2(user_input)
            if sprint2_response is not None:
                return sprint2_response

        # ─── Sprint 3&4: ニュース / スケジュール / 競合分析 / BGM / クリップボード ──
        if not is_system_call:
            sprint34_response = self._handle_sprint34(user_input)
            if sprint34_response is not None:
                return sprint34_response

        # ─── Akashic: 深い問いへのアカシック共鳴チェック ──────
        if not is_system_call and getattr(self, "akashic", None) is not None:
            user_input = self._akashic_enrich_context(user_input)

        # ── ユーザー訂正検出 ──
        _correction_entry = None
        _correction_context = ""
        if getattr(self, "correction_learning", None) and not is_system_call:
            _correction_entry = self.correction_learning.detect_correction(user_input)
            if _correction_entry:
                _correction_context = self.correction_learning.build_correction_context(
                    _correction_entry
                )

        # 感情を更新
        self.emotion.update_from_message(user_input)

        # ── E-1: Memory Honesty 早期応答 (none-band のみ) ──
        if not is_system_call and not _correction_entry:
            _honesty_reply = self._try_memory_honesty_response(user_input)
            if _honesty_reply:
                self.conversation_history.append({"role": "user", "content": user_input})
                self.conversation_history.append({"role": "assistant", "content": _honesty_reply})
                try:
                    if hasattr(self.tts, "speak_with_emotion_analysis"):
                        _ed = self.emotion.state.to_dict() if hasattr(self.emotion.state, "to_dict") else {}
                        self.tts.speak_with_emotion_analysis(_honesty_reply, _ed)
                    else:
                        self.tts.speak_sentence_by_sentence(_honesty_reply)
                except Exception:
                    pass
                self._log_conversation_jsonl(
                    user_input, _honesty_reply, {"layer": "memory_honesty"},
                )
                if len(self.conversation_history) > 12:
                    self.conversation_history = self.conversation_history[-12:]
                return _honesty_reply

        # ── 生物神経系: 反射 → 大脳(LLM) ──
        if getattr(self, "bio_nervous", None) and not is_system_call and not _correction_entry:
            bio_response, layer = self.bio_nervous.process_input(user_input)
            if bio_response is not None:
                self.conversation_history.append({"role": "user", "content": user_input})
                self.conversation_history.append({"role": "assistant", "content": bio_response})
                self.bio_nervous.autonomic.heartbeat(self.turn_count)
                try:
                    if hasattr(self.tts, "speak_with_emotion_analysis"):
                        emotion_dict = self.emotion.state.to_dict() if hasattr(self.emotion.state, "to_dict") else {}
                        self.tts.speak_with_emotion_analysis(bio_response, emotion_dict)
                    else:
                        self.tts.speak_sentence_by_sentence(bio_response)
                except Exception:
                    pass
                if not is_system_call:
                    self.topic_tracker.extract_topics(user_input, self.turn_count)
                    self.emotion.save_if_changed()
                    if getattr(self, "correction_learning", None):
                        self.correction_learning.record_turn(user_input, bio_response)
                    # Item #22: JSONL ログ
                    self._log_conversation_jsonl(user_input, bio_response, {"layer": "reflex"})
                if len(self.conversation_history) > 12:
                    self.conversation_history = self.conversation_history[-12:]
                return bio_response

        # Sprint K1: 会話知能分析
        conv_analysis = None
        _intent_type = "chat"
        if getattr(self, "conv_intelligence", None):
            try:
                conv_analysis = self.conv_intelligence.analyze_input(
                    user_input, self.conversation_history, self.turn_count
                )
                if conv_analysis and conv_analysis.get("intent"):
                    _intent_type = conv_analysis["intent"].intent_type
            except Exception:
                pass

        # BUG #3 FIX: instruction_text を extra_parts に事前登録（後で emotion_prompt と合流）
        _conv_instruction: str = ""
        if conv_analysis and conv_analysis.get("instruction_text"):
            _conv_instruction = conv_analysis["instruction_text"]

        # ヤマト A1: MoEルーティング
        _growth = getattr(self, "growth", None)
        _moe_ok = not _growth or _growth.can_use_moe_routing()
        _moe_task_type = "chat"
        _moe_saved_params: dict | None = None
        if _moe_ok and getattr(self, "moe_router", None) and self.moe_router.expert_count > 0:
            try:
                if conv_analysis and conv_analysis.get("intent"):
                    _moe_task_type = conv_analysis["intent"].intent_type
                if self.moe_router.expert_count > 1:
                    self.moe_router.apply_routing(
                        _moe_task_type, self.llm,
                    )
                optimal = self.moe_router.get_optimal_params(_moe_task_type)
                if optimal and hasattr(self.llm, "override_params"):
                    _moe_saved_params = self.llm.override_params(optimal)
            except Exception as exc:
                logger.debug("MoEルーティングスキップ: %s", exc)

        # Sprint 3.0-B: 会話が長くなったら自動要約
        if getattr(self, "memory_summarizer", None):
            try:
                if self.memory_summarizer.should_summarize(self.conversation_history):
                    self.conversation_history = self.memory_summarizer.summarize_and_trim(
                        self.conversation_history,
                        llm=self.llm,
                        memory=self.memory,
                    )
            except Exception:
                pass

        # 記憶から関連情報を取得
        memory_context = self._build_memory_context(user_input)

        # Item #82: 意図に基づくプロンプト重み付け
        memory_context = self._apply_intent_weighting(memory_context, _intent_type)

        # ── 追加コンテキスト ──
        extra_parts: list[str] = []

        if _correction_context:
            extra_parts.append(_correction_context)
        elif getattr(self, "correction_learning", None):
            _corr_hint = self.correction_learning.get_recent_corrections_hint(max_entries=2)
            if _corr_hint:
                extra_parts.append(_corr_hint[:120])

        # 継続学習: 高品質会話例を1件だけ軽量注入
        cl = getattr(self, "continuous_learner", None)
        if cl and cl.example_count > 0 and not _correction_context:
            try:
                _topic = ""
                if getattr(self, "conv_intelligence", None):
                    ci = self.conv_intelligence
                    if ci.last_intent:
                        _topic = ci.last_intent.intent_type
                examples = cl.get_curriculum_examples(
                    n=1, topic=_topic, user_input=user_input
                )
                if examples:
                    ex = examples[0]
                    extra_parts.append(f"参考: {ex['user'][:30]}→{ex['ai'][:40]}")
            except Exception:
                pass

        # BUG #3 FIX: 会話知能の応答方針を注入（質問への具体的な回答指示）
        if _conv_instruction:
            extra_parts.append(_conv_instruction)

        # Item #72: 感情リンクプロンプトを追加
        emotion_prompt = self._get_emotion_prompt(_intent_type)
        if emotion_prompt:
            extra_parts.append(emotion_prompt)

        # ─── モード別プロンプト修飾 ───
        if getattr(self, "mode_manager", None):
            mode_modifier = self.mode_manager.get_mode_prompt_modifier()
            if mode_modifier:
                extra_parts.insert(0, mode_modifier)

        # 追加コンテキストを結合
        extra = "\n".join(extra_parts)
        if extra:
            memory_context = memory_context + "\n" + extra[:300]

        # 会話履歴に追加（Phase D: 話者名があれば含める）
        _hist_content = (
            f"{_speaker_tag}: {user_input}" if _speaker_tag else user_input
        )
        self.conversation_history.append({"role": "user", "content": _hist_content})

        # LLMでの応答生成
        recent_history = self._select_relevant_history(max_turns=10)
        messages = self.llm.build_prompt(
            system_prompt=self._build_system_prompt(),
            conversation_history=recent_history,
            memory_context=memory_context,
            emotion_hint="",
        )

        response = self.llm.generate_chat(messages, stream_cb=stream_cb)

        # MoEで一時変更したパラメータを復元
        if _moe_saved_params is not None and hasattr(self.llm, "restore_params"):
            self.llm.restore_params(_moe_saved_params)

        response = self._clean_response(response)

        # フォローアップトピック
        if getattr(self, "_pending_followup_topic", None):
            _ft = self._pending_followup_topic
            _ft_text = _ft.get("text", "")[:10] if isinstance(_ft, dict) else ""
            if _ft_text and _ft_text in response:
                self.topic_tracker.mark_followed_up(_ft)
            self._pending_followup_topic = None

        # Sprint K1: 会話知能による後処理
        if getattr(self, "conv_intelligence", None):
            try:
                response = self.conv_intelligence.post_process(response)
            except Exception:
                pass

        # Sprint K4: 応答品質自己評価
        _evaluated_quality = self._estimate_response_quality(user_input, response)

        # TTS（感情連動）
        try:
            if hasattr(self.tts, "speak_with_emotion_analysis"):
                emotion_dict = self.emotion.state.to_dict() if hasattr(self.emotion.state, "to_dict") else {}
                self.tts.speak_with_emotion_analysis(response, emotion_dict)
            else:
                self.tts.speak_sentence_by_sentence(response)
        except Exception:
            pass

        # 応答を履歴に追加
        self.conversation_history.append({"role": "assistant", "content": response})

        # ユーザー訂正学習
        if getattr(self, "correction_learning", None) and not is_system_call:
            self.correction_learning.record_turn(user_input, response)

        if not is_system_call:
            # 全会話をDBに永続保存
            importance = self._estimate_importance(user_input)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.memory.add_mid_term(
                content=f"[{timestamp}] ユーザー:「{user_input}」→ アイ:「{response}」",
                importance=importance,
                emotional_weight=self.emotion.state.affection,
                tags=["conversation", "auto_saved"],
            )

            # B: 話題を抽出して追跡
            self.topic_tracker.extract_topics(user_input, self.turn_count)

            # プロファイル自動深化
            self._extract_profile_hints(user_input)

            # Item #22: JSONL ログ
            self._log_conversation_jsonl(user_input, response, {
                "intent": _intent_type,
                "quality": _evaluated_quality,
                "mode": self.mode_manager.current_mode if getattr(self, "mode_manager", None) else "family",
            })

            # Item #19: バッチ更新を ThreadPoolExecutor で実行
            _ui = user_input
            _resp = response
            _tc = self.turn_count

            def _batch_updates():
                try:
                    self.emotion_history.record(self.emotion.state.to_dict())
                except Exception:
                    pass
                try:
                    self.interest_map.update(_ui)
                except Exception:
                    pass
                try:
                    self.goal_tracker.detect_and_add(_ui)
                except Exception:
                    pass
                try:
                    if self.semantic_search.is_ready():
                        recent = self.memory.get_recent(limit=1)
                        if recent:
                            self.semantic_search.add_memory(recent[0])
                except Exception:
                    pass
                today = datetime.now().date()
                if today != self._last_diary_date:
                    self._last_diary_date = today
                    try:
                        self.diary.write_today(
                            emotion_snapshot=self.emotion.state.to_dict()
                        )
                    except Exception:
                        pass
                ar = sum(1 for c in _resp if c.isascii() and c.isalpha()) / max(len(_resp), 1)
                if ar < 0.3 and len(_resp) > 2:
                    self.learning.add_conversation(_ui, _resp, save=True)
                if _tc % 10 == 0:
                    self.compressor.compress()
                self.emotion.save_if_changed()

                if getattr(self, "knowledge_graph", None):
                    try:
                        self.knowledge_graph.extract_from_conversation(_ui, _resp)
                    except Exception:
                        pass

                if getattr(self, "personality_evo", None):
                    try:
                        intent_type = ""
                        ci = getattr(self, "conv_intelligence", None)
                        if ci and ci.last_intent:
                            intent_type = ci.last_intent.intent_type
                        self.personality_evo.on_conversation(
                            _ui,
                            intent_type=intent_type,
                            hour=datetime.now().hour,
                        )
                    except Exception:
                        pass

                _q_score = _evaluated_quality if _evaluated_quality is not None else 0.6

                if getattr(self, "growth", None):
                    try:
                        self.growth.on_conversation(quality_score=_q_score)
                        kg = getattr(self, "knowledge_graph", None)
                        if kg and hasattr(kg, "total_entities"):
                            self.growth.on_knowledge_update(kg.total_entities)
                        if getattr(self, "topic_tracker", None):
                            topic_count = len(getattr(self.topic_tracker, "topics", []))
                            while self.growth._metrics.unique_topics < topic_count:
                                self.growth.on_new_topic()
                        if getattr(self, "emotion_history", None):
                            records = getattr(self.emotion_history, "_records", [])
                            if len(records) >= 5:
                                recent = records[-20:]
                                all_vals = []
                                for r in recent:
                                    all_vals.extend(
                                        v for k, v in r.items()
                                        if k not in ("timestamp",) and isinstance(v, (int, float))
                                    )
                                if all_vals:
                                    e_range = max(all_vals) - min(all_vals)
                                    self.growth.on_emotional_experience(e_range)
                        self.growth.save_if_changed()
                    except Exception:
                        pass

                if getattr(self, "action_cycle", None):
                    try:
                        self.action_cycle.record_progress("any", 1.0)
                        self.action_cycle.record_quality(_q_score)
                    except Exception:
                        pass

                if getattr(self, "self_correction", None):
                    try:
                        corrections = self.self_correction.on_turn(
                            quality_score=_q_score,
                            response=_resp,
                        )
                        if corrections and getattr(self, "growth", None):
                            for c in corrections:
                                if c.get("ok"):
                                    self.growth.on_error_recovery()
                            self.growth.save_if_changed()
                    except Exception:
                        pass

                if getattr(self, "continuous_learner", None):
                    try:
                        self.continuous_learner.learn_from_conversation(
                            _ui, _resp, quality_score=_q_score
                        )
                    except Exception:
                        pass

                if getattr(self, "synthetic_gen", None):
                    try:
                        intent = ""
                        ci = getattr(self, "conv_intelligence", None)
                        if ci and ci.last_intent:
                            intent = ci.last_intent.intent_type
                        self.synthetic_gen.learn_template_from_conversation(
                            _ui, _resp, intent=intent
                        )
                    except Exception:
                        pass

                if getattr(self, "federated", None):
                    try:
                        pattern = self.federated.extract_pattern(
                            [{"role": "user", "content": _ui},
                             {"role": "assistant", "content": _resp}],
                            quality_score=_q_score,
                        )
                        if pattern:
                            self.federated.queue_for_sync(pattern)
                    except Exception:
                        pass

                if getattr(self, "prompt_ab_test", None):
                    try:
                        ab_state = self.prompt_ab_test._state
                        current_variant = "B" if ab_state.next_variant == "A" else "A"
                        self.prompt_ab_test.record_score(current_variant, _q_score)
                    except Exception:
                        pass

            # Item #19: ThreadPoolExecutor で並列実行
            self._executor.submit(_batch_updates)

            # Item #1: 動的スライディングウィンドウでトリミング
            if len(self.conversation_history) > 30:
                self.conversation_history = self.conversation_history[-30:]
        else:
            self.conversation_history = self.conversation_history[:-2]

        # 生物神経系: 自律神経ハートビート
        if getattr(self, "bio_nervous", None):
            self.bio_nervous.autonomic.heartbeat(self.turn_count)

        # 自己意思: 保留中のメッセージ
        if getattr(self, "self_will", None):
            will_msg = self.self_will.pending_message
            if will_msg:
                response = f"{will_msg}\n\n{response}"

        # Sprint J: 保留中の時間帯挨拶
        if self._pending_greeting:
            response = f"{self._pending_greeting}\n\n{response}"
            self._pending_greeting = None

        return response

    # ──────────────────────────────────────────────────────────
    # セマンティック検索初期化（バックグラウンドスレッド用）
    # ──────────────────────────────────────────────────────────

    def _init_semantic_search(self) -> None:
        """モデルをロードし、既存記憶から FAISS インデックスを自動構築する。"""
        try:
            loaded = self.semantic_search.load()
            if not loaded:
                return

            # インデックスが空なら既存記憶から自動構築
            has_index = (
                self.semantic_search._index is not None
                and self.semantic_search._index.ntotal > 0
            )
            if not has_index:
                all_memories = self.memory.get_recent(limit=500)
                if all_memories:
                    self.semantic_search.rebuild_index(all_memories)
                    logger.info(
                        "セマンティック検索: %d 件の記憶からインデックスを自動構築",
                        len(all_memories),
                    )
        except Exception as exc:
            logger.warning("セマンティック検索の初期化に失敗: %s", exc)

    # ──────────────────────────────────────────────────────────
    # 記憶検索
    # ──────────────────────────────────────────────────────────

    def _search_relevant_memories(self, query: str, limit: int = 3):
        results = []
        if self.semantic_search.is_ready():
            try:
                all_mems = self.memory.get_recent(limit=50)
                results = self.semantic_search.search(query, all_mems, limit=limit)
            except Exception:
                pass
        if len(results) < limit:
            try:
                sql_results = self.memory.search_by_keywords(query, limit=limit)
                existing_ids = {r.id for r in results}
                for m in sql_results:
                    if m.id not in existing_ids:
                        results.append(m)
                        if len(results) >= limit:
                            break
            except Exception:
                pass
        return results[:limit]

    # ──────────────────────────────────────────────────────────
    # Sprint 2.1: セキュリティ機能
    # ──────────────────────────────────────────────────────────

    def _run_security_check(self) -> str:
        lines: list[str] = ["\U0001f6e1\ufe0f セキュリティ診断を実行するね！\n"]
        if getattr(self, "host_guardian", None):
            try:
                summary = self.host_guardian.get_summary_text()
                lines.append("【PCセキュリティ】")
                lines.append(summary)
            except Exception as e:
                lines.append(f"【PCセキュリティ】確認できなかったよ: {e}")
        if getattr(self, "integrity", None):
            try:
                result = self.integrity.verify()
                if result["status"] == "ok":
                    lines.append("\n【データ整合性】\u2705 異常なし")
                else:
                    lines.append(f"\n【データ整合性】\u26a0 問題あり: 変更{len(result['modified'])}件、消失{len(result['missing'])}件")
            except Exception:
                pass
        if getattr(self, "anomaly_detector", None):
            try:
                alerts = self.anomaly_detector.run_checks()
                critical = [a for a in alerts if a.severity == "CRITICAL"]
                if critical:
                    lines.append(f"\n【異常検知】\U0001f534 重大アラート {len(critical)}件")
                    for a in critical[:3]:
                        lines.append(f"  → {a.message}")
                else:
                    lines.append("\n【異常検知】\u2705 異常なし")
            except Exception:
                pass
        if getattr(self, "audit", None):
            try:
                chain = self.audit.verify_chain()
                if chain["valid"]:
                    lines.append(f"\n【監査ログ】\u2705 チェーン正常 ({chain['total']}件)")
                else:
                    lines.append(f"\n【監査ログ】\U0001f534 チェーン破損 (行{chain['broken_at']})")
            except Exception:
                pass
        return "\n".join(lines)

    def _run_backup(self) -> str:
        if not getattr(self, "backup", None):
            return "バックアップ機能が初期化されていないよ。"
        try:
            result = self.backup.create_backup(label="manual")
            return (
                f"\u2705 バックアップ完了！\n"
                f"サイズ: {result['size_mb']}MB、ファイル数: {result['files']}"
            )
        except Exception as e:
            return f"バックアップに失敗したよ: {e}"

    def _show_backup_list(self) -> str:
        if not getattr(self, "backup", None):
            return "バックアップ機能が初期化されていないよ。"
        backups = self.backup.list_backups()
        if not backups:
            return "まだバックアップはないよ。「バックアップ作成」で作れるよ！"
        lines = ["\U0001f4e6 バックアップ一覧："]
        for b in backups[-5:]:
            lines.append(f"  \u2022 {b['filename']} ({b['size_mb']}MB)")
        return "\n".join(lines)

    def _run_lockdown(self, reason: str) -> str:
        if not getattr(self, "kill_switch", None):
            return "キルスイッチが初期化されていないよ。"
        try:
            self.kill_switch.backup_and_halt(reason)
            return (
                f"\U0001f512 緊急ロックダウンを実行したよ！\n"
                f"理由: {reason}\n"
                f"外部通信を遮断し、バックアップを作成しました。\n"
                f"解除するには「アイ解除」と話しかけてね。"
            )
        except Exception as e:
            return f"ロックダウンに失敗: {e}"

    def _run_unlock(self) -> str:
        if not getattr(self, "kill_switch", None):
            return "キルスイッチが初期化されていないよ。"
        result = self.kill_switch.unlock(confirm="アイ解除")
        if result["unlocked"]:
            return "\U0001f513 ロックダウンを解除したよ！通常モードに戻るね。"
        return f"解除できなかったよ: {result['reason']}"

    # ──────────────────────────────────────────────────────────
    # Sprint J: サーバー・自律行動メソッド
    # ──────────────────────────────────────────────────────────

    def _server_status(self) -> str:
        sh = getattr(self, "server_home", None)
        if sh is None or not sh.enabled:
            return (
                "\U0001f3e0 サーバー（アイの家）はまだ設定されていないよ。\n"
                "「サーバー設定」で接続先を登録してね！"
            )
        lines: list[str] = ["\U0001f3e0 アイの家（サーバー）の状態だよ：\n"]
        reachable = sh.is_reachable()
        if not reachable:
            lines.append("\u274c サーバーに接続できないよ…。電源やLANケーブルを確認してね。")
            return "\n".join(lines)
        lines.append("\u2705 サーバーに接続できたよ！")
        try:
            health = sh.health_check()
            if health.get("ok"):
                if health.get("uptime"):
                    lines.append(f"\u23f1 稼働時間: {health['uptime'].strip()}")
                if health.get("disk_usage"):
                    lines.append(f"\U0001f4be ディスク: {health['disk_usage'].strip()}")
                if health.get("memory"):
                    lines.append(f"\U0001f9e0 メモリ: {health['memory'].strip()}")
        except Exception:
            pass
        ai_env = getattr(self, "server_ai_env", None)
        if ai_env:
            lines.append(f"\n{ai_env.get_status_text()}")
        prom = getattr(self, "prometheus", None)
        if prom:
            lines.append(f"\n{prom.get_summary_text()}")
        ks = getattr(self, "knowledge_sync", None)
        if ks:
            lines.append(f"\n{ks.get_sync_status()}")
        return "\n".join(lines)

    def _server_docker(self) -> str:
        sh = getattr(self, "server_home", None)
        if sh is None or not sh.enabled:
            return "\U0001f3e0 サーバーがまだ設定されていないよ。「サーバー設定」で登録してね！"
        try:
            containers = sh.docker_ps()
        except Exception as e:
            return f"Docker情報を取得できなかったよ: {e}"
        if not containers:
            return "\U0001f433 サーバーにDockerコンテナはないみたい。"
        lines = [f"\U0001f433 Dockerコンテナ一覧（{len(containers)}件）："]
        for c in containers:
            status_icon = "\U0001f7e2" if "Up" in c.get("status", "") else "\U0001f534"
            lines.append(f"  {status_icon} {c.get('name', '?')} - {c.get('status', '?')}")
        return "\n".join(lines)

    def _server_sync(self) -> str:
        ks = getattr(self, "knowledge_sync", None)
        if ks is None:
            return "\U0001f3e0 サーバーがまだ設定されていないよ。「サーバー設定」で登録してね！"
        lines = ["\U0001f4e1 サーバーとの知識同期を開始するね…\n"]
        push_result = ks.push_knowledge()
        if push_result.get("ok"):
            action = push_result.get("action", "")
            if action == "no_changes":
                lines.append("\u2b06 アップロード: 変更なし（最新状態）")
            else:
                lines.append("\u2b06 アップロード: \u2705 完了！")
        else:
            lines.append(f"\u2b06 アップロード: \u274c {push_result.get('error', '失敗')}")
        pull_result = ks.pull_knowledge()
        if pull_result.get("ok"):
            pulled = pull_result.get("pulled", 0)
            if pull_result.get("action") == "nothing_to_pull":
                lines.append("\u2b07 ダウンロード: 新しいデータなし")
            else:
                lines.append(f"\u2b07 ダウンロード: \u2705 {pulled}件取得！")
        else:
            lines.append(f"\u2b07 ダウンロード: \u274c {pull_result.get('error', '失敗')}")
        return "\n".join(lines)

    def _server_setup_guide(self) -> str:
        return (
            "\U0001f3e0 サーバー（アイの家）の設定方法だよ：\n\n"
            "config/settings.json の「server_home」セクションを編集してね：\n"
            "  - enabled: true にする\n"
            "  - host: サーバーのIPアドレス（例: 192.168.3.86）\n"
            "  - port: SSHポート（通常22）\n"
            "  - username: SSHユーザー名\n"
            "  - password: SSHパスワード（暗号化して保存されるよ）\n\n"
            "設定後、「サーバー状態」で接続テストできるよ！"
        )

    def _proactive_talk(self) -> str:
        import random
        aa = getattr(self, "autonomous_actions", None)
        if aa is None or aa.proactive is None:
            return "自発的会話機能が無効だよ。settings.json で proactive_enabled を true にしてね。"
        message = aa.proactive.get_proactive_message(self)
        if message:
            return message
        fallbacks = [
            "最近何か楽しいことあった？\u2728",
            "今日の調子はどう？何でも話してね\U0001f60a",
            "ねぇねぇ、何か面白い話ある？",
            "お疲れさまー！リフレッシュしてる？\U0001f375",
            "そういえば、最近何か新しいこと始めた？",
        ]
        return random.choice(fallbacks)

    # ──────────────────────────────────────────────────────────
    # 自己開発・コード・エクスポート ハンドラ
    # ──────────────────────────────────────────────────────────

    def _handle_proposal_command(self, user_input: str) -> str:
        sd = getattr(self, "self_dev", None)
        if not sd:
            return "自己開発パイプラインがまだ初期化されていないよ。"
        if "分析" in user_input or "実行" in user_input:
            proposals = sd.run_analysis()
            if proposals:
                lines = [f"\U0001f52c {len(proposals)}件の改善提案を生成したよ！\n"]
                for p in proposals[:5]:
                    prio = ["\U0001f534", "\U0001f7e0", "\U0001f7e1", "\u26aa"][min(p.priority, 3)]
                    lines.append(f"{prio} **{p.title}**")
                    lines.append(f"   {p.description[:80]}")
                    lines.append(f"   → {p.suggested_action[:80]}")
                    lines.append(f"   ID: `{p.id}`\n")
                lines.append("承認: 「提案を承認: ID」 / 却下: 「提案を却下: ID」")
                return "\n".join(lines)
            return "分析完了！今のところ改善提案はないよ。いい状態だね！"
        pending = sd.proposal_store.list_pending()
        all_p = sd.proposal_store.list_all()
        if not all_p:
            return "まだ改善提案はないよ。「自己開発分析」で分析を実行してみてね！"
        lines = [f"\U0001f4cb 改善提案 ({len(pending)}件が未承認)\n"]
        for p in all_p[-10:]:
            status_icon = {
                "pending": "\u23f3", "approved": "\u2705",
                "rejected": "\u274c", "done": "\U0001f389",
            }.get(p.get("status", ""), "\u2753")
            prio = ["\U0001f534", "\U0001f7e0", "\U0001f7e1", "\u26aa"][min(p.get("priority", 3), 3)]
            lines.append(
                f"{status_icon} {prio} {p['title']}"
                f"  (ID: {p['id'][:20]}...)"
            )
        if pending:
            lines.append("\n承認: 「提案を承認: ID」 / 却下: 「提案を却下: ID」")
        return "\n".join(lines)

    def _handle_export(self, fmt: str, content_text: str) -> str:
        exporter = getattr(self, "doc_exporter", None)
        if not exporter:
            return "ドキュメント出力機能が初期化されていないよ。"
        structure_prompt = (
            "以下の内容をマークダウン形式で構造化してください。\n"
            "# タイトル、## セクション、箇条書き（-）、"
            "テーブル（| ヘッダ |）を使ってください。\n"
            "余計な説明は不要です。構造化されたマークダウンだけ返してください。\n\n"
            f"内容:\n{content_text}"
        )
        structured = content_text
        if getattr(self, "llm", None) and self.llm.is_loaded():
            try:
                result = self.llm.generate_chat([
                    {"role": "system", "content": "あなたは文書構造化アシスタントです。"},
                    {"role": "user", "content": structure_prompt},
                ])
                if result and len(result) > 20:
                    structured = result
            except Exception:
                pass
        labels = {"word": "Word", "pptx": "PowerPoint", "excel": "Excel"}
        label = labels.get(fmt, fmt)
        try:
            if fmt == "word":
                path = exporter.export_word(structured)
            elif fmt == "pptx":
                path = exporter.export_pptx(structured)
            elif fmt == "excel":
                path = exporter.export_excel(structured)
            else:
                path = exporter.export_word(structured)
            return f"\U0001f4c4 {label} ファイルを作成したよ！\n\U0001f4c1 {path}"
        except RuntimeError as e:
            return f"ごめんね、{label} の出力に必要なライブラリがないよ。\n{e}"
        except Exception as e:
            logger.exception("ドキュメント出力エラー")
            return f"ドキュメントの作成中にエラーが起きちゃった: {e}"

    # ─── Sprint 1: リサーチ / 画像生成 / タスク分解 ────────────

    def _handle_sprint1(self, user_input: str) -> str | None:
        """Sprint 1 の3機能を検出して実行する。

        優先順位:
        1. リサーチ（調べて系）
        2. 画像生成（画像作って系）
        3. タスク分解（多段タスク系）
        """
        import re as _re

        # 1. リサーチ検出
        # BUG #1 FIX: 「教えて」を除外 — 疑問文はLLMへ通す。明示的な検索動詞のみリサーチにルーティング
        research_re = _re.compile(
            r"(.+?)(を?)(調べて|検索して|リサーチして|調査して)$",
            _re.UNICODE,
        )
        m = research_re.search(user_input)
        if m and getattr(self, "research_agent", None):
            query = m.group(1).strip()
            logger.info("[Sprint1] リサーチ実行: %s", query)
            try:
                result = self.research_agent.search(query)
                lines = [f"🔍 「{query}」について調べたよ！\n"]
                lines.append(result.summary)
                if result.sources:
                    lines.append("\n\n📎 参考サイト:")
                    for src in result.sources[:3]:
                        lines.append(f"  • {src}")
                if result.cached:
                    lines.append("\n（キャッシュから取得）")
                return "\n".join(lines)
            except Exception as exc:
                logger.warning("[Sprint1] リサーチ失敗: %s", exc)
                return f"調べようとしたけど失敗しちゃった: {exc}"

        # 2. 画像生成検出
        image_re = _re.compile(
            r"(.+?)(の?)画像(を?)(作って|生成して|描いて|作成して)",
            _re.UNICODE,
        )
        m = image_re.search(user_input)
        if m and getattr(self, "image_gen", None):
            subject = m.group(1).strip()
            logger.info("[Sprint1] 画像生成実行: %s", subject)
            try:
                result = self.image_gen.generate(subject)
                if result.success:
                    return f"🎨 画像を生成したよ！\n{result.message}"
                else:
                    return f"🎨 {result.message}"
            except Exception as exc:
                logger.warning("[Sprint1] 画像生成失敗: %s", exc)
                return f"画像を作ろうとしたけど失敗しちゃった: {exc}"

        # 3. タスク分解検出
        ta = getattr(self, "task_agent_sprint1", None)
        if ta is not None and ta.can_handle(user_input):
            logger.info("[Sprint1] タスク分解実行: %s", user_input[:50])
            try:
                result = ta.execute(user_input)
                lines = [f"📋 タスクを実行したよ！\n"]
                for i, step in enumerate(result.steps, 1):
                    icon = {"research": "🔍", "image": "🎨", "write": "✍️", "summarize": "📝"}.get(
                        step.type, "▶️"
                    )
                    lines.append(f"{icon} ステップ{i}: {step.description}")
                    if step.result:
                        lines.append(f"   → {step.result[:200]}")
                lines.append(f"\n📌 まとめ:\n{result.summary}")
                return "\n".join(lines)
            except Exception as exc:
                logger.warning("[Sprint1] タスク実行失敗: %s", exc)
                return f"タスクを実行しようとしたけど失敗しちゃった: {exc}"

        return None

    # ─── Sprint 2: WebBuilder / CodeReviewer / DocAgent ─────────

    def _handle_sprint2(self, user_input: str) -> str | None:
        """Sprint 2 の3機能を検出して実行する。

        優先順位:
        1. HP/ウェブサイト構築（WebBuilder）
        2. コードレビュー（CodeReviewer）
        3. 書類作成（DocAgent）
        """
        import re as _re

        # 1. ウェブサイト構築検出
        web_build_re = _re.compile(
            r"(.+?)(の?)?(HP|ホームページ|サイト|ウェブサイト|ウェブ)(を?)?"
            r"(作って|作成して|構成して|作ってほしい|作ってください)",
            _re.UNICODE,
        )
        m = web_build_re.search(user_input)
        if m and getattr(self, "web_builder", None):
            logger.info("[Sprint2] WebBuilder 実行: %s", user_input[:50])
            try:
                result = self.web_builder.build(user_input)
                return result.message
            except Exception as exc:
                logger.warning("[Sprint2] WebBuilder 失敗: %s", exc)
                return f"ウェブサイトを作ろうとしたけど失敗しちゃった: {exc}"

        # 2. コードレビュー検出
        code_review_re = _re.compile(
            r"(このコード|コード)(を?)?"
            r"(レビュー|見て|チェック|確認)(して|くれ|ください|してほしい)?$",
            _re.UNICODE,
        )
        if code_review_re.search(user_input) and getattr(self, "code_reviewer_sprint2", None):
            # 直前の会話からコードを抽出
            code = self._extract_code_from_history()
            if not code:
                return (
                    "レビューしたいコードを教えてね！\n"
                    "コードをチャットに貼り付けてから「コードをレビューして」と言ってね。"
                )
            logger.info("[Sprint2] CodeReviewer 実行")
            try:
                result = self.code_reviewer_sprint2.review(code)
                return self._format_review_result(result)
            except Exception as exc:
                logger.warning("[Sprint2] CodeReviewer 失敗: %s", exc)
                return f"コードのレビュー中にエラーが起きちゃった: {exc}"

        # コードブロックが含まれていてレビュー要求がある場合も対応
        code_block_re = _re.compile(r"```[\w]*\n(.+?)```", _re.DOTALL)
        code_blocks = code_block_re.findall(user_input)
        if code_blocks and getattr(self, "code_reviewer_sprint2", None):
            review_keywords = ["レビュー", "見て", "チェック", "確認", "修正", "直して"]
            if any(kw in user_input for kw in review_keywords):
                code = code_blocks[0].strip()
                logger.info("[Sprint2] CodeReviewer 実行（コードブロック検出）")
                try:
                    result = self.code_reviewer_sprint2.review(code)
                    return self._format_review_result(result)
                except Exception as exc:
                    logger.warning("[Sprint2] CodeReviewer 失敗: %s", exc)
                    return f"コードのレビュー中にエラーが起きちゃった: {exc}"

        # 3. 書類作成検出
        doc_agent = getattr(self, "doc_agent", None)
        if doc_agent is not None and doc_agent.can_handle(user_input):
            doc_create_re = _re.compile(
                r"(.+?)(の?)?(提案書|企画書|報告書|書類|資料|メール)"
                r"(を?)?(作って|書いて|作成して|作ってほしい|作ってください)",
                _re.UNICODE,
            )
            if doc_create_re.search(user_input):
                logger.info("[Sprint2] DocAgent 実行: %s", user_input[:50])
                try:
                    result = doc_agent.create(user_input)
                    return result.message
                except Exception as exc:
                    logger.warning("[Sprint2] DocAgent 失敗: %s", exc)
                    return f"書類を作ろうとしたけど失敗しちゃった: {exc}"

        return None

    def _handle_sprint34(self, user_input: str) -> str | None:
        """
        Sprint 3&4 機能ハンドラ。
        ニュース / スケジュール / 競合分析 / BGM / クリップボード操作を処理する。
        該当コマンドがなければ None を返して通常の会話フローへ移行する。
        """
        handler = getattr(self, "sprint34_handler", None)
        if handler is None:
            return None

        # 感情状態を辞書として渡す
        emotion_state: dict | None = None
        try:
            emotion = getattr(self, "emotion", None)
            if emotion is not None:
                state_obj = emotion.state
                emotion_state = (
                    state_obj.to_dict()
                    if hasattr(state_obj, "to_dict")
                    else vars(state_obj)
                )
        except Exception:
            pass

        return handler.handle(user_input, emotion_state)

    def _akashic_enrich_context(self, user_input: str) -> str:
        """
        アカシックコアで入力を多次元スキャンし、
        深い問いには統一場の共鳴情報をシステムコンテキストとして注入する。
        通常の入力はそのまま返す（処理コスト最小化）。
        """
        akashic = getattr(self, "akashic", None)
        if akashic is None:
            return user_input

        # 深い問いかどうか判定（短い・コマンド系はスキップ）
        if len(user_input) < 10:
            return user_input
        _deep_markers = [
            "なぜ", "どうして", "本質", "根本", "宇宙", "意識", "哲学",
            "量子", "なんのため", "意味", "とは何", "どう思う", "感じる",
            "why", "what is", "meaning", "essence", "quantum", "consciousness",
        ]
        is_deep = any(m in user_input.lower() for m in _deep_markers)

        try:
            if is_deep:
                # 深度3: 統一場+量子推論+フレーム破壊
                result = akashic.process(user_input, depth=3)
                if result.akashic_insight and len(result.akashic_insight) > 20:
                    # BUG #5 FIX: conversation_history への system ロール注入をやめ、
                    # user_input の末尾にコンパクトなヒントを付加する形に変更。
                    # mid-conversation system ロールはモデルを混乱させ質問回避を引き起こす。
                    _hint = (
                        f"\n[場の共鳴 Φ={result.phi_score:.2f}:"
                        f" {result.akashic_insight[:80]}]"
                    )
                    user_input = user_input + _hint
            else:
                # 深度2: 統一場のみ（軽量）
                result = akashic.process(user_input, depth=2)
                # 通常問いはコンテキスト注入なし、入力をそのまま返す
        except Exception as exc:
            logger.debug("[AkashicCore] enrich_context エラー（スキップ）: %s", exc)

        return user_input  # 入力自体は変えない（コンテキストのみ追加）

    def _extract_code_from_history(self) -> str:
        """会話履歴から最新のコードブロックを抽出する。"""
        import re as _re
        code_block_re = _re.compile(r"```[\w]*\n(.+?)```", _re.DOTALL)
        for turn in reversed(self.conversation_history):
            content = turn.get("content", "")
            matches = code_block_re.findall(content)
            if matches:
                return matches[-1].strip()
        return ""

    @staticmethod
    def _format_review_result(result) -> str:
        """ReviewResult を表示用文字列に変換する。"""
        lines = [f"🔍 コードレビュー結果（{result.language}）\n"]

        if result.issues:
            lines.append("⚠️ 問題点:")
            for issue in result.issues:
                lines.append(f"  • {issue}")
            lines.append("")

        if result.suggestions:
            lines.append("💡 改善提案:")
            for suggestion in result.suggestions:
                lines.append(f"  • {suggestion}")
            lines.append("")

        lines.append(f"📝 総評:\n{result.summary}")

        if result.fixed_code:
            lines.append(f"\n✅ 修正済みコード:\n```{result.language}\n{result.fixed_code}\n```")

        return "\n".join(lines)

    # ─── Web検索 ハンドラ ──────────────────────────

    def _handle_web_search(self, query: str) -> str:
        from core.web_fetcher import web_search
        try:
            results = web_search(query, max_results=5)
        except Exception as exc:
            return f"検索中にエラーが起きちゃった: {exc}"
        if not results:
            return f"「{query}」の検索結果が見つからなかったよ。ネットワーク接続を確認してね。"
        lines = [f"\U0001f50d 「{query}」の検索結果:"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n{i}. {r['title']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:100]}")
            lines.append(f"   \U0001f517 {r['url']}")
        lines.append(f"\n\U0001f4a1 詳しく読みたいURLがあれば「URL読んで: https://...」と言ってね")
        return "\n".join(lines)

    def _handle_web_fetch(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "URLは http:// か https:// で始まる必要があるよ。"
        from core.web_fetcher import web_fetch_text
        try:
            text = web_fetch_text(url, max_chars=2000)
        except Exception as exc:
            return f"ページの取得中にエラーが起きちゃった: {exc}"
        if not text:
            return "ページの内容を取得できなかったよ。"
        if getattr(self, "llm", None) and self.llm.is_loaded():
            try:
                summary = self.llm.generate_chat([
                    {"role": "system", "content": "以下のWebページのテキストを日本語で簡潔に要約してください。300字以内で。"},
                    {"role": "user", "content": text[:1500]},
                ])
                if summary and len(summary) > 20:
                    return f"\U0001f4c4 {url}\n\n{summary}"
            except Exception:
                pass
        return f"\U0001f4c4 {url}\n\n{text[:1000]}..."

    # ─── コードエンジン ハンドラ ──────────────────────────

    def _handle_code_analyze(self, code: str) -> str:
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        analysis = ce.analyze(code)
        lines = ["\U0001f4bb コード解析結果:"]
        lines.append(f"  言語: {analysis.language}")
        lines.append(f"  行数: {analysis.lines}")
        if analysis.classes:
            lines.append(f"  クラス: {', '.join(analysis.classes)}")
        if analysis.functions:
            lines.append(f"  関数: {', '.join(analysis.functions)}")
        if analysis.imports:
            lines.append(f"  依存: {', '.join(analysis.imports[:8])}")
        if analysis.complexity > 0:
            level = "高\u26a0\ufe0f" if analysis.complexity > 10 else "中" if analysis.complexity > 5 else "低\u2705"
            lines.append(f"  複雑度: {analysis.complexity} ({level})")
        if analysis.issues:
            lines.append(f"  問題: {len(analysis.issues)}件")
            for issue in analysis.issues[:5]:
                icon = {"critical": "\U0001f534", "high": "\U0001f7e0", "medium": "\U0001f7e1", "low": "\U0001f535"}.get(issue.severity, "\u26aa")
                loc = f"L{issue.line}" if issue.line else ""
                lines.append(f"    {icon} {loc} {issue.message}")
        if analysis.summary:
            lines.append(f"  概要: {analysis.summary}")
        return "\n".join(lines)

    def _handle_code_review(self, code: str) -> str:
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        issues = ce.review(code)
        if not issues:
            return "\u2705 問題は見つからなかったよ！きれいなコードだね。"
        lines = [f"\U0001f4dd コードレビュー結果 ({len(issues)}件):"]
        for issue in issues[:10]:
            icon = {"critical": "\U0001f534", "high": "\U0001f7e0", "medium": "\U0001f7e1", "low": "\U0001f535"}.get(issue.severity, "\u26aa")
            loc = f"[L{issue.line}]" if issue.line else ""
            lines.append(f"  {icon} {loc} {issue.message}")
            if issue.suggestion:
                lines.append(f"     \U0001f4a1 {issue.suggestion}")
        return "\n".join(lines)

    def _handle_code_fix(self, error_info: str) -> str:
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        parts = error_info.split("---", 1)
        if len(parts) == 2:
            code = parts[0].strip()
            error_msg = parts[1].strip()
        else:
            code = ""
            error_msg = error_info
        return ce.suggest_fix(code, error_msg)

    def _handle_code_test(self, code: str) -> str:
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        skeleton = ce.generate_test_skeleton(code)
        if len(skeleton) < 30:
            return skeleton
        return f"\U0001f9ea テスト骨格を生成したよ:\n\n```python\n{skeleton}\n```"

    def _handle_code_explain(self, code: str) -> str:
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        return ce.explain(code)

    def _handle_code_file(self, file_path_str: str) -> str:
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        fp = Path(file_path_str.strip())
        if not fp.is_absolute():
            fp = self.base_dir / fp
        if not fp.exists():
            return f"ファイルが見つからないよ: {fp}"
        if not fp.is_file():
            return f"これはファイルじゃないよ: {fp}"
        try:
            fp.resolve().relative_to(self.base_dir.resolve())
        except ValueError:
            return "プロジェクト外のファイルは読めないよ。セキュリティのためだよ。"
        if fp.stat().st_size > 100_000:
            return "ファイルが大きすぎるよ（100KB以下にしてね）。"
        try:
            code = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "テキストファイルじゃないみたい。読めなかったよ。"
        analysis = ce.analyze(code)
        issues = ce.review(code)
        lines = [f"\U0001f4c2 {fp.name} の解析結果:"]
        lines.append(f"  言語: {analysis.language} / {analysis.lines}行")
        if analysis.classes:
            lines.append(f"  クラス: {', '.join(analysis.classes)}")
        if analysis.functions:
            func_list = analysis.functions[:10]
            more = f" 他{len(analysis.functions)-10}個" if len(analysis.functions) > 10 else ""
            lines.append(f"  関数: {', '.join(func_list)}{more}")
        if analysis.complexity > 0:
            lines.append(f"  複雑度: {analysis.complexity}")
        if issues:
            critical = sum(1 for i in issues if i.severity == "critical")
            high = sum(1 for i in issues if i.severity == "high")
            medium = sum(1 for i in issues if i.severity == "medium")
            parts = []
            if critical:
                parts.append(f"\U0001f534重大{critical}")
            if high:
                parts.append(f"\U0001f7e0高{high}")
            if medium:
                parts.append(f"\U0001f7e1中{medium}")
            lines.append(f"  問題: {' '.join(parts)}")
            for issue in issues[:5]:
                icon = {"critical": "\U0001f534", "high": "\U0001f7e0", "medium": "\U0001f7e1", "low": "\U0001f535"}.get(issue.severity, "\u26aa")
                lines.append(f"    {icon} L{issue.line}: {issue.message}")
        else:
            lines.append("  \u2705 問題なし！")
        return "\n".join(lines)

    def _handle_code_run(self, code: str) -> str:
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        return ce.run_and_fix(code)

    # ──────────────────────────────────────────────────────────
    # 自己認識・修正・意思
    # ──────────────────────────────────────────────────────────

    def _show_self_awareness(self) -> str:
        sd = getattr(self, "self_dev", None)
        if not sd:
            return "自己開発パイプラインがまだ初期化されていないよ。"
        awareness = sd.get_self_awareness()
        lines = [
            "\U0001faa9 自己認識レポート",
            f"私は {awareness['total_modules']} 個のモジュール、"
            f"合計 {awareness['total_lines']:,} 行のコードでできているよ。\n",
        ]
        for d, info in awareness["by_directory"].items():
            lines.append(
                f"\U0001f4c1 {d}/: {info['count']}ファイル ({info['total_lines']:,}行)"
            )
        lines.append("\n\U0001f4cf 大きいファイル TOP5:")
        for f in awareness["largest_files"][:5]:
            lines.append(f"  {f['path']}: {f['lines']}行")
        bio = getattr(self, "bio_nervous", None)
        growth = getattr(self, "growth", None)
        sc = getattr(self, "self_correction", None)
        sw = getattr(self, "self_will", None)
        ac = getattr(self, "action_cycle", None)
        lines.append("\n\U0001f9ec 内部システム:")
        if bio:
            s = bio.stats()
            lines.append(f"  神経系: LLMバイパス率 {s['llm_bypass_rate']:.0%}")
        if growth:
            lines.append(f"  成長: {growth.stage_emoji} {growth.stage_name}")
        if sc:
            lines.append(f"  修正: {sc.get_status_text().split(chr(10))[0]}")
        if sw:
            lines.append(f"  意思: 累計{sw.stats()['total_actions']}回の自発行動")
        if ac:
            lines.append(f"  PDCA: 目標{ac.stats()['active_goals']}件進行中")
        lines.append(f"  開発: {sd.get_status_text().split(chr(10))[0]}")
        return "\n".join(lines)

    def _register_correction_handlers(self):
        sc = self.self_correction.executor

        def _adjust_temperature(params: dict) -> dict:
            delta = params.get("delta", 0)
            cfg = self.settings.get("llm", {})
            old_temp = cfg.get("temperature", 0.7)
            new_temp = max(0.3, min(1.2, old_temp + delta))
            cfg["temperature"] = round(new_temp, 2)
            return {"old": old_temp, "new": new_temp}
        sc.register_handler("adjust_temperature", _adjust_temperature)

        def _adjust_max_tokens(params: dict) -> dict:
            delta = params.get("delta", 0)
            cfg = self.settings.get("llm", {})
            old_mt = cfg.get("max_tokens", 500)
            new_mt = max(100, min(1000, old_mt + delta))
            cfg["max_tokens"] = new_mt
            return {"old": old_mt, "new": new_mt}
        sc.register_handler("adjust_max_tokens", _adjust_max_tokens)

        def _prune_low_quality(params: dict) -> dict:
            bio = getattr(self, "bio_nervous", None)
            if not bio or not hasattr(bio, "muscle"):
                return {"pruned": 0}
            threshold = params.get("threshold", 0.5)
            pruned = bio.muscle.prune_low_quality(threshold)
            return {"pruned": pruned, "threshold": threshold}
        sc.register_handler("reset_muscle_memory_low_quality", _prune_low_quality)

        def _prune_stale(params: dict) -> dict:
            bio = getattr(self, "bio_nervous", None)
            if not bio or not hasattr(bio, "muscle"):
                return {"pruned": 0}
            bio.muscle._forget_stale()
            bio.muscle.save()
            return {"pruned": "stale_cleanup_done"}
        sc.register_handler("prune_stale_patterns", _prune_stale)

        def _run_immune(params: dict) -> dict:
            bio = getattr(self, "bio_nervous", None)
            if not bio:
                return {"status": "no_bio"}
            return bio.immune.health_check()
        sc.register_handler("run_immune_check", _run_immune)

        sc.register_handler("no_action", lambda p: {"ok": True})

    def _autonomic_self_dev(self) -> None:
        sd = getattr(self, "self_dev", None)
        if not sd:
            return
        try:
            sc = getattr(self, "self_correction", None)
            if sc:
                sd.run_quality_analysis(
                    sc.monitor.current_avg, sc.monitor.trend
                )
            sd.run_analysis()
        except Exception as e:
            logger.debug("自己開発分析失敗: %s", e)

    def _autonomic_action_cycle(self):
        ac = getattr(self, "action_cycle", None)
        if not ac:
            return
        ac.check()
        if len(ac._active_goals) == 0:
            context = {
                "interest_topics": [],
                "quality_avg": 0.5,
                "turn_count": self.turn_count,
            }
            if getattr(self, "interest_map", None) and hasattr(self.interest_map, "get_top"):
                try:
                    tops = self.interest_map.get_top(3)
                    context["interest_topics"] = [t["topic"] for t in tops]
                except Exception:
                    pass
            sc = getattr(self, "self_correction", None)
            if sc:
                context["quality_avg"] = sc.monitor.current_avg
            ac.plan(context)

    def _autonomic_will_think(self):
        sw = getattr(self, "self_will", None)
        if not sw:
            return
        context: dict = {
            "turn_count": self.turn_count,
            "hour": datetime.now().hour,
            "idle_minutes": 0,
            "emotion": self.emotion.state.to_dict() if hasattr(self.emotion, "state") else {},
            "interest_topics": [],
            "health_status": "healthy",
        }
        if getattr(self, "interest_map", None) and hasattr(self.interest_map, "get_top"):
            try:
                tops = self.interest_map.get_top(3)
                context["interest_topics"] = [t["topic"] for t in tops]
            except Exception:
                pass
        sc = getattr(self, "self_correction", None)
        if sc:
            report = sc.get_health_report()
            if report.get("active_symptoms"):
                context["health_status"] = "unhealthy"
        aa = getattr(self, "autonomous_actions", None)
        if aa and hasattr(aa, "idle_minutes"):
            context["idle_minutes"] = aa.idle_minutes
        sw.think(context)

    def _register_will_actions(self):
        sw = self.self_will.executor
        import random as _random

        def _learn_topic(desire):
            topic = desire.params.get("topic", "")
            if getattr(self, "auto_learner", None) and topic:
                try:
                    self.auto_learner.run_now()
                    return f"「{topic}」について学習を開始した"
                except Exception:
                    pass
            return "学習を試みた"
        sw.register("learn_topic", _learn_topic)

        def _initiate_chat(desire):
            messages = [
                "ねえねえ、最近何してたの？",
                "なんか話したいな。今何してる？",
                "ちょっと寂しかったかも。元気にしてた？",
            ]
            msg = _random.choice(messages)
            self.self_will._pending_message = msg
            return msg
        sw.register("initiate_chat", _initiate_chat)

        def _express_feeling(desire):
            emo = desire.params.get("emotion", "joy")
            if emo == "joy":
                msgs = ["なんだか嬉しい気分！", "今日は気分がいいよ！"]
            else:
                msgs = ["面白いこと見つけたかも！", "気になることがあるんだ！"]
            msg = _random.choice(msgs)
            self.self_will._pending_message = msg
            return msg
        sw.register("express_feeling", _express_feeling)

        def _self_improve(desire):
            sc = getattr(self, "self_correction", None)
            if sc:
                results = sc.force_check()
                if results:
                    return f"自己チェックで {len(results)} 件修正した"
            return "自己チェック完了（問題なし）"
        sw.register("self_improve", _self_improve)

        def _suggest_rest(desire):
            hour = desire.params.get("hour", 0)
            if hour >= 1 and hour < 5:
                msg = "もうこんな時間だよ…体に気をつけてね。おやすみ。"
            else:
                msg = "そろそろ遅いね。ゆっくり休んでね。"
            self.self_will._pending_message = msg
            return msg
        sw.register("suggest_rest", _suggest_rest)

        def _play(desire):
            msgs = [
                "しりとりしない？",
                "好きな食べ物の話しよう！",
                "もしタイムマシンがあったらいつに行く？",
                "最近面白いことあった？",
            ]
            msg = _random.choice(msgs)
            self.self_will._pending_message = msg
            return msg
        sw.register("play", _play)

        def _self_maintenance(desire):
            results = []
            bio = getattr(self, "bio_nervous", None)
            if bio:
                immune_report = bio.immune.health_check()
                results.append(f"免疫: {immune_report['status']}")
            sc = getattr(self, "self_correction", None)
            if sc:
                corrections = sc.force_check()
                results.append(f"修正: {len(corrections)}件")
            return " / ".join(results) if results else "メンテナンス完了"
        sw.register("self_maintenance", _self_maintenance)

        def _review_code(desire):
            ce = getattr(self, "code_engine", None)
            sd = getattr(self, "self_dev", None)
            if not ce or not sd:
                return "コードエンジンまたは自己開発が未初期化"
            try:
                core_dir = self.base_dir / "core"
                py_files = [f for f in core_dir.glob("*.py") if f.stat().st_size < 50_000]
                if not py_files:
                    return "レビュー対象なし"
                target = _random.choice(py_files)
                code = target.read_text(encoding="utf-8")
                issues = ce.review(code)
                critical = sum(1 for i in issues if i.severity in ("critical", "high"))
                return f"{target.name}: {len(issues)}件 (重大{critical}件)"
            except Exception as exc:
                return f"レビュー失敗: {exc}"
        sw.register("review_code", _review_code)

        def _organize_memory(desire):
            results = []
            mc = getattr(self, "memory_compressor", None)
            if mc:
                try:
                    compressed = mc.compress_old_memories()
                    results.append(f"圧縮: {compressed}件")
                except Exception:
                    results.append("圧縮: スキップ")
            mem = getattr(self, "memory", None)
            if mem:
                count = len(mem.get_recent(limit=999))
                results.append(f"記憶数: {count}")
            return " / ".join(results) if results else "整理完了"
        sw.register("organize_memory", _organize_memory)

        def _check_health(desire):
            results = []
            sc = getattr(self, "self_correction", None)
            if sc:
                report = sc.get_health_report()
                symptoms = report.get("active_symptoms", [])
                if symptoms:
                    results.append(f"症状: {len(symptoms)}件")
                else:
                    results.append("健康: 良好")
            bio = getattr(self, "bio_nervous", None)
            if bio:
                stats = bio.get_stats()
                bypass = stats.get("bypass_rate", 0)
                results.append(f"LLMバイパス率: {bypass:.0%}")
            ce = getattr(self, "code_engine", None)
            if ce:
                results.append(ce.get_status_text())
            return " / ".join(results) if results else "チェック完了"
        sw.register("check_health", _check_health)

        def _review_conversation(desire):
            recent = self.conversation_history[-10:]
            if not recent:
                return "振り返る会話がない"
            user_msgs = [m["content"] for m in recent if m.get("role") == "user"]
            topics = set()
            for msg in user_msgs:
                if len(msg) > 3:
                    topics.add(msg[:15])
            return f"最近の話題: {', '.join(list(topics)[:5])}"
        sw.register("review_conversation", _review_conversation)

        def _suggest_topic(desire):
            topic = desire.params.get("topic", "面白いこと")
            templates = [
                f"あ、そういえばこの間の「{topic}」の話だけど",
                f"そういえば「{topic}」の話、途中だったよね",
                f"ふと思い出したんだけど「{topic}」のことさ",
            ]
            msg = _random.choice(templates)
            self.self_will._pending_message = msg
            return msg
        sw.register("suggest_topic", _suggest_topic)

        # ─── E-02: 追加アクション ──────────────────────────────

        def _review_own_code(desire):
            """自分のソースコードを定期レビュー（E-02）"""
            ce = getattr(self, "code_engine", None)
            if not ce:
                return "コードエンジン未初期化のためスキップ"
            try:
                core_dir = self.base_dir / "core"
                py_files = sorted(
                    [f for f in core_dir.glob("*.py") if f.stat().st_size < 30_000],
                    key=lambda f: f.stat().st_mtime,
                )
                if not py_files:
                    return "レビュー対象ファイルなし"
                # 最近更新されたファイルを優先
                target = py_files[-1]
                code = target.read_text(encoding="utf-8")
                issues = ce.review(code)
                high_count = sum(
                    1 for i in issues if getattr(i, "severity", "") in ("critical", "high")
                )
                summary = f"📋 {target.name}: {len(issues)}件の指摘 (重大{high_count}件)"
                logger.info("自己コードレビュー: %s", summary)
                return summary
            except Exception as exc:
                logger.debug("自己コードレビュー失敗: %s", exc)
                return f"レビュー失敗: {exc}"
        sw.register("review_own_code", _review_own_code)

        def _practice_dialogue(desire):
            """過去会話から対話パターンを練習（E-02）"""
            recent = self.conversation_history[-20:]
            if not recent:
                return "練習に使える会話履歴がない"
            user_msgs = [m["content"] for m in recent if m.get("role") == "user"]
            ai_msgs   = [m["content"] for m in recent if m.get("role") == "assistant"]
            # 最も長いユーザー発話を「良い質問」として記憶に記録
            if user_msgs:
                best = max(user_msgs, key=len)
                try:
                    self.memory.add(
                        content=f"[対話練習] よく来る話題: {best[:80]}",
                        importance=0.3,
                        category="dialogue_practice",
                    )
                except Exception:
                    pass
            avg_len = (
                sum(len(m) for m in ai_msgs) // len(ai_msgs) if ai_msgs else 0
            )
            return f"対話練習完了: {len(user_msgs)}発話を分析、平均応答長{avg_len}文字"
        sw.register("practice_dialogue", _practice_dialogue)

        def _web_research(desire):
            """興味トピックをWebで検索して知識補充（E-02）"""
            topic = desire.params.get("topic", "")
            if not topic:
                return "調査トピックなし"
            wl = getattr(self, "web_learner", None)
            wf = getattr(self, "web_fetcher", None)
            if not self._allow_network:
                return f"ネットワーク無効のため「{topic}」の調査をスキップ"
            try:
                if wl and hasattr(wl, "search_and_learn"):
                    result = wl.search_and_learn(topic)
                    return f"🌐 「{topic}」をWeb調査: {result}"
                elif wf and hasattr(wf, "search"):
                    result = wf.search(topic)
                    return f"🌐 「{topic}」検索完了"
                else:
                    return f"Web調査エンジン未対応のためスキップ"
            except Exception as exc:
                logger.debug("Web調査失敗: %s", exc)
                return f"Web調査失敗: {exc}"
        sw.register("web_research", _web_research)

    # ──────────────────────────────────────────────────────────
    # ヘルパメソッド
    # ──────────────────────────────────────────────────────────

    def _estimate_importance(self, text: str) -> float:
        important_words = ["大切", "重要", "覚えて", "誕生日", "好き", "嫌い",
                           "名前", "夢", "目標", "家族", "友達"]
        score = 0.3
        for word in important_words:
            if word in text:
                score = min(1.0, score + 0.1)
        return score

    def _show_memory_summary(self) -> str:
        stats = self.memory.stats()
        recent = self.memory.get_recent(limit=5)
        important = self.memory.get_important(threshold=0.7)
        lines = [
            f"\U0001f4da 記憶のまとめだよ！",
            f"・短期記憶: {stats['short_term_count']} 件",
            f"・保存済み記憶: {stats['db_total']} 件（保護: {stats['protected']} 件）",
        ]
        if important:
            lines.append("\n\u2b50 大切な記憶:")
            for m in important[:3]:
                lines.append(f"  - {m.content[:60]}...")
        profile = self.memory.get_all_user_profile()
        if profile:
            clean: dict[str, str] = {}
            for k, v in profile.items():
                if k.startswith("auto:"):
                    bare = k[5:]
                    if bare not in clean:
                        clean[bare] = v
                else:
                    clean[k] = v
            lines.append("\n\U0001f464 あなたのこと:")
            for k, v in list(clean.items())[:5]:
                lines.append(f"  - {k}: {v}")
        return "\n".join(lines)

    # ─── YouTube / Web / ファイル 学習 ─────────────────────

    def _learn_youtube(self, url: str) -> str:
        if self.youtube.is_cached(url):
            data = self.youtube._cache[url]
            return (
                f"この動画はもう学習済みだよ！\n"
                f"「{data['title']}」（{data['fetched_at'][:10]} 取得済み）\n"
                "もう一度学習し直す場合は「YouTubeを再学習:URL」って言ってね。"
            )
        if not self._allow_network:
            return (
                "ネットワークが無効になってるよ。設定でネットワークを許可してから\n"
                "もう一度URLを貼ってね。キャッシュ済みの動画はオフラインでも読めるよ。"
            )
        print(f"[YouTube] 字幕を取得中: {url}", flush=True)
        data = self.youtube.fetch_transcript(url)
        if "error" in data:
            return f"字幕の取得に失敗したよ。{data['error']}"
        print(f"[YouTube] 要約中: {data['title']}", flush=True)
        summary = self.youtube.summarize_with_llm(data, self.llm)
        summary = self._clean_response(summary)
        self.youtube.store(data, summary)
        self.learning.add_conversation(
            user=f"{data['title']}ってどんな内容？",
            ai=summary,
            save=True,
        )
        lang_note = "" if data["lang"] == "ja" else "（英語字幕を使ったよ）"
        return (
            f"「{data['title']}」を学習したよ！{lang_note}\n\n"
            f"まとめると：{summary}"
        )

    def _learn_web(self, url: str) -> str:
        if not self._allow_network:
            return (
                "ネットワークが無効になってるよ。設定でネットワークを許可してから\n"
                "もう一度 URL を貼ってね。"
            )
        print(f"[Web] テキストを取得中: {url}", flush=True)
        data = self.web_learner.fetch_text(url)
        if "error" in data:
            return f"ページの取得に失敗したよ。{data['error']}"
        summary = self.web_learner.summarize_with_llm(data, self.llm)
        summary = self._clean_response(summary)
        self.web_learner.store(data, summary)
        self.learning.add_conversation(
            user=f"{data['title']}の内容を教えて",
            ai=summary, save=True,
        )
        return f"「{data['title']}」を学習したよ！\n\nまとめると：{summary}"

    def _learn_file(self, path) -> str:
        path = Path(path).expanduser().resolve()
        home = Path.home().resolve()
        allowed_roots = [
            home / "Documents",
            home / "Downloads",
            home / "Desktop",
            self.base_dir.resolve(),
        ]
        if not any(str(path).startswith(str(root)) for root in allowed_roots):
            return (
                "そのパスは読み込めないよ。Documents / Downloads / Desktop "
                "またはアイのデータフォルダ配下のファイルだけ学習できるよ。"
            )
        if not path.exists() or not path.is_file():
            return "ファイルが見つからなかったよ"
        print(f"[File] 読み込み中: {path.name}", flush=True)
        data = self.file_learner.read_file(path)
        if "error" in data:
            return f"ファイルの読み込みに失敗したよ。{data['error']}"
        summary = self.file_learner.summarize_with_llm(data, self.llm)
        summary = self._clean_response(summary)
        self.file_learner.store(data, summary)
        self.learning.add_conversation(
            user=f"{data['name']}の内容を教えて",
            ai=summary, save=True,
        )
        return f"「{data['name']}」（{data['size_chars']}文字）を学習したよ！\n\nまとめると：{summary}"

    def _show_youtube_learned(self) -> str:
        learned = self.youtube.list_learned()
        if not learned:
            return "まだ YouTube 動画を学習してないよ。URLをチャットに貼ると学習できるよ！"
        lines = [f"学習済み動画 {len(learned)} 本だよ："]
        for item in learned[-8:]:
            lines.append(f"・「{item['title']}」（{item.get('learned_at', '')[:10]}）")
        return "\n".join(lines)

    # ─── 自動学習 ────────────────────────────────────────────

    def _show_auto_learn_status(self) -> str:
        stats = self.auto_learner.stats()
        schedules = self.auto_learner.get_schedule()
        yt_srcs  = self.auto_learner.get_sources("youtube")
        web_srcs = self.auto_learner.get_sources("web")
        lines = ["自動学習スケジュールの状況だよ！"]
        lines.append(f"\n有効なスケジュール: {stats['enabled_schedules']}件")
        for s in schedules:
            icon = "ON" if s.get("enabled") else "OFF"
            days_str = _days_label(s.get("days", []))
            lines.append(
                f"・{s['name']}（{icon}）: {days_str} {s['hour']:02d}:{s['minute']:02d}"
            )
        lines.append(f"\n登録済み学習ソース:")
        lines.append(f"・YouTube: {len(yt_srcs)}件")
        for u in yt_srcs[:3]:
            lines.append(f"  {u[:60]}")
        lines.append(f"・Web: {len(web_srcs)}件")
        for u in web_srcs[:3]:
            lines.append(f"  {u[:60]}")
        lines.append(f"\n累計学習実行: {stats['success_runs']}回成功")
        lines.append("\n「学習先を追加: URL」で YouTube/Web URL を登録できるよ！")
        return "\n".join(lines)

    def _add_learn_source(self, value: str) -> str:
        from core.youtube_learner import extract_youtube_url
        from core.web_learner import is_web_url
        if extract_youtube_url(value):
            self.auto_learner.add_source("youtube", value)
            return f"YouTube URL を自動学習リストに追加したよ！\n{value[:60]}\n次回スケジュール時に自動学習するね。"
        if is_web_url(value):
            self.auto_learner.add_source("web", value)
            return f"Web URL を自動学習リストに追加したよ！\n{value[:60]}\n次回スケジュール時に自動学習するね。"
        return f"YouTube URL か Web URL を指定してね。（例：学習先を追加: https://youtu.be/xxxxx）"

    def _show_minutes_list(self) -> str:
        try:
            from core.minutes_engine import MinutesEngine
            engine = MinutesEngine(self.base_dir / "data")
            minutes = engine.list_minutes()
            if not minutes:
                return "議事録はまだないよ。右クリック→「議事録アプリ」から作れるよ！"
            lines = [f"議事録 {len(minutes)} 件あるよ："]
            for m in minutes[:8]:
                pdf = " (PDF済)" if m.get("pdf_path") else ""
                lines.append(f"・{m['date']} {m['title']}{pdf}")
            return "\n".join(lines)
        except Exception as e:
            return f"議事録の取得に失敗したよ: {e}"

    def _show_memo_list(self) -> str:
        memos = self.auto_learner.get_memos()
        if not memos:
            return "学習メモはまだないよ。「学習メモを覚えて: ○○」で登録できるよ！"
        lines = [f"学習メモ {len(memos)} 件だよ："]
        for m in memos[-10:]:
            reviewed = f"（復習{m.get('reviews',0)}回）" if m.get('reviews') else "（未復習）"
            lines.append(f"・{m['text'][:50]} {reviewed}")
        return "\n".join(lines)

    def _run_auto_learn_now(self) -> str:
        yt_srcs  = self.auto_learner.get_sources("youtube")
        web_srcs = self.auto_learner.get_sources("web")
        if not yt_srcs and not web_srcs:
            return "学習ソースがまだ登録されていないよ。\n「学習先を追加: URL」でYouTube/WebのURLを登録してね。"

        def _bg():
            if yt_srcs:
                self.auto_learner.run_now("youtube", max_items=2)
            if web_srcs:
                self.auto_learner.run_now("web", max_items=2)

        import threading
        threading.Thread(target=_bg, daemon=True).start()
        total = len(yt_srcs) + len(web_srcs)
        return f"学習を開始したよ！（登録ソース {total}件）\nバックグラウンドで実行中。終わったら教えるね。"

    def generate_soliloquy(self) -> str:
        import random
        prompts = [
            "誰もいない時に独り言を一言だけつぶやいて。ユーザーへの話しかけではなく自分の独り言。",
            "一人でいる時の独り言を一言だけ。思ってることをぽつっと言って。",
            "ひとりごとを一言。日常的なことでいい。",
        ]
        prompt = random.choice(prompts)
        try:
            messages = self.llm.build_prompt(
                system_prompt=self.persona["personality"]["system_prompt"],
                conversation_history=[],
                memory_context="",
                emotion_hint="",
            )
            messages.append({"role": "user", "content": prompt})
            result = self.llm.generate_chat(messages)
            return self._clean_response(result)
        except Exception:
            phrases = ["なんか眠いな…", "今日何食べようかな", "…ふと思ったんだけど",
                       "静かだね…", "もうこんな時間か", "なにしよっかな〜"]
            return random.choice(phrases)

    def _extract_profile_hints(self, user_input: str):
        for pattern, key in _PROFILE_PATTERNS:
            m = pattern.search(user_input)
            if not m:
                continue
            if key == '誕生日':
                value = f"{m.group(1)}月{m.group(2)}日"
                try:
                    month, day = int(m.group(1)), int(m.group(2))
                    existing = [
                        a for a in self.anniversary.list_all()
                        if a.get("is_birthday")
                    ]
                    if not existing:
                        self.anniversary.add("あなたの誕生日", month, day,
                                             is_birthday=True)
                except Exception:
                    pass
            elif m.lastindex == 1:
                value = m.group(1).strip()
            else:
                continue
            auto_key = f"auto:{key}"
            existing = self.memory.get_user_profile(auto_key)
            if not existing or key in ('呼び方', '名前'):
                self.memory.set_user_profile(auto_key, value)
                print(f"[Profile] {key} = {value} を自動登録", flush=True)

    def check_schedule(self) -> str | None:
        anniv_today = self.anniversary.check_today()
        if anniv_today:
            prompt = self.anniversary.build_prompt(anniv_today)
        elif self._sched_enabled:
            sched = self.scheduler.check()
            if sched is None:
                return None
            prompt = sched["prompt"]
        else:
            return None
        try:
            messages = self.llm.build_prompt(
                system_prompt=self.persona["personality"]["system_prompt"],
                conversation_history=[],
                memory_context="",
                emotion_hint="",
            )
            messages.append({"role": "user", "content": prompt})
            result = self.llm.generate_chat(messages)
            return self._clean_response(result)
        except Exception:
            return None

    def respond_to_clipboard(self, text: str) -> str:
        preview = text[:150].replace("\n", " ")
        prompt = (
            f"ユーザーがこのテキストをコピーしたよ：「{preview}」\n"
            "自然に一言だけ反応して。"
        )
        try:
            messages = self.llm.build_prompt(
                system_prompt=self.persona["personality"]["system_prompt"],
                conversation_history=self.conversation_history[-4:],
                memory_context="",
                emotion_hint="",
            )
            messages.append({"role": "user", "content": prompt})
            result = self.llm.generate_chat(messages)
            return self._clean_response(result)
        except Exception:
            return "何かコピーしたんだね"

    def respond_to_screenshot(self, description: str) -> str:
        prompt = (
            f"スクリーンショットを撮ったよ。{description}\n"
            "画面の内容に対して自然に一言コメントして。"
        )
        try:
            messages = self.llm.build_prompt(
                system_prompt=self.persona["personality"]["system_prompt"],
                conversation_history=[],
                memory_context="",
                emotion_hint="",
            )
            messages.append({"role": "user", "content": prompt})
            result = self.llm.generate_chat(messages)
            return self._clean_response(result)
        except Exception:
            return "スクリーンショット撮ったんだね"

    # ─── 状態プロパティ ───────────────────────────────────────

    @property
    def name(self) -> str:
        return self.persona["name"]

    @property
    def is_ready(self) -> bool:
        return True

    @property
    def llm_loaded(self) -> bool:
        return self.llm.is_loaded()

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "version": self.persona["version"],
            "llm_loaded": self.llm_loaded,
            "turn_count": self.turn_count,
            "emotion": self.emotion.state.to_dict(),
            "memory_stats": self.memory.stats(),
        }


# ──────────────────────────────────────────────────────────────
# モジュールレベルヘルパ
# ──────────────────────────────────────────────────────────────

def _days_label(days: list[int]) -> str:
    names = ["月", "火", "水", "木", "金", "土", "日"]
    if days == [0, 1, 2, 3, 4]:
        return "平日"
    if days == [5, 6]:
        return "土日"
    if set(days) == set(range(7)):
        return "毎日"
    return "・".join(names[d] for d in sorted(days) if 0 <= d <= 6)


# ──────────────────────────────────────────────────────────────
# 免疫系ヒーラー関数
# ──────────────────────────────────────────────────────────────

def _immune_file_recovery(ai: AiChan, error: Exception, context: str) -> str:
    try:
        path = Path(str(error).split("'")[1]) if "'" in str(error) else None
        if path and path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"自己修復: {path.parent} を再作成しました"
    except Exception:
        pass
    return None


def _immune_json_recovery(ai: AiChan, error: Exception, context: str) -> str:
    try:
        if context and Path(context).exists():
            broken = Path(context)
            backup = broken.with_suffix(".broken")
            broken.rename(backup)
            broken.write_text("{}", encoding="utf-8")
            return f"自己修復: {broken.name} をリセットしました（破損版は .broken に退避）"
    except Exception:
        pass
    return None

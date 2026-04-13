"""
アイ メインクラス
全コンポーネントを統合して管理します
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import datetime

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
from core.youtube_learner import YouTubeLearner, extract_youtube_url
from core.web_learner import WebLearner, is_web_url
from core.file_learner import FileLearner, is_file_path
from core.tts import TTSEngine
from core.battery_monitor import get_battery_hint
from core.calendar_reader import build_calendar_hint, format_events_for_chat
from core.semantic_search import SemanticSearchEngine
from core.auto_learner import AutoLearner
from core.bio_nervous_system import BioNervousSystem
from core.growth_stage import GrowthStageSystem
from core.self_correction import SelfCorrectionSystem
from core.self_will import SelfWillEngine
from core.action_cycle import ActionCycleEngine
from core.self_development import SelfDevelopmentEngine
from core.document_exporter import DocumentExportEngine
from core.code_engine import CodeEngine


# 特殊コマンドのパターン
CMD_REMEMBER   = re.compile(r"^(これを覚えて|覚えて)[：:。]?\s*(.+)$", re.DOTALL)
CMD_FORGET     = re.compile(r"^(これを忘れて|忘れて)[：:。]?\s*(.+)$", re.DOTALL)
CMD_IMPORTANT  = re.compile(r"^(大切な思い出|絶対に覚えて)[：:。]?\s*(.+)$", re.DOTALL)
CMD_MEMORY     = re.compile(r"^(記憶|思い出)を?(見せて|確認|教えて)$")
CMD_PROFILE    = re.compile(r'^私の(.+)は[\u300c\u201c]?(.+?)[\u300d\u201d]?だよ$')
CMD_SEARCH     = re.compile(r'^(記憶を?検索|思い出を?探して)[：:]\s*(.+)$')
CMD_DIARY      = re.compile(r'^(日記|今日の日記)(を?(書いて|見せて|読んで))?$')
CMD_ANNIV_ADD  = re.compile(r'^(記念日|誕生日)を?登録[：:]\s*(.+?)\s+(\d{1,2})月(\d{1,2})日$')
CMD_ANNIV_LIST = re.compile(r'^(記念日|誕生日)(一覧|リスト|を?見せて)$')
CMD_YT_LIST    = re.compile(r'^(YouTube|ユーチューブ).*(学習|覚えた|見た).*$')
CMD_WEB_LIST   = re.compile(r'^(Web|ウェブ|サイト|ホームページ).*(学習|覚えた|読んだ).*$')
CMD_FILE_LIST  = re.compile(r'^(ファイル|PDF|書類).*(学習|覚えた|読んだ).*$')
CMD_CALENDAR   = re.compile(r'^(カレンダー|予定|スケジュール).*(見せて|確認|教えて|ある)?.*$')
CMD_BATTERY    = re.compile(r'^(バッテリー|充電|電池).*(残量|どのくらい|教えて|確認|何)?.*$')
CMD_AUTO_LEARN = re.compile(r'^(自動学習|学習スケジュール).*(状況|設定|見せて|確認|追加|登録|今すぐ|実行)?.*$')
CMD_LEARN_ADD  = re.compile(r'^(学習先|学習ソース)を?(追加|登録)[：:]\s*(.+)$')
CMD_LEARN_NOW  = re.compile(r'^(今すぐ|すぐに|即座に)?(自動)?学習(して|実行|開始)$')
CMD_MEMO_ADD   = re.compile(r'^(学習メモ|メモ)を?(覚えて|登録|追加)[：:。]?\s*(.+)$', re.DOTALL)
CMD_MEMO_LIST  = re.compile(r'^(学習メモ|メモ)(一覧|リスト|を?見せて|確認)$')
CMD_PROPOSAL   = re.compile(r'^(提案|改善案|自己開発)(一覧|リスト|を?見せて|確認|分析|実行)?$')
CMD_PROPOSAL_OK= re.compile(r'^(提案|改善案)を?(承認|OK|おっけ)[：:。]?\s*(.+)$')
CMD_PROPOSAL_NO= re.compile(r'^(提案|改善案)を?(却下|NG|だめ)[：:。]?\s*(.+)$')
CMD_SELF_AWARE = re.compile(r'^(自分|自己)(認識|構造|分析|について).*$')
CMD_MINUTES    = re.compile(r'^(議事録)(一覧|リスト|を?見せて|確認|開いて)?$')

# Sprint 2.1: セキュリティコマンド
CMD_SECURITY   = re.compile(r'^(セキュリティ|防御|ガーディアン).*(チェック|確認|状態|スコア|診断).*$')
CMD_BACKUP     = re.compile(r'^(バックアップ).*(作成|実行|取って|して|一覧|リスト).*$')
CMD_LOCKDOWN   = re.compile(r'^(ロックダウン|緊急停止|キルスイッチ)(.*)$')
CMD_UNLOCK     = re.compile(r'^(ロック解除|アイ解除)$')

# Sprint J: サーバーホーム + 自律行動コマンド
CMD_SERVER_STATUS  = re.compile(r'^(サーバー|ホーム|家)(の?)?(状態|状況|確認|接続|ステータス).*$')
CMD_SERVER_DOCKER  = re.compile(r'^(サーバー|ホーム)(の?)?Docker(一覧|状態|コンテナ).*$')
CMD_SERVER_SYNC    = re.compile(r'^(サーバー|ホーム)(に?同期|と同期|同期して).*$')
CMD_SERVER_SETUP   = re.compile(r'^(サーバー|ホーム).*?(設定|登録|接続設定).*$')
CMD_PROACTIVE      = re.compile(r'^(話しかけて|会話して|何か話して).*$')

# Sprint K: 国産AI進化コマンド
CMD_KNOWLEDGE      = re.compile(r'^(知識|ナレッジ|知ってること)(グラフ|一覧|を?見せて|確認|について).*$')
CMD_RELATIONSHIP   = re.compile(r'^(関係性|親密度|仲良し度|絆)(を?見せて|確認|どのくらい).*$')
CMD_GROWTH         = re.compile(r'^(成長|進化|アイの成長)(レポート|状況|を?見せて|確認)?.*$')
CMD_QUALITY        = re.compile(r'^(品質|応答品質|会話品質)(レポート|スコア|を?見せて|確認)?.*$')

# ヤマト計画: 国産AI進化コマンド
CMD_YAMATO_DASH    = re.compile(r'^(ヤマト|アーキテクチャ|7層|七層)(ダッシュボード|状態|確認|を?見せて)?.*$')
CMD_MOE_STATUS     = re.compile(r'^(MoE|専門家|モデル切替|エキスパート)(状態|一覧|確認|を?見せて)?.*$')
CMD_LEARNING_STATUS= re.compile(r'^(継続学習|学習エンジン|学習状況)(状態|確認|を?見せて)?.*$')
CMD_SYNTH_GEN      = re.compile(r'^(合成データ|データ生成|学習データ)(生成|作成|を?見せて|状態)?.*$')
CMD_VERIFY_STATUS  = re.compile(r'^(検証|マルチエージェント|品質検証)(状態|結果|を?見せて|確認)?.*$')

# Sprint 3.0-A: マルチモーダルコマンド
CMD_SCREENSHOT  = re.compile(r'^(スクリーンショット|画面|スクショ)(を?見て|解析|を?教えて|チェック)')
CMD_CLIPBOARD_IMG = re.compile(r'^(クリップボード|貼り付け)(の?画像|を?見て|解析)')
CMD_IMAGE_ANALYZE = re.compile(r'^(この?画像|写真)(を?見て|解析|を?教えて|について)')

# Sprint 3.0-E: 防御進化コマンド
CMD_NETWORK_CHECK  = re.compile(r'^(ネットワーク|通信)(チェック|確認|を?見て|状態)')
CMD_PROCESS_CHECK  = re.compile(r'^(プロセス|アプリ)(チェック|確認|を?見て|状態)')
CMD_DEFENSE_REPORT = re.compile(r'^(防御|セキュリティ)(レポート|報告|ダッシュボード|全体)')

# Sprint 3.0: 生活アシスタント + 知識コマンド
CMD_TASK_ADD   = re.compile(r'^(タスク|やること|TODO)を?(追加|登録)[：:。]?\s*(.+)$', re.DOTALL)
CMD_TASK_DONE  = re.compile(r'^(タスク|やること).*(完了|終わった|できた).*(#?(\d+)).*$')
CMD_TASK_LIST  = re.compile(r'^(タスク|やること|TODO)(一覧|リスト|を?見せて|確認)?$')
CMD_HABIT_ADD  = re.compile(r'^(習慣)を?(追加|登録)[：:。]?\s*(.+)$')
CMD_HABIT_REC  = re.compile(r'^(.+?)(した|やった|できた|完了)！?$')
CMD_HABIT_LIST = re.compile(r'^(習慣)(一覧|リスト|を?見せて|確認|レポート)?$')
CMD_DOC_ADD    = re.compile(r'^(ドキュメント|資料|ファイル)を?(読んで|学習|追加)[：:。]?\s*(.+)$')
CMD_DOC_LIST   = re.compile(r'^(ドキュメント|資料)(一覧|リスト|を?見せて)$')
CMD_DOC_SEARCH = re.compile(r'^(資料|ドキュメント).*?(検索|探して)[：:。]?\s*(.+)$')
# ドキュメント出力
# ─── コードエンジン コマンド ──────────────────
# ─── Web検索 コマンド ──────────────────
CMD_WEB_SEARCH   = re.compile(r'^(.+?)(について|を)?(調べて|検索|検索して|サーチ|ググって)$')
CMD_WEB_FETCH    = re.compile(r'^(URL|サイト|ページ)(を?)?(読んで|取得|見て)[：:。]?\s*(.+)$')

# ─── コードエンジン コマンド ──────────────────
CMD_CODE_ANALYZE = re.compile(r'^(この)?コード(を?)?(見て|解析|分析|チェック|確認)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_REVIEW  = re.compile(r'^(この)?コード(を?)?(レビュー|レビューして|審査)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_FIX     = re.compile(r'^(この)?(エラー|バグ)(を?)?(直して|修正|修正して|フィックス)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_TEST    = re.compile(r'^(この)?コード(の?)?(テスト|テスト書いて|テスト作って|テスト生成)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_EXPLAIN = re.compile(r'^(この)?コード(を?)?(説明|説明して|教えて|解説)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_FILE    = re.compile(r'^(ファイル)(を?)?(見て|解析|レビュー|チェック)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_RUN     = re.compile(r'^(この)?コード(を?)?(実行|走らせて|動かして|実行して|ラン)[：:。]?\s*(.+)$', re.DOTALL)

CMD_EXPORT_WORD  = re.compile(r'^(Word|ワード|レポート|報告書)に?(まとめて|作って|出力|書いて|変換)[：:。]?\s*(.+)$', re.DOTALL)
CMD_EXPORT_PPTX  = re.compile(r'^(パワポ|PowerPoint|スライド|プレゼン)に?(まとめて|作って|出力|変換)[：:。]?\s*(.+)$', re.DOTALL)
CMD_EXPORT_EXCEL = re.compile(r'^(エクセル|Excel|表|一覧表|スプレッドシート)に?(まとめて|作って|出力|変換)[：:。]?\s*(.+)$', re.DOTALL)
CMD_EXPORT_AUTO  = re.compile(r'^(資料|ドキュメント|ファイル)に?(まとめて|出力して|書き出して)[：:。]?\s*(.+)$', re.DOTALL)

# プロファイル自動深化パターン（一人称が明確な文のみ）
_PROFILE_PATTERNS = [
    (re.compile(r'(?:私|俺|うち|自分)の名前は(.+?)(?:だ|だよ|です|。|$)'), '名前'),
    (re.compile(r'(?:私|俺|うち|自分)は(\d+)歳'), '年齢'),
    (re.compile(r'(?:私|俺|うち|自分)の誕生日は(\d{1,2})月(\d{1,2})日'), '誕生日'),
    (re.compile(r'(?:私|俺|うち|自分)の仕事は(.+?)(?:だ|だよ|です)'), '職業'),
    (re.compile(r'(?:私|俺|うち|自分)は(.+?)が好き'), '好きなもの'),
    (re.compile(r'(?:私|俺|うち|自分)の趣味は(.+?)(?:だ|だよ|です)'), '趣味'),
    # 呼び方パターン（複数の言い方に対応）
    (re.compile(r'(?:私|俺|うち|自分)のことは?(.+?)(?:と|って)呼んで'), '呼び方'),
    (re.compile(r'(.+?)(?:と|って)呼んで(?:ね|くれ|ください|。|$)'), '呼び方'),
    (re.compile(r'(?:私|俺|うち|自分)の呼び方は(.+?)(?:だ|だよ|です|で|。|$)'), '呼び方'),
    (re.compile(r'ニックネームは(.+?)(?:だ|だよ|です|で|。|$)'), '呼び方'),
]


class AiChan:
    """
    アイのメインクラス。
    対話の受け取り・処理・応答生成を担当します。
    """

    def __init__(self, base_dir: str | Path = "."):
        self.base_dir = Path(base_dir)
        self._load_config()
        self._init_components()
        self.conversation_history: list[dict] = []
        self.turn_count = 0

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

        # ─── personality/*.yaml が存在すれば優先的に上書き（Sprint 1.1 移行） ──
        # persona.json は後方互換のため残すが、YAMLが優先される。
        try:
            from utils.personality_loader import load_personality
            self._personality = load_personality(self.base_dir)
            if self._personality.source == "yaml":
                # レガシーコードが self.persona["personality"]["system_prompt"] 等を
                # 参照しているため、dict を差し替えて互換を保つ。
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
            # 人格ロード失敗は致命ではない。persona.json を使い続ける。
            print(f"[Personality] YAML ロード失敗、persona.json を使用: {e}", flush=True)
            self._personality = None

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
        # （core_id による upsert 動作なので再起動しても重複しない）
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

        # TTS エンジン（設定から有効/無効を読み込む）
        tts_cfg = cfg.get("tts", {})
        self.tts = TTSEngine(
            enabled=tts_cfg.get("enabled", False),
            voice=tts_cfg.get("voice", "Kyoko"),
            rate=tts_cfg.get("rate", 175),
        )

        # セマンティック検索エンジン（オプション）
        self.semantic_search = SemanticSearchEngine(self.base_dir / "data")
        if cfg.get("semantic_search", {}).get("enabled", False):
            import threading
            threading.Thread(
                target=self.semantic_search.load, daemon=True
            ).start()

        # ビジョンエンジン（オプション）
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
        self.auto_learner = AutoLearner(self.base_dir / "data")

        # 生物神経系（反射・筋肉記憶・自律神経・免疫系）
        self.bio_nervous = BioNervousSystem(
            data_dir=self.base_dir / "data"
        )
        # 自律神経タスク登録（意識なしで動くバックグラウンド処理）
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
        # 免疫系ヒーラー登録（エラー自動回復）
        self.bio_nervous.immune.register_healer(
            "FileNotFoundError",
            lambda e, ctx: _immune_file_recovery(self, e, ctx),
        )
        self.bio_nervous.immune.register_healer(
            "JSONDecodeError",
            lambda e, ctx: _immune_json_recovery(self, e, ctx),
        )

        # 成長段階システム（赤ちゃん→幼児→…→成熟期）
        self.growth = GrowthStageSystem(
            data_dir=self.base_dir / "data"
        )
        print(f"[Growth] {self.growth.stage_emoji} {self.growth.stage_name}", flush=True)

        # 自己修正システム（不調を検知して自分で直す）
        self.self_correction = SelfCorrectionSystem(
            data_dir=self.base_dir / "data"
        )
        self._register_correction_handlers()

        # 自己意思エンジン（自分から「〜したい」と思って行動する）
        self.self_will = SelfWillEngine(
            data_dir=self.base_dir / "data"
        )
        self._register_will_actions()

        # 自律行動サイクル（Plan→Do→Check→Act）
        self.action_cycle = ActionCycleEngine(
            data_dir=self.base_dir / "data"
        )

        # 自己開発パイプライン（自分のコードを読んで改善提案する）
        self.self_dev = SelfDevelopmentEngine(
            project_root=self.base_dir,
            data_dir=self.base_dir / "data",
        )

        # ドキュメント出力エンジン
        self.doc_exporter = DocumentExportEngine(
            output_dir=self.base_dir / "data" / "exports",
        )

        # コードエンジン（コード理解・生成・修正）
        self.code_engine = CodeEngine(
            data_dir=self.base_dir / "data",
        )

        # 自律エンジン (Sprint 1.2): 階層ジョブスケジューラ
        # auto_learner._loop と共存する上位ラッパー。起動は start_autonomous() で明示的に。
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

        # 成長レポート (Sprint 1.3): 日次・週次の振り返り
        try:
            from core.growth_report import GrowthReporter
            self.growth_reporter = GrowthReporter(self)
            if self.autonomous is not None:
                # daily: 毎日 02:00 ごろ、weekly: 日曜 02:30 ごろ
                self.autonomous.register(
                    name="daily_growth_report",
                    cadence="daily",
                    fn=self.growth_reporter.daily_job,
                    hour=2,
                    minute=0,
                    description="日次成長レポート (reports/daily/*.md)",
                )
                self.autonomous.register(
                    name="weekly_growth_report",
                    cadence="weekly",
                    fn=self.growth_reporter.weekly_job,
                    hour=2,
                    minute=30,
                    weekday=6,
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
                    hour=3,
                    minute=0,
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
            # ロックダウン中なら起動時に警告
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
                    hour=4,
                    minute=0,
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

        # 時間帯挨拶のペンディング
        self._pending_greeting: str | None = None

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
            print(f"[YamatoArch] ✓ 7層アーキテクチャ基盤を初期化", flush=True)
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

    def _register_yamato_health_checks(self) -> None:
        """7層アーキテクチャにヘルスチェックを登録する"""
        arch = self.yamato_arch
        if arch is None:
            return

        # L2: 分散処理層 — MoEルーター
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

        # L3: データ管理層 — 記憶・知識グラフ
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

        # L4: モデル層 — LLM
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

        # L5: 学習制御層 — 継続学習
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

        # L6: 推論最適化層 — 品質評価
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

        # L7: API/サービス層
        def check_l7() -> dict:
            return {
                "status": "ok",
                "message": f"ターン数: {self.turn_count}",
                "turn_count": self.turn_count,
            }
        arch.register_health_check(7, check_l7)

    def start_autonomous(self) -> bool:
        """
        自律エンジン（階層ジョブスケジューラ）を起動する。

        呼び出し側（desktop_pet / CLI / main）で、バックグラウンド常駐が
        必要なモードの時だけ呼ぶ。テスト環境では呼ばないことで副作用を
        避けられる。
        """
        if self.autonomous is None:
            return False
        self.autonomous.start()
        return True

    def stop_autonomous(self) -> None:
        if self.autonomous is not None:
            self.autonomous.stop()

    # ─── 対話処理 ─────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """
        ユーザーの名前・呼び方をシステムプロンプト本体に直接埋め込みます。
        「あなた」と登録名が同一人物であることを明示し、俯瞰視点を防ぎます。

        脊髄反射パターン: プロフィールが変わるまでキャッシュを再利用。
        """
        profile = self.memory.get_all_user_profile()
        profile_key = (
            profile.get("呼び方", ""),
            profile.get("auto:呼び方", ""),
            profile.get("名前", ""),
            profile.get("auto:名前", ""),
        )

        # キャッシュヒット: プロフィールに変化なし → そのまま返す
        if hasattr(self, "_sys_prompt_cache") and self._sys_prompt_cache_key == profile_key:
            return self._sys_prompt_cache

        base = self.persona["personality"]["system_prompt"]

        # 呼び方 > 名前 の優先順位
        call_name = profile_key[0] or profile_key[1] or profile_key[2] or profile_key[3] or ""
        full_name = profile_key[2] or profile_key[3] or ""

        if call_name:
            lines = [
                f"\n今話している「あなた」は「{call_name}」のこと。",
                f"「あなた」と「{call_name}」は同じ一人の人。呼ぶときは必ず「{call_name}」と呼んで。",
            ]
            if full_name and full_name != call_name:
                lines.append(f"フルネームは「{full_name}」。")
            base = base + "".join(lines)

        self._sys_prompt_cache = base
        self._sys_prompt_cache_key = profile_key
        return base

    def chat(self, user_input: str) -> str:
        """
        ユーザーの入力を受け取り、アイの応答を返します。
        """
        user_input = user_input.strip()
        if not user_input:
            return ""

        self.turn_count += 1

        # Sprint J: ユーザー操作を記録（アイドル検出用）
        if getattr(self, "autonomous_actions", None):
            self.autonomous_actions.on_user_interaction()

        # システム内部呼び出しは履歴に残さない
        is_system_call = user_input in (
            "チャットを開いてくれた。自然に一言だけ話しかけて。",
            "起動した。一言だけ自然に話しかけて。",
            "起動したよ。短く一言挨拶して。",
        )

        # Sprint J: 時間帯挨拶をチェック（コマンド/システム以外の通常会話時）
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

        # ── ユーザー訂正検出 ──
        # 訂正が検出されたら反射をスキップし、必ずLLMで再応答する
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

        # ── 生物神経系: 反射 → 大脳(LLM) ──
        # 短い挨拶・相槌のみ反射で処理。それ以外は全てLLMへ。
        # 筋肉記憶: 現行プリセットは精度不足で無効。会話統計から高精度パターンが
        # 蓄積されたら筋肉記憶に昇格し、LLM負荷を軽減する設計。
        if getattr(self, "bio_nervous", None) and not is_system_call and not _correction_entry:
            bio_response, layer = self.bio_nervous.process_input(user_input)
            if bio_response is not None:
                # 反射で応答完了 → LLMも記憶検索もスキップ
                self.conversation_history.append({"role": "user", "content": user_input})
                self.conversation_history.append({"role": "assistant", "content": bio_response})
                # 自律神経ハートビート（呼吸のように軽く）
                self.bio_nervous.autonomic.heartbeat(self.turn_count)
                # TTS
                try:
                    self.tts.speak(bio_response)
                except Exception:
                    pass
                # 最小限の記録（話題追跡・感情保存）
                if not is_system_call:
                    self.topic_tracker.extract_topics(user_input, self.turn_count)
                    self.emotion.save_if_changed()
                    # 訂正学習: 反射応答も記録（次の訂正検出用）
                    if getattr(self, "correction_learning", None):
                        self.correction_learning.record_turn(user_input, bio_response)
                # 履歴トリミング
                if len(self.conversation_history) > 12:
                    self.conversation_history = self.conversation_history[-12:]
                return bio_response

        # Sprint K1: 会話知能分析（意図分類・応答戦略・文脈チェーン）
        conv_analysis = None
        if getattr(self, "conv_intelligence", None):
            try:
                conv_analysis = self.conv_intelligence.analyze_input(
                    user_input, self.conversation_history, self.turn_count
                )
            except Exception:
                pass

        # ヤマト A1: MoEルーティング（意図に基づくモデル選択）
        # 成長段階: 青年期以降のみ有効（専門性が育つまで使えない）
        _growth = getattr(self, "growth", None)
        _moe_ok = not _growth or _growth.can_use_moe_routing()
        if _moe_ok and getattr(self, "moe_router", None) and self.moe_router.expert_count > 0:
            try:
                task_type = "chat"
                if conv_analysis and conv_analysis.get("intent"):
                    task_type = conv_analysis["intent"]
                routing = self.moe_router.route(task_type=task_type)
                if routing.expert_name:
                    expert_cfg = self.moe_router.get_expert_config(routing.expert_name)
                    # LLMの一時設定を適用（温度・最大トークン）
                    if hasattr(self.llm, "override_params"):
                        self.llm.override_params(expert_cfg)
            except Exception:
                pass

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

        # ── 追加コンテキスト（合計400文字以内に制限。4kモデルの品質維持） ──
        extra_parts: list[str] = []

        # Sprint 3.0-B: RAG からドキュメントコンテキストを追加
        if getattr(self, "rag", None) and self.rag.total_chunks > 0:
            try:
                rag_ctx = self.rag.search_for_context(user_input, limit=1, max_chars=150)
                if rag_ctx:
                    extra_parts.append(rag_ctx)
            except Exception:
                pass

        # Sprint K2: 知識グラフからコンテキストを追加（児童期以降）
        _kg_ok = not _growth or _growth.can_use_knowledge_graph()
        if _kg_ok and getattr(self, "knowledge_graph", None):
            try:
                kg_ctx = self.knowledge_graph.get_context_for_chat(user_input, max_chars=120)
                if kg_ctx:
                    extra_parts.append(kg_ctx)
            except Exception:
                pass

        # Sprint K1: 会話知能の応答指示をコンテキストに追加
        if conv_analysis and conv_analysis.get("instruction_text"):
            extra_parts.append(conv_analysis["instruction_text"][:80])

        # Sprint K3: 性格進化ヒントをコンテキストに追加
        if getattr(self, "personality_evo", None):
            try:
                evo_hint = self.personality_evo.get_personality_prompt_hint()
                if evo_hint:
                    extra_parts.append(evo_hint[:60])
            except Exception:
                pass

        # ユーザー訂正コンテキストを注入（最優先）
        if _correction_context:
            extra_parts.insert(0, _correction_context)
        # 最近の訂正履歴も追加（同じ間違いの繰り返し防止）
        elif getattr(self, "correction_learning", None):
            _corr_hint = self.correction_learning.get_recent_corrections_hint(max_entries=2)
            if _corr_hint:
                extra_parts.append(_corr_hint[:150])

        # 追加コンテキストを400文字以内で結合
        extra = "\n".join(extra_parts)
        if extra:
            memory_context = memory_context + "\n" + extra[:400]

        # 会話履歴に追加
        self.conversation_history.append({"role": "user", "content": user_input})

        # LLMでの応答生成（ユーザー名をシステムプロンプト本体に埋め込む）
        messages = self.llm.build_prompt(
            system_prompt=self._build_system_prompt(),
            conversation_history=self.conversation_history,
            memory_context=memory_context,
            emotion_hint="",
        )

        response = self.llm.generate_chat(messages)
        response = self._clean_response(response)

        # Sprint K1: 会話知能による後処理（日本語品質フィルタ）
        if getattr(self, "conv_intelligence", None):
            try:
                response = self.conv_intelligence.post_process(response)
            except Exception:
                pass

        # ヤマト C7: マルチエージェント検証
        if getattr(self, "multi_verifier", None):
            try:
                consensus = self.multi_verifier.verify(user_input, response)
                if self.multi_verifier.should_regenerate(consensus) and self.llm.is_loaded():
                    hint = consensus.improvement_hint
                    if hint:
                        retry_msgs = list(messages)
                        retry_msgs[-1] = {
                            "role": retry_msgs[-1]["role"],
                            "content": retry_msgs[-1]["content"] + f"\n{hint}",
                        }
                        retry = self.llm.generate_chat(retry_msgs)
                        retry = self._clean_response(retry)
                        retry_consensus = self.multi_verifier.verify(user_input, retry)
                        if retry_consensus.overall_score > consensus.overall_score:
                            response = retry
            except Exception:
                pass

        # Sprint K4: 応答品質自己評価
        # 脊髄反射パターン: 短い入力+短い応答は評価スキップ（LLM再呼び出し回避）
        _skip_eval = (
            len(user_input) <= 8 and len(response) <= 60  # 短い相槌はスキップ
            or not getattr(self, "response_evaluator", None)
        )
        _evaluated_quality: float | None = None
        if not _skip_eval:
            try:
                quality = self.response_evaluator.evaluate(user_input, response)
                _evaluated_quality = quality.overall
                # 品質が低すぎる場合、改善ヒントで再生成を試みる（1回だけ）
                if self.response_evaluator.should_regenerate(quality) and self.llm.is_loaded():
                    hint = self.response_evaluator.get_improvement_hint(quality)
                    if hint:
                        retry_msgs = list(messages)
                        retry_msgs[-1] = {
                            "role": retry_msgs[-1]["role"],
                            "content": retry_msgs[-1]["content"] + f"\n補足: {hint}",
                        }
                        retry_response = self.llm.generate_chat(retry_msgs)
                        retry_response = self._clean_response(retry_response)
                        retry_quality = self.response_evaluator.evaluate(user_input, retry_response)
                        if retry_quality.overall > quality.overall:
                            response = retry_response
                            _evaluated_quality = retry_quality.overall
            except Exception:
                pass

        # TTS で読み上げ（有効な場合のみ）
        try:
            self.tts.speak(response)
        except Exception:
            pass

        # 応答を履歴に追加
        self.conversation_history.append({"role": "assistant", "content": response})

        # ユーザー訂正学習: 今回のターンを記録（次回の訂正検出用）
        if getattr(self, "correction_learning", None) and not is_system_call:
            self.correction_learning.record_turn(user_input, response)

        if not is_system_call:
            # 全会話をDBに永続保存（重要度を評価して分類）
            importance = self._estimate_importance(user_input)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.memory.add_mid_term(
                content=f"[{timestamp}] ユーザー:「{user_input}」→ アイ:「{response}」",
                importance=importance,
                emotional_weight=self.emotion.state.affection,
                tags=["conversation", "auto_saved"],
            )

            # B: 話題を抽出して追跡
            self.topic_tracker.extract_topics(user_input, self.turn_count)

            # プロファイル自動深化（一人称の自己紹介を検出）
            self._extract_profile_hints(user_input)

            # Sprint 2.0: サブシステム更新をバッチ化（1スレッドにまとめる）
            _ui = user_input  # クロージャ用
            _resp = response
            _tc = self.turn_count

            def _batch_updates():
                # 感情履歴を記録
                try:
                    self.emotion_history.record(self.emotion.state.to_dict())
                except Exception:
                    pass
                # 関心マップを更新
                try:
                    self.interest_map.update(_ui)
                except Exception:
                    pass
                # 目標を検出
                try:
                    self.goal_tracker.detect_and_add(_ui)
                except Exception:
                    pass
                # セマンティックインデックス追加
                try:
                    if self.semantic_search.is_ready():
                        recent = self.memory.get_recent(limit=1)
                        if recent:
                            self.semantic_search.add_memory(recent[0])
                except Exception:
                    pass
                # 日記（日付変わり時のみ）
                today = datetime.now().date()
                if today != self._last_diary_date:
                    self._last_diary_date = today
                    try:
                        self.diary.write_today(
                            emotion_snapshot=self.emotion.state.to_dict()
                        )
                    except Exception:
                        pass
                # 学習データ蓄積
                ar = sum(1 for c in _resp if c.isascii() and c.isalpha()) / max(len(_resp), 1)
                if ar < 0.3 and len(_resp) > 2:
                    self.learning.add_conversation(_ui, _resp, save=True)
                # 記憶圧縮（10ターンごと）
                if _tc % 10 == 0:
                    self.compressor.compress()
                # 感情状態を保存（閾値以上の変化時のみI/O実行）
                self.emotion.save_if_changed()

                # Sprint K2: 知識グラフに会話を反映
                if getattr(self, "knowledge_graph", None):
                    try:
                        self.knowledge_graph.extract_from_conversation(_ui, _resp)
                    except Exception:
                        pass

                # Sprint K3: 性格進化に会話を反映
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

                # 品質スコア（会話統計・成長記録用）
                _q_score = _evaluated_quality if _evaluated_quality is not None else 0.6

                # 成長段階: 会話経験を記録
                if getattr(self, "growth", None):
                    try:
                        self.growth.on_conversation(quality_score=_q_score)
                        # 知識グラフエントリ数を同期
                        kg = getattr(self, "knowledge_graph", None)
                        if kg and hasattr(kg, "total_entities"):
                            self.growth.on_knowledge_update(kg.total_entities)
                        # 話題の多様性を成長に反映
                        if getattr(self, "topic_tracker", None):
                            topic_count = len(getattr(self.topic_tracker, "topics", []))
                            while self.growth._metrics.unique_topics < topic_count:
                                self.growth.on_new_topic()
                        # 感情の幅を成長に反映
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

                # 行動サイクル: 進捗記録
                if getattr(self, "action_cycle", None):
                    try:
                        self.action_cycle.record_progress("any", 1.0)
                        self.action_cycle.record_quality(_q_score)
                    except Exception:
                        pass

                # 自己修正: 品質を監視し、不調なら自動で治す
                if getattr(self, "self_correction", None):
                    try:
                        corrections = self.self_correction.on_turn(
                            quality_score=_q_score,
                            response=_resp,
                        )
                        # 自己修正が実行されたら成長に反映
                        if corrections and getattr(self, "growth", None):
                            for c in corrections:
                                if c.get("ok"):
                                    self.growth.on_error_recovery()
                            self.growth.save_if_changed()
                    except Exception:
                        pass

                # ヤマト A2: 継続学習エンジンに高品質会話を蓄積
                if getattr(self, "continuous_learner", None):
                    try:
                        self.continuous_learner.learn_from_conversation(
                            _ui, _resp, quality_score=_q_score
                        )
                    except Exception:
                        pass

                # ヤマト C6: 合成データ生成のテンプレート学習
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

            import threading
            threading.Thread(target=_batch_updates, daemon=True).start()

            # 長すぎる会話履歴をトリミング（最新6ターン = 12メッセージ）
            # Phi-3-mini-4kはコンテキストが限られるため短く保つ
            if len(self.conversation_history) > 12:
                self.conversation_history = self.conversation_history[-12:]
        else:
            # システム呼び出しは履歴から削除する
            self.conversation_history = self.conversation_history[:-2]

        # 生物神経系: 自律神経ハートビート（LLMパスでも実行）
        if getattr(self, "bio_nervous", None):
            self.bio_nervous.autonomic.heartbeat(self.turn_count)

        # 自己意思: 保留中のメッセージがあれば応答に付加
        if getattr(self, "self_will", None):
            will_msg = self.self_will.pending_message
            if will_msg:
                response = f"{will_msg}\n\n{response}"

        # Sprint J: 保留中の時間帯挨拶を応答の前に付加
        if self._pending_greeting:
            response = f"{self._pending_greeting}\n\n{response}"
            self._pending_greeting = None

        return response

    def _clean_response(self, text: str) -> str:
        """
        Phi-3の出力を清書します:
        - 「アイ:」などのプレフィックスを除去
        - 英語のメタ注釈行（**...**, (Note:...) 等）を除去
        - 英語が大部分なら日本語フォールバック
        - 長すぎる応答を2文に制限
        """
        import re
        # 会話シミュレーション（「ユーザー:」以降のロールプレイ）を切り捨て
        for marker in ['ユーザー:', 'ユーザー：', 'User:', 'しょうた:']:
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx].strip()
        # プレフィックス除去（「アイ:」「AI:」など）
        text = re.sub(r'^(アイ|AI|Assistant|アシスタント)\s*[:：]\s*', '', text).strip()
        # 括弧で始まる説明文を除去
        text = re.sub(r'^\(.*?\)\s*', '', text).strip()
        # 漏れ出たブラケット指示を除去
        text = re.sub(r'\[★[^\]]*\]', '', text).strip()
        text = re.sub(r'指示[１２３\d][^\s。]*', '', text).strip()

        # 三人称ナレーション行を除去
        # 「アイは〜」「アイが〜」で始まる行（一人称ではない）
        lines = text.splitlines()
        filtered = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # 「アイは/が〜と言った」「アイは/が〜する」など俯瞰描写
            if re.match(r'^アイ[はがのをに]', stripped):
                continue
            filtered.append(stripped)
        text = '\n'.join(filtered).strip() if filtered else text.strip()

        # 英語のメタ注釈行・翻訳行を除去（**...**, (Note:...), (Translation:...) 等）
        lines = text.splitlines()
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # 空行はスキップ
            if not stripped:
                continue
            # **...** 形式のヘッダー行を除去
            if re.match(r'^\*\*.*\*\*$', stripped):
                continue
            # # 見出し行を除去
            if re.match(r'^#+\s', stripped):
                continue
            # (Note: ...) や (Translation: ...) などの英語注釈行を除去
            if re.match(r'^\((?:Note|Translation|Instruction|Example|Solution)[:\s]', stripped, re.IGNORECASE):
                continue
            # 日本語文字がなく英語単語がある行が来たらそこで打ち切り
            has_japanese = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', stripped))
            if not has_japanese and re.search(r'[a-zA-Z]{3,}', stripped):
                break
            # コード片・技術テキストの混入を検出して打ち切り
            if re.search(r'(例のコード|Cookie\.js|```|import |def |class |function |var |const |let )', stripped):
                break
            cleaned_lines.append(stripped)
        text = '\n'.join(cleaned_lines).strip()

        # 英語が大部分（60%超）の場合のみフォールバック（技術用語の混在は許容）
        ascii_ratio = sum(1 for c in text if c.isascii() and c.isalpha()) / max(len(text), 1)
        has_japanese = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text))
        if ascii_ratio > 0.6 and not has_japanese:
            import random
            fallbacks = [
                "ごめん、うまく言えなかった。もう一回話しかけてみて",
                "えっと…もう少し違う言い方で聞いてもいい？",
                "ちょっと考えすぎちゃった。もう一度話しかけてね",
            ]
            return random.choice(fallbacks)

        # max_sentences を超えたら打ち切り（デフォルト6文）
        max_s = getattr(self, '_max_sentences', 6)
        sentences = re.split(r'(?<=[。！？\n])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) > max_s:
            text = ''.join(sentences[:max_s])

        return text if text else "うん、聞いてるよ"

    def _handle_commands(self, user_input: str) -> str | None:
        """特殊コマンドを解析・実行します"""

        # 「これを覚えて: ○○」
        m = CMD_REMEMBER.match(user_input)
        if m:
            content = m.group(2).strip()
            self.memory.remember(content, is_important=False)
            return f"うん、「{content}」を覚えたよ！大切にしておくね。💕"

        # 「絶対に覚えて: ○○」（保護記憶）
        m = CMD_IMPORTANT.match(user_input)
        if m:
            content = m.group(2).strip()
            self.memory.remember(content, is_important=True)
            return f"「{content}」を大切な思い出として、ずっと覚えておくね。絶対に忘れないよ！✨"

        # 「これを忘れて: ○○」
        m = CMD_FORGET.match(user_input)
        if m:
            content = m.group(2).strip()
            deleted = self.memory.forget(content)
            if deleted > 0:
                return f"「{content}」に関する記憶を {deleted} 件削除したよ。"
            else:
                return f"「{content}」に関する記憶は見つからなかったよ。（保護された思い出は削除できないんだ）"

        # 「記憶を見せて」
        if CMD_MEMORY.match(user_input):
            return self._show_memory_summary()

        # 「私の○○は△△だよ」（プロファイル登録）
        m = CMD_PROFILE.match(user_input)
        if m:
            key   = m.group(1).strip()
            value = m.group(2).strip()
            self.memory.set_user_profile(key, value)
            return f"了解！あなたの「{key}」は「{value}」だね。ちゃんと覚えたよ😊"

        # 「記憶を検索: ○○」（セマンティック検索 or キーワード検索）
        m = CMD_SEARCH.match(user_input)
        if m:
            query   = m.group(2).strip()
            # セマンティック検索が使えれば優先
            all_mems = self.memory.get_recent(limit=200)
            if self.semantic_search.is_ready():
                results = self.semantic_search.search(query, all_mems, limit=5)
            else:
                results = self.memory.search(query, limit=5)
            if not results:
                return f"「{query}」に関する記憶は見つからなかったよ。"
            lines = [f"「{query}」に関する記憶だよ："]
            for r in results:
                snippet = r.content[:60].replace("\n", " ")
                lines.append(f"・{snippet}…")
            return "\n".join(lines)

        # 「日記を見せて」「日記を書いて」
        if CMD_DIARY.match(user_input):
            if "書いて" in user_input:
                entry = self.diary.write_today(
                    emotion_snapshot=self.emotion.state.to_dict()
                )
                if not entry:
                    return "今日はまだあまり話してないから書けることが少ないかな。もう少し話そう！"
                return self.diary.format_for_display(entry)
            else:
                entry = self.diary.get_entry()
                if entry:
                    return self.diary.format_for_display(entry)
                # なければ今すぐ生成
                entry = self.diary.write_today(
                    emotion_snapshot=self.emotion.state.to_dict()
                )
                if entry:
                    return self.diary.format_for_display(entry)
                return "今日の日記はまだ書いてないよ。もう少し話してから見てね！"

        # 「記念日を登録: 名前 M月D日」
        m = CMD_ANNIV_ADD.match(user_input)
        if m:
            is_bday = m.group(1) == "誕生日"
            label   = m.group(2).strip()
            month   = int(m.group(3))
            day     = int(m.group(4))
            self.anniversary.add(label, month, day, is_birthday=is_bday)
            kind = "誕生日" if is_bday else "記念日"
            return f"「{label}」を{kind}として{month}月{day}日に登録したよ！毎年その日になったら話しかけるね。"

        # 「記念日一覧」
        if CMD_ANNIV_LIST.match(user_input):
            items = self.anniversary.list_all()
            if not items:
                return "まだ記念日は登録されていないよ。「誕生日を登録: 名前 M月D日」で追加できるよ！"
            lines = ["登録済みの記念日だよ："]
            for item in items:
                kind = "🎂" if item.get("is_birthday") else "🎉"
                lines.append(f"{kind} {item['label']}  {item['month']}月{item['day']}日")
            return "\n".join(lines)

        # 「YouTube学習一覧」
        if CMD_YT_LIST.match(user_input):
            return self._show_youtube_learned()

        # 「Web学習一覧」
        if CMD_WEB_LIST.match(user_input):
            learned = self.web_learner.list_learned()
            if not learned:
                return "まだ Web ページを学習してないよ。URL をチャットに貼ると学習できるよ！"
            lines = [f"学習済み Web ページ {len(learned)} 件だよ："]
            for item in learned[-8:]:
                lines.append(f"・「{item['title']}」（{item.get('learned_at','')[:10]}）")
            return "\n".join(lines)

        # 「ファイル学習一覧」
        if CMD_FILE_LIST.match(user_input):
            learned = self.file_learner.list_learned()
            if not learned:
                return "まだファイルを学習してないよ。ファイルのパスをチャットに貼ると学習できるよ！"
            lines = [f"学習済みファイル {len(learned)} 件だよ："]
            for item in learned[-8:]:
                lines.append(f"・「{item['name']}」（{item.get('learned_at','')[:10]}）")
            return "\n".join(lines)

        # 「カレンダーを見せて」
        if CMD_CALENDAR.match(user_input):
            return format_events_for_chat()

        # 「バッテリー残量」
        if CMD_BATTERY.match(user_input):
            from core.battery_monitor import get_battery_info
            info = get_battery_info()
            if not info["found"]:
                return "バッテリー情報を取得できなかったよ。"
            pct = info["percent"]
            charging = "充電中" if info["charging"] else "放電中"
            return f"バッテリーは今 {pct}%（{charging}）だよ。"

        # YouTube URL が含まれていたら学習処理
        yt_url = extract_youtube_url(user_input)
        if yt_url:
            return self._learn_youtube(yt_url)

        # Web URL が含まれていたら学習処理
        web_url = is_web_url(user_input)
        if web_url:
            return self._learn_web(web_url)

        # ファイルパスが含まれていたら学習処理
        file_path = is_file_path(user_input)
        if file_path:
            return self._learn_file(file_path)

        # 自動学習スケジュール確認・管理
        if CMD_AUTO_LEARN.match(user_input):
            return self._show_auto_learn_status()

        # 学習ソース追加: 「学習先を追加: URL」
        m = CMD_LEARN_ADD.match(user_input)
        if m:
            value = m.group(3).strip()
            return self._add_learn_source(value)

        # 即時学習実行
        if CMD_LEARN_NOW.match(user_input):
            return self._run_auto_learn_now()

        # メモ登録: 「学習メモを覚えて: ○○」
        m = CMD_MEMO_ADD.match(user_input)
        if m:
            text = m.group(3).strip()
            entry = self.auto_learner.add_memo(text)
            return f"メモを学習リストに登録したよ！📝\n「{text[:60]}」\n夜の復習タイムに振り返るね。"

        # メモ一覧
        if CMD_MEMO_LIST.match(user_input):
            return self._show_memo_list()

        # ─── 自己開発コマンド ──────────────────────────────

        # 「提案一覧」「改善案を見せて」「自己開発分析」
        if CMD_PROPOSAL.match(user_input):
            return self._handle_proposal_command(user_input)

        # 「提案を承認: proposal_id」
        m = CMD_PROPOSAL_OK.match(user_input)
        if m:
            pid = m.group(3).strip()
            sd = getattr(self, "self_dev", None)
            if sd and sd.proposal_store.approve(pid):
                return f"提案「{pid}」を承認したよ！対応を進めるね。"
            return f"提案「{pid}」が見つからなかったよ。「提案一覧」で確認してみてね。"

        # 「提案を却下: proposal_id」
        m = CMD_PROPOSAL_NO.match(user_input)
        if m:
            pid = m.group(3).strip()
            sd = getattr(self, "self_dev", None)
            if sd and sd.proposal_store.reject(pid):
                return f"提案「{pid}」を却下したよ。了解！"
            return f"提案「{pid}」が見つからなかったよ。"

        # 「自分について」「自己認識」
        if CMD_SELF_AWARE.match(user_input):
            return self._show_self_awareness()

        # 議事録一覧
        if CMD_MINUTES.match(user_input):
            return self._show_minutes_list()

        # ─── Sprint 3.0-A: マルチモーダルコマンド ────────────────

        # 「スクショ見て」「画面チェック」
        if CMD_SCREENSHOT.match(user_input) and getattr(self, "multimodal", None):
            return self.multimodal.describe_screenshot()

        # 「クリップボードの画像を見て」
        if CMD_CLIPBOARD_IMG.match(user_input) and getattr(self, "multimodal", None):
            return self.multimodal.describe_clipboard_image()

        # 「この画像を見て」
        if CMD_IMAGE_ANALYZE.match(user_input) and getattr(self, "multimodal", None):
            return "画像パスを教えてね！「資料を読んで: /path/to/image.png」の形式で送ってね。\nまたは「スクショ見て」「クリップボードの画像を見て」も使えるよ！"

        # ─── Sprint 3.0-E: 防御進化コマンド ────────────────────

        # 「ネットワークチェック」「通信確認」
        if CMD_NETWORK_CHECK.match(user_input):
            if getattr(self, "network_monitor", None):
                return self.network_monitor.get_connection_summary()
            return "ネットワークモニターが初期化されていないよ。"

        # 「プロセスチェック」「アプリ確認」
        if CMD_PROCESS_CHECK.match(user_input):
            if getattr(self, "process_monitor", None):
                return self.process_monitor.get_summary()
            return "プロセスモニターが初期化されていないよ。"

        # 「セキュリティレポート」「防御ダッシュボード」
        if CMD_DEFENSE_REPORT.match(user_input):
            if getattr(self, "defense_dashboard", None):
                return self.defense_dashboard.get_full_report()
            return "防御ダッシュボードが初期化されていないよ。"

        # ─── Sprint 3.0: 生活アシスタント + 知識コマンド ────────

        # タスク追加: 「タスクを追加: 明日までにレポート」
        m = CMD_TASK_ADD.match(user_input)
        if m and getattr(self, "task_manager", None):
            text = m.group(3).strip()
            task = self.task_manager.add_from_text(text)
            due = f"（期限: {task.due_date}）" if task.due_date else ""
            return f"📌 タスクを登録したよ！\n「{task.title}」{due}\nID: #{task.id}"

        # タスク完了: 「タスク完了 #1」
        m = CMD_TASK_DONE.match(user_input)
        if m and getattr(self, "task_manager", None):
            task_id = int(m.group(4))
            if self.task_manager.complete(task_id):
                return f"✅ タスク #{task_id} を完了にしたよ！お疲れさま！"
            return f"タスク #{task_id} が見つからないよ。"

        # タスク一覧
        if CMD_TASK_LIST.match(user_input) and getattr(self, "task_manager", None):
            return self.task_manager.format_task_list()

        # 習慣追加: 「習慣を追加: 運動」
        m = CMD_HABIT_ADD.match(user_input)
        if m and getattr(self, "habit_tracker", None):
            name = m.group(3).strip()
            self.habit_tracker.add_habit(name)
            return f"🎯 習慣「{name}」を登録したよ！毎日一緒に頑張ろうね。"

        # 習慣一覧/レポート
        if CMD_HABIT_LIST.match(user_input) and getattr(self, "habit_tracker", None):
            if "レポート" in user_input:
                return self.habit_tracker.get_weekly_report()
            return self.habit_tracker.get_today_status()

        # 習慣記録: 「運動した！」
        m = CMD_HABIT_REC.match(user_input)
        if m and getattr(self, "habit_tracker", None):
            name = m.group(1).strip()
            if name in self.habit_tracker.list_habits():
                self.habit_tracker.record(name)
                streak = self.habit_tracker.get_streak(name)
                msg = f"✅ 「{name}」を記録したよ！"
                if streak > 1:
                    msg += f" 🔥 {streak}日連続！すごい！"
                return msg

        # ドキュメント追加: 「資料を読んで: /path/to/file」
        m = CMD_DOC_ADD.match(user_input)
        if m and getattr(self, "rag", None):
            path = m.group(3).strip()
            result = self.rag.add_document(path)
            if "error" in result:
                return f"読み込めなかったよ: {result['error']}"
            if result.get("status") == "already_indexed":
                return "この資料はもう読み込み済みだよ！"
            return f"📄 「{result['name']}」を読み込んだよ！{result['chunks']}チャンクに分割して覚えたよ。"

        # ドキュメント一覧
        if CMD_DOC_LIST.match(user_input) and getattr(self, "rag", None):
            docs = self.rag.list_documents()
            if not docs:
                return "まだ資料は登録されていないよ。「資料を読んで: /path」で追加できるよ！"
            lines = ["📚 登録済み資料："]
            for d in docs:
                lines.append(f"  • {d['name']} ({d['chunks']}チャンク)")
            return "\n".join(lines)

        # ドキュメント検索: 「資料から検索: キーワード」
        m = CMD_DOC_SEARCH.match(user_input)
        if m and getattr(self, "rag", None):
            query = m.group(3).strip()
            results = self.rag.search(query, limit=3)
            if not results:
                return f"「{query}」に関する情報は資料から見つからなかったよ。"
            lines = [f"📖 「{query}」の検索結果："]
            for r in results:
                snippet = r["text"][:100].replace("\n", " ")
                lines.append(f"  [{r['doc_name']}] {snippet}…")
            return "\n".join(lines)

        # ─── Web検索 コマンド ──────────────────

        # 「〇〇について調べて」
        m = CMD_WEB_SEARCH.match(user_input)
        if m:
            return self._handle_web_search(m.group(1).strip())

        # 「URL読んで: https://...」
        m = CMD_WEB_FETCH.match(user_input)
        if m:
            return self._handle_web_fetch(m.group(4).strip())

        # ─── コードエンジン コマンド ──────────────────

        # 「コードを見て: xxx」「コード解析: xxx」
        m = CMD_CODE_ANALYZE.match(user_input)
        if m:
            return self._handle_code_analyze(m.group(4).strip())

        # 「コードレビュー: xxx」
        m = CMD_CODE_REVIEW.match(user_input)
        if m:
            return self._handle_code_review(m.group(4).strip())

        # 「エラー直して: xxx」
        m = CMD_CODE_FIX.match(user_input)
        if m:
            return self._handle_code_fix(m.group(5).strip())

        # 「コードテスト書いて: xxx」
        m = CMD_CODE_TEST.match(user_input)
        if m:
            return self._handle_code_test(m.group(4).strip())

        # 「コード説明して: xxx」
        m = CMD_CODE_EXPLAIN.match(user_input)
        if m:
            return self._handle_code_explain(m.group(4).strip())

        # 「ファイルを見て: path」
        m = CMD_CODE_FILE.match(user_input)
        if m:
            return self._handle_code_file(m.group(4).strip())

        # 「コード実行: code」
        m = CMD_CODE_RUN.match(user_input)
        if m:
            return self._handle_code_run(m.group(4).strip())

        # ─── ドキュメント出力コマンド ──────────────────
        m = CMD_EXPORT_WORD.match(user_input)
        if m:
            return self._handle_export("word", m.group(3).strip())

        m = CMD_EXPORT_PPTX.match(user_input)
        if m:
            return self._handle_export("pptx", m.group(3).strip())

        m = CMD_EXPORT_EXCEL.match(user_input)
        if m:
            return self._handle_export("excel", m.group(3).strip())

        m = CMD_EXPORT_AUTO.match(user_input)
        if m:
            return self._handle_export("word", m.group(3).strip())

        # ─── Sprint 2.1: セキュリティコマンド ──────────────────

        # 「セキュリティチェック」「防御診断」
        if CMD_SECURITY.match(user_input):
            return self._run_security_check()

        # 「バックアップ作成」「バックアップ一覧」
        if CMD_BACKUP.match(user_input):
            if "一覧" in user_input or "リスト" in user_input:
                return self._show_backup_list()
            return self._run_backup()

        # 「ロックダウン」「緊急停止」
        m = CMD_LOCKDOWN.match(user_input)
        if m:
            reason = m.group(2).strip() or "手動実行"
            return self._run_lockdown(reason)

        # 「ロック解除」
        if CMD_UNLOCK.match(user_input):
            return self._run_unlock()

        # ─── Sprint J: サーバー・自律行動コマンド ──────────────

        # 「サーバー状態」「ホーム確認」
        if CMD_SERVER_STATUS.match(user_input):
            return self._server_status()

        # 「サーバーDocker一覧」
        if CMD_SERVER_DOCKER.match(user_input):
            return self._server_docker()

        # 「サーバーに同期」
        if CMD_SERVER_SYNC.match(user_input):
            return self._server_sync()

        # 「サーバー設定」「ホーム接続設定」
        if CMD_SERVER_SETUP.match(user_input):
            return self._server_setup_guide()

        # 「話しかけて」「何か話して」
        if CMD_PROACTIVE.match(user_input):
            return self._proactive_talk()

        # ─── Sprint K: 国産AI進化コマンド ──────────────────────

        # 「知識グラフ」「知ってることを見せて」
        if CMD_KNOWLEDGE.match(user_input):
            kg = getattr(self, "knowledge_graph", None)
            if kg:
                return kg.get_user_world_summary()
            return "知識グラフがまだ初期化されていないよ。"

        # 「関係性」「親密度」
        if CMD_RELATIONSHIP.match(user_input):
            evo = getattr(self, "personality_evo", None)
            if evo:
                return evo.get_relationship_display()
            return "関係性トラッカーがまだ初期化されていないよ。"

        # 「成長レポート」「アイの成長」
        if CMD_GROWTH.match(user_input):
            evo = getattr(self, "personality_evo", None)
            if evo:
                return evo.get_growth_summary()
            return "成長システムがまだ初期化されていないよ。"

        # 「応答品質」「会話品質スコア」
        if CMD_QUALITY.match(user_input):
            ev = getattr(self, "response_evaluator", None)
            if ev:
                return ev.get_quality_summary()
            return "品質評価システムがまだ初期化されていないよ。"

        # ─── ヤマト計画コマンド ───────────────────────────────

        # 「ヤマトダッシュボード」「アーキテクチャ確認」「7層」
        if CMD_YAMATO_DASH.match(user_input):
            arch = getattr(self, "yamato_arch", None)
            if arch:
                return arch.get_dashboard()
            return "ヤマトアーキテクチャがまだ初期化されていないよ。"

        # 「MoE状態」「専門家一覧」
        if CMD_MOE_STATUS.match(user_input):
            moe = getattr(self, "moe_router", None)
            if moe:
                return moe.get_status_text()
            return "MoEルーターがまだ初期化されていないよ。"

        # 「継続学習状態」「学習エンジン確認」
        if CMD_LEARNING_STATUS.match(user_input):
            cl = getattr(self, "continuous_learner", None)
            if cl:
                return cl.get_status_text()
            return "継続学習エンジンがまだ初期化されていないよ。"

        # 「合成データ生成」「データ生成」
        if CMD_SYNTH_GEN.match(user_input):
            sg = getattr(self, "synthetic_gen", None)
            if sg:
                if "生成" in user_input or "作成" in user_input:
                    results = sg.generate_batch(count=10)
                    return f"🧬 合成データを{len(results)}件生成したよ！\n{sg.get_status_text()}"
                return sg.get_status_text()
            return "合成データ生成がまだ初期化されていないよ。"

        # 「マルチエージェント検証」「品質検証確認」
        if CMD_VERIFY_STATUS.match(user_input):
            mv = getattr(self, "multi_verifier", None)
            if mv:
                return mv.get_status_text()
            return "マルチエージェント検証がまだ初期化されていないよ。"

        return None

    # ─── Sprint 2.1: セキュリティ機能 ────────────────────────

    def _run_security_check(self) -> str:
        """ホスト＋アイ内部の総合セキュリティチェック"""
        lines: list[str] = ["🛡️ セキュリティ診断を実行するね！\n"]

        # ホストPC診断
        if getattr(self, "host_guardian", None):
            try:
                summary = self.host_guardian.get_summary_text()
                lines.append("【PCセキュリティ】")
                lines.append(summary)
            except Exception as e:
                lines.append(f"【PCセキュリティ】確認できなかったよ: {e}")

        # 内部整合性
        if getattr(self, "integrity", None):
            try:
                result = self.integrity.verify()
                if result["status"] == "ok":
                    lines.append("\n【データ整合性】✅ 異常なし")
                else:
                    lines.append(f"\n【データ整合性】⚠ 問題あり: 変更{len(result['modified'])}件、消失{len(result['missing'])}件")
            except Exception:
                pass

        # 異常検知
        if getattr(self, "anomaly_detector", None):
            try:
                alerts = self.anomaly_detector.run_checks()
                critical = [a for a in alerts if a.severity == "CRITICAL"]
                if critical:
                    lines.append(f"\n【異常検知】🔴 重大アラート {len(critical)}件")
                    for a in critical[:3]:
                        lines.append(f"  → {a.message}")
                else:
                    lines.append("\n【異常検知】✅ 異常なし")
            except Exception:
                pass

        # 監査ログ
        if getattr(self, "audit", None):
            try:
                chain = self.audit.verify_chain()
                if chain["valid"]:
                    lines.append(f"\n【監査ログ】✅ チェーン正常 ({chain['total']}件)")
                else:
                    lines.append(f"\n【監査ログ】🔴 チェーン破損 (行{chain['broken_at']})")
            except Exception:
                pass

        return "\n".join(lines)

    def _run_backup(self) -> str:
        """手動バックアップを実行"""
        if not getattr(self, "backup", None):
            return "バックアップ機能が初期化されていないよ。"
        try:
            result = self.backup.create_backup(label="manual")
            return (
                f"✅ バックアップ完了！\n"
                f"サイズ: {result['size_mb']}MB、ファイル数: {result['files']}"
            )
        except Exception as e:
            return f"バックアップに失敗したよ: {e}"

    def _show_backup_list(self) -> str:
        """バックアップ一覧を表示"""
        if not getattr(self, "backup", None):
            return "バックアップ機能が初期化されていないよ。"
        backups = self.backup.list_backups()
        if not backups:
            return "まだバックアップはないよ。「バックアップ作成」で作れるよ！"
        lines = ["📦 バックアップ一覧："]
        for b in backups[-5:]:
            lines.append(f"  • {b['filename']} ({b['size_mb']}MB)")
        return "\n".join(lines)

    def _run_lockdown(self, reason: str) -> str:
        """緊急ロックダウンを実行"""
        if not getattr(self, "kill_switch", None):
            return "キルスイッチが初期化されていないよ。"
        try:
            result = self.kill_switch.backup_and_halt(reason)
            return (
                f"🔒 緊急ロックダウンを実行したよ！\n"
                f"理由: {reason}\n"
                f"外部通信を遮断し、バックアップを作成しました。\n"
                f"解除するには「アイ解除」と話しかけてね。"
            )
        except Exception as e:
            return f"ロックダウンに失敗: {e}"

    def _run_unlock(self) -> str:
        """ロックダウンを解除"""
        if not getattr(self, "kill_switch", None):
            return "キルスイッチが初期化されていないよ。"
        result = self.kill_switch.unlock(confirm="アイ解除")
        if result["unlocked"]:
            return "🔓 ロックダウンを解除したよ！通常モードに戻るね。"
        return f"解除できなかったよ: {result['reason']}"

    # ─── Sprint J: サーバー・自律行動メソッド ──────────────────

    def _server_status(self) -> str:
        """サーバーの接続状態とメトリクスを返す"""
        sh = getattr(self, "server_home", None)
        if sh is None or not sh.enabled:
            return (
                "🏠 サーバー（アイの家）はまだ設定されていないよ。\n"
                "「サーバー設定」で接続先を登録してね！"
            )

        lines: list[str] = ["🏠 アイの家（サーバー）の状態だよ：\n"]

        # 接続チェック
        reachable = sh.is_reachable()
        if not reachable:
            lines.append("❌ サーバーに接続できないよ…。電源やLANケーブルを確認してね。")
            return "\n".join(lines)

        lines.append("✅ サーバーに接続できたよ！")

        # ヘルスチェック
        try:
            health = sh.health_check()
            if health.get("ok"):
                if health.get("uptime"):
                    lines.append(f"⏱ 稼働時間: {health['uptime'].strip()}")
                if health.get("disk_usage"):
                    lines.append(f"💾 ディスク: {health['disk_usage'].strip()}")
                if health.get("memory"):
                    lines.append(f"🧠 メモリ: {health['memory'].strip()}")
        except Exception:
            pass

        # AI環境
        ai_env = getattr(self, "server_ai_env", None)
        if ai_env:
            lines.append(f"\n{ai_env.get_status_text()}")

        # Prometheus メトリクス
        prom = getattr(self, "prometheus", None)
        if prom:
            lines.append(f"\n{prom.get_summary_text()}")

        # 知識同期
        ks = getattr(self, "knowledge_sync", None)
        if ks:
            lines.append(f"\n{ks.get_sync_status()}")

        return "\n".join(lines)

    def _server_docker(self) -> str:
        """サーバー上のDockerコンテナ一覧を返す"""
        sh = getattr(self, "server_home", None)
        if sh is None or not sh.enabled:
            return "🏠 サーバーがまだ設定されていないよ。「サーバー設定」で登録してね！"

        try:
            containers = sh.docker_ps()
        except Exception as e:
            return f"Docker情報を取得できなかったよ: {e}"

        if not containers:
            return "🐳 サーバーにDockerコンテナはないみたい。"

        lines = [f"🐳 Dockerコンテナ一覧（{len(containers)}件）："]
        for c in containers:
            status_icon = "🟢" if "Up" in c.get("status", "") else "🔴"
            lines.append(f"  {status_icon} {c.get('name', '?')} - {c.get('status', '?')}")
        return "\n".join(lines)

    def _server_sync(self) -> str:
        """知識ベースをサーバーと同期する"""
        ks = getattr(self, "knowledge_sync", None)
        if ks is None:
            return "🏠 サーバーがまだ設定されていないよ。「サーバー設定」で登録してね！"

        lines = ["📡 サーバーとの知識同期を開始するね…\n"]

        # Push
        push_result = ks.push_knowledge()
        if push_result.get("ok"):
            action = push_result.get("action", "")
            if action == "no_changes":
                lines.append("⬆ アップロード: 変更なし（最新状態）")
            else:
                lines.append("⬆ アップロード: ✅ 完了！")
        else:
            lines.append(f"⬆ アップロード: ❌ {push_result.get('error', '失敗')}")

        # Pull
        pull_result = ks.pull_knowledge()
        if pull_result.get("ok"):
            pulled = pull_result.get("pulled", 0)
            if pull_result.get("action") == "nothing_to_pull":
                lines.append("⬇ ダウンロード: 新しいデータなし")
            else:
                lines.append(f"⬇ ダウンロード: ✅ {pulled}件取得！")
        else:
            lines.append(f"⬇ ダウンロード: ❌ {pull_result.get('error', '失敗')}")

        return "\n".join(lines)

    def _server_setup_guide(self) -> str:
        """サーバー接続の設定ガイドを返す"""
        return (
            "🏠 サーバー（アイの家）の設定方法だよ：\n\n"
            "config/settings.json の「server_home」セクションを編集してね：\n"
            "  - enabled: true にする\n"
            "  - host: サーバーのIPアドレス（例: 192.168.3.86）\n"
            "  - port: SSHポート（通常22）\n"
            "  - username: SSHユーザー名\n"
            "  - password: SSHパスワード（暗号化して保存されるよ）\n\n"
            "設定後、「サーバー状態」で接続テストできるよ！"
        )

    def _proactive_talk(self) -> str:
        """自発的な話題を提供する"""
        aa = getattr(self, "autonomous_actions", None)
        if aa is None or aa.proactive is None:
            return "自発的会話機能が無効だよ。settings.json で proactive_enabled を true にしてね。"

        message = aa.proactive.get_proactive_message(self)
        if message:
            return message

        # 自発ネタがない場合はランダムな話しかけ
        import random
        fallbacks = [
            "最近何か楽しいことあった？✨",
            "今日の調子はどう？何でも話してね😊",
            "ねぇねぇ、何か面白い話ある？",
            "お疲れさまー！リフレッシュしてる？🍵",
            "そういえば、最近何か新しいこと始めた？",
        ]
        return random.choice(fallbacks)

    def _build_memory_context(self, user_input: str) -> str:
        """
        LLM のシステムプロンプトに追記する自然な日本語指示文を生成します。
        括弧・記号などの特殊表記は使わず、通常の指示文として書きます。

        脊髄反射パターン: 2ターン以内で同トピックなら重い検索をスキップし
        キャッシュされたコンテキストを再利用。
        """
        # ── キャッシュ判定: 短い相槌(5文字以下)で直近キャッシュがあればそのまま返す ──
        if (len(user_input) <= 5
                and hasattr(self, "_mem_ctx_cache")
                and self._mem_ctx_cache
                and self._mem_ctx_turn >= self.turn_count - 2):
            return self._mem_ctx_cache

        parts: list[str] = []

        # ── ユーザープロファイル（重複排除・auto:プレフィックス除去） ──
        profile = self.memory.get_all_user_profile()
        if profile:
            # 手動設定を優先し、auto: プレフィックス付きは手動版がない場合のみ使用
            clean: dict[str, str] = {}
            for k, v in profile.items():
                if k.startswith("auto:"):
                    bare = k[5:]  # "auto:" を除去
                    if bare not in clean:
                        clean[bare] = v
                else:
                    clean[k] = v  # 手動設定は常に優先
            items = list(clean.items())[:4]
            desc = "、".join(f"{k}は{v}" for k, v in items)
            parts.append(f"ユーザーの{desc}。")

        # ── 関連記憶の自動検索（キーワード+セマンティック） ──
        try:
            related = self._search_relevant_memories(user_input, limit=3)
            if related:
                snippets = [m.content[:80].replace("\n", " ") for m in related]
                parts.append("関連する過去の記憶：" + "／".join(snippets) + "。")
        except Exception:
            pass

        # ── 気分ヒント ──
        mood_info = MoodAnalyzer.analyze(user_input)
        if mood_info["hint"]:
            hint = mood_info["hint"]
            if "→" in hint:
                parts.append(hint.split("→")[-1].strip() + "。")
            else:
                parts.append(hint + "。")

        # ── フォローアップ ──
        followup = self.topic_tracker.get_followup_topic(self.turn_count, min_gap=5)
        if followup:
            brief = followup["text"][:20]
            parts.append(f"会話の中で「{brief}」のことも自然に聞いて。")
            self.topic_tracker.mark_followed_up(followup)

        # ── 天気・ニュース（ネットワーク許可時、5ターンに1回） ──
        if self._allow_network and self.turn_count % 5 == 1:
            try:
                from core.web_fetcher import build_weather_hint, build_news_hint
                w_hint = build_weather_hint(self._weather_city)
                if w_hint:
                    parts.append(f"今日の{w_hint}。")
                elif self.turn_count % 15 == 1:
                    n_hint = build_news_hint()
                    if n_hint:
                        parts.append(f"最近のニュース：{n_hint[:40]}。")
            except Exception:
                pass

        # ── バッテリー警告（20ターンに1回） ──
        if self.turn_count % 20 == 1:
            try:
                batt_hint = get_battery_hint()
                if batt_hint:
                    parts.append(batt_hint)
            except Exception:
                pass

        # ── カレンダー（10ターンに1回） ──
        if self.turn_count % 10 == 1:
            try:
                cal_hint = build_calendar_hint(days=1)
                if cal_hint:
                    parts.append(cal_hint + "。")
            except Exception:
                pass

        # ── few-shot 会話例（常時2例を注入して口調を安定させる） ──
        try:
            examples = self.learning.get_few_shot_examples(n=2, user_input=user_input)
            if examples:
                parts.append(examples)
        except Exception:
            pass

        # ── 直近の応答を繰り返さないよう指示 ──
        recent_responses = [
            m["content"][:30]
            for m in self.conversation_history[-6:]
            if m["role"] == "assistant"
        ]
        if recent_responses:
            parts.append("直前と同じ言い回しを繰り返さず、新鮮な表現で答えて。")

        result = "".join(parts)[:500]
        self._mem_ctx_cache = result
        self._mem_ctx_turn = self.turn_count
        return result

    def _search_relevant_memories(self, query: str, limit: int = 3):
        """
        ユーザー入力に関連する記憶をDB＋セマンティック検索で取得する。
        Sprint 2.0: チャットの主経路で自動的に呼ばれる。
        """
        results = []

        # セマンティック検索が有効ならそちらを優先
        if self.semantic_search.is_ready():
            try:
                all_mems = self.memory.get_recent(limit=50)
                results = self.semantic_search.search(query, all_mems, limit=limit)
            except Exception:
                pass

        # セマンティック検索が使えない or 結果が少ない場合はSQL検索
        if len(results) < limit:
            try:
                sql_results = self.memory.search_by_keywords(query, limit=limit)
                # 重複排除
                existing_ids = {r.id for r in results}
                for m in sql_results:
                    if m.id not in existing_ids:
                        results.append(m)
                        if len(results) >= limit:
                            break
            except Exception:
                pass

        return results[:limit]

    # ─── 自己修正ハンドラ登録 ─────────────────────────────

    def _handle_proposal_command(self, user_input: str) -> str:
        """提案関連のコマンド処理"""
        sd = getattr(self, "self_dev", None)
        if not sd:
            return "自己開発パイプラインがまだ初期化されていないよ。"

        # 「分析」「実行」が含まれていたら即座に分析実行
        if "分析" in user_input or "実行" in user_input:
            proposals = sd.run_analysis()
            if proposals:
                lines = [f"🔬 {len(proposals)}件の改善提案を生成したよ！\n"]
                for p in proposals[:5]:
                    prio = ["🔴", "🟠", "🟡", "⚪"][min(p.priority, 3)]
                    lines.append(f"{prio} **{p.title}**")
                    lines.append(f"   {p.description[:80]}")
                    lines.append(f"   → {p.suggested_action[:80]}")
                    lines.append(f"   ID: `{p.id}`\n")
                lines.append("承認: 「提案を承認: ID」 / 却下: 「提案を却下: ID」")
                return "\n".join(lines)
            return "分析完了！今のところ改善提案はないよ。いい状態だね！"

        # 一覧表示
        pending = sd.proposal_store.list_pending()
        all_p = sd.proposal_store.list_all()

        if not all_p:
            return "まだ改善提案はないよ。「自己開発分析」で分析を実行してみてね！"

        lines = [f"📋 改善提案 ({len(pending)}件が未承認)\n"]
        for p in all_p[-10:]:
            status_icon = {
                "pending": "⏳", "approved": "✅",
                "rejected": "❌", "done": "🎉",
            }.get(p.get("status", ""), "❓")
            prio = ["🔴", "🟠", "🟡", "⚪"][min(p.get("priority", 3), 3)]
            lines.append(
                f"{status_icon} {prio} {p['title']}"
                f"  (ID: {p['id'][:20]}...)"
            )

        if pending:
            lines.append("\n承認: 「提案を承認: ID」 / 却下: 「提案を却下: ID」")

        return "\n".join(lines)

    def _handle_export(self, fmt: str, content_text: str) -> str:
        """ドキュメントエクスポート処理"""
        exporter = getattr(self, "doc_exporter", None)
        if not exporter:
            return "ドキュメント出力機能が初期化されていないよ。"

        # LLM に構造化してもらう（マークダウン形式で整形）
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
                pass  # LLM失敗時は元テキストをそのまま使う

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
            return f"📄 {label} ファイルを作成したよ！\n📁 {path}"
        except RuntimeError as e:
            return f"ごめんね、{label} の出力に必要なライブラリがないよ。\n{e}"
        except Exception as e:
            logger.exception("ドキュメント出力エラー")
            return f"ドキュメントの作成中にエラーが起きちゃった: {e}"

    # ─── Web検索 ハンドラ ──────────────────────────

    def _handle_web_search(self, query: str) -> str:
        """Web検索ハンドラ"""
        from core.web_fetcher import web_search
        try:
            results = web_search(query, max_results=5)
        except Exception as exc:
            return f"検索中にエラーが起きちゃった: {exc}"

        if not results:
            return f"「{query}」の検索結果が見つからなかったよ。ネットワーク接続を確認してね。"

        lines = [f"🔍 「{query}」の検索結果:"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n{i}. {r['title']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:100]}")
            lines.append(f"   🔗 {r['url']}")
        lines.append(f"\n💡 詳しく読みたいURLがあれば「URL読んで: https://...」と言ってね")
        return "\n".join(lines)

    def _handle_web_fetch(self, url: str) -> str:
        """URL取得ハンドラ"""
        if not url.startswith(("http://", "https://")):
            return "URLは http:// か https:// で始まる必要があるよ。"
        from core.web_fetcher import web_fetch_text
        try:
            text = web_fetch_text(url, max_chars=2000)
        except Exception as exc:
            return f"ページの取得中にエラーが起きちゃった: {exc}"
        if not text:
            return "ページの内容を取得できなかったよ。"
        # LLMで要約（可能であれば）
        if getattr(self, "llm", None) and self.llm.is_loaded():
            try:
                summary = self.llm.generate_chat([
                    {"role": "system", "content": "以下のWebページのテキストを日本語で簡潔に要約してください。300字以内で。"},
                    {"role": "user", "content": text[:1500]},
                ])
                if summary and len(summary) > 20:
                    return f"📄 {url}\n\n{summary}"
            except Exception:
                pass
        # LLM使えない場合はそのまま
        return f"📄 {url}\n\n{text[:1000]}..."

    # ─── コードエンジン ハンドラ ──────────────────────────

    def _handle_code_analyze(self, code: str) -> str:
        """コード解析ハンドラ"""
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        analysis = ce.analyze(code)
        lines = ["💻 コード解析結果:"]
        lines.append(f"  言語: {analysis.language}")
        lines.append(f"  行数: {analysis.lines}")
        if analysis.classes:
            lines.append(f"  クラス: {', '.join(analysis.classes)}")
        if analysis.functions:
            lines.append(f"  関数: {', '.join(analysis.functions)}")
        if analysis.imports:
            lines.append(f"  依存: {', '.join(analysis.imports[:8])}")
        if analysis.complexity > 0:
            level = "高⚠️" if analysis.complexity > 10 else "中" if analysis.complexity > 5 else "低✅"
            lines.append(f"  複雑度: {analysis.complexity} ({level})")
        if analysis.issues:
            lines.append(f"  問題: {len(analysis.issues)}件")
            for issue in analysis.issues[:5]:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(issue.severity, "⚪")
                loc = f"L{issue.line}" if issue.line else ""
                lines.append(f"    {icon} {loc} {issue.message}")
        if analysis.summary:
            lines.append(f"  概要: {analysis.summary}")
        return "\n".join(lines)

    def _handle_code_review(self, code: str) -> str:
        """コードレビューハンドラ"""
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        issues = ce.review(code)
        if not issues:
            return "✅ 問題は見つからなかったよ！きれいなコードだね。"
        lines = [f"📝 コードレビュー結果 ({len(issues)}件):"]
        for issue in issues[:10]:
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(issue.severity, "⚪")
            loc = f"[L{issue.line}]" if issue.line else ""
            lines.append(f"  {icon} {loc} {issue.message}")
            if issue.suggestion:
                lines.append(f"     💡 {issue.suggestion}")
        return "\n".join(lines)

    def _handle_code_fix(self, error_info: str) -> str:
        """エラー修正提案ハンドラ"""
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        # エラー情報からコード部分とエラーメッセージを分離
        parts = error_info.split("---", 1)
        if len(parts) == 2:
            code = parts[0].strip()
            error_msg = parts[1].strip()
        else:
            code = ""
            error_msg = error_info
        return ce.suggest_fix(code, error_msg)

    def _handle_code_test(self, code: str) -> str:
        """テスト骨格生成ハンドラ"""
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        skeleton = ce.generate_test_skeleton(code)
        if len(skeleton) < 30:
            return skeleton
        return f"🧪 テスト骨格を生成したよ:\n\n```python\n{skeleton}\n```"

    def _handle_code_explain(self, code: str) -> str:
        """コード説明ハンドラ"""
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        return ce.explain(code)

    def _handle_code_file(self, file_path_str: str) -> str:
        """ファイル読み込み→解析ハンドラ"""
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        from pathlib import Path
        fp = Path(file_path_str.strip())
        if not fp.is_absolute():
            fp = self.base_dir / fp
        if not fp.exists():
            return f"ファイルが見つからないよ: {fp}"
        if not fp.is_file():
            return f"これはファイルじゃないよ: {fp}"
        # セキュリティ: プロジェクト内のみ
        try:
            fp.resolve().relative_to(self.base_dir.resolve())
        except ValueError:
            return "プロジェクト外のファイルは読めないよ。セキュリティのためだよ。"
        # サイズチェック
        if fp.stat().st_size > 100_000:
            return "ファイルが大きすぎるよ（100KB以下にしてね）。"
        try:
            code = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "テキストファイルじゃないみたい。読めなかったよ。"
        # 解析 + レビュー
        analysis = ce.analyze(code)
        issues = ce.review(code)
        lines = [f"📂 {fp.name} の解析結果:"]
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
                parts.append(f"🔴重大{critical}")
            if high:
                parts.append(f"🟠高{high}")
            if medium:
                parts.append(f"🟡中{medium}")
            lines.append(f"  問題: {' '.join(parts)}")
            for issue in issues[:5]:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(issue.severity, "⚪")
                lines.append(f"    {icon} L{issue.line}: {issue.message}")
        else:
            lines.append("  ✅ 問題なし！")
        return "\n".join(lines)

    def _handle_code_run(self, code: str) -> str:
        """コード実行ハンドラ — サンドボックスで安全に実行"""
        ce = getattr(self, "code_engine", None)
        if not ce:
            return "コードエンジンがまだ初期化されていないよ。"
        return ce.run_and_fix(code)

    def _show_self_awareness(self) -> str:
        """自己認識レポート"""
        sd = getattr(self, "self_dev", None)
        if not sd:
            return "自己開発パイプラインがまだ初期化されていないよ。"

        awareness = sd.get_self_awareness()
        lines = [
            "🪞 自己認識レポート",
            f"私は {awareness['total_modules']} 個のモジュール、"
            f"合計 {awareness['total_lines']:,} 行のコードでできているよ。\n",
        ]

        for d, info in awareness["by_directory"].items():
            lines.append(
                f"📁 {d}/: {info['count']}ファイル ({info['total_lines']:,}行)"
            )

        lines.append("\n📏 大きいファイル TOP5:")
        for f in awareness["largest_files"][:5]:
            lines.append(f"  {f['path']}: {f['lines']}行")

        # 各システムのステータスも表示
        bio = getattr(self, "bio_nervous", None)
        growth = getattr(self, "growth", None)
        sc = getattr(self, "self_correction", None)
        sw = getattr(self, "self_will", None)
        ac = getattr(self, "action_cycle", None)

        lines.append("\n🧬 内部システム:")
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
        """自己修正システムの治療アクションを登録する"""
        sc = self.self_correction.executor

        # ① 温度調整（応答の安定性/多様性を制御）
        def _adjust_temperature(params: dict) -> dict:
            delta = params.get("delta", 0)
            cfg = self.settings.get("llm", {})
            old_temp = cfg.get("temperature", 0.7)
            new_temp = max(0.3, min(1.2, old_temp + delta))
            cfg["temperature"] = round(new_temp, 2)
            return {"old": old_temp, "new": new_temp}

        sc.register_handler("adjust_temperature", _adjust_temperature)

        # ② 最大トークン調整
        def _adjust_max_tokens(params: dict) -> dict:
            delta = params.get("delta", 0)
            cfg = self.settings.get("llm", {})
            old_mt = cfg.get("max_tokens", 500)
            new_mt = max(100, min(1000, old_mt + delta))
            cfg["max_tokens"] = new_mt
            return {"old": old_mt, "new": new_mt}

        sc.register_handler("adjust_max_tokens", _adjust_max_tokens)

        # ③ 筋肉記憶プルーニング（現行プリセットは精度不足のため無効。
        #    会話統計から高精度パターンが形成された後に再有効化する）
        sc.register_handler("reset_muscle_memory_low_quality", lambda p: {"pruned": 0})

        # ④ 古い筋肉記憶の忘却（同上 — パターン蓄積後に再有効化）
        sc.register_handler("prune_stale_patterns", lambda p: {"pruned": 0})

        # ⑤ 免疫系チェック
        def _run_immune(params: dict) -> dict:
            bio = getattr(self, "bio_nervous", None)
            if not bio:
                return {"status": "no_bio"}
            return bio.immune.health_check()

        sc.register_handler("run_immune_check", _run_immune)

        # no_action は何もしない
        sc.register_handler("no_action", lambda p: {"ok": True})

    def _autonomic_self_dev(self) -> None:
        """自律神経から呼ばれる: 自己開発分析を実行"""
        sd = getattr(self, "self_dev", None)
        if not sd:
            return
        try:
            # 品質トレンドも渡す
            sc = getattr(self, "self_correction", None)
            if sc:
                sd.run_quality_analysis(
                    sc.monitor.current_avg, sc.monitor.trend
                )
            sd.run_analysis()
        except Exception as e:
            logger.debug("自己開発分析失敗: %s", e)

    def _autonomic_action_cycle(self):
        """自律神経から呼ばれる: 目標のチェック＆新規計画"""
        ac = getattr(self, "action_cycle", None)
        if not ac:
            return

        # Check: 期限チェック
        ac.check()

        # Plan: 目標がなければ新しく立てる
        if len(ac._active_goals) == 0:
            context = {
                "interest_topics": [],
                "quality_avg": 0.5,
                "turn_count": self.turn_count,
            }
            # 興味トピック
            if getattr(self, "interest_map", None) and hasattr(self.interest_map, "get_top"):
                try:
                    tops = self.interest_map.get_top(3)
                    context["interest_topics"] = [t["topic"] for t in tops]
                except Exception:
                    pass
            # 品質
            sc = getattr(self, "self_correction", None)
            if sc:
                context["quality_avg"] = sc.monitor.current_avg
            ac.plan(context)

    def _autonomic_will_think(self):
        """自律神経から呼ばれる: アイが「今何がしたいか」を考える"""
        sw = getattr(self, "self_will", None)
        if not sw:
            return

        # コンテキスト構築
        context: dict = {
            "turn_count": self.turn_count,
            "hour": datetime.now().hour,
            "idle_minutes": 0,
            "emotion": self.emotion.state.to_dict() if hasattr(self.emotion, "state") else {},
            "interest_topics": [],
            "health_status": "healthy",
        }

        # 興味トピック
        if getattr(self, "interest_map", None) and hasattr(self.interest_map, "get_top"):
            try:
                tops = self.interest_map.get_top(3)
                context["interest_topics"] = [t["topic"] for t in tops]
            except Exception:
                pass

        # 健康状態
        sc = getattr(self, "self_correction", None)
        if sc:
            report = sc.get_health_report()
            if report.get("active_symptoms"):
                context["health_status"] = "unhealthy"

        # アイドル時間
        aa = getattr(self, "autonomous_actions", None)
        if aa and hasattr(aa, "idle_minutes"):
            context["idle_minutes"] = aa.idle_minutes

        sw.think(context)

    def _register_will_actions(self):
        """自己意思エンジンのアクションハンドラを登録する"""
        sw = self.self_will.executor

        # 学習したい → 自動学習を発動
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

        # 話しかけたい → pending_message にセット
        def _initiate_chat(desire):
            messages = [
                "ねえねえ、最近何してたの？",
                "なんか話したいな。今何してる？",
                "ちょっと寂しかったかも。元気にしてた？",
            ]
            import random
            msg = random.choice(messages)
            self.self_will._pending_message = msg
            return msg

        sw.register("initiate_chat", _initiate_chat)

        # 気持ちを伝えたい → pending_message にセット
        def _express_feeling(desire):
            emo = desire.params.get("emotion", "joy")
            if emo == "joy":
                msgs = ["なんだか嬉しい気分！", "今日は気分がいいよ！"]
            else:
                msgs = ["面白いこと見つけたかも！", "気になることがあるんだ！"]
            import random
            msg = random.choice(msgs)
            self.self_will._pending_message = msg
            return msg

        sw.register("express_feeling", _express_feeling)

        # 成長したい → 自己修正の強制チェック
        def _self_improve(desire):
            sc = getattr(self, "self_correction", None)
            if sc:
                results = sc.force_check()
                if results:
                    return f"自己チェックで {len(results)} 件修正した"
            return "自己チェック完了（問題なし）"

        sw.register("self_improve", _self_improve)

        # 休息を提案 → pending_message にセット
        def _suggest_rest(desire):
            hour = desire.params.get("hour", 0)
            if hour >= 1 and hour < 5:
                msg = "もうこんな時間だよ…体に気をつけてね。おやすみ。"
            else:
                msg = "そろそろ遅いね。ゆっくり休んでね。"
            self.self_will._pending_message = msg
            return msg

        sw.register("suggest_rest", _suggest_rest)

        # 遊びたい → 雑談メッセージ
        def _play(desire):
            import random
            msgs = [
                "しりとりしない？",
                "好きな食べ物の話しよう！",
                "もしタイムマシンがあったらいつに行く？",
                "最近面白いことあった？",
            ]
            msg = random.choice(msgs)
            self.self_will._pending_message = msg
            return msg

        sw.register("play", _play)

        # 自己メンテナンス → 免疫チェック + 自己修正
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

        # コードレビュー → 自分のコードを定期的にレビュー
        def _review_code(desire):
            ce = getattr(self, "code_engine", None)
            sd = getattr(self, "self_dev", None)
            if not ce or not sd:
                return "コードエンジンまたは自己開発が未初期化"
            try:
                # 自分のソースから1つランダムに選んでレビュー
                import random
                core_dir = self.base_dir / "core"
                py_files = [f for f in core_dir.glob("*.py") if f.stat().st_size < 50_000]
                if not py_files:
                    return "レビュー対象なし"
                target = random.choice(py_files)
                code = target.read_text(encoding="utf-8")
                issues = ce.review(code)
                critical = sum(1 for i in issues if i.severity in ("critical", "high"))
                return f"{target.name}: {len(issues)}件 (重大{critical}件)"
            except Exception as exc:
                return f"レビュー失敗: {exc}"

        sw.register("review_code", _review_code)

        # 記憶整理 → 古い記憶の圧縮・整理
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

        # ヘルスチェック → システム全体の健康診断
        def _check_health(desire):
            results = []
            # 自己修正の健康状態
            sc = getattr(self, "self_correction", None)
            if sc:
                report = sc.get_health_report()
                symptoms = report.get("active_symptoms", [])
                if symptoms:
                    results.append(f"症状: {len(symptoms)}件")
                else:
                    results.append("健康: 良好")
            # 生体神経系
            bio = getattr(self, "bio_nervous", None)
            if bio:
                stats = bio.get_stats()
                bypass = stats.get("bypass_rate", 0)
                results.append(f"LLMバイパス率: {bypass:.0%}")
            # コードエンジン
            ce = getattr(self, "code_engine", None)
            if ce:
                results.append(ce.get_status_text())
            return " / ".join(results) if results else "チェック完了"

        sw.register("check_health", _check_health)

    def _estimate_importance(self, text: str) -> float:
        """テキストの重要度を簡易推定します"""
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
            f"📚 記憶のまとめだよ！",
            f"・短期記憶: {stats['short_term_count']} 件",
            f"・保存済み記憶: {stats['db_total']} 件（保護: {stats['protected']} 件）",
        ]

        if important:
            lines.append("\n⭐ 大切な記憶:")
            for m in important[:3]:
                lines.append(f"  - {m.content[:60]}...")

        profile = self.memory.get_all_user_profile()
        if profile:
            # auto: プレフィックスを除去し、重複を排除して表示
            clean: dict[str, str] = {}
            for k, v in profile.items():
                if k.startswith("auto:"):
                    bare = k[5:]
                    if bare not in clean:
                        clean[bare] = v
                else:
                    clean[k] = v
            lines.append("\n👤 あなたのこと:")
            for k, v in list(clean.items())[:5]:
                lines.append(f"  - {k}: {v}")

        return "\n".join(lines)

    # ─── YouTube 学習 ─────────────────────────────────────────────

    def _learn_youtube(self, url: str) -> str:
        """YouTube URLを受け取り、字幕を取得・要約・保存して結果を返す"""

        # キャッシュ済み確認
        if self.youtube.is_cached(url):
            data = self.youtube._cache[url]
            return (
                f"この動画はもう学習済みだよ！\n"
                f"「{data['title']}」（{data['fetched_at'][:10]} 取得済み）\n"
                "もう一度学習し直す場合は「YouTubeを再学習:URL」って言ってね。"
            )

        # ネットワーク許可確認
        if not self._allow_network:
            return (
                "ネットワークが無効になってるよ。設定でネットワークを許可してから\n"
                "もう一度URLを貼ってね。キャッシュ済みの動画はオフラインでも読めるよ。"
            )

        # 字幕取得（ネットワーク使用）
        print(f"[YouTube] 字幕を取得中: {url}", flush=True)
        data = self.youtube.fetch_transcript(url)

        if "error" in data:
            return f"字幕の取得に失敗したよ。{data['error']}"

        # Phi-3 で要約（ローカル）
        print(f"[YouTube] 要約中: {data['title']}", flush=True)
        summary = self.youtube.summarize_with_llm(data, self.llm)
        summary = self._clean_response(summary)

        # 学習データとして保存
        self.youtube.store(data, summary)

        # learning エンジンにも反映（次の会話 few-shot に使われる）
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
        """Web URL を受け取り、テキストを取得・要約・保存して結果を返す"""
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
        """ファイルパスを受け取り、内容を要約・保存して結果を返す"""
        from pathlib import Path
        path = Path(path).expanduser().resolve()
        # セキュリティ: ユーザーディレクトリ配下のみ許可（機密ファイル読み出し防止）
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
        """学習済み YouTube 動画一覧を返す"""
        learned = self.youtube.list_learned()
        if not learned:
            return "まだ YouTube 動画を学習してないよ。URLをチャットに貼ると学習できるよ！"
        lines = [f"学習済み動画 {len(learned)} 本だよ："]
        for item in learned[-8:]:  # 最新8件
            lines.append(f"・「{item['title']}」（{item.get('learned_at', '')[:10]}）")
        return "\n".join(lines)

    # ─── 自動学習 ────────────────────────────────────────────────

    def _show_auto_learn_status(self) -> str:
        """自動学習スケジュールの状況を表示"""
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
        """YouTube URL または Web URL をソースリストに追加"""
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
        """議事録一覧を表示"""
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
        """登録メモ一覧を表示"""
        memos = self.auto_learner.get_memos()
        if not memos:
            return "学習メモはまだないよ。「学習メモを覚えて: ○○」で登録できるよ！"
        lines = [f"学習メモ {len(memos)} 件だよ："]
        for m in memos[-10:]:
            reviewed = f"（復習{m.get('reviews',0)}回）" if m.get('reviews') else "（未復習）"
            lines.append(f"・{m['text'][:50]} {reviewed}")
        return "\n".join(lines)

    def _run_auto_learn_now(self) -> str:
        """学習ソースを今すぐ学習する"""
        yt_srcs  = self.auto_learner.get_sources("youtube")
        web_srcs = self.auto_learner.get_sources("web")
        if not yt_srcs and not web_srcs:
            return "学習ソースがまだ登録されていないよ。\n「学習先を追加: URL」でYouTube/WebのURLを登録してね。"

        import threading
        def _bg():
            results = []
            if yt_srcs:
                r = self.auto_learner.run_now("youtube", max_items=2)
                results.append(r)
            if web_srcs:
                r = self.auto_learner.run_now("web", max_items=2)
                results.append(r)
        threading.Thread(target=_bg, daemon=True).start()
        total = len(yt_srcs) + len(web_srcs)
        return f"学習を開始したよ！（登録ソース {total}件）\nバックグラウンドで実行中。終わったら教えるね。"

    def generate_soliloquy(self) -> str:
        """J. 放置中の独り言を生成します（ユーザーへの話しかけではなく自然な独り言）"""
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
            # システムプロンプトだけ使ってワンショット生成
            messages.append({"role": "user", "content": prompt})
            result = self.llm.generate_chat(messages)
            return self._clean_response(result)
        except Exception:
            phrases = ["なんか眠いな…", "今日何食べようかな", "…ふと思ったんだけど",
                       "静かだね…", "もうこんな時間か", "なにしよっかな〜"]
            return random.choice(phrases)

    def _extract_profile_hints(self, user_input: str):
        """会話からプロファイル情報を自動抽出してDBに保存（サイレント）"""
        for pattern, key in _PROFILE_PATTERNS:
            m = pattern.search(user_input)
            if not m:
                continue
            if key == '誕生日':
                value = f"{m.group(1)}月{m.group(2)}日"
                # 誕生日は記念日にも自動登録
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
            # auto: プレフィックスで手動設定と区別
            auto_key = f"auto:{key}"
            existing = self.memory.get_user_profile(auto_key)
            # 呼び方・名前は上書き可。それ以外は初回のみ
            if not existing or key in ('呼び方', '名前'):
                self.memory.set_user_profile(auto_key, value)
                print(f"[Profile] {key} = {value} を自動登録", flush=True)

    def check_schedule(self) -> str | None:
        """K. 時刻に応じた日課 + 記念日メッセージを生成します（1日1回のみ）"""
        # 記念日チェックを優先
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
        """クリップボードのテキストに対してコメントを生成します"""
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
        """スクリーンショットの説明に対してコメントを生成します"""
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

    # ─── 状態プロパティ ───────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.persona["name"]

    @property
    def is_ready(self) -> bool:
        return True  # 記憶・感情は常に動作。LLMはフォールバックあり

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


def _days_label(days: list[int]) -> str:
    """曜日リスト [0-6] を「月〜金」のような文字列に変換"""
    names = ["月", "火", "水", "木", "金", "土", "日"]
    if days == [0, 1, 2, 3, 4]:
        return "平日"
    if days == [5, 6]:
        return "土日"
    if set(days) == set(range(7)):
        return "毎日"
    return "・".join(names[d] for d in sorted(days) if 0 <= d <= 6)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 免疫系ヒーラー関数（怪我したら勝手に治る）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _immune_file_recovery(ai: "AiChan", error: Exception, context: str) -> str:
    """ファイル欠損の自己修復: ディレクトリ再作成"""
    try:
        path = Path(str(error).split("'")[1]) if "'" in str(error) else None
        if path and path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"自己修復: {path.parent} を再作成しました"
    except Exception:
        pass
    return None


def _immune_json_recovery(ai: "AiChan", error: Exception, context: str) -> str:
    """JSON破損の自己修復: 壊れたファイルをバックアップして空で再作成"""
    try:
        # contextにファイルパスが含まれていれば修復
        if context and Path(context).exists():
            broken = Path(context)
            backup = broken.with_suffix(".broken")
            broken.rename(backup)
            broken.write_text("{}", encoding="utf-8")
            return f"自己修復: {broken.name} をリセットしました（破損版は .broken に退避）"
    except Exception:
        pass
    return None

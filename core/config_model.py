"""
アプリケーション設定モデル

settings.json を Pydantic BaseModel でバリデーションします。
各セクションはサブモデルに分割し、型安全なアクセスを提供します。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field, validator  # type: ignore[import]
    _PYDANTIC = True
except ImportError:
    # pydantic が未インストールの場合、dataclasses ベースのフォールバック
    from dataclasses import dataclass as _dataclass, field as _field
    _PYDANTIC = False

    class _BaseModelMeta(type):
        """Pydantic BaseModel 互換の簡易メタクラス"""
        pass

    class BaseModel(metaclass=_BaseModelMeta):  # type: ignore[no-redef]
        """pydantic.BaseModel の軽量フォールバック"""
        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                if hasattr(type(self), k):
                    attr = getattr(type(self), k)
                    # サブモデルの場合は再帰的に構築
                    if isinstance(v, dict) and isinstance(attr, type) and issubclass(attr, BaseModel):
                        v = attr(**v)
                setattr(self, k, v)
            # デフォルト値を設定
            for k in vars(type(self)):
                if k.startswith("_"):
                    continue
                if not hasattr(self, k):
                    default = getattr(type(self), k)
                    if callable(default) and not isinstance(default, type):
                        setattr(self, k, default())
                    else:
                        setattr(self, k, default)

        def dict(self) -> dict:
            result: dict = {}
            for k in vars(self):
                if k.startswith("_"):
                    continue
                v = getattr(self, k)
                if isinstance(v, BaseModel):
                    result[k] = v.dict()
                else:
                    result[k] = v
            return result

    class Field:  # type: ignore[no-redef]
        """pydantic.Field の軽量フォールバック"""
        def __init__(self, default: object = None, default_factory: object = None, **_kw: object) -> None:
            self.default = default
            self.default_factory = default_factory

    validator = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ─── サブモデル定義 ─────────────────────────────────────────────


class MLXConfig(BaseModel):
    """MLX (Apple Silicon) 固有設定"""

    model_path: str = "models/Qwen2.5-3B-Instruct-mlx-4bit"
    adapter_path: str = "models/adapters/aether-v1"
    adapter_enabled: bool = False


class LLMConfig(BaseModel):
    """LLM 推論エンジン設定"""

    model_path: str = "models/"
    model_file: str = "qwen2.5-3b-instruct-q4_k_m.gguf"
    context_length: int = Field(default=8192, ge=512, le=131072)
    max_tokens: int = Field(default=400, ge=1, le=8192)
    max_sentences: int = Field(default=8, ge=1)
    temperature: float = Field(default=0.65, ge=0.0, le=2.0)
    top_p: float = Field(default=0.85, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=1.0, le=2.0)
    top_k: int = Field(default=30, ge=0)
    n_gpu_layers: int = -1
    n_threads: int = Field(default=8, ge=1)
    n_batch: int = Field(default=512, ge=1)
    flash_attn: bool = True
    use_mmap: bool = True
    use_mlock: bool = False
    mlx: MLXConfig = Field(default_factory=MLXConfig)


class MemoryConfig(BaseModel):
    """記憶システム設定"""

    short_term_max: int = Field(default=100, ge=1)
    mid_term_max: int = Field(default=200, ge=1)
    compression_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    importance_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    db_path: str = "data/memories.db"


class SecurityConfig(BaseModel):
    """セキュリティ設定"""

    encrypt_database: bool = True
    key_file: str = "data/.key"


class UIConfig(BaseModel):
    """UI 設定"""

    language: str = "ja"
    show_emotion: bool = True
    color_theme: str = "pink"
    user_icon: str = "\U0001f464"
    ai_icon: str = "\U0001f497"
    user_name: str = "あなた"
    pet_image: str = ""
    ai_icon_image: str = ""
    user_icon_image: str = ""


class PortabilityConfig(BaseModel):
    """移植性・バックアップ設定"""

    auto_backup: bool = False
    backup_interval_hours: int = Field(default=24, ge=1)


class AutonomousConfig(BaseModel):
    """自律行動設定"""

    idle_minutes: int = Field(default=30, ge=1)
    allow_network: bool = True
    weather_city: str = "Tokyo"
    schedule_enabled: bool = True
    clipboard_watch: bool = True


class TTSConfig(BaseModel):
    """音声合成設定"""

    enabled: bool = True
    voice: str = "Kyoko"
    rate: int = Field(default=175, ge=50, le=500)


class STTConfig(BaseModel):
    """音声認識設定"""

    enabled: bool = True
    model_size: str = "small"
    language: str = "ja"


class SemanticSearchConfig(BaseModel):
    """セマンティック検索設定"""

    enabled: bool = False


class VisionConfig(BaseModel):
    """画像認識設定"""

    enable_moondream: bool = True


class NotionConfig(BaseModel):
    """Notion 連携設定"""

    enabled: bool = False
    api_key: str = ""
    minutes_database_id: str = ""
    todo_database_id: str = ""


class GoogleCalendarConfig(BaseModel):
    """Google Calendar 連携設定"""

    enabled: bool = False
    credentials_file: str = ""
    calendar_id: str = "primary"


class IntegrationsConfig(BaseModel):
    """外部連携設定"""

    notion: NotionConfig = Field(default_factory=NotionConfig)
    google_calendar: GoogleCalendarConfig = Field(default_factory=GoogleCalendarConfig)


class MinutesConfig(BaseModel):
    """議事録設定"""

    whisper_model: str = "small"
    auto_extract: bool = True
    auto_push_notion: bool = False
    auto_push_gcal: bool = False


class ServerHomeConfig(BaseModel):
    """ホームサーバー設定"""

    enabled: bool = False
    host: str = "192.168.3.86"
    port: int = Field(default=22, ge=1, le=65535)
    username: str = ""
    password: str = ""
    connect_timeout_sec: int = Field(default=10, ge=1)
    allowed_commands: List[str] = Field(default_factory=lambda: [
        "docker", "df", "free", "uptime", "systemctl status",
        "cat", "ls", "pwd", "whoami", "hostname", "uname",
        "curl localhost", "top -bn1", "ps aux", "mkdir",
    ])


class AutonomousActionsConfig(BaseModel):
    """自律行動の有効/無効設定"""

    greeting_enabled: bool = True
    proactive_enabled: bool = True
    diary_enrich_enabled: bool = True
    idle_learn_enabled: bool = True


# ─── メイン設定モデル ─────────────────────────────────────────


class AppConfig(BaseModel):
    """アプリケーション全体の設定"""

    version: str = "0.1.0"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    portability: PortabilityConfig = Field(default_factory=PortabilityConfig)
    autonomous: AutonomousConfig = Field(default_factory=AutonomousConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    semantic_search: SemanticSearchConfig = Field(default_factory=SemanticSearchConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
    minutes: MinutesConfig = Field(default_factory=MinutesConfig)
    server_home: ServerHomeConfig = Field(default_factory=ServerHomeConfig)
    autonomous_actions: AutonomousActionsConfig = Field(
        default_factory=AutonomousActionsConfig
    )

    @classmethod
    def load(cls, path: Path) -> AppConfig:
        """JSON ファイルから設定を読み込みバリデーションする

        Args:
            path: settings.json のパス

        Returns:
            バリデーション済みの AppConfig インスタンス

        Raises:
            FileNotFoundError: ファイルが存在しない場合
            json.JSONDecodeError: JSON パースに失敗した場合
            pydantic.ValidationError: バリデーションに失敗した場合
        """
        resolved: Path = Path(path).resolve()
        logger.info("設定ファイル読み込み: %s", resolved)

        raw_text: str = resolved.read_text(encoding="utf-8")
        raw_data: Dict[str, Any] = json.loads(raw_text)
        config: AppConfig = cls(**raw_data)

        logger.info("設定バリデーション成功: version=%s", config.version)
        return config

    def to_dict(self) -> Dict[str, Any]:
        """設定を辞書に変換する"""
        return self.dict()

    def save(self, path: Path) -> None:
        """設定を JSON ファイルに保存する"""
        resolved: Path = Path(path).resolve()
        data: Dict[str, Any] = self.dict()
        resolved.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("設定ファイル保存: %s", resolved)

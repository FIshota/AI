"""
プロトコルインターフェース定義

依存性注入のために Protocol クラスを定義します。
各コンポーネントはこれらのプロトコルに準拠する実装を差し替えられます。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMProtocol(Protocol):
    """LLM 推論エンジンのプロトコル"""

    def generate(
        self,
        prompt: str,
        max_tokens: int = 400,
        temperature: float = 0.65,
        stop: Optional[List[str]] = None,
    ) -> str:
        """プロンプトからテキストを生成する"""
        ...

    def is_loaded(self) -> bool:
        """モデルがロード済みかどうか"""
        ...


@runtime_checkable
class MemoryProtocol(Protocol):
    """記憶管理システムのプロトコル"""

    def store(
        self,
        content: str,
        memory_type: str = "mid",
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> int:
        """記憶を保存し、IDを返す"""
        ...

    def search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """クエリに関連する記憶を検索する"""
        ...

    def forget(self, memory_id: int) -> bool:
        """指定IDの記憶を削除する（保護されていない場合のみ）"""
        ...

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """最近の記憶を取得する"""
        ...


@runtime_checkable
class EmotionProtocol(Protocol):
    """感情エンジンのプロトコル"""

    def get_state(self) -> Dict[str, float]:
        """現在の感情状態を辞書で返す"""
        ...

    def update(self, text: str, context: Optional[Dict[str, Any]] = None) -> None:
        """テキストと文脈に基づいて感情状態を更新する"""
        ...

    def dominant(self) -> str:
        """支配的感情の名前を返す"""
        ...


@runtime_checkable
class TTSProtocol(Protocol):
    """音声合成エンジンのプロトコル"""

    def speak(self, text: str) -> bool:
        """テキストを音声で読み上げる。成功なら True"""
        ...

    def stop(self) -> None:
        """再生を停止する"""
        ...


@runtime_checkable
class STTProtocol(Protocol):
    """音声認識エンジンのプロトコル"""

    def recognize(self, audio_path: str) -> str:
        """音声ファイルからテキストを認識する"""
        ...


@runtime_checkable
class DiaryProtocol(Protocol):
    """日記管理のプロトコル"""

    def write(self, content: str, date: Optional[str] = None) -> bool:
        """日記エントリを書く"""
        ...

    def read(self, date: Optional[str] = None) -> Optional[str]:
        """指定日の日記を読む"""
        ...


@runtime_checkable
class LearningProtocol(Protocol):
    """学習エンジンのプロトコル"""

    def get_examples(self, limit: int = 5) -> List[Dict[str, str]]:
        """学習済み例文を取得する"""
        ...

    def add_example(self, user_text: str, ai_text: str) -> bool:
        """例文を追加する"""
        ...


@runtime_checkable
class AuditLogProtocol(Protocol):
    """監査ログのプロトコル (H1, 2026-04-21)"""

    def info(self, event: str, detail: str = "") -> None:
        """情報イベントを記録する"""
        ...

    def critical(self, event: str, detail: str = "") -> None:
        """重大イベントを記録する (purge など)"""
        ...


@runtime_checkable
class SubjectRightsProtocol(Protocol):
    """GDPR 17/20 条対応 (H1, 2026-04-21)"""

    def export_subject(self, subject_id: str = "self") -> Dict[str, Any]:
        """subject の全データを辞書として返す (GDPR 20 条)"""
        ...

    def purge_subject(
        self, subject_id: str = "self", dry_run: bool = False
    ) -> Dict[str, Any]:
        """subject の全データを削除する (GDPR 17 条)"""
        ...


@runtime_checkable
class PluginProtocol(Protocol):
    """プラグインのプロトコル"""

    @property
    def name(self) -> str:
        """プラグイン名"""
        ...

    @property
    def version(self) -> str:
        """プラグインバージョン"""
        ...

    def register(self, bus: Any) -> None:
        """イベントバスに登録する"""
        ...

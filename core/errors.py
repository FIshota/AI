"""
アイちゃん例外階層

全コンポーネントで共通の例外クラスを定義します。
各例外は message と任意の details を持ち、ログ出力やデバッグに活用できます。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AiChanError(Exception):
    """アイちゃんシステム共通の基底例外"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: Dict[str, Any] = details or {}

    def __repr__(self) -> str:
        cls = type(self).__name__
        if self.details:
            return f"{cls}(message={self.message!r}, details={self.details!r})"
        return f"{cls}(message={self.message!r})"


class LLMError(AiChanError):
    """LLM 推論に関するエラー（モデルロード失敗・生成タイムアウト等）"""


class MemoryError_(AiChanError):
    """記憶システムに関するエラー（DB接続・暗号化復号失敗等）

    組み込みの MemoryError とのシャドウイングを避けるために末尾に _ を付与。
    """


class SecurityError_(AiChanError):
    """セキュリティ関連のエラー（認証・署名検証・暗号化等）

    組み込みの SecurityError は存在しないが、慣例として _ を付与。
    """


class ConfigError(AiChanError):
    """設定読み込み・バリデーションに関するエラー"""


class PluginError(AiChanError):
    """プラグインのロード・初期化・実行に関するエラー"""


class SandboxError(AiChanError):
    """コード実行サンドボックスに関するエラー"""


class TimeoutError_(AiChanError):
    """タイムアウトに関するエラー

    組み込みの TimeoutError とのシャドウイングを避けるために末尾に _ を付与。
    """


class InjectionError(SecurityError_):
    """プロンプトインジェクション検出時のエラー"""


class IntegrityError(SecurityError_):
    """データ整合性（ハッシュ不一致・改竄検出等）に関するエラー"""


class MigrationError(AiChanError):
    """データベースマイグレーションに関するエラー"""

"""
スクリーンショット機密画面検出器。

外部ネット接続は行わず、ウィンドウタイトル / アプリ bundle id の
ローカル正規表現照合のみで機密画面を分類する。

Author: ai-chan
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class SensitiveAction(Enum):
    """機密画面検出時の処理アクション。"""

    BLOCK = "block"    # 取り込み完全禁止 (空バイト返却)
    BLUR = "blur"      # 強ブラー
    REDACT = "redact"  # 全面黒塗り


@dataclass(frozen=True)
class SensitivePattern:
    """機密画面パターン定義 (immutable)。"""

    name: str
    window_title_regex: str
    app_bundle_ids: Tuple[str, ...]
    action: SensitiveAction


# 初期パターン定義。全て frozen dataclass のため変更不可。
DEFAULT_PATTERNS: Tuple[SensitivePattern, ...] = (
    # --- パスワードマネージャ / Keychain → BLOCK ---
    SensitivePattern(
        name="1Password",
        window_title_regex=r"1Password|1password",
        app_bundle_ids=(
            "com.1password.1password",
            "com.agilebits.onepassword7",
            "com.1password.1password7",
        ),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="Bitwarden",
        window_title_regex=r"Bitwarden|bitwarden",
        app_bundle_ids=(
            "com.bitwarden.desktop",
            "com.bitwarden.macos",
        ),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="Keychain Access",
        window_title_regex=r"(?:Keychain\s+Access|キーチェーンアクセス)",
        app_bundle_ids=("com.apple.keychainaccess",),
        action=SensitiveAction.BLOCK,
    ),
    # --- 銀行 → BLOCK ---
    SensitivePattern(
        name="三井住友銀行",
        window_title_regex=r"(?:三井住友銀行|SMBC|Sumitomo\s*Mitsui)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="みずほ銀行",
        window_title_regex=r"(?:みずほ銀行|Mizuho)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="三菱UFJ銀行",
        window_title_regex=r"(?:三菱\s*UFJ|三菱ＵＦＪ|MUFG)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="ゆうちょ銀行",
        window_title_regex=r"(?:ゆうちょ|ゆうちょ銀行|JP\s*Bank)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="楽天銀行",
        window_title_regex=r"(?:楽天銀行|Rakuten\s*Bank)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    # --- 証券 → BLOCK ---
    SensitivePattern(
        name="楽天証券",
        window_title_regex=r"(?:楽天証券|Rakuten\s*Securities)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="SBI証券",
        window_title_regex=r"(?:SBI証券|SBI\s*Securities)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    SensitivePattern(
        name="松井証券",
        window_title_regex=r"(?:松井証券|Matsui\s*Securities)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    # --- 医療 → BLOCK ---
    SensitivePattern(
        name="医療ポータル",
        window_title_regex=r"(?:医療ポータル|電子カルテ|お薬手帳|処方箋|カルテ)",
        app_bundle_ids=(),
        action=SensitiveAction.BLOCK,
    ),
    # --- メール → BLUR ---
    SensitivePattern(
        name="Mail.app",
        window_title_regex=r"(?:受信(?:トレイ|箱)|メール|Inbox|Mail)",
        app_bundle_ids=("com.apple.mail",),
        action=SensitiveAction.BLUR,
    ),
    SensitivePattern(
        name="Outlook",
        window_title_regex=r"Outlook",
        app_bundle_ids=(
            "com.microsoft.Outlook",
            "com.microsoft.outlook",
        ),
        action=SensitiveAction.BLUR,
    ),
    SensitivePattern(
        name="Thunderbird",
        window_title_regex=r"Thunderbird",
        app_bundle_ids=("org.mozilla.thunderbird",),
        action=SensitiveAction.BLUR,
    ),
    SensitivePattern(
        name="Gmail Web",
        window_title_regex=r"Gmail",
        app_bundle_ids=(),
        action=SensitiveAction.BLUR,
    ),
    # --- メッセンジャー → BLUR ---
    SensitivePattern(
        name="LINE",
        window_title_regex=r"LINE",
        app_bundle_ids=(
            "jp.naver.line.mac",
            "com.line.line",
        ),
        action=SensitiveAction.BLUR,
    ),
    SensitivePattern(
        name="Signal",
        window_title_regex=r"Signal",
        app_bundle_ids=("org.whispersystems.signal-desktop",),
        action=SensitiveAction.BLUR,
    ),
    SensitivePattern(
        name="WhatsApp",
        window_title_regex=r"WhatsApp",
        app_bundle_ids=(
            "net.whatsapp.WhatsApp",
            "desktop.WhatsApp",
        ),
        action=SensitiveAction.BLUR,
    ),
    # --- 税務 → REDACT ---
    SensitivePattern(
        name="確定申告 / e-Tax",
        window_title_regex=r"(?:確定申告|e-Tax|国税庁|eTax)",
        app_bundle_ids=(),
        action=SensitiveAction.REDACT,
    ),
)


class SensitiveClassifier:
    """
    スレッドセーフな機密画面分類器。

    - 外部ネット接続禁止
    - 全てローカル正規表現照合
    - パターン群は immutable tuple として保持
    """

    def __init__(
        self,
        patterns: Tuple[SensitivePattern, ...] = DEFAULT_PATTERNS,
    ) -> None:
        self._patterns: Tuple[SensitivePattern, ...] = tuple(patterns)
        # 事前コンパイル (case-insensitive)。RLock でスレッドセーフに。
        self._lock = threading.RLock()
        self._compiled: Tuple[Tuple[SensitivePattern, "re.Pattern[str]"], ...] = tuple(
            (p, re.compile(p.window_title_regex, re.IGNORECASE))
            for p in self._patterns
        )

    def classify(
        self,
        window_title: Optional[str],
        app_bundle_id: Optional[str] = None,
    ) -> Optional[SensitivePattern]:
        """
        ウィンドウメタデータを機密パターンに照合する。

        一致したら最初のパターンを返し、なければ None を返す。
        引数は None / 空文字でも安全に扱う。
        """
        title = window_title or ""
        bundle = (app_bundle_id or "").lower()

        with self._lock:
            compiled = self._compiled

        for pattern, regex in compiled:
            # bundle id の完全一致 (大文字小文字無視)
            if bundle:
                for bid in pattern.app_bundle_ids:
                    if bid.lower() == bundle:
                        return pattern
            # タイトル部分一致
            if title and regex.search(title):
                return pattern
        return None

    @property
    def patterns(self) -> Tuple[SensitivePattern, ...]:
        """登録パターンの immutable tuple を返す。"""
        return self._patterns

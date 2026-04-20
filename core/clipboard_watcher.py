"""
クリップボード監視システム（macOS専用）
コピーされたテキストを検出してアイに通知します。
settings.json の autonomous.clipboard_watch: true の場合のみ動作。

H3 fix (2026-04-21): PII deny-list を強制適用。
    クレジットカード番号 / マイナンバー / パスポート番号 / API key 形など
    高リスク文字列を含むクリップボードは callback に渡さない（ドロップ）。
"""
from __future__ import annotations
import logging
import re
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

MIN_LENGTH    = 10     # 反応する最小文字数
MAX_LENGTH    = 3000   # 反応する最大文字数
COOLDOWN_SECS = 40     # 連続通知の抑制間隔（秒）
POLL_INTERVAL = 2.5    # ポーリング間隔（秒）


# ─── H3: PII deny-list ────────────────────────────────────────
# 検出されたらクリップボード内容を完全に破棄し、callback には一切渡さない。
# 厳格に False-positive を許容する設計（プライバシー優先）。
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # クレジットカード番号 (Luhn チェックはせず、13-19 桁の連続/ハイフン/スペース区切り)
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    # マイナンバー 12 桁
    ("my_number", re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
    # 日本のパスポート番号 (英字2 + 数字7)
    ("jp_passport", re.compile(r"\b[A-Z]{2}\d{7}\b")),
    # 米 SSN
    ("us_ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # AWS Access Key ID
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # GitHub PAT (ghp_ / gho_ / ghu_ / ghs_ / ghr_)
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    # OpenAI / Anthropic API key 形
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    # Slack bot token
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    # Google API key
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    # JWT ヘッダ (eyJ で始まる base64url.base64url.base64url)
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")),
    # BEGIN RSA/OPENSSH/EC PRIVATE KEY ブロック
    ("private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")),
    # クレジットカード CVV とセットになりがちな `CVV\s*[:=]\s*\d{3,4}`
    ("cvv_label", re.compile(r"\b(?:CVV|CVC|セキュリティコード)\s*[:=]?\s*\d{3,4}\b", re.IGNORECASE)),
)


def contains_pii(text: str) -> tuple[bool, list[str]]:
    """PII が含まれていれば (True, マッチしたラベル一覧) を返す。

    公開関数 — テストから直接呼べる。
    """
    hits: list[str] = []
    for label, pattern in _PII_PATTERNS:
        if pattern.search(text):
            hits.append(label)
    return (bool(hits), hits)


def _read_clipboard() -> str:
    """macOS の pbpaste でクリップボードを読む"""
    try:
        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2
        )
        return result.stdout
    except Exception:
        return ""


# ─── H7: NSPasteboard.changeCount ─────────────────────────────
# pbpaste を毎回 spawn せず、AppKit.NSPasteboard.generalPasteboard().changeCount
# を軽量ポーリングして、変化があったときだけ pbpaste を起動する。
# PyObjC が無い環境では fallback (_get_change_count() が None を返す)。
_NSPASTEBOARD = None
try:
    from AppKit import NSPasteboard  # type: ignore[import-not-found]
    _NSPASTEBOARD = NSPasteboard.generalPasteboard()
except Exception:
    _NSPASTEBOARD = None


def _get_change_count() -> int | None:
    """NSPasteboard.changeCount を返す。PyObjC 不在なら None。"""
    if _NSPASTEBOARD is None:
        return None
    try:
        return int(_NSPASTEBOARD.changeCount())
    except Exception:
        return None


class ClipboardWatcher(threading.Thread):
    """
    バックグラウンドでクリップボードを監視し、
    テキストが変わったら callback(text) を呼び出します。

    H3: PII が検出された場合は callback をスキップ（内容は破棄）。
    """

    def __init__(self, callback, interval: float = POLL_INTERVAL):
        super().__init__(daemon=True, name="ClipboardWatcher")
        self._callback    = callback
        self._interval    = interval
        self._last_text   = _read_clipboard()   # 起動時の内容は無視
        self._last_fired  = 0.0
        self._running     = True
        self._pii_dropped = 0  # H3: 観測性
        self._last_change_count = _get_change_count()  # H7: 変更検出

    def run(self):
        while self._running:
            time.sleep(self._interval)
            try:
                # H7: changeCount が同じなら pbpaste を起動しない
                cc = _get_change_count()
                if cc is not None:
                    if cc == self._last_change_count:
                        continue
                    self._last_change_count = cc
                text = _read_clipboard()
                if (
                    text
                    and text != self._last_text
                    and MIN_LENGTH <= len(text) <= MAX_LENGTH
                    and time.time() - self._last_fired >= COOLDOWN_SECS
                ):
                    # H3: PII check — 見つかれば破棄
                    has_pii, labels = contains_pii(text)
                    if has_pii:
                        self._pii_dropped += 1
                        # text 本体はログに残さない（機密の漏洩を避ける）
                        logger.warning(
                            "[ClipboardWatcher] PII detected, drop clipboard event "
                            "(labels=%s, len=%d, total_dropped=%d)",
                            labels, len(text), self._pii_dropped,
                        )
                        self._last_text = text  # re-trigger 防止のため更新のみ
                        continue
                    self._last_text  = text
                    self._last_fired = time.time()
                    self._callback(text)
                elif text != self._last_text:
                    # 内容は更新しておく（クールダウン中 or 長さ外でもリセット）
                    self._last_text = text
            except Exception as e:
                # 失敗を可視化（pbpaste権限エラーやコールバック例外を隠さない）
                logger.error("[ClipboardWatcher] error: %s", e)

    def stop(self):
        self._running = False

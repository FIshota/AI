"""
keychain — OS の鍵ストア (macOS Keychain / Linux secret-tool / Windows Credential)
を使って ai-chan のマスター鍵を保管する。

B3 fix (2026-04-21): 鍵ファイル (data/memory.key) を単独で置く現状は
ディスク窃取で丸裸になる。OS の鍵ストアに保管し、起動時のみ取り出す。

優先順位:
    1. 環境変数 AICHAN_MASTER_PASSPHRASE があれば PBKDF2 で派生
    2. macOS Keychain (`security` コマンド) から取得
    3. Linux secret-tool / gnome-keyring
    4. フォールバック: 既存の data/memory.key ファイル（警告付き）

使い方:
    from utils.keychain import get_master_key
    key = get_master_key(base_dir)
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

from utils.crypto import generate_key, load_or_create_key

logger = logging.getLogger(__name__)

_SERVICE_NAME = "ai-chan"
_ACCOUNT_NAME = "master-key"
_SALT_FILE = "key.salt"


# ── macOS Keychain ──────────────────────────────────────────────

def _mac_keychain_get() -> Optional[bytes]:
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", _SERVICE_NAME,
                "-a", _ACCOUNT_NAME,
                "-w",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import base64
            return base64.b64decode(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("macOS Keychain get 失敗: %s", exc)
    return None


def _mac_keychain_set(key: bytes) -> bool:
    try:
        import base64
        encoded = base64.b64encode(key).decode("ascii")
        result = subprocess.run(
            [
                "security", "add-generic-password",
                "-s", _SERVICE_NAME,
                "-a", _ACCOUNT_NAME,
                "-w", encoded,
                "-U",  # update existing
            ],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("macOS Keychain set 失敗: %s", exc)
        return False


# ── passphrase からの派生 ──────────────────────────────────────

def _derive_from_passphrase(passphrase: str, salt_path: Path) -> bytes:
    """passphrase + salt で PBKDF2-SHA256 により 32 byte 鍵を派生。"""
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    if salt_path.exists():
        salt = salt_path.read_bytes()
    else:
        salt = os.urandom(16)
        salt_path.write_bytes(salt)
        try:
            os.chmod(salt_path, 0o600)
        except OSError:
            pass
    key, _ = generate_key(passphrase=passphrase, salt=salt)
    return key


# ── 公開 API ────────────────────────────────────────────────────

def get_master_key(base_dir: Path) -> bytes:
    """ai-chan のマスター鍵を取得する。

    優先度:
      1. AICHAN_MASTER_PASSPHRASE env var → PBKDF2 派生
      2. macOS Keychain
      3. フォールバック: data/memory.key ファイル

    戻り値: 32-byte AES-256 鍵
    """
    base_dir = Path(base_dir)
    data_dir = base_dir / "data"

    # 1. passphrase 優先
    passphrase = os.environ.get("AICHAN_MASTER_PASSPHRASE", "").strip()
    if passphrase:
        salt_path = data_dir / _SALT_FILE
        key = _derive_from_passphrase(passphrase, salt_path)
        logger.info("マスター鍵: passphrase (PBKDF2) から派生")
        return key

    # 2. macOS Keychain
    if platform.system() == "Darwin":
        existing = _mac_keychain_get()
        if existing is not None and len(existing) == 32:
            logger.info("マスター鍵: macOS Keychain から取得")
            return existing
        # 新規生成して保管
        new_key = os.urandom(32)
        if _mac_keychain_set(new_key):
            logger.info("マスター鍵: macOS Keychain に新規保存")
            return new_key
        logger.warning(
            "macOS Keychain へのアクセスに失敗。"
            "ファイルフォールバックに切り替えます。"
        )

    # 3. フォールバック: 既存のファイル方式
    key_file = data_dir / "memory.key"
    logger.warning(
        "マスター鍵: ファイル %s を使用中 (ディスク窃取に弱い)。"
        "AICHAN_MASTER_PASSPHRASE または macOS Keychain 利用を推奨。",
        key_file,
    )
    return load_or_create_key(key_file)

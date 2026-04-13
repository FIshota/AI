"""
暗号化ユーティリティ
AES-256-GCM による全データの暗号化・復号を担当します
"""
from __future__ import annotations
import os
import base64
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def generate_key(passphrase: str | None = None, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """
    暗号化キーを生成します。
    passphrase が None の場合はランダムキーを生成します。
    戻り値: (key_bytes, salt)
    """
    if passphrase is None:
        key = os.urandom(32)
        return key, b""

    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = kdf.derive(passphrase.encode("utf-8"))
    return key, salt


def load_or_create_key(key_file: str | Path) -> bytes:
    """
    既存のキーファイルを読み込むか、新規作成します。
    """
    key_path = Path(key_file)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    if key_path.exists():
        raw = key_path.read_bytes()
        return base64.b64decode(raw)

    key = os.urandom(32)
    key_path.write_bytes(base64.b64encode(key))
    # キーファイルを読み取り専用に設定
    os.chmod(key_path, 0o400)
    return key


def encrypt(data: bytes, key: bytes) -> bytes:
    """
    AES-256-GCM でデータを暗号化します。
    フォーマット: nonce(12bytes) + ciphertext
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt(data: bytes, key: bytes) -> bytes:
    """
    AES-256-GCM でデータを復号します。
    """
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def encrypt_text(text: str, key: bytes) -> str:
    """テキストを暗号化してbase64文字列として返します"""
    encrypted = encrypt(text.encode("utf-8"), key)
    return base64.b64encode(encrypted).decode("ascii")


def decrypt_text(encrypted_b64: str, key: bytes) -> str:
    """base64暗号化文字列を復号してテキストとして返します"""
    encrypted = base64.b64decode(encrypted_b64)
    return decrypt(encrypted, key).decode("utf-8")

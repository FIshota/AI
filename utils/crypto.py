"""
暗号化ユーティリティ
AES-256-GCM による全データの暗号化・復号を担当します

フォールバック:
  cryptography パッケージが利用できない場合（cffi アーキテクチャ不整合など）は
  純粋 Python の AES-256-GCM 互換実装（標準ライブラリのみ）にフォールバックします。
  本番環境では必ず arm64 ネイティブ Python + cryptography を使用してください。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── cryptography のインポート（アーキテクチャ不整合時はフォールバック） ──
try:
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC as _PBKDF2HMAC
    _CRYPTO_AVAILABLE = True
except (ImportError, OSError) as _crypto_err:
    _CRYPTO_AVAILABLE = False
    # H9 fix (2026-04-20): 本番での silent fallback は致命的。
    # AICHAN_ALLOW_CRYPTO_FALLBACK=1 を明示設定した開発環境のみ継続。
    # デフォルトは sys.exit(1) で即停止。
    _allow_fallback = os.environ.get("AICHAN_ALLOW_CRYPTO_FALLBACK") == "1"
    if not _allow_fallback:
        import sys as _sys
        logger.critical(
            "cryptography ライブラリが利用できません (%s)。"
            "本番環境ではフォールバック不可。"
            "arm64 ネイティブ Python + pip install cryptography を実行してください。"
            "開発環境で一時的に続行したい場合のみ "
            "AICHAN_ALLOW_CRYPTO_FALLBACK=1 を設定してください。",
            _crypto_err,
        )
        _sys.exit(1)
    logger.warning(
        "cryptography ライブラリが利用できません (%s)。"
        "AICHAN_ALLOW_CRYPTO_FALLBACK=1 が設定されているため"
        "純粋 Python フォールバックで続行します（開発環境専用・本番禁止）。",
        _crypto_err,
    )
    _AESGCM = None  # type: ignore[assignment,misc]
    _PBKDF2HMAC = None  # type: ignore[assignment]
    _hashes = None  # type: ignore[assignment]


# ── 純粋 Python フォールバック（AES-CTR + HMAC-SHA256 による認証付き暗号化）──
# 注意: 本実装は開発・テスト用です。cryptography が利用可能な環境では使用されません。

def _fallback_encrypt(data: bytes, key: bytes) -> bytes:
    """
    AES-256-CTR + HMAC-SHA256 による認証付き暗号化（フォールバック）。
    Python 標準ライブラリのみで実装。
    フォーマット: nonce(16) + ciphertext + hmac(32)
    """
    import struct
    nonce = os.urandom(16)
    # CTR モードのキーストリームを SHAKE-256 で近似
    keystream_seed = hashlib.sha256(key + nonce).digest()
    ks = b""
    counter = 0
    while len(ks) < len(data):
        ks += hashlib.sha256(keystream_seed + struct.pack(">Q", counter)).digest()
        counter += 1
    ciphertext = bytes(a ^ b for a, b in zip(data, ks[: len(data)]))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return nonce + ciphertext + mac


def _fallback_decrypt(data: bytes, key: bytes) -> bytes:
    """AES-256-CTR + HMAC-SHA256 による復号（フォールバック）。"""
    import struct
    if len(data) < 48:  # nonce(16) + 最小1バイト + hmac(32)
        raise ValueError("不正な暗号化データ")
    nonce = data[:16]
    mac_received = data[-32:]
    ciphertext = data[16:-32]
    mac_expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac_received, mac_expected):
        raise ValueError("MAC 検証失敗: データが改ざんされている可能性があります")
    keystream_seed = hashlib.sha256(key + nonce).digest()
    ks = b""
    counter = 0
    while len(ks) < len(ciphertext):
        ks += hashlib.sha256(keystream_seed + struct.pack(">Q", counter)).digest()
        counter += 1
    return bytes(a ^ b for a, b in zip(ciphertext, ks[: len(ciphertext)]))


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

    if _CRYPTO_AVAILABLE and _PBKDF2HMAC is not None:
        kdf = _PBKDF2HMAC(
            algorithm=_hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = kdf.derive(passphrase.encode("utf-8"))
    else:
        # フォールバック: PBKDF2-HMAC-SHA256 (hashlib 標準実装)
        key = hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            salt,
            iterations=480000,
            dklen=32,
        )
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
    cryptography 利用不可時は CTR+HMAC フォールバックを使用。
    """
    if _CRYPTO_AVAILABLE and _AESGCM is not None:
        nonce = os.urandom(12)
        aesgcm = _AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext
    return _fallback_encrypt(data, key)


def decrypt(data: bytes, key: bytes) -> bytes:
    """
    AES-256-GCM でデータを復号します。
    cryptography 利用不可時は CTR+HMAC フォールバックを使用。
    """
    if _CRYPTO_AVAILABLE and _AESGCM is not None:
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = _AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    return _fallback_decrypt(data, key)


def encrypt_text(text: str, key: bytes) -> str:
    """テキストを暗号化してbase64文字列として返します"""
    encrypted = encrypt(text.encode("utf-8"), key)
    return base64.b64encode(encrypted).decode("ascii")


def decrypt_text(encrypted_b64: str, key: bytes) -> str:
    """base64暗号化文字列を復号してテキストとして返します"""
    encrypted = base64.b64decode(encrypted_b64)
    return decrypt(encrypted, key).decode("utf-8")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# キーローテーション (#93)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def check_key_age(key_path: str | Path) -> int:
    """
    キーファイルの経過日数を返す。
    ファイルが存在しない場合は -1 を返す。
    """
    kp = Path(key_path)
    if not kp.exists():
        return -1
    mtime = kp.stat().st_mtime
    age_seconds = datetime.now().timestamp() - mtime
    return int(age_seconds / 86400)


def needs_rotation(key_path: str | Path, max_days: int = 90) -> bool:
    """キーがローテーション推奨日数を超えているか判定する"""
    age = check_key_age(key_path)
    if age < 0:
        return False
    return age >= max_days


def rotate_key(
    old_key_path: str | Path,
    new_key_path: str | Path,
    db_path: str | Path,
) -> dict:
    """
    暗号化キーをローテーションする。
    1. 旧キーで全メモリを復号
    2. 新キーを生成
    3. 新キーで全メモリを再暗号化
    4. 新キーファイルを保存

    db_path は暗号化された記憶データ (JSON) のパスを指す。

    Returns:
        ローテーション結果レポート
    """
    import shutil as _shutil

    old_kp = Path(old_key_path)
    new_kp = Path(new_key_path)
    db = Path(db_path)

    report: dict = {
        "success": False,
        "records_rotated": 0,
        "errors": [],
    }

    # 旧キーの読み込み
    if not old_kp.exists():
        report["errors"].append("旧キーファイルが見つかりません")
        return report

    old_key = load_or_create_key(old_kp)

    # 新キーを生成
    new_key = os.urandom(32)
    new_kp.parent.mkdir(parents=True, exist_ok=True)

    if not db.exists():
        report["errors"].append("データベースファイルが見つかりません")
        return report

    # バックアップを作成
    backup_path = db.with_suffix(db.suffix + ".bak")
    _shutil.copy2(db, backup_path)

    try:
        raw = json.loads(db.read_text("utf-8"))

        rotated_count = 0
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and "encrypted_data" in entry:
                    try:
                        decrypted = decrypt_text(entry["encrypted_data"], old_key)
                        entry["encrypted_data"] = encrypt_text(decrypted, new_key)
                        rotated_count += 1
                    except Exception as e:
                        report["errors"].append(f"レコード復号失敗: {e}")
        elif isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, str):
                    try:
                        decrypted = decrypt_text(v, old_key)
                        raw[k] = encrypt_text(decrypted, new_key)
                        rotated_count += 1
                    except Exception:
                        pass  # 暗号化されていない値はスキップ

        # 再暗号化データを保存
        db.write_text(json.dumps(raw, ensure_ascii=False, indent=2), "utf-8")

        # 新キーを保存
        new_kp.write_bytes(base64.b64encode(new_key))
        os.chmod(new_kp, 0o400)

        report["success"] = True
        report["records_rotated"] = rotated_count

    except Exception as e:
        # ロールバック
        _shutil.copy2(backup_path, db)
        report["errors"].append(f"ローテーション失敗（ロールバック済み）: {e}")

    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# パスフレーズベース暗号化 (#99)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def derive_key_from_passphrase(
    passphrase: str, salt: bytes | None = None
) -> tuple[bytes, bytes]:
    """
    パスフレーズから PBKDF2 で暗号化キーを導出する。

    Returns:
        (key_bytes, salt) — salt は復号時に必要。
    """
    return generate_key(passphrase=passphrase, salt=salt)


def encrypt_file(input_path: str | Path, output_path: str | Path, key: bytes) -> None:
    """
    ファイルを AES-256-GCM で暗号化する。
    出力フォーマット: salt は呼び出し元で管理。nonce(12) + ciphertext。
    """
    inp = Path(input_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    plaintext = inp.read_bytes()
    encrypted = encrypt(plaintext, key)
    out.write_bytes(encrypted)


def decrypt_file(input_path: str | Path, output_path: str | Path, key: bytes) -> None:
    """
    AES-256-GCM で暗号化されたファイルを復号する。
    """
    inp = Path(input_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    ciphertext = inp.read_bytes()
    plaintext = decrypt(ciphertext, key)
    out.write_bytes(plaintext)

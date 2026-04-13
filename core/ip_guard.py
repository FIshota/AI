"""
IP保護モジュール - 独自開発の知的財産を保護する

機能:
1. モデルアダプター・訓練レシピの暗号化保存
2. コード難読化用のハッシュ署名
3. 実行環境バインディング（特定マシンでのみ動作）
4. 改ざん検知
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import secrets
import struct
import time
from pathlib import Path
from typing import Any


def _machine_fingerprint() -> str:
    """マシン固有のフィンガープリントを生成"""
    parts = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        str(os.cpu_count()),
    ]
    raw = "|".join(parts).encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _derive_key(master: bytes, salt: bytes, iterations: int = 100_000) -> bytes:
    """PBKDF2でマスターキーからサブキーを導出"""
    import hashlib
    dk = hashlib.pbkdf2_hmac("sha256", master, salt, iterations, dklen=32)
    return dk


class IPGuard:
    """知的財産保護ガード"""

    MANIFEST_FILE = ".ip_manifest.json"

    def __init__(self, data_dir: str | Path, key_file: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = Path(key_file)
        self._master_key = self._load_or_create_key()
        self._fingerprint = _machine_fingerprint()

    def _load_or_create_key(self) -> bytes:
        """マスターキーをロードまたは新規生成"""
        if self.key_file.exists():
            return self.key_file.read_bytes()
        key = secrets.token_bytes(32)
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self.key_file.write_bytes(key)
        os.chmod(str(self.key_file), 0o400)
        return key

    def encrypt_artifact(self, data: bytes, artifact_name: str) -> bytes:
        """
        訓練アダプター・レシピを暗号化保存。
        マシンバインディング付き - このマシンでのみ復号可能。
        """
        salt = secrets.token_bytes(16)
        # マシンフィンガープリントをソルトに混ぜる
        bound_salt = salt + self._fingerprint.encode()[:16]
        key = _derive_key(self._master_key, bound_salt)

        # XOR暗号 + HMAC検証（AESは外部依存、標準ライブラリのみで実現）
        # 本番では Fernet/AES-GCM を推奨。ここは依存最小限のため XOR+HMAC。
        encrypted = self._xor_crypt(data, key)
        mac = hmac.new(key, encrypted, hashlib.sha256).digest()

        # ヘッダー: salt(16) + mac(32) + data
        return salt + mac + encrypted

    def decrypt_artifact(self, blob: bytes, artifact_name: str) -> bytes | None:
        """暗号化アーティファクトを復号"""
        if len(blob) < 48:
            return None
        salt = blob[:16]
        stored_mac = blob[16:48]
        encrypted = blob[48:]

        bound_salt = salt + self._fingerprint.encode()[:16]
        key = _derive_key(self._master_key, bound_salt)

        expected_mac = hmac.new(key, encrypted, hashlib.sha256).digest()
        if not hmac.compare_digest(stored_mac, expected_mac):
            print(f"[IPGuard] 改ざんまたは別マシンからのアクセス検知: {artifact_name}")
            return None

        return self._xor_crypt(encrypted, key)

    def save_protected(self, data: bytes, name: str) -> Path:
        """保護されたアーティファクトを保存"""
        encrypted = self.encrypt_artifact(data, name)
        out_path = self.data_dir / f"{name}.protected"
        out_path.write_bytes(encrypted)
        self._update_manifest(name, len(data), len(encrypted))
        return out_path

    def load_protected(self, name: str) -> bytes | None:
        """保護されたアーティファクトを読み込み"""
        path = self.data_dir / f"{name}.protected"
        if not path.exists():
            return None
        blob = path.read_bytes()
        return self.decrypt_artifact(blob, name)

    def sign_file(self, file_path: str | Path) -> str:
        """ファイルの改ざん検知用署名を生成"""
        data = Path(file_path).read_bytes()
        return hmac.new(self._master_key, data, hashlib.sha256).hexdigest()

    def verify_file(self, file_path: str | Path, expected_sig: str) -> bool:
        """ファイルの改ざんを検証"""
        actual_sig = self.sign_file(file_path)
        return hmac.compare_digest(actual_sig, expected_sig)

    def sign_module(self, module_paths: list[str | Path]) -> dict[str, str]:
        """複数モジュールの署名を一括生成"""
        return {str(p): self.sign_file(p) for p in module_paths}

    def verify_modules(self, signatures: dict[str, str]) -> dict[str, bool]:
        """複数モジュールの改ざんを一括検証"""
        results = {}
        for path_str, sig in signatures.items():
            p = Path(path_str)
            if p.exists():
                results[path_str] = self.verify_file(p, sig)
            else:
                results[path_str] = False
        return results

    def _update_manifest(self, name: str, orig_size: int, enc_size: int) -> None:
        """保護アーティファクトのマニフェストを更新"""
        manifest_path = self.data_dir / self.MANIFEST_FILE
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
            except Exception:
                pass
        manifest[name] = {
            "original_size": orig_size,
            "encrypted_size": enc_size,
            "timestamp": time.time(),
            "machine": self._fingerprint[:8],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    @staticmethod
    def _xor_crypt(data: bytes, key: bytes) -> bytes:
        """XORストリーム暗号（キーを繰り返し適用）"""
        key_len = len(key)
        return bytes(b ^ key[i % key_len] for i, b in enumerate(data))

    def get_machine_id(self) -> str:
        """このマシンのIDを取得（デバッグ用）"""
        return self._fingerprint[:8]

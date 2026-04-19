"""
YAMATO Shield -- 整合性検証・ライセンスチェック・署名検証・監査ログ
アイの自己防衛の核。改竄検知、不正アクセス防止。

機能:
  - FileIntegrityChecker: コアファイルのSHA-256チェックサム管理・改竄検知
  - LicenseChecker: 依存パッケージのライセンス互換性チェック
  - UpdateVerifier: HMAC-SHA256署名によるアップデート検証
  - check_license_compliance: ランタイムライセンスチェック (importlib.metadata)
  - sign_log_entry / verify_log_entry / verify_audit_log: 監査ログの署名・検証
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FileIntegrityChecker — ファイル改竄検知
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)
class IntegrityBaseline:
    """チェックサムベースラインのスナップショット。"""
    created_at: str
    checksums: Dict[str, str]  # {相対パス: SHA-256ハッシュ}


class FileIntegrityChecker:
    """core/*.py ファイルのSHA-256チェックサムを管理し改竄を検知する。"""

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        """単一ファイルのSHA-256ハッシュを計算する。"""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def compute_checksums(self, base_dir: str | Path | None = None) -> Dict[str, str]:
        """core/*.py の全ファイルについてSHA-256を計算する。

        Args:
            base_dir: 走査するベースディレクトリ。Noneならインスタンスのbase_dir。

        Returns:
            {相対パス文字列: SHA-256ハッシュ文字列}
        """
        target = Path(base_dir) if base_dir is not None else self._base
        core_dir = target / "core"
        checksums: Dict[str, str] = {}

        if not core_dir.is_dir():
            logger.warning("core ディレクトリが見つかりません: %s", core_dir)
            return checksums

        for py_file in sorted(core_dir.glob("*.py")):
            if py_file.is_file():
                rel = str(py_file.relative_to(target))
                checksums[rel] = self._sha256_file(py_file)

        logger.info("チェックサム計算完了: %d ファイル", len(checksums))
        return checksums

    def save_baseline(self, path: str | Path) -> None:
        """現在のチェックサムをベースラインとしてJSONに保存する。"""
        checksums = self.compute_checksums()
        baseline = IntegrityBaseline(
            created_at=datetime.now(timezone.utc).isoformat(),
            checksums=checksums,
        )
        data = {
            "created_at": baseline.created_at,
            "checksums": baseline.checksums,
        }
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("ベースライン保存: %s (%d ファイル)", out, len(checksums))

    def verify_integrity(self, path: str | Path) -> List[str]:
        """ベースラインと現在のファイルを比較し、変更されたファイルを返す。

        Args:
            path: save_baseline() で保存したJSONファイルのパス。

        Returns:
            変更・追加・削除されたファイルの相対パスリスト。
            空リストなら全ファイルが一致。
        """
        baseline_path = Path(path)
        if not baseline_path.exists():
            logger.error("ベースラインファイルが見つかりません: %s", baseline_path)
            return ["[ERROR] ベースラインファイルが存在しません"]

        raw = json.loads(baseline_path.read_text(encoding="utf-8"))
        saved: Dict[str, str] = raw.get("checksums", {})
        current = self.compute_checksums()

        modified: List[str] = []

        # 変更・削除の検出
        for rel_path, saved_hash in saved.items():
            current_hash = current.get(rel_path)
            if current_hash is None:
                modified.append(f"[DELETED] {rel_path}")
                logger.warning("ファイル削除検出: %s", rel_path)
            elif current_hash != saved_hash:
                modified.append(f"[MODIFIED] {rel_path}")
                logger.warning("ファイル改竄検出: %s", rel_path)

        # 新規ファイルの検出
        for rel_path in current:
            if rel_path not in saved:
                modified.append(f"[NEW] {rel_path}")
                logger.info("新規ファイル検出: %s", rel_path)

        if not modified:
            logger.info("整合性検証OK: 全ファイル一致")
        else:
            logger.warning("整合性検証NG: %d 件の差分", len(modified))

        return modified


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LicenseChecker — ライセンス互換性チェック
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# GPLライセンスを持つことが知られているパッケージ（非GPL プロジェクトで問題になる）
_KNOWN_GPL_PACKAGES: Dict[str, str] = {
    "pygobject": "LGPL-2.1+",
    "pylint": "GPL-2.0",
    "readline": "GPL-3.0",
    "ghostscript": "AGPL-3.0",
    "mysql-connector-python": "GPL-2.0 (commercial option available)",
    "pycairo": "LGPL-2.1 / MPL-1.1",
    "pyqt5": "GPL-3.0 (commercial option available)",
    "pyqt6": "GPL-3.0 (commercial option available)",
    "sip": "GPL-2.0 / GPL-3.0",
    "mecab-python3": "GPL/LGPL/BSD (depends on MeCab build)",
}

# 注意が必要だが即座に問題にはならないライセンス
_CAUTION_PACKAGES: Dict[str, str] = {
    "chardet": "LGPL-2.1",
    "ffmpeg-python": "Apache-2.0 (but ffmpeg itself is LGPL/GPL)",
    "unidic": "GPL/LGPL/BSD (dictionary dependent)",
}


@dataclass(frozen=True)
class LicenseIssue:
    """ライセンス問題の報告。"""
    package: str
    installed_version: str
    license_info: str
    severity: str  # "critical" | "warning" | "info"
    message: str


class LicenseChecker:
    """requirements.txt を読み取り、既知の問題あるライセンスを検出する。"""

    def check_dependencies(
        self, requirements_txt: str | Path
    ) -> List[Dict[str, Any]]:
        """requirements.txt を解析し、ライセンス問題を報告する。

        Args:
            requirements_txt: requirements.txt のパス。

        Returns:
            問題のあるパッケージ情報の辞書リスト。
        """
        req_path = Path(requirements_txt)
        if not req_path.exists():
            logger.error("requirements.txt が見つかりません: %s", req_path)
            return [{"error": f"ファイルが見つかりません: {req_path}"}]

        issues: List[LicenseIssue] = []
        lines = req_path.read_text(encoding="utf-8").splitlines()

        for line in lines:
            stripped = line.strip()
            # コメント・空行をスキップ
            if not stripped or stripped.startswith("#"):
                continue

            # パッケージ名を抽出（バージョン指定を除去）
            pkg_name = stripped.split("==")[0].split(">=")[0].split("<=")[0]
            pkg_name = pkg_name.split("[")[0].strip().lower()
            version = stripped.replace(pkg_name, "").strip().lstrip("=<>!")

            # GPL チェック
            if pkg_name in _KNOWN_GPL_PACKAGES:
                issues.append(LicenseIssue(
                    package=pkg_name,
                    installed_version=version,
                    license_info=_KNOWN_GPL_PACKAGES[pkg_name],
                    severity="critical",
                    message=f"GPL系ライセンス検出: {pkg_name} ({_KNOWN_GPL_PACKAGES[pkg_name]})",
                ))
            # 注意パッケージ
            elif pkg_name in _CAUTION_PACKAGES:
                issues.append(LicenseIssue(
                    package=pkg_name,
                    installed_version=version,
                    license_info=_CAUTION_PACKAGES[pkg_name],
                    severity="warning",
                    message=f"要注意ライセンス: {pkg_name} ({_CAUTION_PACKAGES[pkg_name]})",
                ))

        result: List[Dict[str, Any]] = []
        for issue in issues:
            result.append({
                "package": issue.package,
                "version": issue.installed_version,
                "license": issue.license_info,
                "severity": issue.severity,
                "message": issue.message,
            })

        if result:
            logger.warning("ライセンスチェック: %d 件の問題検出", len(result))
        else:
            logger.info("ライセンスチェック: 問題なし")

        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UpdateVerifier — 署名付きアップデート検証
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class UpdateVerifier:
    """HMAC-SHA256署名によるファイルの真正性検証。

    アップデートファイルが正当な発行元から来たことを確認する。
    """

    @staticmethod
    def sign_file(file_path: str | Path, key: str) -> str:
        """ファイルのHMAC-SHA256署名を生成する。

        Args:
            file_path: 署名対象ファイルのパス。
            key: HMAC鍵（文字列）。

        Returns:
            16進文字列の署名。
        """
        target = Path(file_path)
        if not target.exists():
            raise FileNotFoundError(f"署名対象ファイルが見つかりません: {target}")

        content = target.read_bytes()
        signature = hmac.new(
            key.encode("utf-8"),
            content,
            hashlib.sha256,
        ).hexdigest()

        logger.info("署名生成: %s -> %s...", target.name, signature[:16])
        return signature

    @staticmethod
    def verify_signature(
        file_path: str | Path,
        signature: str,
        key: str,
    ) -> bool:
        """ファイルのHMAC-SHA256署名を検証する。

        Args:
            file_path: 検証対象ファイルのパス。
            signature: 期待される16進署名文字列。
            key: HMAC鍵（文字列）。

        Returns:
            True なら署名が一致（改竄なし）。
        """
        target = Path(file_path)
        if not target.exists():
            logger.error("検証対象ファイルが見つかりません: %s", target)
            return False

        content = target.read_bytes()
        expected = hmac.new(
            key.encode("utf-8"),
            content,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature)

        if is_valid:
            logger.info("署名検証OK: %s", target.name)
        else:
            logger.warning("署名検証NG (改竄の可能性): %s", target.name)

        return is_valid


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ライセンスコンプライアンスチェック (#50)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# GPL 系ライセンスキーワード
_GPL_KEYWORDS = ("gpl", "gnu general public", "agpl")


def check_license_compliance(requirements_txt: str | Path | None = None) -> dict:
    """
    requirements.txt の依存パッケージのライセンスを
    importlib.metadata で実際にチェックし、GPL 系を検出する。

    Args:
        requirements_txt: requirements.txt のパス（None の場合はインストール済み全パッケージ）

    Returns:
        {
            "compliant": bool,
            "packages": [{"name": str, "version": str, "license": str, "gpl_flag": bool}],
            "gpl_packages": [str],
            "total_checked": int,
        }
    """
    import importlib.metadata as _metadata

    packages_to_check: list[str] = []

    if requirements_txt is not None:
        req_path = Path(requirements_txt)
        if req_path.exists():
            for line in req_path.read_text("utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                pkg = stripped.split("==")[0].split(">=")[0].split("<=")[0]
                pkg = pkg.split("[")[0].strip()
                if pkg:
                    packages_to_check.append(pkg)

    # インストール済みパッケージからメタデータを取得
    if not packages_to_check:
        packages_to_check = [d.metadata["Name"] for d in _metadata.distributions()]

    result: dict = {
        "compliant": True,
        "packages": [],
        "gpl_packages": [],
        "total_checked": 0,
    }

    for pkg_name in packages_to_check:
        try:
            dist = _metadata.distribution(pkg_name)
            version = dist.metadata.get("Version", "unknown")
            license_text = dist.metadata.get("License", "")
            # License-Expression もチェック（PEP 639）
            license_expr = dist.metadata.get("License-Expression", "")
            combined_license = f"{license_text} {license_expr}".strip()

            if not combined_license:
                # classifiers からライセンス情報を取得
                classifiers = dist.metadata.get_all("Classifier") or []
                license_classifiers = [
                    c for c in classifiers if c.startswith("License")
                ]
                combined_license = "; ".join(license_classifiers) if license_classifiers else "Unknown"

            is_gpl = any(kw in combined_license.lower() for kw in _GPL_KEYWORDS)

            entry = {
                "name": pkg_name,
                "version": version,
                "license": combined_license[:200],
                "gpl_flag": is_gpl,
            }
            result["packages"].append(entry)
            result["total_checked"] += 1

            if is_gpl:
                result["gpl_packages"].append(pkg_name)
                result["compliant"] = False

        except _metadata.PackageNotFoundError:
            result["packages"].append({
                "name": pkg_name,
                "version": "not installed",
                "license": "N/A",
                "gpl_flag": False,
            })
            result["total_checked"] += 1

    if result["gpl_packages"]:
        logger.warning("GPL ライセンス検出: %s", result["gpl_packages"])
    else:
        logger.info("ライセンスチェック完了: 問題なし (%d パッケージ)", result["total_checked"])

    return result


def generate_license_report(
    output_path: str | Path,
    requirements_txt: str | Path | None = None,
) -> str:
    """
    ライセンスレポートを生成してファイルに保存する。

    Returns:
        保存先のパス文字列
    """
    compliance = check_license_compliance(requirements_txt)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    report_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **compliance,
    }
    out.write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2), "utf-8"
    )
    logger.info("ライセンスレポート保存: %s", out)
    return str(out)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 監査ログの署名・検証 (#94)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def sign_log_entry(entry: str, key: str) -> str:
    """
    監査ログエントリに HMAC-SHA256 署名を生成する。

    Args:
        entry: ログエントリ文字列
        key: HMAC 鍵（文字列）

    Returns:
        16進数の署名文字列
    """
    signature = hmac.new(
        key.encode("utf-8"),
        entry.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def verify_log_entry(entry: str, signature: str, key: str) -> bool:
    """
    監査ログエントリの署名を検証する。

    Returns:
        True なら署名が一致（改竄なし）
    """
    expected = hmac.new(
        key.encode("utf-8"),
        entry.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_audit_log(log_path: str | Path, key: str) -> dict:
    """
    監査ログファイル全体を検証する。

    ログファイルフォーマット（1行ずつ）:
        {"entry": "...", "signature": "..."}

    Returns:
        {
            "total_entries": int,
            "valid_entries": int,
            "invalid_entries": int,
            "invalid_lines": [int],
            "verified": bool,
        }
    """
    lp = Path(log_path)
    result: dict = {
        "total_entries": 0,
        "valid_entries": 0,
        "invalid_entries": 0,
        "invalid_lines": [],
        "verified": True,
    }

    if not lp.exists():
        logger.error("監査ログが見つかりません: %s", lp)
        result["verified"] = False
        return result

    for line_num, line in enumerate(lp.read_text("utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue

        result["total_entries"] += 1
        try:
            obj = json.loads(stripped)
            entry_text = obj.get("entry", "")
            sig = obj.get("signature", "")
            if verify_log_entry(entry_text, sig, key):
                result["valid_entries"] += 1
            else:
                result["invalid_entries"] += 1
                result["invalid_lines"].append(line_num)
                result["verified"] = False
        except (json.JSONDecodeError, KeyError, TypeError):
            result["invalid_entries"] += 1
            result["invalid_lines"].append(line_num)
            result["verified"] = False

    if result["verified"]:
        logger.info("監査ログ検証OK: %d エントリ", result["total_entries"])
    else:
        logger.warning(
            "監査ログ検証NG: %d/%d エントリが不正",
            result["invalid_entries"],
            result["total_entries"],
        )

    return result

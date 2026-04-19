"""
ファイル操作機能 — アイのファイルシステムアクセス
安全なファイル操作を提供する。書き込みは承認が必要。

forbidden_actions に従い:
- 外部システムへのアクセスは禁止
- ユーザーのホームディレクトリ配下のみアクセス可能
- 書き込みはユーザー承認が必要

Integration point:
    ai_chan.py の CMD パターンに以下のようなパターンを追加して利用する:

        CMD_FILE_READ = re.compile(r"ファイル(を?)?読(んで|む|み)|read\\s+file", re.I)
        CMD_FILE_LIST = re.compile(r"ファイル一覧|ls|ディレクトリ(を?)?見(て|る)", re.I)
        CMD_FILE_DIFF = re.compile(r"diff|ファイル(の?)?比較", re.I)

    コマンドハンドラ内で:

        if CMD_FILE_READ.match(user_input):
            ok, content = self.file_ops.read_file(path)
            return content if ok else f"読み込み失敗: {content}"

    初期化例:

        from core.file_ops import FileOperations
        self.file_ops = FileOperations(
            allowed_dirs=[str(Path.home())],
            require_approval_for_write=True,
        )
"""
from __future__ import annotations

import difflib
import fnmatch
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# 読み込みサイズ上限: 1MB
_MAX_READ_BYTES = 1_048_576

# ACL 設定ファイルのデフォルトパス
_DEFAULT_ACL_PATH = Path(__file__).resolve().parent.parent / "config" / "access_control.json"

# ACL が見つからない場合のデフォルト設定
_DEFAULT_ACL: Dict[str, Any] = {
    "allowed_dirs": [],
    "denied_patterns": ["*.key", "*.env", ".git/*"],
    "require_approval": ["*.py", "*.json"],
}


def _load_acl(acl_path: Path) -> Dict[str, Any]:
    """ACL 設定ファイルを読み込む。存在しなければデフォルトを作成して返す。"""
    if acl_path.exists():
        try:
            return json.loads(acl_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("ACL 読み込み失敗、デフォルトを使用: %s", e)

    # デフォルトを作成
    acl_path.parent.mkdir(parents=True, exist_ok=True)
    acl_path.write_text(
        json.dumps(_DEFAULT_ACL, ensure_ascii=False, indent=2), "utf-8"
    )
    logger.info("デフォルト ACL を作成: %s", acl_path)
    return dict(_DEFAULT_ACL)


class FileOperations:
    """
    安全なファイル操作を提供するクラス。

    - allowed_dirs 配下のパスのみアクセスを許可（ACL から読み込み）
    - denied_patterns に一致するファイルへのアクセスをブロック
    - require_approval パターンに一致するファイルは書き込みに承認が必要
    - パストラバーサル（../）を検出してブロック
    """

    def __init__(
        self,
        allowed_dirs: List[str] | None = None,
        require_approval_for_write: bool = True,
        acl_path: str | Path | None = None,
    ) -> None:
        self._acl_path = Path(acl_path) if acl_path else _DEFAULT_ACL_PATH
        self._acl = _load_acl(self._acl_path)

        # ACL の allowed_dirs とコンストラクタ引数をマージ
        acl_dirs = [str(d) for d in self._acl.get("allowed_dirs", [])]
        init_dirs = list(allowed_dirs) if allowed_dirs else []
        merged_dirs = list(set(acl_dirs + init_dirs))

        # 許可ディレクトリを正規化して保持（不変リスト）
        self._allowed_dirs: Tuple[Path, ...] = tuple(
            Path(d).resolve() for d in merged_dirs
        ) if merged_dirs else (Path.home().resolve(),)

        self._denied_patterns: List[str] = self._acl.get("denied_patterns", [])
        self._approval_patterns: List[str] = self._acl.get("require_approval", [])
        self._require_approval = require_approval_for_write
        logger.info(
            "FileOperations 初期化: allowed_dirs=%s, require_approval=%s, "
            "denied_patterns=%d, approval_patterns=%d",
            [str(d) for d in self._allowed_dirs],
            self._require_approval,
            len(self._denied_patterns),
            len(self._approval_patterns),
        )

    def reload_acl(self) -> None:
        """ACL 設定を再読み込みする（実行時の設定変更に対応）"""
        self._acl = _load_acl(self._acl_path)
        acl_dirs = [str(d) for d in self._acl.get("allowed_dirs", [])]
        if acl_dirs:
            self._allowed_dirs = tuple(Path(d).resolve() for d in acl_dirs)
        self._denied_patterns = self._acl.get("denied_patterns", [])
        self._approval_patterns = self._acl.get("require_approval", [])
        logger.info("ACL 再読み込み完了")

    # ─── パス安全性チェック ───────────────────────────────────

    def _is_denied_pattern(self, path: str) -> bool:
        """パスが denied_patterns に一致するか判定する"""
        filename = Path(path).name
        rel_path = path.replace("\\", "/")
        for pattern in self._denied_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def _needs_approval(self, path: str) -> bool:
        """パスが require_approval パターンに一致するか判定する"""
        filename = Path(path).name
        for pattern in self._approval_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def _is_safe_path(self, path: str) -> bool:
        """
        パスが許可ディレクトリ配下にあり、トラバーサルが無いか検証する。

        チェック内容:
        1. '..' セグメントによるディレクトリトラバーサルの検出
        2. resolve() 後のパスが allowed_dirs のいずれかの配下であること
        3. denied_patterns に一致しないこと
        """
        try:
            raw = Path(path)
            # 生のパス文字列に '..' が含まれていたら拒否
            # (resolve前にチェックすることでシンボリックリンク経由の回避も防ぐ)
            if ".." in raw.parts:
                logger.warning("パストラバーサル検出: %s", path)
                return False

            # denied_patterns チェック
            if self._is_denied_pattern(path):
                logger.warning("拒否パターンに一致: %s", path)
                return False

            resolved = raw.resolve()
            for allowed in self._allowed_dirs:
                try:
                    resolved.relative_to(allowed)
                    return True
                except ValueError:
                    continue

            logger.warning(
                "許可範囲外のパス: %s (resolved=%s)", path, resolved,
            )
            return False
        except (OSError, ValueError) as exc:
            logger.warning("パス検証エラー: %s — %s", path, exc)
            return False

    # ─── ファイル読み込み ─────────────────────────────────────

    def read_file(self, path: str) -> Tuple[bool, str]:
        """
        ファイルを読み込む。

        Returns:
            (True, ファイル内容) または (False, エラーメッセージ)
        """
        if not self._is_safe_path(path):
            return False, "アクセスが許可されていないパスだよ。"

        target = Path(path).resolve()
        if not target.exists():
            logger.info("ファイル未発見: %s", target)
            return False, f"ファイルが見つからないよ: {target.name}"

        if not target.is_file():
            return False, "指定されたパスはファイルじゃないよ。"

        # サイズチェック
        try:
            size = target.stat().st_size
        except OSError as exc:
            logger.error("stat失敗: %s — %s", target, exc)
            return False, f"ファイル情報の取得に失敗したよ: {exc}"

        if size > _MAX_READ_BYTES:
            return False, (
                f"ファイルが大きすぎるよ（{size:,} bytes）。"
                f"上限は {_MAX_READ_BYTES:,} bytes だよ。"
            )

        try:
            content = target.read_text(encoding="utf-8")
            logger.info("ファイル読み込み成功: %s (%d bytes)", target, size)
            return True, content
        except UnicodeDecodeError:
            # バイナリファイルの可能性
            logger.info("UTF-8デコード失敗（バイナリ？）: %s", target)
            return False, "テキストファイルとして読めなかったよ（バイナリファイルかも）。"
        except OSError as exc:
            logger.error("ファイル読み込みエラー: %s — %s", target, exc)
            return False, f"読み込みに失敗したよ: {exc}"

    # ─── ファイル書き込み ─────────────────────────────────────

    def write_file(
        self, path: str, content: str, approved: bool = False,
    ) -> Tuple[bool, str]:
        """
        ファイルに書き込む。approved=True かつパスが安全な場合のみ実行する。

        Returns:
            (True, 成功メッセージ) または (False, エラーメッセージ)
        """
        if not self._is_safe_path(path):
            return False, "アクセスが許可されていないパスだよ。"

        if (self._require_approval or self._needs_approval(path)) and not approved:
            logger.info("書き込み未承認: %s", path)
            return False, (
                "ファイルへの書き込みにはユーザーの承認が必要だよ。"
                "「書き込みを許可」と言ってね。"
            )

        target = Path(path).resolve()

        # 親ディレクトリが存在しない場合は作成しない（安全のため）
        if not target.parent.exists():
            return False, f"親ディレクトリが存在しないよ: {target.parent}"

        try:
            target.write_text(content, encoding="utf-8")
            written_size = target.stat().st_size
            logger.info(
                "ファイル書き込み成功: %s (%d bytes)", target, written_size,
            )
            return True, f"書き込み完了: {target.name} ({written_size:,} bytes)"
        except OSError as exc:
            logger.error("ファイル書き込みエラー: %s — %s", target, exc)
            return False, f"書き込みに失敗したよ: {exc}"

    # ─── ディレクトリ一覧 ─────────────────────────────────────

    def list_dir(self, path: str) -> Tuple[bool, List[str]]:
        """
        ディレクトリの内容を一覧する。

        Returns:
            (True, エントリ名リスト) または (False, [エラーメッセージ])
        """
        if not self._is_safe_path(path):
            return False, ["アクセスが許可されていないパスだよ。"]

        target = Path(path).resolve()
        if not target.exists():
            return False, [f"ディレクトリが見つからないよ: {target.name}"]

        if not target.is_dir():
            return False, ["指定されたパスはディレクトリじゃないよ。"]

        try:
            entries = sorted(
                entry.name + ("/" if entry.is_dir() else "")
                for entry in target.iterdir()
                if not entry.name.startswith(".")  # 隠しファイルは除外
            )
            logger.info(
                "ディレクトリ一覧: %s (%d entries)", target, len(entries),
            )
            return True, entries
        except OSError as exc:
            logger.error("ディレクトリ一覧エラー: %s — %s", target, exc)
            return False, [f"一覧取得に失敗したよ: {exc}"]

    # ─── ファイル差分 ─────────────────────────────────────────

    def diff_files(self, path1: str, path2: str) -> Tuple[bool, str]:
        """
        2つのファイルの差分を表示する（unified diff 形式）。

        Returns:
            (True, diff文字列) または (False, エラーメッセージ)
        """
        ok1, content1 = self.read_file(path1)
        if not ok1:
            return False, f"ファイル1の読み込み失敗: {content1}"

        ok2, content2 = self.read_file(path2)
        if not ok2:
            return False, f"ファイル2の読み込み失敗: {content2}"

        lines1 = content1.splitlines(keepends=True)
        lines2 = content2.splitlines(keepends=True)

        name1 = Path(path1).name
        name2 = Path(path2).name

        diff_lines = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=name1,
            tofile=name2,
            lineterm="",
        ))

        if not diff_lines:
            logger.info("差分なし: %s vs %s", path1, path2)
            return True, "2つのファイルに差分はないよ。"

        result = "\n".join(diff_lines)
        logger.info(
            "差分検出: %s vs %s (%d lines)", path1, path2, len(diff_lines),
        )
        return True, result

    # ─── ファイル情報 ─────────────────────────────────────────

    def file_info(self, path: str) -> dict:
        """
        ファイルのメタ情報を返す。

        Returns:
            {
                "exists": bool,
                "name": str,
                "size": int (bytes),
                "modified": str (ISO format),
                "type": "file" | "directory" | "symlink" | "other",
                "readable": bool,
                "writable": bool,
                "error": str | None,
            }
        """
        base: dict = {
            "exists": False,
            "name": Path(path).name,
            "size": 0,
            "modified": "",
            "type": "other",
            "readable": False,
            "writable": False,
            "error": None,
        }

        if not self._is_safe_path(path):
            return {**base, "error": "アクセスが許可されていないパス"}

        target = Path(path).resolve()
        if not target.exists():
            return {**base, "error": None}  # exists=False, no error

        try:
            st = target.stat()
        except OSError as exc:
            return {**base, "exists": True, "error": str(exc)}

        # ファイルタイプ判定
        if target.is_symlink():
            ftype = "symlink"
        elif target.is_file():
            ftype = "file"
        elif target.is_dir():
            ftype = "directory"
        else:
            ftype = "other"

        modified_dt = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)

        return {
            **base,
            "exists": True,
            "size": st.st_size,
            "modified": modified_dt.isoformat(),
            "type": ftype,
            "readable": os.access(target, os.R_OK),
            "writable": os.access(target, os.W_OK),
        }

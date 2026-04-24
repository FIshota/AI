"""
tenant_context — マルチテナント物理分離のための root-scoped コンテキスト。

既存の ``core.tenant`` が `TenantId` / `tenant_dir` という論理識別子を提供するのに対し、
``TenantContext`` は「1 テナントにつき 1 つの独立した root_dir」を前提とした、
ファイルシステム分離境界を司る抽象である。

主な責務:
    * tenant_id のバリデーション (``^[a-z0-9_-]{3,32}$``)
    * 専用 root 配下に ``memory/`` / ``config/`` / ``logs/`` / ``data/`` を作成
    * ``guard_path(p)`` による root 外への書き込み拒否 (シンボリックリンク攻撃も拒否)
    * purge によるテナント単位の安全な物理削除

Python 3.9 互換・stdlib のみ。frozen dataclass。
"""
from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

__all__ = [
    "TenantContext",
    "InvalidTenantIdError",
    "TenantIsolationError",
    "list_tenants",
    "purge_tenant",
]

_TENANT_ID_RE = re.compile(r"^[a-z0-9_-]{3,32}$")

# 分離された sub-tree 名
_SUBDIRS = ("memory", "config", "logs", "data", "audit")

# 並列書き込み時の root 作成競合を抑える
_CREATE_LOCK = threading.Lock()


class InvalidTenantIdError(ValueError):
    """tenant_id の形式が不正。"""


class TenantIsolationError(PermissionError):
    """root_dir を越える書き込み/読み取り試行。"""


def _validate_tenant_id(tenant_id: str) -> None:
    if not isinstance(tenant_id, str):
        raise InvalidTenantIdError(
            f"tenant_id must be str, got {type(tenant_id).__name__}"
        )
    if not _TENANT_ID_RE.fullmatch(tenant_id):
        raise InvalidTenantIdError(
            "tenant_id must match ^[a-z0-9_-]{3,32}$: "
            f"{tenant_id!r}"
        )


@dataclass(frozen=True)
class TenantContext:
    """テナント 1 個に紐づく物理分離境界。

    Attributes:
        tenant_id: 正規化済み識別子 (lowercase, 3-32 chars, [a-z0-9_-])
        root_dir: テナント専用ルート。全 I/O はこの配下で完結する。
    """

    tenant_id: str
    root_dir: Path

    def __post_init__(self) -> None:
        _validate_tenant_id(self.tenant_id)
        if not isinstance(self.root_dir, Path):
            object.__setattr__(self, "root_dir", Path(self.root_dir))

    # ─── factories ─────────────────────────────────────────────

    @classmethod
    def create_isolated(
        cls, base_dir: os.PathLike | str, tenant_id: str
    ) -> "TenantContext":
        """``base_dir/<tenant_id>/`` 配下に専用サブツリーを作成して返す。

        既存ディレクトリがある場合は冪等に再利用する。
        """
        _validate_tenant_id(tenant_id)
        base = Path(base_dir).resolve()
        root = (base / tenant_id).resolve()
        # path-traversal 保険: base の下に収まっているか確認
        if base != root and base not in root.parents:
            raise TenantIsolationError(
                f"resolved root escapes base_dir: base={base} root={root}"
            )
        with _CREATE_LOCK:
            root.mkdir(parents=True, exist_ok=True)
            for sub in _SUBDIRS:
                (root / sub).mkdir(parents=True, exist_ok=True)
        return cls(tenant_id=tenant_id, root_dir=root)

    # ─── path helpers ──────────────────────────────────────────

    @property
    def memory_dir(self) -> Path:
        return self.root_dir / "memory"

    @property
    def config_dir(self) -> Path:
        return self.root_dir / "config"

    @property
    def logs_dir(self) -> Path:
        return self.root_dir / "logs"

    @property
    def data_dir(self) -> Path:
        return self.root_dir / "data"

    @property
    def audit_dir(self) -> Path:
        return self.root_dir / "audit"

    # ─── guard ────────────────────────────────────────────────

    def guard_path(self, path: os.PathLike | str) -> Path:
        """``path`` が ``root_dir`` 配下に収まっていることを検証する。

        Returns:
            解決済み (resolve 済み) の Path。そのまま I/O に使える。

        Raises:
            TenantIsolationError: ``../`` 脱出やシンボリックリンクで
                root_dir の外を指している場合。
        """
        root_resolved = self.root_dir.resolve()
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (self.root_dir / candidate)
        # strict=False: 未作成ファイルも検査できるよう親を解決する
        try:
            resolved = candidate.resolve(strict=False)
        except OSError as exc:  # pragma: no cover - OS依存
            raise TenantIsolationError(f"cannot resolve path: {candidate}") from exc

        # symlink detection: lexically resolved path must still be inside root.
        # Also, if any component is a symlink pointing outside root, resolve()
        # will follow it and land outside; we catch that via the parents check.
        if resolved != root_resolved and root_resolved not in resolved.parents:
            raise TenantIsolationError(
                f"path escapes tenant root: path={resolved} root={root_resolved}"
            )
        # さらに、経路上のどこかにシンボリックリンクがあり、
        # その lstat target が root 外なら拒否する (paranoia 二重チェック)。
        cur = candidate
        seen: set[Path] = set()
        while True:
            if cur in seen:
                break
            seen.add(cur)
            if cur.is_symlink():
                target = os.readlink(cur)
                target_path = Path(target)
                if not target_path.is_absolute():
                    target_path = (cur.parent / target_path)
                target_resolved = target_path.resolve(strict=False)
                if (
                    target_resolved != root_resolved
                    and root_resolved not in target_resolved.parents
                ):
                    raise TenantIsolationError(
                        f"symlink target escapes tenant root: "
                        f"link={cur} -> {target_resolved} root={root_resolved}"
                    )
            if cur.parent == cur:
                break
            cur = cur.parent
            try:
                if root_resolved == cur.resolve(strict=False):
                    break
            except OSError:
                break
        return resolved

    # ─── convenience ──────────────────────────────────────────

    def subpath(self, *parts: str) -> Path:
        """``root_dir`` を基点とした安全なサブパス。"""
        return self.guard_path(self.root_dir.joinpath(*parts))


# ─── module-level helpers ─────────────────────────────────────


def list_tenants(base_dir: os.PathLike | str) -> list[str]:
    """``base_dir`` 配下に存在する tenant_id を昇順で返す。"""
    base = Path(base_dir)
    if not base.is_dir():
        return []
    out: list[str] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if _TENANT_ID_RE.fullmatch(name):
            out.append(name)
    return out


def purge_tenant(
    base_dir: os.PathLike | str,
    tenant_id: str,
    *,
    confirm: bool = False,
) -> Path:
    """指定テナントの root_dir を削除する (破壊的)。

    ``confirm=False`` の場合は dry-run として何も削除せず、
    対象パスだけを返す。他テナントには絶対に触れない。
    """
    _validate_tenant_id(tenant_id)
    base = Path(base_dir).resolve()
    target = (base / tenant_id).resolve()
    if base != target and base not in target.parents:
        raise TenantIsolationError(
            f"resolved purge target escapes base_dir: {target}"
        )
    if not confirm:
        return target
    if target.exists():
        shutil.rmtree(target)
    return target

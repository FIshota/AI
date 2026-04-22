"""M9 Phase 1: sqlite-vec loadability detection.

Python's stdlib ``sqlite3`` only exposes ``enable_load_extension`` when the
underlying SQLite was built with ``--enable-loadable-sqlite-extensions``.
Official python.org binaries ship this OFF; homebrew and most Linux distros
ship it ON. We need a fast, non-raising probe to decide whether the
``sqlite-vec`` backend is usable in the current environment.

Usage::

    from utils.sqlite_vec_support import check_sqlite_vec_support
    report = check_sqlite_vec_support()
    if report.usable:
        ...

The function **never raises**; all exceptions are captured in the result.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SQLiteVecSupport:
    """Result of probing the current environment for sqlite-vec usability."""

    usable: bool
    has_enable_load_extension: bool
    sqlite_vec_installed: bool
    sqlite_version: str = ""
    sqlite_vec_version: str = ""
    error: str = ""
    hints: tuple[str, ...] = field(default_factory=tuple)


def check_sqlite_vec_support() -> SQLiteVecSupport:
    """Return a best-effort report on whether sqlite-vec can be loaded.

    Never raises — failure modes are captured in the dataclass fields.
    """
    hints: list[str] = []
    sqlite_version = sqlite3.sqlite_version

    # 1) Probe: does this sqlite3 build support loadable extensions?
    has_elx = False
    elx_error = ""
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(":memory:")
        has_elx = hasattr(conn, "enable_load_extension")
        if has_elx:
            # Calling it may still raise if symbol is stubbed out
            try:
                conn.enable_load_extension(True)
                conn.enable_load_extension(False)
            except (sqlite3.NotSupportedError, AttributeError, sqlite3.OperationalError) as exc:
                has_elx = False
                elx_error = f"{type(exc).__name__}: {exc}"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if not has_elx:
        hints.append(
            "Python の sqlite3 が loadable extension に非対応です。"
            "homebrew python か pyenv (PYTHON_CONFIGURE_OPTS=--enable-loadable-sqlite-extensions) で再ビルドしてください。"
        )

    # 2) Probe: is sqlite-vec installed?
    sv_installed = False
    sv_version = ""
    try:
        import sqlite_vec  # type: ignore[import-not-found]
        sv_installed = True
        sv_version = getattr(sqlite_vec, "__version__", "")
    except ImportError:
        hints.append("sqlite-vec が未インストールです (`pip install sqlite-vec`)")

    usable = has_elx and sv_installed
    error = elx_error if elx_error else ("" if usable else "; ".join(hints))

    return SQLiteVecSupport(
        usable=usable,
        has_enable_load_extension=has_elx,
        sqlite_vec_installed=sv_installed,
        sqlite_version=sqlite_version,
        sqlite_vec_version=sv_version,
        error=error,
        hints=tuple(hints),
    )

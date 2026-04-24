"""
Shared pytest fixtures and marker configuration.

Provides:
    - tk_root: module-scoped hidden Tk() root, or skips if no display.
    - Custom marker registration (ui).
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Iterator

import pytest

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "ui: UI / desktop widget tests (require a display, skipped headless)",
    )


def _display_available() -> bool:
    """
    Return True if a Tk display is likely usable.

    - macOS: Tk talks to WindowServer; skip when no GUI session.
    - Linux: require $DISPLAY (typically provided by Xvfb in CI).
    """
    if sys.platform == "darwin":
        # On Darwin, Tk() can raise TclError in headless contexts.
        # There is no reliable env-flag short of trying it.
        return os.environ.get("AICHAN_FORCE_UI_TESTS") == "1" or (
            os.environ.get("DISPLAY") is not None
        )
    if sys.platform.startswith("linux"):
        if os.environ.get("DISPLAY"):
            return True
        # Allow xvfb-run wrapper to set this even if DISPLAY is lazy.
        return shutil.which("xvfb-run") is not None and os.environ.get(
            "AICHAN_FORCE_UI_TESTS"
        ) == "1"
    return os.environ.get("DISPLAY") is not None


@pytest.fixture(scope="module")
def tk_root() -> Iterator[object]:
    """
    Yield a hidden Tk() root for UI tests.

    Skips the entire test module if Tk cannot open a display. The root is
    withdrawn (never shown) and destroyed on teardown.
    """
    if not _display_available():
        pytest.skip(
            "No display available for Tk UI tests "
            "(set DISPLAY or AICHAN_FORCE_UI_TESTS=1)."
        )
    try:
        import tkinter as tk
    except ImportError as exc:  # pragma: no cover - tkinter is stdlib
        pytest.skip(f"tkinter unavailable: {exc}")

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk() failed to initialize: {exc}")

    root.withdraw()
    logger.info("tk_root fixture initialized (hidden)")
    try:
        yield root
    finally:
        try:
            root.destroy()
        except Exception as exc:  # pragma: no cover
            logger.warning("tk_root teardown error: %s", exc)

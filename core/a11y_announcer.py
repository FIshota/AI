"""
Screen reader announcer for state changes in the desktop pet.

The announcer is intentionally small: given a short text string, route it
through the best available speech channel for the current platform.

Routing order
-------------
1. macOS:  ``osascript`` + ``tell application "VoiceOver" to output ...``.
   If VoiceOver is not running, ``say`` is tried as a softer fallback.
2. Linux:  ``speak`` (espeak-ng) if available.
3. Other / all above missing: ``FileSink`` fallback that appends the
   message to ``logs/a11y_announcements.log`` and echoes to stdout.

The module never raises for a missing backend. Announcement is always
best-effort: a screen-reader failure must never break the pet UI.

Python 3.9 compatible, stdlib only.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess  # nosec B404 - intentional, arguments are hard-coded
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

_DEFAULT_LOG_REL = Path("logs") / "a11y_announcements.log"


class _Sink(Protocol):
    name: str
    def speak(self, text: str) -> bool: ...


@dataclass
class FileSink:
    """Fallback sink that writes announcements to a log file and stdout."""

    name: str = "file"
    log_path: Path = _DEFAULT_LOG_REL

    def speak(self, text: str) -> bool:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(text.rstrip("\n") + "\n")
        except OSError as exc:
            logger.warning("FileSink write failed: %s", exc)
        # Also echo to stdout so a terminal user can see announcements.
        try:
            print(f"[a11y] {text}", flush=True)
        except Exception:  # pragma: no cover - stdout closed
            pass
        return True


@dataclass
class _MacVoiceOverSink:
    name: str = "voiceover"

    def speak(self, text: str) -> bool:
        if sys.platform != "darwin":
            return False
        osascript = shutil.which("osascript")
        if not osascript:
            return False
        # Prefer VoiceOver output; if VoiceOver is off, `say` is softer.
        script = f'tell application "VoiceOver" to output "{_escape_applescript(text)}"'
        try:
            result = subprocess.run(  # nosec B603 - fixed argv
                [osascript, "-e", script],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("VoiceOver osascript failed: %s", exc)

        # Fallback to `say` (builtin TTS) which works even without VoiceOver.
        say = shutil.which("say")
        if not say:
            return False
        try:
            subprocess.run(  # nosec B603
                [say, text], capture_output=True, timeout=5.0, check=False,
            )
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("say command failed: %s", exc)
            return False


@dataclass
class _LinuxSpeakSink:
    name: str = "speak"

    def speak(self, text: str) -> bool:
        if not sys.platform.startswith("linux"):
            return False
        # `speak` is the espeak-ng CLI; `espeak` is an older alias.
        binary = shutil.which("speak") or shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            return False
        try:
            subprocess.run(  # nosec B603
                [binary, text], capture_output=True, timeout=5.0, check=False,
            )
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("linux speak failed: %s", exc)
            return False


def _escape_applescript(text: str) -> str:
    # AppleScript string escape: backslash and double-quote.
    return text.replace("\\", "\\\\").replace('"', '\\"')


class A11yAnnouncer:
    """Thread-safe announcer that falls back gracefully across platforms.

    Parameters
    ----------
    enabled:
        If False, ``announce`` is a no-op that still returns True. This
        lets callers wire the announcer unconditionally without branching.
    log_path:
        Path used by the fallback ``FileSink``. Defaults to
        ``logs/a11y_announcements.log`` relative to cwd.
    """

    def __init__(
        self,
        enabled: bool = False,
        log_path: Optional[Path] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        self._file_sink = FileSink(log_path=log_path or _DEFAULT_LOG_REL)
        self._primary: Optional[_Sink]
        if sys.platform == "darwin":
            self._primary = _MacVoiceOverSink()
        elif sys.platform.startswith("linux"):
            self._primary = _LinuxSpeakSink()
        else:
            self._primary = None

    def announce(self, text: str) -> bool:
        """Announce ``text``. Returns True on best-effort success."""
        if not self.enabled:
            return True
        if not text:
            return True
        msg = str(text).strip()
        if not msg:
            return True

        with self._lock:
            if self._primary is not None:
                try:
                    if self._primary.speak(msg):
                        return True
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug(
                        "primary sink %s raised: %s",
                        getattr(self._primary, "name", "?"),
                        exc,
                    )
            # Always fall back to FileSink — it never raises.
            return self._file_sink.speak(msg)


__all__ = ["A11yAnnouncer", "FileSink"]

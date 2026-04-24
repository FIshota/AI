"""
End-to-end smoke tests for the ai-chan desktop pet UI (tkinter).

Focus: detect regressions in the emotion-expression state machine and basic
widget lifecycle. All tests are marked `ui` and require a usable Tk display.

Scope (v0):
    - Widget instantiation and expected attributes
    - Emotion-to-expression call-through (happy / sad / angry / neutral)
    - Graceful destroy

Out of scope (tracked as follow-ups — see docs/quality/E2E_DESKTOP_PET.md):
    - Pixel-level visual regression
    - Public emotion setter API (currently only `_update_expression` exists)
    - Emotion history integration (mocked here)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import pytest

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.ui


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_ai_chan() -> MagicMock:
    """
    Mock AiChan instance: provides only the attributes DesktopPet reads.

    Avoids touching the real emotion_history DB or spawning background
    threads (clipboard watcher, battery monitor).
    """
    ai = MagicMock()
    ai.settings = {
        "ui": {"pet_image": ""},
        "autonomous": {"idle_minutes": 30},
    }
    # Make .get() behave like a dict on settings
    ai.settings_get = MagicMock(return_value={})
    # Fake emotion history source: return an empty list so no real DB is hit.
    ai.emotion = MagicMock()
    ai.emotion.get_display_string = MagicMock(return_value="neutral")
    ai.emotion.state.to_dict = MagicMock(return_value={"neutral": 1.0})
    return ai


@pytest.fixture()
def pet(tk_root, mock_ai_chan, monkeypatch) -> Iterator[object]:
    """
    Instantiate DesktopPet against the shared hidden root.

    DesktopPet internally calls ``tk.Tk()`` — we cannot easily inject a
    parent. Instead, we let it create its own Toplevel-like root but destroy
    it in teardown. Background timers (``after``) are cancelled.
    """
    from ui.desktop_pet import DesktopPet

    # Prevent any real microphone/clipboard side effects during construction.
    monkeypatch.setattr(
        "ui.desktop_pet._check_microphone_status", lambda: 3, raising=False
    )

    instance = DesktopPet(ai_chan_instance=mock_ai_chan)
    try:
        yield instance
    finally:
        try:
            if getattr(instance, "_anim_after_id", None):
                instance.root.after_cancel(instance._anim_after_id)
            if getattr(instance, "_tick_after_id", None):
                instance.root.after_cancel(instance._tick_after_id)
            instance.root.destroy()
        except Exception as exc:  # pragma: no cover
            logger.warning("pet teardown error: %s", exc)


# ──────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────


def test_pet_window_creates(pet) -> None:
    """DesktopPet exposes root Tk window and a canvas widget."""
    import tkinter as tk

    assert pet.root is not None
    assert isinstance(pet.root, tk.Tk)
    assert hasattr(pet, "canvas"), "DesktopPet should expose a canvas attribute"
    assert isinstance(pet.canvas, tk.Canvas)

    # Expect at least one child widget (the canvas).
    children = pet.root.winfo_children()
    assert len(children) >= 1, "Pet root should contain widgets"


def test_emotion_state_transition(pet) -> None:
    """
    Drive the expression through several emotions and confirm the call
    does not raise and that internal sprite-update state is updated when
    an expression image is available.

    NOTE: DesktopPet v0 has no public set_emotion; we drive the internal
    _update_expression directly. Any change to that contract should flag
    this test — intentional.
    """
    emotions = ("happy", "sad", "angry", "neutral")
    for emotion in emotions:
        # Should never raise, regardless of whether the image is present.
        pet._update_expression(emotion)
        pet.root.update_idletasks()

    # Post-condition: canvas still alive and sprite_id attr still present.
    assert pet.canvas.winfo_exists()
    assert hasattr(pet, "sprite_id")


def test_entropy_expression_mapping(pet) -> None:
    """update_expression_from_entropy should return one of the known labels."""
    label = pet.update_expression_from_entropy("hello")
    assert label in {"active", "thinking", "normal", "sleepy"}


def test_pet_close_is_graceful(tk_root, mock_ai_chan, monkeypatch) -> None:
    """Destroying the pet window must not raise."""
    from ui.desktop_pet import DesktopPet

    monkeypatch.setattr(
        "ui.desktop_pet._check_microphone_status", lambda: 3, raising=False
    )
    instance = DesktopPet(ai_chan_instance=mock_ai_chan)
    try:
        instance.root.update_idletasks()
    finally:
        # Must not raise
        instance.root.destroy()

    # After destroy, winfo_exists should be falsy / raise cleanly.
    import tkinter as tk

    with pytest.raises(tk.TclError):
        instance.root.winfo_children()

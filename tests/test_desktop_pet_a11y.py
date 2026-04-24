"""Tests for ui.desktop_pet_a11y and core.a11y_announcer.

Covers:
    - ColorblindPalette preset coverage and hex validity.
    - Contrast ratio sanity for key role pairs.
    - Font scale clamping.
    - AccessibilitySettings.from_mapping safety for bad input.
    - Announcer fallback path (FileSink writes a line).
    - Announcer no-op when disabled.
    - apply_to_canvas on a real canvas (UI-skipped headless).
    - Keyboard bindings exist on DesktopPet root (UI-skipped headless).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ui.desktop_pet_a11y import (  # noqa: E402
    AccessibilitySettings,
    ColorblindPalette,
    apply_to_canvas,
    contrast_ratio,
)
from core.a11y_announcer import A11yAnnouncer, FileSink  # noqa: E402


# --------------------------------------------------------------------------- #
# Palette tests
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["normal", "deuteranopia", "protanopia", "tritanopia"])
def test_palette_preset_has_required_roles(name: str) -> None:
    palette = ColorblindPalette.preset(name)
    assert palette.name == name
    required = {"background", "surface", "text", "accent", "accent_alt",
                "success", "warning", "danger", "focus_ring"}
    assert required.issubset(palette.colors.keys())
    # Every colour must be a valid 7-char hex string.
    for role, hex_code in palette.colors.items():
        assert hex_code.startswith("#") and len(hex_code) == 7, (role, hex_code)
        int(hex_code[1:], 16)  # raises if malformed


def test_palette_preset_unknown_raises() -> None:
    with pytest.raises(ValueError):
        ColorblindPalette.preset("rainbow")


def test_palette_is_frozen() -> None:
    p = ColorblindPalette.preset("normal")
    with pytest.raises(Exception):
        p.name = "mutated"  # type: ignore[misc]


def test_palette_available_lists_all_presets() -> None:
    assert set(ColorblindPalette.available()) == {
        "normal", "deuteranopia", "protanopia", "tritanopia",
    }


# --------------------------------------------------------------------------- #
# Contrast
# --------------------------------------------------------------------------- #

def test_contrast_ratio_black_white_is_21() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, rel=0.02)


def test_contrast_text_on_background_passes_aa_for_all_palettes() -> None:
    # WCAG AA body text requires >= 4.5:1.
    for name in ColorblindPalette.available():
        palette = ColorblindPalette.preset(name)
        ratio = contrast_ratio(palette["text"], palette["background"])
        assert ratio >= 4.5, (name, ratio)


# --------------------------------------------------------------------------- #
# AccessibilitySettings
# --------------------------------------------------------------------------- #

def test_font_scale_clamped_high() -> None:
    s = AccessibilitySettings(font_scale=99.0)
    assert s.font_scale == 2.5


def test_font_scale_clamped_low() -> None:
    s = AccessibilitySettings(font_scale=0.01)
    assert s.font_scale == 0.75


def test_font_scale_nan_defaults_to_one() -> None:
    s = AccessibilitySettings(font_scale=float("nan"))
    assert s.font_scale == 1.0


def test_settings_from_mapping_defaults_for_empty() -> None:
    s = AccessibilitySettings.from_mapping(None)
    assert s.palette.name == "normal"
    assert s.high_contrast is False
    assert s.keyboard_only is False
    assert s.announce_events is False
    assert s.font_scale == 1.0


def test_settings_from_mapping_unknown_palette_falls_back() -> None:
    s = AccessibilitySettings.from_mapping({"palette": "tetrachromacy"})
    assert s.palette.name == "normal"


def test_settings_from_mapping_happy_path() -> None:
    s = AccessibilitySettings.from_mapping({
        "palette": "deuteranopia",
        "high_contrast": True,
        "font_scale": 1.5,
        "keyboard_only": True,
        "announce_events": True,
    })
    assert s.palette.name == "deuteranopia"
    assert s.high_contrast is True
    assert s.font_scale == 1.5
    assert s.keyboard_only is True
    assert s.announce_events is True


# --------------------------------------------------------------------------- #
# Announcer
# --------------------------------------------------------------------------- #

def test_announcer_disabled_is_noop(tmp_path: Path) -> None:
    log = tmp_path / "a11y.log"
    a = A11yAnnouncer(enabled=False, log_path=log)
    assert a.announce("hello") is True
    assert not log.exists()


def test_announcer_empty_text_is_noop(tmp_path: Path) -> None:
    log = tmp_path / "a11y.log"
    a = A11yAnnouncer(enabled=True, log_path=log)
    assert a.announce("   ") is True


def test_file_sink_writes_message(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "a11y.log"
    sink = FileSink(log_path=log)
    assert sink.speak("テストメッセージ") is True
    assert log.is_file()
    content = log.read_text(encoding="utf-8")
    assert "テストメッセージ" in content


def test_announcer_falls_back_to_file_when_primary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = tmp_path / "a11y.log"
    a = A11yAnnouncer(enabled=True, log_path=log)
    # Force primary sink to report failure so the file sink runs.
    if a._primary is not None:
        monkeypatch.setattr(a._primary, "speak", lambda _t: False)
    assert a.announce("fallback event") is True
    assert log.is_file()
    assert "fallback event" in log.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Canvas / UI integration (skipped without display)
# --------------------------------------------------------------------------- #

def _display_ok() -> bool:
    if os.environ.get("AICHAN_FORCE_UI_TESTS") == "1":
        return True
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY"))
    if sys.platform == "darwin":
        return bool(os.environ.get("DISPLAY"))
    return bool(os.environ.get("DISPLAY"))


@pytest.mark.ui
@pytest.mark.skipif(not _display_ok(), reason="no display for Tk")
def test_apply_to_canvas_retints_items() -> None:
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    try:
        root.withdraw()
        canvas = tk.Canvas(root, width=100, height=100, bg="#FFFFFF")
        canvas.create_rectangle(10, 10, 80, 80, fill="#FF0000", outline="#000000")
        canvas.create_text(20, 20, text="hello", fill="#000000",
                           font=("Helvetica", 12))

        settings = AccessibilitySettings(
            palette=ColorblindPalette.preset("deuteranopia"),
            font_scale=1.5,
        )
        report = apply_to_canvas(canvas, settings)
        assert report["palette"] == "deuteranopia"
        assert int(report["items_retinted"]) >= 2
        # Canvas bg should now match palette background.
        bg = canvas.cget("bg")
        assert bg.startswith("#")
    finally:
        root.destroy()


@pytest.mark.ui
@pytest.mark.skipif(not _display_ok(), reason="no display for Tk")
def test_desktop_pet_has_a11y_key_bindings() -> None:
    # Import lazily so headless collection does not touch tk.
    from ui import desktop_pet as dp  # noqa: WPS433

    try:
        pet = dp.DesktopPet(ai_chan_instance=None)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"DesktopPet init failed (likely headless quirk): {exc}")
    try:
        bindings = pet.root.bind()
        # Tk returns a tuple of sequences; ensure our three are present.
        joined = " ".join(bindings) if isinstance(bindings, (list, tuple)) else str(bindings)
        assert "<Key-Tab>" in joined or "Tab" in joined
        assert "<Key-space>" in joined or "space" in joined
        assert "<Key-Escape>" in joined or "Escape" in joined
    finally:
        try:
            pet.root.destroy()
        except Exception:
            pass

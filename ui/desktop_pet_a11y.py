"""
Accessibility (a11y) helpers for the Desktop Pet.

This module is additive: it does not modify ``ui/desktop_pet.py`` behaviour
unless the caller explicitly opts in. It provides:

- :class:`ColorblindPalette` — frozen dataclass holding a small set of
  perceptually safe colours, with presets for normal vision and for the
  three most common forms of colour vision deficiency (deuteranopia,
  protanopia, tritanopia).
- :class:`AccessibilitySettings` — user-level configuration container.
- :func:`apply_to_canvas` — small helper that retints a ``tk.Canvas``
  and scales its fonts according to a settings instance.
- :func:`contrast_ratio` — WCAG-style luminance contrast ratio.

Design notes
------------
The palettes are specified in HSV first (so hue shifts are intentional),
then converted to hex for tk. Confusion lines for each CVD type are
avoided: the deuteranopia / protanopia palettes replace the red/green
accent pair with blue/orange, and the tritanopia palette replaces the
blue/yellow pair with pink/teal.

This module is Python 3.9 compatible and depends only on the standard
library.
"""
from __future__ import annotations

import colorsys
import logging
from dataclasses import dataclass, field, replace
from typing import Dict, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Colour primitives
# --------------------------------------------------------------------------- #

def _hsv_to_hex(h: float, s: float, v: float) -> str:
    """Convert HSV (each 0..1) to a ``#RRGGBB`` hex string."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


def _hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    """Convert ``#RRGGBB`` or ``#RGB`` to an (r, g, b) int triple."""
    s = hex_code.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"invalid hex colour: {hex_code!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _relative_luminance(hex_code: str) -> float:
    """WCAG relative luminance for a sRGB hex colour."""
    r, g, b = (c / 255.0 for c in _hex_to_rgb(hex_code))

    def _ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """Return the WCAG contrast ratio (>= 1.0) between two hex colours."""
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# --------------------------------------------------------------------------- #
# Palettes
# --------------------------------------------------------------------------- #

# Semantic roles the pet UI uses. Kept intentionally small so palette switches
# remain auditable. All values are HSV triples in 0..1.
_NORMAL_HSV: Dict[str, Tuple[float, float, float]] = {
    "background":   (0.00, 0.00, 0.98),
    "surface":      (0.00, 0.00, 0.94),
    "text":         (0.00, 0.00, 0.12),
    "text_muted":   (0.00, 0.00, 0.38),
    "accent":       (0.95, 0.55, 0.95),  # ai-chan pink
    "accent_alt":   (0.58, 0.70, 0.85),  # blue
    "success":      (0.33, 0.70, 0.70),  # green
    "warning":      (0.12, 0.90, 0.95),  # amber
    "danger":       (0.00, 0.75, 0.85),  # red
    "focus_ring":   (0.58, 0.85, 0.95),
}

# For deuteranopia/protanopia (red-green CVD) replace the red/green axis with
# a blue/orange axis that does not lie on the confusion line.
_DEUTAN_HSV: Dict[str, Tuple[float, float, float]] = {
    **_NORMAL_HSV,
    "accent":     (0.08, 0.85, 0.95),   # warm orange
    "accent_alt": (0.60, 0.75, 0.85),   # deep blue
    "success":    (0.58, 0.70, 0.80),   # blue-teal, not green
    "warning":    (0.12, 0.95, 1.00),   # saturated amber
    "danger":     (0.04, 0.90, 0.75),   # brown-red, distinct from orange
    "focus_ring": (0.60, 0.95, 1.00),
}
_PROTAN_HSV: Dict[str, Tuple[float, float, float]] = {
    **_DEUTAN_HSV,
    # Protans lose more long-wavelength sensitivity; push danger darker still.
    "danger": (0.04, 0.95, 0.60),
}

# For tritanopia (blue-yellow CVD) replace blue/yellow with pink/teal.
_TRITAN_HSV: Dict[str, Tuple[float, float, float]] = {
    **_NORMAL_HSV,
    "accent":     (0.92, 0.70, 0.90),   # magenta-pink
    "accent_alt": (0.48, 0.65, 0.75),   # teal
    "success":    (0.50, 0.70, 0.70),
    "warning":    (0.02, 0.75, 0.90),   # red-orange, not amber
    "danger":     (0.95, 0.85, 0.70),
    "focus_ring": (0.92, 0.85, 0.95),
}


_PALETTE_PRESETS: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "normal":        _NORMAL_HSV,
    "deuteranopia":  _DEUTAN_HSV,
    "protanopia":    _PROTAN_HSV,
    "tritanopia":    _TRITAN_HSV,
}


@dataclass(frozen=True)
class ColorblindPalette:
    """A named immutable palette mapping semantic roles to hex colours."""

    name: str
    colors: Mapping[str, str] = field(default_factory=dict)

    def __getitem__(self, role: str) -> str:
        return self.colors[role]

    def get(self, role: str, default: Optional[str] = None) -> Optional[str]:
        return self.colors.get(role, default)

    def as_dict(self) -> Dict[str, str]:
        return dict(self.colors)

    @classmethod
    def preset(cls, name: str) -> "ColorblindPalette":
        """Return one of the built-in palette presets."""
        key = (name or "normal").strip().lower()
        if key not in _PALETTE_PRESETS:
            raise ValueError(
                f"unknown palette {name!r}; "
                f"expected one of {sorted(_PALETTE_PRESETS)}"
            )
        hsv = _PALETTE_PRESETS[key]
        colors = {role: _hsv_to_hex(*triple) for role, triple in hsv.items()}
        return cls(name=key, colors=colors)

    @classmethod
    def available(cls) -> Tuple[str, ...]:
        return tuple(sorted(_PALETTE_PRESETS))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

_FONT_SCALE_MIN = 0.75
_FONT_SCALE_MAX = 2.5


def _clamp_font_scale(value: float) -> float:
    """Clamp a font scale into a safe range."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    if v != v:  # NaN
        return 1.0
    return max(_FONT_SCALE_MIN, min(_FONT_SCALE_MAX, v))


@dataclass(frozen=True)
class AccessibilitySettings:
    """User-facing accessibility settings.

    All fields default to a "feature is off" state so the desktop pet's
    existing behaviour is completely preserved when a11y is not configured.
    """

    palette: ColorblindPalette = field(
        default_factory=lambda: ColorblindPalette.preset("normal")
    )
    high_contrast: bool = False
    font_scale: float = 1.0
    keyboard_only: bool = False
    announce_events: bool = False

    def __post_init__(self) -> None:
        # dataclass is frozen; use object.__setattr__ for normalisation.
        object.__setattr__(self, "font_scale", _clamp_font_scale(self.font_scale))

    # -- constructors -------------------------------------------------------
    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, object]]) -> "AccessibilitySettings":
        """Build from a ``settings.json`` ``accessibility`` sub-dict.

        Unknown fields are ignored. Missing fields fall back to defaults,
        which makes it safe to load from legacy config files.
        """
        if not data:
            return cls()
        palette_name = str(data.get("palette", "normal"))
        try:
            palette = ColorblindPalette.preset(palette_name)
        except ValueError:
            logger.warning("unknown palette %r, falling back to normal", palette_name)
            palette = ColorblindPalette.preset("normal")
        return cls(
            palette=palette,
            high_contrast=bool(data.get("high_contrast", False)),
            font_scale=_clamp_font_scale(data.get("font_scale", 1.0)),
            keyboard_only=bool(data.get("keyboard_only", False)),
            announce_events=bool(data.get("announce_events", False)),
        )

    def with_palette(self, name: str) -> "AccessibilitySettings":
        return replace(self, palette=ColorblindPalette.preset(name))


# --------------------------------------------------------------------------- #
# Canvas application helper
# --------------------------------------------------------------------------- #

def _scaled_font(spec, scale: float):
    """Return a font spec with its size scaled. Accepts (family, size, *style)."""
    if not isinstance(spec, (tuple, list)) or len(spec) < 2:
        return spec
    family = spec[0]
    try:
        size = int(round(float(spec[1]) * scale))
    except (TypeError, ValueError):
        return spec
    size = max(8, size)
    return (family, size, *tuple(spec[2:]))


def apply_to_canvas(canvas, settings: AccessibilitySettings) -> Dict[str, object]:
    """Retint a ``tk.Canvas`` and scale its fonts to match ``settings``.

    Returns a small report dict describing what changed. The function is
    defensive: any Tk errors are caught and logged, because accessibility
    should never crash the pet UI.
    """
    palette = settings.palette
    bg_role = "background" if not settings.high_contrast else "text"
    fg_role = "text" if not settings.high_contrast else "background"

    bg = palette[bg_role]
    fg = palette[fg_role]

    report: Dict[str, object] = {
        "palette": palette.name,
        "bg": bg,
        "fg": fg,
        "font_scale": settings.font_scale,
        "items_retinted": 0,
        "fonts_rescaled": 0,
    }

    try:
        canvas.configure(bg=bg)
    except Exception as exc:  # pragma: no cover - Tk edge case
        logger.debug("canvas.configure(bg=...) failed: %s", exc)

    try:
        item_ids = canvas.find_all()
    except Exception as exc:  # pragma: no cover
        logger.debug("canvas.find_all() failed: %s", exc)
        return report

    for item_id in item_ids:
        try:
            item_type = canvas.type(item_id)
        except Exception:  # pragma: no cover
            continue

        try:
            if item_type in {"rectangle", "oval", "polygon", "arc"}:
                canvas.itemconfigure(item_id, outline=fg)
                # Only retint fills that are not already transparent/image-based.
                current_fill = canvas.itemcget(item_id, "fill")
                if current_fill:
                    canvas.itemconfigure(item_id, fill=palette.get("surface", bg))
                report["items_retinted"] = int(report["items_retinted"]) + 1
            elif item_type == "text":
                canvas.itemconfigure(item_id, fill=fg)
                font_spec = canvas.itemcget(item_id, "font")
                if font_spec and settings.font_scale != 1.0:
                    # Tk font specs come back as a string; split and rescale.
                    parts = font_spec.split()
                    if len(parts) >= 2:
                        new_font = _scaled_font(tuple(parts), settings.font_scale)
                        canvas.itemconfigure(item_id, font=new_font)
                        report["fonts_rescaled"] = int(report["fonts_rescaled"]) + 1
                report["items_retinted"] = int(report["items_retinted"]) + 1
            elif item_type == "line":
                canvas.itemconfigure(item_id, fill=fg)
                report["items_retinted"] = int(report["items_retinted"]) + 1
        except Exception as exc:  # pragma: no cover
            logger.debug("itemconfigure failed on %s (%s): %s", item_id, item_type, exc)

    return report


__all__ = [
    "AccessibilitySettings",
    "ColorblindPalette",
    "apply_to_canvas",
    "contrast_ratio",
]

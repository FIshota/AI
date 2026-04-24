# Desktop Pet E2E Smoke Tests

## Why

The desktop pet is ai-chan's most visible surface. Its **emotion-expression
state machine** (sprite swap driven by emotion history + entropy) is easy to
break silently — a regression shows up as a frozen face, wrong mood, or a
crash on close, none of which unit tests catch.

These tests are a lightweight safety net for that state machine and the
widget lifecycle around it. They are intentionally cheap and headless-safe.

## How

- Framework: `pytest` + stdlib `tkinter` (no Qt, no pytest-qt).
- Technique: **widget introspection**. We instantiate `DesktopPet`, call
  its expression-update methods, and assert on attributes and widget
  liveness. No screenshot comparison in v0.
- All real I/O is mocked:
  - `AiChan` instance is a `MagicMock`
  - `_check_microphone_status` is patched to "granted"
  - No real `emotion_history` DB reads
- A single hidden `Tk()` root is created per module via the `tk_root`
  fixture in `tests/conftest.py`.

## How to Run

```bash
cd ai-chan
PYTHONPATH=. pytest tests/test_desktop_pet_e2e.py -v -m ui
```

Force-run on a Mac with a GUI session:

```bash
AICHAN_FORCE_UI_TESTS=1 pytest tests/test_desktop_pet_e2e.py -v -m ui
```

Linux headless CI (via Xvfb):

```bash
xvfb-run -a pytest tests/test_desktop_pet_e2e.py -v -m ui
```

## Known Limitations (v0)

1. **No visual regression.** We do not diff pixels. v1 will use
   `ttk.Widget.grab()` (or platform equivalent) plus Pillow for per-emotion
   pixel-diff snapshots at stable breakpoints.
2. **No public emotion setter.** `DesktopPet` currently exposes only
   `_update_expression(emotion)` (private) and `update_expression_from_entropy(text)`
   (returns a label but does not mutate internal state). Tests reach into
   the private method; any refactor to that contract must update these
   tests intentionally.
3. **No internal `current_emotion` attribute.** We cannot assert "state
   changed" at a semantic level — only that the sprite update call didn't
   raise. See follow-up TODOs below.
4. **Single-module fixture scope.** The hidden `Tk()` root is module-scoped.
   Cross-module concurrent UI tests are not supported.

## CI Strategy

| Platform | Strategy |
|----------|----------|
| Linux (GitHub Actions) | Wrap pytest in `xvfb-run -a` |
| macOS CI | Not currently set up — tests skip by default |
| Developer macOS (local, GUI session) | Set `AICHAN_FORCE_UI_TESTS=1` |
| Headless dev container | Skip (design intent) |

The `tk_root` fixture skips the whole module when no display is available,
so headless runs stay green.

## Follow-up TODOs (UI API gaps)

The following public API would unlock deeper tests:

- [ ] `DesktopPet.set_emotion(emotion: str) -> None` — public setter that
      also updates a `self.current_emotion` attribute.
- [ ] `DesktopPet.current_emotion` — read-only public attribute reflecting
      the most recent emotion applied.
- [ ] `DesktopPet.apply_emotion_history(history: Sequence[EmotionEvent])` —
      drive the sprite from a supplied history instead of pulling from DB.
- [ ] v1: per-emotion golden-image fixtures under
      `tests/support/desktop_pet_snapshots/`.

## Related

- Source: `ui/desktop_pet.py` — class `DesktopPet`
- Fixtures: `tests/conftest.py` — `tk_root`
- Tests: `tests/test_desktop_pet_e2e.py`

# CODEMAP: ui/

> Auto-generated 2026-04-24 — Cat 5 codemap (C5)

Total modules: **12**

Tkinter UI surfaces: desktop pet, emotion drift window, search, accessibility.

| File | Summary | Public API (excerpt) | Lines |
|------|---------|----------------------|-------|
| `__init__.py` | — | — | 1 |
| `chat_widgets.py` | チャットUI用カスタムウィジェット | detect_dark_mode(), get_theme_colors(), class TypewriterMixin, class EmotionBar, class TypingIndicator | 460 |
| `cli.py` | CLIインターフェース | print_header(), print_ai_response(), print_ai_stream_header(), chat_with_stream(), print_user_prompt() | 308 |
| `desktop_pet.py` | デスクトップペット UI | find_character_image(), class SpeechBubble, class ChatWindow, class DesktopPet, run_desktop_pet() | 2099 |
| `desktop_pet_a11y.py` | Accessibility (a11y) helpers for the Desktop Pet. | contrast_ratio(), class ColorblindPalette, class AccessibilitySettings, apply_to_canvas() | 323 |
| `emotion_drift_window.py` | 感情ドリフト「心の健康診断」ウィンドウ。 | render_text_summary(), class EmotionDriftWindow, open_from_history() | 158 |
| `export_window.py` | 会話ログエクスポートウィンドウ | class ExportWindow | 217 |
| `graph_window.py` | 成長記録ウィンドウ | class GraphWindow | 362 |
| `minutes_window.py` | 議事録アプリ ウィンドウ | class MinutesWindow, launch_standalone() | 1377 |
| `search_window.py` | 会話履歴検索ウィンドウ (Sprint 5.7 UX). | class ParsedKeywordInput, parse_keyword_input(), class SearchWindow | 259 |
| `settings_window.py` | 設定GUIウィンドウ | class SettingsWindow | 1121 |
| `setup_wizard.py` | 初回セットアップウィザード | is_first_run(), class SetupWizard | 303 |

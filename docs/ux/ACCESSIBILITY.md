# Accessibility (a11y) ガイド

アイちゃん Desktop Pet の a11y 機能は「既定 OFF、必要な家族だけオンにする」方針で設計されています。現行 UI に破壊的変更は加えず、以下の 3 本柱で後方互換に追加されます。

- 色覚多様性対応 (赤緑・青黄)
- スクリーンリーダー通知 (macOS VoiceOver / Linux speak / fallback)
- キーボード操作 (Tab / Space / Esc)

## モジュール構成

| ファイル | 役割 |
|---|---|
| `ui/desktop_pet_a11y.py` | `ColorblindPalette`, `AccessibilitySettings`, `apply_to_canvas` |
| `core/a11y_announcer.py` | `A11yAnnouncer` (VoiceOver / speak / FileSink) |
| `ui/desktop_pet.py` | 最小改変: 設定読込 + キーバインド (Tab / Space / Esc) |
| `config/settings.json` | `accessibility` セクション (既定値はすべて OFF) |

## 設定例

`config/settings.json`:

```json
{
  "accessibility": {
    "palette": "deuteranopia",
    "high_contrast": false,
    "font_scale": 1.25,
    "keyboard_only": true,
    "announce_events": true
  }
}
```

### palette

| 値 | 対象 | 主な差し替え軸 |
|---|---|---|
| `normal` | 通常視覚 | ai-chan pink 基準 |
| `deuteranopia` | 緑系色弱 (最多) | 赤緑 → 青/オレンジ |
| `protanopia` | 赤系色弱 | 赤緑 → 青/オレンジ、danger をさらに暗く |
| `tritanopia` | 青黄色弱 (稀) | 青黄 → ピンク/ティール |

すべての `text` / `background` 組み合わせは WCAG AA (4.5:1) を満たすよう調整されています。`tests/test_desktop_pet_a11y.py::test_contrast_text_on_background_passes_aa_for_all_palettes` で継続検証。

### font_scale

0.75〜2.5 の範囲にクランプされます。不正値 (NaN / 文字列) は `1.0` に戻ります。

### announce_events

有効時、起動・フォーカス移動・チャット起動・非表示の各イベントで以下を試行します。

1. macOS: `osascript` で VoiceOver に `output` → 失敗時は `say`
2. Linux: `speak` / `espeak-ng` / `espeak`
3. いずれも不在: `logs/a11y_announcements.log` に追記 + stdout echo

`A11yAnnouncer` は例外を飲み込み、UI を絶対に落としません。

## キーボードショートカット

| Key | 動作 |
|---|---|
| `Tab` | ペット ↔ チャットウィンドウのフォーカス巡回 |
| `Space` | チャットを開く |
| `Esc` | ペットを非表示 |

既定動作はマウス操作と並存します。`keyboard_only: true` はこのガイドでは「マウスホバーで情報が出ない / キーボード操作でも同じ UI に到達できる」ことを保証する将来フラグとして扱います (現状は将来拡張の宣言)。

## 将来 TODO

- 大型キーアイコンのオンスクリーン表示 (矢印 / Enter / Esc のチート)
- 発話サブタイトル表示 (音量ゼロでも字幕で理解できる)
- 高コントラストモードのキャンバス以外 (チャットウィンドウ) への伝播
- フォーカスリングをキャンバス内スプライトにも明示 (`focus_ring` 色を利用)
- 設定 UI (設定ウィンドウから palette 切替、現在は settings.json 直編集)
- スクリーンリーダー非対応 OS 向けの stderr 通知経路

## テスト

```bash
pytest tests/test_desktop_pet_a11y.py -q
```

- UI テストは `DISPLAY` が無い、または `AICHAN_FORCE_UI_TESTS=1` が無い場合 skip されます
- パレット / コントラスト / クランプ / announcer fallback はヘッドレスでも通ります

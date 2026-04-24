# Screenshot Sensitive Screen Protection (5.10)

ai-chan がスクリーンショットを介して誤って機密情報を取り込むのを防ぐための
事前分類器 & ブラー / REDACT / BLOCK 層のドキュメント。

## 1. 脅威モデル

| # | シナリオ | 影響 |
|---|----------|------|
| T1 | パスワードマネージャ (1Password / Bitwarden / Keychain) が開いた状態でスクリーンショットが撮られ、AI 文脈に取り込まれる | 資格情報の永続漏洩 (最悪) |
| T2 | 銀行 / 証券 Web サイトが前面にあり、残高・口座番号・取引履歴が OCR される | 経済的被害、なりすまし |
| T3 | 医療ポータル / お薬手帳 / 電子カルテ | 最機微情報の漏洩 |
| T4 | メール本文 / LINE / Signal / WhatsApp の会話 | プライバシー、第三者のプライバシー侵害 |
| T5 | 確定申告 / e-Tax 画面に個人番号 / 還付情報 | 個人番号漏洩 |

全て「ai-chan の後段処理 (長期メモリ / クラウド転送 / 同期) に渡る前」に防ぐ必要がある。

## 2. 仕組み

1. `core/screenshot_reader.py` の `capture_screen()` が macOS `screencapture` で PNG を取得。
2. 直後に `_apply_sensitive_guard()` がウィンドウタイトル / app bundle id を
   `SensitiveClassifier` に投入し、マッチしたら `apply_blur()` で
   - `BLOCK`: ファイルを空 bytes に上書き (ログ出力)
   - `BLUR`: Pillow BoxBlur (Pillow 無しなら単色フォールバック)
   - `REDACT`: 全面黒塗り
3. 元画像は中間ファイルに**残さず**、常に上書きのみ。

既定は有効、opt-out できない (安全側)。

## 3. パターン追加ガイド

家庭ごとに保護対象は異なる (特定の地方銀行、独自の社内ポータルなど)。
追加パターンは次のいずれかで投入する。

### 3.1 コードで追加

```python
from core.screenshot_sensitive import (
    DEFAULT_PATTERNS, SensitivePattern, SensitiveAction, SensitiveClassifier,
)

extra = (
    SensitivePattern(
        name="MyLocalBank",
        window_title_regex=r"MyLocal\s*Bank|マイローカル銀行",
        app_bundle_ids=("jp.example.mybank",),
        action=SensitiveAction.BLOCK,
    ),
)
classifier = SensitiveClassifier(DEFAULT_PATTERNS + extra)
```

### 3.2 YAML で追加 (推奨)

`config/screenshot_sensitive_patterns.yaml.example` をコピーして
`config/screenshot_sensitive_patterns.yaml` を作成する。

- `window_title_regex` は Python の `re` 構文 (case-insensitive で評価)
- `app_bundle_ids` は macOS の LSBundleIdentifier の**完全一致**
- `action` は `BLOCK | BLUR | REDACT`

## 4. ブラー強度の調整指針

`apply_blur(..., strength=N)` の `N` は Pillow BoxBlur の半径。

| 画面サイズ | 推奨 strength |
|------------|---------------|
| 1280×800 以下 | 15-25 |
| 1920×1080 | 25-40 |
| 4K (3840×2160) | 40-80 |

数字が大きいほど OCR 耐性は上がるが、計算コストも線形に増える。
**機密度が高い場合は BLUR ではなく REDACT or BLOCK を選ぶ。**

## 5. 手動テスト

1. 1Password を開き、前面に出した状態で:
   ```python
   from core.screenshot_reader import capture_screen
   p = capture_screen()
   print(p.stat().st_size)  # 0 なら BLOCK 動作
   ```
2. ログに `[Screenshot] BLOCK 機密画面検出: 1Password` が出れば成功。
3. 同様に Mail.app / e-Tax で BLUR / REDACT を確認。

## 6. 既知の限界

- **ウィンドウメタデータが取れない全画面ゲーム内のブラウザ**等、タイトルが
  見えない場合は分類できない。
- OCR 後のテキスト解析による二次検出は未実装 (今後の課題)。
- 正規表現ベースのため、パターンを回避する命名のアプリ (例: タイトルを空にする拡張) には対応できない。
- macOS 以外では screencapture が使えないため本機能は起動しない。
- 機密パターンはユーザー固有の価値観に依存する。定期的な見直しを推奨。

## 7. プライバシー

- 外部ネット接続なし: 全照合はローカル `re` モジュールのみ。
- ディスク残留なし: 元画像は即 in-place 上書きされる。
- ログは名前 (例: "1Password") のみ出力、内容やスクショ本体は記録しない。

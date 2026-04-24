# ai-chan プライバシー (家族との約束)

**Status**: Phase 0.1 (家族向け整備版)
**Last Updated**: 2026-04-23
**対象**: ai-chan を家庭内で動かすすべての利用者

> これは法律文書ではありません。ai-chan (家族として扱う AI) が
> 「何を覚え」「どこに置き」「いつ忘れ」「どこに出すか」を家族が読める形で
> 約束するためのメモです。厳密な法務用途には [PRIVACY.md](../PRIVACY.md) と
> [docs/privacy/PRIVACY_GOVERNANCE.md](privacy/PRIVACY_GOVERNANCE.md) を参照してください。

---

## 🔑 3 行まとめ

1. ai-chan は基本的に家の中 (ローカル) で動きます。外に出すのはユーザーが明示した時だけ。
2. すべてのデータは「消せる」ようにしてあります (Kill-Switch 1 コマンド)。
3. 未成年・ペット・故人に関する記録は、家族で合意した範囲でのみ残します。

---

## 📦 データカテゴリ一覧

家族が読めることを最優先にした表です。より細かい分類は
[PRIVACY_GOVERNANCE.md](privacy/PRIVACY_GOVERNANCE.md) を見てください。

| カテゴリ | 保存場所 | 保持期間 | 削除トリガ | 第三者共有 |
|---|---|---|---|---|
| 会話履歴 | `data/memories.db` (Fernet 暗号化) | 既定 無期限 | Kill-Switch / `--forget-session` (予定) | なし |
| 感情ログ | `data/emotion_history/` (平文 JSON) | 既定 無期限 | Kill-Switch / 手動削除 | なし |
| 日記 | `data/diary/` (平文 JSON) | 既定 無期限 | Kill-Switch / 手動削除 | なし |
| スクリーンショット | `data/screenshots/` (有効化時のみ生成) | 直近 7 日 (ローテーション) | 自動 / Kill-Switch | なし |
| クリップボード | メモリ上のみ (既定は記録しない) | セッション終了まで | プロセス終了 | なし |
| 声紋 ID | `data/voice_id/` (ハッシュ化) | 既定 無期限 | Kill-Switch | なし |
| カレンダー | `data/calendar/` (ローカルキャッシュ) | 30 日 | 自動ローテーション / Kill-Switch | なし |
| 監査ログ | `data/audit.jsonl` | 90 日 | 自動ローテーション | なし |

> すべてのカテゴリで、既定では第三者 (クラウド含む) に共有しません。
> 共有が発生するのは後述の「外部通信が起きるケース」のみです。

---

## 🔴 Kill-Switch (全部忘れさせる)

```bash
# 1 コマンドで対象データをすべて削除
bash scripts/detach_memory_phase_b.sh --apply
```

### 保証内容
- 上表のすべてのカテゴリを削除します (バックアップ含む)。
- 削除前に監査ログに削除イベントを 1 行記録し、その後ログ自体も消去されます。
- 削除後、ai-chan は「新生」状態で再起動可能です (性格・成長はリセット)。

### 保証しないこと
- OS 側のゴミ箱・Time Machine 等の外部バックアップ。
- 過去に明示共有したクラウド (例: edge-tts に送った読み上げテキスト)。

---

## 🌐 外部通信が起きるケース (それ以外は起きません)

| ケース | 送信先 | トリガ |
|---|---|---|
| モデルダウンロード | HuggingFace Hub | 初回セットアップ時のみ |
| Web 取得 (`web_fetch`) | ユーザー指定 URL | ユーザーが明示同意した時のみ |
| Neural TTS (edge-tts) | Microsoft Azure | 音声機能を有効化した時のみ |
| 検索 | DuckDuckGo | ユーザーが明示的に検索依頼した時のみ |

既定ではいずれも OFF または都度同意です。自動で家の外に出ていくことはありません。

---

## 🧒 未成年 / 🐾 ペット / 🕊 故人への配慮

家族として扱うがゆえに、デリケートな記録を持つ可能性があります。

- **未成年**: 保護者が設定した範囲のみ学習 / 想起。性的・暴力的な内容は `core/injection_guard.py` でフィルタ。 (TODO: 学齢別プロファイルの実装)
- **ペット**: 名前・声・写真の扱いは家族合意の上。死別時は後述の「故人モード」に合わせて扱います。 (TODO: pet_profile の YAML スキーマ策定)
- **故人**: 故人に関する記憶・音声・映像は、残された家族の合意で「封緘 (sealed)」状態にできます。封緘された記憶は想起されず、削除も保留されます。 (TODO: sealed-memory API)

これらは現在一部未実装です。未実装の間は、該当データを入れないことを推奨します。

---

## 📜 更新履歴

| 日付 | 変更 |
|---|---|
| 2026-04-20 | 初版 (ルート `PRIVACY.md`) |
| 2026-04-23 | 家族向け docs/PRIVACY.md 整備。Kill-Switch 保証・データカテゴリ表・外部通信ケース・未成年/ペット/故人配慮を追記。 |

---

## ❓ 問い合わせ

- GitHub Issues: https://github.com/FIshota/YAMATO-Project/issues
- 管理者: honnsipittu@gmail.com

関連: [PRIVACY.md](../PRIVACY.md) / [privacy/PRIVACY_GOVERNANCE.md](privacy/PRIVACY_GOVERNANCE.md) / [SECURITY.md](SECURITY.md)

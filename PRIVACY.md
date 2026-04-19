# ai-chan Privacy Policy

**Status**: Phase 0 (Baseline)
**Last Updated**: 2026-04-20

ai-chan は "家族として振る舞う AI パートナー" を目指すアプリケーションであり、
通常の AI アシスタントと比較して **非常に広範な個人データ** にアクセスします。
本書はユーザーが知っておくべきデータの扱いを網羅的に開示するものです。

## 🔑 Executive Summary (3 行)

1. ai-chan は **完全ローカル** で動作し、データは既定でインターネットに送信されません。
2. 暗号化は **Fernet (AES-128-CBC + HMAC-SHA256)**、鍵は `data/.key` にローカル保存。
3. ユーザーはいつでも `scripts/detach_memory_phase_b.sh --apply` で全記憶を消去できます。

---

## 📦 収集・保存されるデータ

### A. 会話データ
| 項目 | 保存先 | 暗号化 | 保持期間 |
|---|---|---|---|
| 会話履歴 (テキスト) | `data/memories.db` (SQLite) | Fernet | 既定 無期限 |
| 感情ログ | `data/emotion_history/` | 平文 JSON | 既定 無期限 |
| 日記エントリ | `data/diary/` | 平文 JSON | 既定 無期限 |
| 記念日 | `data/anniversary/` | 平文 JSON | 既定 無期限 |
| 記憶ベクトル | `data/memory.db` + FAISS index | 平文 | 既定 無期限 |

### B. 環境センシング (オプション機能、**既定で OFF**)
| 機能 | 読み取るもの | 既定 | 設定キー |
|---|---|---|---|
| Clipboard Watcher | OS クリップボード内容 | OFF | `settings.json > clipboard_watcher.enabled` |
| Screenshot Reader | 画面キャプチャ + OCR | OFF | `settings.json > screenshot_reader.enabled` |
| Voice ID | マイク音声の声紋 | OFF | `settings.json > voice_id.enabled` |
| Wake Word | 常時マイク音声解析 | OFF | `settings.json > voice.wake_word.enabled` |

これらは **明示的に有効化しない限り起動しません**。有効化時は起動時に警告が表示されます。

### C. セキュリティログ
| 項目 | 保存先 | 内容 |
|---|---|---|
| 監査ログ | `data/audit.jsonl` | 暗号化操作・権限変更の履歴 |
| プロセス baseline | `data/.process_baseline.json` | 起動時に期待されるプロセス一覧 |
| ネットワーク状態 | `data/.network_state.json` | 外部接続監視のスナップショット |

### D. 性格・学習
| 項目 | 保存先 | 内容 |
|---|---|---|
| 基本性格 | `personality/core.yaml` | 初期値 + ランタイム学習による微調整 |
| 成長段階 | `personality/growth.yaml` | 経験に応じた性格パラメータ |

---

## 🌐 外部送信

### 既定で送信されるもの
**なし** (完全ローカル動作)。

### オプション機能で送信されうるもの
| 機能 | 送信先 | 送信内容 | トリガー |
|---|---|---|---|
| Web Research | DuckDuckGo / 指定 URL | 検索クエリ / URL | ユーザーが明示的に質問した時のみ |
| Neural TTS (edge-tts) | Microsoft Azure | 読み上げテキスト | 音声機能使用時 |
| HuggingFace モデル DL | HuggingFace Hub | ダウンロード要求のみ | 初回セットアップ時のみ |

> **⚠ edge-tts について**: ネットワーク経由で Azure に音声合成テキストを送信します。
> Phase 0.5 で pyttsx3 / VOICEVOX (ローカル) への差し替えを予定しています。

---

## 🔐 暗号化

### 鍵管理
- Fernet 鍵は `data/.key` に保存 (パーミッション `0400`)
- 起動ごとに整合性を確認 (`data/.integrity_manifest.json`)
- **ユーザーが `data/.key` を失うと復号不可** — バックアップ必須

### 暗号化対象
- 会話履歴 DB (`data/memories.db`)
- 一部の秘匿 state ファイル (`*.enc`)

### 暗号化対象外 (平文)
- 感情・日記・記念日 (可読性を優先、Fernet 鍵ありでも開けない方が不便)
- ログファイル全般

---

## 🗑 データ削除

### 通常削除
```bash
# 特定セッションの忘却
# (未実装 — Phase 0.5 で --forget-session オプション追加予定)

# 全記憶の消去 + 外部アーカイブ保存
bash scripts/detach_memory_phase_b.sh --apply
```

### 完全消去 (Right to be Forgotten)
```bash
rm -rf data/ logs/ personality/ yamato_dna/ backups/ output/ reports/
```

この操作を行うと ai-chan は "新生" 状態で再起動します。

---

## 👥 第三者提供

**一切行いません**。ai-chan はローカルアプリケーションであり、ユーザーの記憶や会話を
第三者に送信・共有する機能を意図的に持ちません。

---

## 🛡 セキュリティ対策

- 日次で `pip-audit` + `bandit` + `gitleaks` による自動監査 (`logs/security/`)
- 週次で集約サマリを生成
- 既知受容 CVE は `config/security_policy.yaml` で期限付き管理
- 詳細: [docs/SECURITY.md](docs/SECURITY.md)

---

## 🧒 未成年の使用について

ai-chan は **家族との長期的な関係構築を前提** としているため、未成年が使用する場合は
保護者の関与を推奨します。性的・暴力的な内容へのフィルタは `core/injection_guard.py` で
実装されていますが、100% の安全性は保証できません。

---

## 🤖 AI の誤出力について

- ai-chan はローカル LLM (Sarashina2-7B 等) を使用する性質上、**誤った情報を出力する可能性** があります
- 医療・法律・金融・緊急事態に関する判断には使用しないでください
- 重要な意思決定は必ず専門家・公的機関に確認してください

---

## 📜 変更履歴

| 日付 | 変更 |
|---|---|
| 2026-04-20 | Phase 0 初版作成。記憶切り離しポリシーを明文化。 |

---

## ❓ 問い合わせ

- GitHub Issues: https://github.com/FIshota/YAMATO-Project/issues
- Email: honnsipittu@gmail.com (管理者)

本ポリシーは予告なく改定される可能性があります。重要な変更は README.md の通知欄でお知らせします。

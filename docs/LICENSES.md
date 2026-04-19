# ai-chan License Matrix

**Date**: 2026-04-20
**Status**: Phase 0 baseline

本書は ai-chan 本体および同梱する主要依存と、選定したベースモデルの
ライセンス連鎖を可視化する。"国産AI" を名乗る上で、ライセンス違反を
しない / 再配布時に必要な同梱物が明確である、ことを保証するのが目的。

## 本体

| 項目 | 値 |
|---|---|
| プロジェクト | ai-chan |
| ライセンス | MIT (予定 — Phase 0 で公開方針を確定) |
| 暗号化 | Fernet (cryptography, Apache 2.0) |
| 配布形式 | ローカル実行バイナリ + Python パッケージ |

## ベースモデル (Phase 0 採用)

| family | model | license | 再配布 | 商用 | 改変 | Notes |
|---|---|---|---|---|---|---|
| **sarashina2-7b** | Sarashina2-7B (SB Intuitions) | **MIT** | ✅ | ✅ | ✅ | Phase 0 既定。完全クリーン。 |
| elyza-llama3-8b | ELYZA-japanese-Llama-3-8B-Instruct | Meta Llama 3 Community | ⚠ 条件付 | ⚠ MAU 7億人規制 | ✅ | 再配布時に LICENSE / Use Policy 同梱必須 |
| swallow-8b | Llama-3.1-Swallow-8B | Meta 3.1 + Gemma terms | ⚠ 条件付 | ⚠ | ✅ | Gemma terms も連鎖 |
| karakuri-8b | karakuri-lm-8x7b-instruct-v0.1 | Apache 2.0 | ✅ | ✅ | ✅ | クリーン。メモリ要件が重い |
| qwen2-legacy | Qwen2.5 | Qwen License | ⚠ | ⚠ | ⚠ | 互換のためだけに残存 |

## 主要 Python 依存 (抜粋)

| パッケージ | ライセンス | 備考 |
|---|---|---|
| llama-cpp-python | MIT | |
| cryptography | Apache 2.0 / BSD-3 dual | |
| faiss-cpu | MIT | |
| sentence-transformers | Apache 2.0 | モデルは別ライセンス (基本は Apache 2.0 の all-MiniLM 系) |
| edge-tts | GPL-3.0 | ⚠ 再配布時に要注意。Phase 1 で pyttsx3 / OpenJTalk に差し替え検討 |
| fastapi | MIT | |
| uvicorn | BSD-3 | |
| slowapi | MIT | |
| duckduckgo-search | MIT | |
| beautifulsoup4 | MIT | |
| requests | Apache 2.0 | |
| numpy | BSD-3 | |
| librosa | ISC | |
| sounddevice | MIT | |
| soundfile | BSD-3 | |
| pip-audit | Apache 2.0 | 監査専用 |
| bandit | Apache 2.0 | 監査専用 |
| cyclonedx-bom | Apache 2.0 | 監査専用 |

`edge-tts` は GPL-3.0 のため、本体がクローズドソースで配布される場合は
静的同梱を避けるか、音声合成系をリプレースする必要がある。Phase 1 タスクとして
記録。

## ライセンス再配布チェックリスト (リリース時)

- [ ] `docs/LICENSES.md` を最新化
- [ ] `THIRD_PARTY_NOTICES` を自動生成 (pip-licenses 等)
- [ ] ベースモデルの LICENSE を `models/<family>/LICENSE` に配置
- [ ] Meta/Gemma 系を採用した場合は原 LICENSE と Use Policy の PDF を同梱
- [ ] README に "Powered by Sarashina2-7B (MIT)" を明記

## 参考

- docs/MODEL_BASELINE.md — ベースモデル選定の決定記録
- docs/SECURITY.md — 依存 CVE の運用ポリシー

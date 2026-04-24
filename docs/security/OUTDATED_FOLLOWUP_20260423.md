# OUTDATED Follow-up Plan — 2026-04-23

**前提**: `docs/security/OUTDATED_AUDIT_20260423.md` のトリアージ結果を受けて、具体的な upgrade アクションを時系列で計画する。

---

## 🔥 即時 (本 PR)

| パッケージ | 現 pin | → | 新 pin | 理由 |
|---|---|---|---|---|
| click | 8.3.0 | → | 8.3.3 | micro bump (CVE 予防ライン維持) |

適用済 (requirements.txt)。他は別 PR に回す。

---

## 🟡 次 1 週間 (minor bump 検討)

PoC ブランチで smoke test → 問題なければ req を bump。

| パッケージ | 現 | 最新 | 備考 |
|---|---|---|---|
| faiss-cpu | 1.11.0 | 1.13.2 | embedding サーチ。memory/search 経路で回帰テスト必須 |
| safetensors | 0.5.0 | 0.7.0 | モデル保存 I/O。HinoMotoBridge がまだ torch.save 経由なので影響小 |
| scipy | 1.15.0 | 1.17.1 | numpy 1.26 と共存確認 |
| tiktoken | 0.9.0 | 0.12.0 | トークン概算で使用。差分は無視できるレベル |
| gguf | 0.17.0 | 0.18.0 | llama-cpp 側。緊急フォールバック用なので余裕 |
| fpdf2 | 2.8.0 | 2.8.7 | export PDF。軽微 |
| pymupdf | 1.27.0 | 1.27.2.2 | 同上 |

**ブランチ方針**: `chore/deps-bump-202604-minor` を切り、ここに 1 行 ずつ追加して回帰テストを回す。

---

## 🟠 次 1 ヶ月 (中 minor / major 手前)

| パッケージ | 現 | 最新 | 検討事項 |
|---|---|---|---|
| duckduckgo-search | 7.0.0 | 8.1.1 | 8.x は API 変化あり。web_fetcher の呼び出しを確認 |
| rich | 14.0.0 | 15.0.0 | CLI 出力。breaking 差分を changelog 確認 |
| sentence-transformers | 4.0.0 | 5.4.1 | memory の意味類似度検索。5.x は HuggingFace deps 変更あり |
| librosa | 0.10 | 0.11 | 音声経路のみ。voice_id が動作するか確認 |
| python-dotenv | 1.1.0 | 1.2.2 | 軽微 |
| llama-cpp-python | 0.3.4 | 0.3.20 | フォールバック経路、bump して動作確認 |

---

## 🔴 当面保留 (major / 破壊的変更)

| パッケージ | 現 | 最新 | 保留理由 |
|---|---|---|---|
| numpy | 1.26.4 | 2.4.4 | 2.x は広範に breaking。torch / scipy / faiss の numpy2 サポート確認後 |
| paramiko | 3.5.0 | 4.0.0 | SSH 経路。server_ops 経路が動いてから bump |
| notion-client | 2.2.0 | 3.0.0 | 3.x の API 差分を確認 |
| pdfminer.six | 20250506 | 20260107 | date-versioned。機能変更が多く、回帰が重い |

---

## 運用ルール

1. **1 bump = 1 commit**: 回帰が起きたとき revert しやすいように。
2. **bump 前に**: 必ず `pytest tests/` 全グリーン、CHANGELOG 該当節を読む。
3. **bump 後 48h**: `launchctl` が吐く daily audit で bandit / pip-audit に新警告が出ないか監視。
4. **major bump**: 必ず別 PR 単独で。レビューアーが diff を 1 箇所で見れるように。

---

## 参考

- 日次の raw data: `logs/security/outdated-20260423.txt`
- 監査結果: `docs/security/OUTDATED_AUDIT_20260423.md`
- CVE 受容: `docs/security/POLICY_REVIEW_20260423.md`

# ai-chan セキュリティ＆アップデート ロードマップ

最終更新: 2026-04-20

## 概要

ai-chan はローカル優先の生活伴走エージェントとして、個人情報・音声・
会話ログ・認証情報を扱う。よってセキュリティは **使いやすさよりも優先**
される第一級要件である。本ドキュメントは現状の対策、運用上の前提、
継続対応 (Stage 1 - 5 / P1 - P8) の全体像を示す。

---

## 1. 現在の保護レイヤー

### 1.1 ネットワーク境界
- **`utils/url_guard.py`** : http/https スキーム限定・プライベート/ループバック/リンクローカル IP 拒否（SSRF 防御）
- 外部 HTTP 呼び出し箇所 (`competitor_analyzer`, `github_learner`, `image_gen`, `web_fetcher` 等) はすべて `assert_safe_http_url()` を通過

### 1.2 認証情報・機微データ
- **Fernet 対称鍵暗号** による `CredentialStore` で `server_home` 認証情報を暗号化
- `_migrate_plaintext_credentials()` により `settings.json` の平文パスワードを自動マイグレーション＋ワイプ
- SSH 接続のホスト鍵検証 : デフォルト `RejectPolicy` + `load_system_host_keys`、明示的に `ssh_trust_on_first_use` 設定時のみ TOFU

### 1.3 モデル・キャッシュ
- LLM キャッシュ (`diskcache`) に対する **CVE-2025-69872 緩和策**
  - `_secure_cache_dir()` でキャッシュディレクトリ権限 0o700 / オーナー確認 / `.pkl` 自動除去
  - `core/llm.py` 初期化時に `_harden_llm_cache()` を自動実行

### 1.4 ハッシュ用途
- セキュリティ非目的の MD5 呼び出し (ID生成, 重複検出) は
  `hashlib.md5(x.encode(), usedforsecurity=False)` で統一

### 1.5 監査・検出
- `scripts/audit.sh` : quick / full モード。`pip-audit` + `bandit` + `gitleaks` + outdated + SBOM
- `scripts/secret_scan.py` : ローカル gitleaks 代替（AWS/GCP/GitHub/OpenAI/Anthropic/Notion/Stripe/PEM/JWT）
- `scripts/check_outdated.py` : PyPI 最新版との floor 比較
- `.bandit` 設定 : 不要な誤検知 (B101/B404/B603/B607) をスキップ

### 1.6 依存関係ロック
- `requirements.lock` : `pip-compile` により **cryptographic hash 固定**
- `requirements.txt` : Python バージョン条件付き pin
  - `numpy`, `torch` は `python_version < "3.13"` / `>= "3.13"` で別 pin

### 1.7 自動監視
- L1 Remote Trigger (Anthropic Cloud) : **毎朝 9:00 JST** に脆弱性スキャン自動実行
- known accepted residual risks を prompt に埋め込み、再フラグを抑制

---

## 2. 残存リスク (Known Residual Risks)

| ID | 概要 | 受容理由 | 対応予定 |
|---|---|---|---|
| CVE-2025-69872 | diskcache pickle RCE (upstream 未修正) | `_harden_llm_cache()` でアタックサーフェス最小化 | Stage 4: 代替 KV ストア検討 |
| CVE-2026-1839 | transformers Trainer torch.load | 本アプリは Trainer 未使用で非到達 | Stage 3: transformers 5.x 移行時に解消 |

---

## 3. ステージ別ロードマップ

### Stage 1 — 即時対応（完了）
- [x] Stage 1 依存 bump (numpy/torch/transformers/paramiko/notion-client/vosk)
- [x] Py3.13 条件付き pin
- [x] SSRF ガード (`utils/url_guard.py`)
- [x] Bandit HIGH 解消 (4 → 0)
- [x] CVE-2025-69872 緩和

### Stage 2 — 供給鎖保護（完了）
- [x] SBOM (CycloneDX) 自動生成
- [x] `requirements.lock` ハッシュ固定
- [x] シークレットスキャナ自作
- [x] server_home 平文パスワード撤廃
- [x] L1 自動監視トリガー

### Stage 3 — メジャー移行（計画中）
- [ ] numpy 2.x 完全移行（Py3.13 テスト）
- [ ] transformers 5.x 移行（Trainer-free API 確認）
- [ ] paramiko 4.x 移行（API 差分レビュー）
- [ ] Pillow 12.x 移行（CVE-2024-28219 解消）

### Stage 4 — 構造強化（計画中）
- [ ] SQLCipher 導入（SQLite 透過暗号化）
- [ ] `hnswlib` / `usearch` 評価（FAISS 代替）
- [ ] 検索バックエンド抽象化（DI パターン）
- [ ] llama-cpp-python 代替評価（`mlc-llm` / `vllm`）
- [ ] diskcache → `lmdb` / カスタム KV 検討

### Stage 5 — CI / ガバナンス（計画中）
- [ ] Dependabot / Renovate セットアップ
- [ ] CI ゲート : pip-audit / bandit / secret-scan を main マージ必須に
- [ ] SLO 文書化 (CVE 検出→パッチ 72 時間、CRITICAL は 24 時間)
- [ ] Policy A : CRITICAL auto-merge 候補 / HIGH 以下は human-review

---

## 4. パフォーマンス改善ロードマップ (P1 - P8)

| ID | 項目 | 状態 |
|---|---|---|
| P1 | lazy imports で起動時間短縮 (30s → 3.6s) | **完了** |
| P2 | LLM response LRU cache + n_threads/n_batch auto-tune | **完了** |
| P3 | QuantumReasoner worldline 並列化 (ThreadPool) | **完了** |
| P4 | UnifiedField resonate LRU キャッシュ (256 件) | **完了** |
| P5 | 階層メモリ検索 (Hot → Warm → Cold 早期 return) | **完了** |
| P6 | TTS 短フレーズ合成キャッシュ (32 件 LRU) | **完了** |
| P7 | STT 信頼度フィルタ + 重複フレーム除去 | **完了** |
| P8 | 自動量子化選択 (RAM 量でQ4/Q5/Q8切替、明示指定優先) | **完了** |

---

## 5. 運用ガイド

### 日次
- L1 Remote Trigger の結果を `logs/security/` で確認
- `scripts/audit.sh quick` をローカルで実行推奨

### 週次
- `scripts/audit.sh full` で SBOM + outdated 比較
- HIGH/CRITICAL があれば Stage 1 相当対応を即時検討

### 機微データ取扱
- `config/settings.json` に平文パスワードを書かない
  （起動時に自動で Fernet ストアへ移行される）
- `data/llm_cache/` の権限が 0o700 でないと LLM 初期化がエラー終了する

### インシデント時
1. 問題を再現し `logs/security/` にコピー保存
2. 該当 CVE を `requirements.txt` で floor bump
3. `pip-compile` で `requirements.lock` 更新
4. 影響スコープ最小化後にデプロイ

---

## 6. コード所在参照

| 機能 | ファイル |
|---|---|
| SSRF ガード | `utils/url_guard.py` |
| 認証情報暗号化 | `core/server_home.py` (`CredentialStore`, `_migrate_plaintext_credentials`) |
| LLM キャッシュ hardening | `core/llm.py` (`_secure_cache_dir`, `_harden_llm_cache`) |
| 脆弱性スキャン | `scripts/audit.sh`, `scripts/check_outdated.py`, `scripts/secret_scan.py` |
| Initiative Driver 配線 | `core/ai_chan.py` (`attach_desktop_channel` 等) |
| 依存 floor | `requirements.txt` (Py3.13 条件付き) |
| 依存 lock | `requirements.lock` (hash 固定) |
| Bandit 設定 | `.bandit` |

---

## 7. 変更履歴

- 2026-04-20 : 自動監査 HIGH (CVE=2 Bandit-HIGH=0 Secrets=0) — 既知受容: CVE-2025-69872 / CVE-2026-1839
- 2026-04-20 : 自動監査スケジュール (launchd 09:00 JST) + Mail.app通知 稼働開始
- 2026-04-20 : Stage 1 + 2 完了、P1 完了、SECURITY.md 初版

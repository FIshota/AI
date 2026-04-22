# Security Triage — 2026-04-21

**Auditor:** security-reviewer agent  
**Scope:** Bandit MED 22件 + Outdated deps 20件  
**Reference policy:** `config/security_policy.yaml` v1  
**Project context:** on-device / オフライン運用前提 (家から出ない)

---

## Part 1: Bandit MEDIUM 22件

### 凡例

| 判定 | 意味 |
|------|------|
| **FIX** | 実害リスクあり — 修正推奨 |
| **ACCEPT** | 誤検知 or コンテキスト上実害なし |
| **SUPPRESS** | `# nosec` コメント追加で十分 |

---

### B310 — urllib.request.urlopen スキーム検証 (11件)

Banditは「file:/ やカスタムスキームを許可している可能性」を警告するが、
各呼び出し箇所の上流に `utils/url_guard.py::assert_safe_http_url()` が存在するかどうかで判定を分ける。

| # | ファイル | 行 | 判定 | 理由 |
|---|----------|----|------|------|
| 1 | `core/competitor_analyzer.py` | 116 | **SUPPRESS** | 直前 112行で `assert_safe_http_url()` 呼び出し済み。スキームは `http`/`https` に制限済み。`# noqa: S310 (scheme asserted)` コメントも既存。`# nosec B310` を追加すれば十分。 |
| 3 | `core/github_learner.py` | 180 | **SUPPRESS** | 175行で `assert_safe_http_url(url)` 呼び出し済み。スキーム検証済み。`# noqa: S310` も付与済み。`# nosec B310` 追加で十分。 |
| 4 | `core/image_gen.py` | 156 | **SUPPRESS** | 154行で `assert_safe_http_url(url)` 呼び出し済み。`# noqa: S310` 付与済み。`# nosec B310` 追加で十分。 |
| 9 | `core/research_agent.py` | 198 | **SUPPRESS** | 185行で `assert_safe_http_url(url)` + `UnsafeURLError` ハンドリング済み。`# noqa: S310` 付与済み。`# nosec B310` 追加で十分。 |
| 16 | `core/tts/engine.py` | 126 | **ACCEPT** | `self._base` は `__init__` で `f"http://{spec.voicevox_host}:{spec.voicevox_port}"` と内部固定。`voicevox_host` はローカル設定値 (localhost/127.0.0.1)。外部入力が混入しない構造。ヘルスチェック用の `available()` のみ。オフライン運用前提でリスク無し。 |
| 17 | `core/tts/engine.py` | 145 | **ACCEPT** | 同上。`self._base` 固定 + `audio_query` POST。VOICEVOX ローカルAPI 呼び出しのみ。スキームは `http://` 固定。 |
| 18 | `core/tts/engine.py` | 165 | **ACCEPT** | 同上。`synthesis` POST。VOICEVOX ローカルAPI。 |
| 19 | `core/web_fetcher.py` | 67 | **FIX** | `city` パラメータは呼び出し元から渡される可変値。URL が `https://wttr.in/{city}?format=j1` とテンプレート展開されており、`assert_safe_http_url()` が呼ばれていない。`city` に `file://` や `ftp://` は入らないが、URL注入経由での予期しないホストへのリクエストの余地がある。**対処:** `urlopen` 前に `from utils.url_guard import assert_safe_http_url` を呼び出す。または `city` をホワイトリスト/正規表現 `[a-zA-Z0-9\-]+` でバリデートする。 |
| 21 | `core/web_fetcher.py` | 149 | **FIX** | `web_search_duckduckgo` の `query` 由来 URL。DDG Lite への固定URL (`lite.duckduckgo.com`) だが `urlopen` 前に `assert_safe_http_url()` が呼ばれていない。同関数内の他の urlopen (行97) には `nosec B310` があり一貫性がない。**対処:** 行148の `req` 生成前に `assert_safe_http_url(url)` を追加する。 |
| 22 | `core/web_fetcher.py` | 212 | **FIX** | `web_fetch_text(url: str)` — `url` は外部から自由に渡せる公開関数。`assert_safe_http_url()` の呼び出しが一切ない。SSRF の直接的な入口になりうる。**対処 (優先度高):** 関数冒頭で `url = assert_safe_http_url(url)` を追加する。オフライン運用でも LLM が生成した URL を渡すケースがあるため対処すべき。 |

---

### B608 — SQL 文字列フォーマット (4件)

| # | ファイル | 行 | 判定 | 理由 |
|---|----------|----|------|------|
| 2 | `core/data_exporter.py` | 160 | **ACCEPT** | `table_name` は 152-158行で `sqlite_master` に対してパラメータ化クエリで存在確認済み。存在するテーブル名のみ到達する。識別子のクォーティングが無いのは惜しいが、想定テーブルが内部固定 (`memories`, `conversations` 等) であり、外部入力が直接届く経路が確認できない。`# noqa: S608` コメントも付与済み。**ただし要確認:** `table_name` の呼び出し元が外部APIから受け取る場合は **FIX** に格上げ。 |
| 5 | `core/memory.py` | 710 | **ACCEPT** | `where_clauses` は 705行で `"content LIKE ?"` の繰り返し結合のみ。`level_placeholders` は 706行で `"?"` の繰り返し。いずれもユーザー値は `?` プレースホルダーで渡している。フォーマット文字列に含まれるのは内部生成の固定文字列のみ。実質的にパラメータ化クエリと同等。 |
| 6 | `core/memory.py` | 754 | **ACCEPT** | 同上。`where_sql` は 744-750行で内部定数 (`COALESCE(security_level, 'public') IN (...)`, `memory_type = ?`) のみで構成。ユーザー値はすべて `params` に分離。 |
| 7 | `core/memory.py` | 848 | **ACCEPT** | FTS5 クエリ。`placeholders` は 845行で `"?"` の繰り返し。`query`, `allowed`, `limit` はすべて `?` バインド。フォーマット変数に外部入力は混入しない。 |
| 8 | `core/memory_compressor.py` | 68 | **ACCEPT** | `ids_to_delete` は内部で生成した Memory オブジェクトのIDリスト (UUID/int)。`','.join('?'*len(ids_to_delete))` でプレースホルダー生成し、値はバインドパラメータで渡している。インジェクションの経路なし。 |

---

### B601 — Paramiko exec_command (5件)

| # | ファイル | 行 | 判定 | 理由 |
|---|----------|----|------|------|
| 10 | `core/server_home.py` | 204 | **SUPPRESS** | `is_reachable()` で `"echo ok"` のリテラル文字列のみ実行。ユーザー入力なし。`# nosec B601` 追加で十分。 |
| 11 | `core/server_home.py` | 228 | **FIX** | `run_command(cmd)` で `_is_allowed(cmd)` チェックが入っているが、`_is_allowed` は **プレフィックスマッチ**のみ (`cmd.strip().startswith(prefix)`)。`DEFAULT_ALLOWED_PREFIXES` に `"cat"` や `"ls"` がある場合、`cat /etc/passwd` や `ls /root/.ssh/` が通過してしまう。また `"rm -rf /home"` が許可リストに存在し非常に危険。**対処:** (1) `rm -rf /home` を許可リストから即座に削除する。(2) プレフィックスマッチを完全一致 or 厳密な正規表現マッチに変更する。(3) コマンドを enum で定義し、文字列ではなくコマンドキーで呼び出す方式に変更することを強く推奨。 |
| 12 | `core/server_home.py` | 261 | **SUPPRESS** | `health_check()` 内で `"uptime -p"` のリテラル固定。ユーザー入力なし。`# nosec B601` 追加で十分。 |
| 13 | `core/server_home.py` | 265 | **SUPPRESS** | `"df -h / | tail -1"` のリテラル固定。同上。 |
| 14 | `core/server_home.py` | 269 | **SUPPRESS** | `"free -h | grep Mem | awk '...'"` のリテラル固定。同上。 |
| 15 | `core/server_home.py` | 275 | **SUPPRESS** | `"docker ps --format '{{.Names}}' | wc -l"` のリテラル固定。同上。 |

---

### B314 — xml.etree.ElementTree (1件)

| # | ファイル | 行 | 判定 | 理由 |
|---|----------|----|------|------|
| 20 | `core/web_fetcher.py` | 98 | **FIX** | NHK RSS フィードを `xml.etree.ElementTree.parse()` で直接パースしている。84-93行に `defusedxml` を優先使用するコードがあるが、**ImportError フォールバックで標準 ET を使う実装になっており、defusedxml がインストールされていない環境では XXE 脆弱性が露出する**。`requirements.txt` に `defusedxml` が入っているか要確認。**対処:** (1) `requirements.txt` に `defusedxml>=0.7.1` を追加し必須依存にする。(2) フォールバックを削除するか、フォールバック時は処理を中断してエラーを返す。現状の「警告ログだけ出して処理続行」はリスクあり。 |

---

### Bandit トリアージ集計

| 判定 | 件数 | テスト |
|------|------|--------|
| FIX | 4 | B310×3 (web_fetcher), B601×1 (server_home run_command), B314×1 (web_fetcher XXE) — ※B314含め実質5件 |
| ACCEPT | 9 | B310×3 (tts/engine), B608×5 (data_exporter, memory×3, memory_compressor) |
| SUPPRESS | 8 | B310×4 (competitor_analyzer, github_learner, image_gen, research_agent), B601×4 (server_home 固定文字列) |

> **FIX 優先順位:**
> 1. `core/server_home.py:228` — `_is_allowed` プレフィックスバイパス + `rm -rf /home` 許可リスト混入 (CRITICAL相当)
> 2. `core/web_fetcher.py:212` — `web_fetch_text()` に SSRF ガード欠落 (HIGH)
> 3. `core/web_fetcher.py:98` — XXE: defusedxml フォールバックが脆弱 (HIGH)
> 4. `core/web_fetcher.py:67,149` — urlopen 前の URL検証欠落 (MEDIUM)

---

## Part 2: Outdated Dependencies 20件

### 凡例

| 判定 | 意味 |
|------|------|
| **UPGRADE_NOW** | 互換性あり、セキュリティ修正含む可能性、即アップグレード推奨 |
| **UPGRADE_CAREFUL** | メジャーバージョン跨ぎ / breaking change 可能性あり |
| **PIN** | 意図的に固定 (理由付き) |

---

| # | パッケージ | 現在 | 最新 | 判定 | 理由・方針 |
|---|-----------|------|------|------|-----------|
| 1 | `cryptography` | 45.0.0 | 46.0.7 | **UPGRADE_NOW** | `cryptography` はセキュリティライブラリ本体。マイナーバージョンアップにも暗号実装の修正が含まれることが多い。45→46 はメジャー跨ぎではなく互換性は維持される見込み。`Fernet` / `PKCS` 等の使用箇所への影響は低い。早期アップグレード推奨。 |
| 2 | `duckduckgo-search` | 7.0.0 | 8.1.1 | **UPGRADE_CAREFUL** | メジャーバージョン跨ぎ (7→8)。API の呼び出しインターフェースが変更される可能性がある。`core/github_learner.py` や `core/research_agent.py` での `DDGS().text()` 呼び出し互換性を事前確認すること。 |
| 3 | `faiss-cpu` | 1.9.0 | 1.13.2 | **UPGRADE_NOW** | マイナーバージョン 4段階。セキュリティ Surface は低いが、既知のメモリ安全性修正が含まれる可能性。互換性は維持されている。アップグレード推奨。 |
| 4 | `fastapi` | 0.118.0 | 0.136.0 | **UPGRADE_NOW** | 0.x のマイナー 18段階。`starlette` 依存経由でのセキュリティ修正が含まれる可能性がある。WebAPI の公開範囲が限定的でも、ヘッダー処理・リクエストバリデーション修正は取り込む価値がある。互換性は高い。 |
| 5 | `gguf` | 0.10.0 | 0.18.0 | **UPGRADE_NOW** | フォーマットパーサライブラリ。マイナー 8段階。モデルファイルパース時のバッファ境界修正が含まれる可能性。ローカルファイル読み込みのみでも、悪意あるモデルファイルを読み込むシナリオへの対策として有効。 |
| 6 | `google-api-python-client` | 2.150.0 | 2.194.0 | **UPGRADE_NOW** | 自動生成クライアント、マイナー 44段階。セキュリティ Surface は低い。 `google-auth` 依存経由での OAuth 修正が含まれる可能性。互換性は維持されている。 |
| 7 | `notion-client` | 2.2.0 | 3.0.0 | **UPGRADE_CAREFUL** | メジャー跨ぎ (2→3)。Notion API v3 対応の可能性あり。現在の使用箇所 (連携機能) の API インターフェース確認が必要。 |
| 8 | `numpy` | 1.26.4 | 2.4.4 | **UPGRADE_CAREFUL** | メジャー跨ぎ (1.x→2.x)。numpy 2.0 は C API の breaking change あり。`faiss-cpu`, `scipy`, `scikit-learn`, `sentence-transformers` 等の numpy 依存ライブラリが numpy 2.x に対応しているか依存関係全体で確認が必要。**一括アップグレードが必要なためまとめて計画すること。** |
| 9 | `paramiko` | 3.5.0 | 4.0.0 | **UPGRADE_CAREFUL** | メジャー跨ぎ (3→4)。`server_home.py` が Paramiko を使用しており、SSH 認証 / `exec_command` / SFTP の API 互換性を確認する必要がある。4.x で廃止された認証方式がある場合に接続が切れるリスクあり。Paramiko 4 はセキュリティ修正も含むため、互換確認後はアップグレードすべき。 |
| 10 | `pdfminer.six` | 20240706 | 20260107 | **UPGRADE_NOW** | 日付バージョン、約1.5年差。PDF パーサはバッファオーバーフロー・悪意ある PDF 対策が含まれることが多い。セキュリティ観点で更新推奨。互換性は通常維持される。 |
| 11 | `pillow` | 11.0.0 | 12.2.0 | **UPGRADE_CAREFUL** | メジャー跨ぎ (11→12)。Pillow はイメージパーサ系 CVE が頻繁に発見されるライブラリ。セキュリティ面ではアップグレード価値が高い。ただし 12.x で削除された API (古い `Image.show()` 引数など) がないか使用箇所を確認すること。 |
| 12 | `pydantic` | 2.11.0 | 2.13.3 | **UPGRADE_NOW** | マイナー 2段階。v2 系内の互換性は高い。バリデーションロジックのバグ修正が含まれる可能性。推奨。 |
| 13 | `pymupdf` | 1.24.0 | 1.27.2.2 | **UPGRADE_NOW** | MuPDF ライブラリをバンドルしており、PDF/XPS の脆弱性修正が含まれる。マイナー 3段階。互換性は通常維持される。セキュリティ観点で更新推奨。 |
| 14 | `rich` | 14.0.0 | 15.0.0 | **UPGRADE_CAREFUL** | メジャー跨ぎ (14→15)。セキュリティ Surface は極めて低いが、出力フォーマット変更や一部 API 廃止が想定される。テスト実行後にアップグレード可能。優先度は低い。 |
| 15 | `safetensors` | 0.4.5 | 0.7.0 | **UPGRADE_NOW** | モデルファイル読み込みライブラリ。マイナー 3段階。Rust 実装のシリアライズ境界修正が含まれる可能性あり。ローカルモデル限定でも悪意あるファイルへの耐性向上のため更新推奨。 |
| 16 | `scikit-learn` | 1.5.0 | 1.8.0 | **UPGRADE_NOW** | マイナー 3段階。numpy 2.x 互換対応が含まれる。numpy アップグレード時に同時更新が必要になる可能性大。セキュリティ Surface は低い。 |
| 17 | `scipy` | 1.13.0 | 1.17.1 | **UPGRADE_NOW** | マイナー 4段階。numpy 2.x compat が含まれる。numpy アップグレード計画と連動。セキュリティ Surface は低い。 |
| 18 | `sentence-transformers` | 3.3.0 | 5.4.1 | **UPGRADE_CAREFUL** | メジャー跨ぎ 2段階 (3→4→5)。`SentenceTransformer` のモデルロード API や `encode()` シグネチャが変更されている可能性がある。使用箇所の確認必要。numpy 2.x との互換性とセットで確認すること。 |
| 19 | `tiktoken` | 0.8.0 | 0.12.0 | **UPGRADE_NOW** | マイナー 4段階。トークナイザ更新のみ。互換性は高い。セキュリティ Surface は低いが最新に保つことを推奨。 |
| 20 | `uvicorn` | 0.34.0 | 0.45.0 | **UPGRADE_NOW** | マイナー 11段階。`h11` / `httptools` の HTTP パーサ修正が含まれる可能性。HTTP リクエストスマグリング等の修正が連鎖することがある。FastAPI と同時更新推奨。 |

---

### Outdated トリアージ集計

| 判定 | 件数 | パッケージ |
|------|------|-----------|
| UPGRADE_NOW | 12 | cryptography, faiss-cpu, fastapi, gguf, google-api-python-client, pdfminer.six, pydantic, pymupdf, safetensors, scikit-learn, scipy, tiktoken, uvicorn — ※uvicorn含め13件 |
| UPGRADE_CAREFUL | 7 | duckduckgo-search, notion-client, numpy, paramiko, pillow, rich, sentence-transformers |
| PIN | 0 | 現時点で意図的固定の根拠が確認できたものはなし |

> **UPGRADE_CAREFUL の推奨順:**
> 1. `paramiko` 3→4: `server_home.py` の SSH 機能に直結。セキュリティ修正も含むため早期検証を。
> 2. `pillow` 11→12: イメージパーサ CVE 対策として価値が高い。
> 3. `numpy` + `scipy` + `scikit-learn` + `sentence-transformers`: 依存関係が連鎖するため一括計画が必要。
> 4. `duckduckgo-search` 7→8: AI 検索機能への影響を事前確認。
> 5. `notion-client` 2→3: 連携機能の利用頻度次第で優先度調整。
> 6. `rich` 14→15: 優先度最低。

---

## Part 3: policy.yaml との照合

| CVE / エントリ | ステータス | 備考 |
|---------------|-----------|------|
| CVE-2025-69872 (diskcache) | 有効 (期限 2026-10-20) | 今回の監査対象外。期限内。 |
| CVE-2026-1839 (transformers) | 有効 (期限 2026-07-20) | 今回の監査対象外。期限内。transformers の outdated 確認推奨。 |
| `accepted_bandit` | 空 | 今回 ACCEPT/SUPPRESS として整理した件をポリシーに追記することを推奨。 |
| `accepted_outdated` | 空 | numpy 固定等の方針が決まれば追記すること。 |

---

## 次アクション (優先順)

1. **即日対応 (CRITICAL):** `core/server_home.py` L44-49 の `DEFAULT_ALLOWED_PREFIXES` から `"rm -rf /home"` を削除し、プレフィックスマッチ方式を厳格化する。
2. **今週中 (HIGH):** `core/web_fetcher.py` の `web_fetch_text()` (L212) に `assert_safe_http_url()` を追加する。
3. **今週中 (HIGH):** `defusedxml` を `requirements.txt` に明示追加し、`core/web_fetcher.py` L89 のフォールバックを除去する。
4. **今週中 (MEDIUM):** `core/web_fetcher.py` L67, L149 に `assert_safe_http_url()` を追加する。
5. **今月中 (MEDIUM):** SUPPRESS 対象の `# nosec B310` / `# nosec B601` コメントを追記し bandit ノイズを抑制する。
6. **計画的対応:** `cryptography`, `fastapi`, `uvicorn`, `pymupdf`, `pdfminer.six` の UPGRADE_NOW を requirements.txt に反映し動作確認する。
7. **要計画:** numpy 2.x 移行を含む UPGRADE_CAREFUL 群 (numpy + scipy + scikit-learn + sentence-transformers) の互換性検証計画を立てる。

---

*Generated by security-reviewer agent. Triage only — no code was modified.*

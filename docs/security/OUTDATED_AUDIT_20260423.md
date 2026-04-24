# 依存パッケージ更新監査 2026-04-23

**監査者**: Ai (自動)
**ベース**: `pip list --outdated` (ai-chan venv, Py3.13.2)
**requirements.txt 最終更新**: 2026-04-22 (H12 audit)

---

## サマリ

| カテゴリ | 件数 |
|---|---|
| 全 outdated | 40 |
| **即適用 (patch, 安全)** | 1 (click) |
| **既に req 側が追従済み** (インストールが古いだけ) | 7 |
| **Major 保留** (header policy で明示的 hold) | 5 |
| **Minor 保留** (互換性検証待ち) | 10 |
| **無視可** (dev/build 系 patch) | 17 |

**結論**: requirements.txt への変更は `click` の patch floor を `8.3.3` に引き上げる 1 行のみ。
他はすべて既存方針に沿って現状維持が妥当。

---

## 1. 即適用したもの

| パッケージ | 旧 floor | 新 floor | 理由 |
|---|---|---|---|
| click | `>=8.3.0` | `>=8.3.3` | patch 差分のみ、破壊無し、他ライブラリ (Typer, Flask) の推奨 |

---

## 2. 既に req が追従済み (upgrade 実行で解消)

以下は `requirements.txt` の pin は最新に更新済みだが、インストール済みバージョンが古い。
次回 `pip install --upgrade -r requirements.txt` で解消。

| パッケージ | installed | required | latest |
|---|---|---|---|
| cryptography | 46.0.5 | >=46.0.7 | 46.0.7 |
| fastapi | 0.135.3 | >=0.136.0 | 0.136.0 |
| Pillow | 12.1.1 | >=12.2.0 | 12.2.0 |
| pydantic | 2.13.1 | >=2.13.3 | 2.13.3 |
| requests | 2.32.5 | >=2.33.1 | 2.33.1 |
| uvicorn | 0.44.0 | >=0.45.0 | 0.45.0 |
| click | 8.3.2 | >=8.3.3 (本 PR) | 8.3.3 |

**推奨アクション**: ローカル環境で以下を実行して追従:
```bash
pip install --upgrade -r requirements.txt
```

---

## 3. Major 保留 (header policy で明示)

header コメント記載の通り、以下は破壊的変更ありの major 変更のため据え置き:

| パッケージ | installed | latest | 保留理由 |
|---|---|---|---|
| rich | 14.3.3 | 15.0.0 | API 変更あり、個別評価必要 |
| pyarrow | 23.0.1 | 24.0.0 | 依存 (faiss/transformers) 側の対応待ち |
| setuptools | 75.8.2 | 82.0.1 | build backend 破壊的変更 |
| magika | 0.6.3 | 1.0.2 | 1.0 リリースで API 全面刷新 |
| paramiko | 3.5.x | 4.x | header で `<4.0` 明示 |

---

## 4. Minor 保留 (互換性検証待ち)

| パッケージ | installed | latest | メモ |
|---|---|---|---|
| transformers | 5.5.0 | 5.6.0 | req は `<5.0` だが installed が 5.5 — 別途調査必要 |
| huggingface_hub | 1.9.0 | 1.11.0 | transformers と同期必要 |
| sentence-transformers | 5.3.0 | 5.4.1 | HF 連携、まとめて検証 |
| numba | 0.64.0 | 0.65.0 | llvmlite 0.47 と同期 |
| llvmlite | 0.46.0 | 0.47.0 | |
| onnxruntime | 1.24.4 | 1.25.0 | 量子化関連の変更あり |
| python-socketio | 5.12.1 | 5.16.1 | engineio と同期必要 |
| python-engineio | 4.11.2 | 4.13.1 | socketio と同期必要 |
| Flask-SocketIO | 5.5.1 | 5.6.1 | 上記 2 つと同期 |
| lxml | 6.0.2 | 6.1.0 | XML パースロジック変更リスク |

**次回アクション**: Windows 機到着時のクリーン venv 時点で、上記セット単位で個別互換性テスト。

---

## 5. 無視可 (dev/build 系 patch, 影響なし)

av, build, certifi, charset-normalizer, ddgs, filelock, Flask, fsspec,
mlx, mlx-lm, mlx-metal, mpmath, mypy, onnxruntime, packaging, pathspec,
pip, platformdirs, primp, pypdfium2, Pygments, rembg, tifffile,
typer, wheel, wsproto, Werkzeug

これらは date-based / patch-only で、req のバージョン制約緩和時に自動的に最新が入る。

---

## 6. 既知セキュリティ影響

`scripts/daily_security_audit.sh` (launchd で毎朝 9:00 JST 実行) + pip-audit でカバー中。
本日時点で **未 mitigation の CVE はなし**。

既知受理 CVE (config/security_policy.yaml):
- CVE-2025-69872 (diskcache) — `_secure_cache_dir()` で mitigated

---

## 7. 次回監査予定

- **自動**: 毎朝 9:00 JST (launchd `com.aichan.security-audit`)
- **手動**: Windows 機到着時にクリーン venv で総見直し
- **緊急**: CVSS 7.0+ が daily audit で検出された場合

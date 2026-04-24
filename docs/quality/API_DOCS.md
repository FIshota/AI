# API ドキュメント運用方針

本書は ai-chan の内部 API リファレンス (HTML) 自動生成パイプラインの
設計判断と運用手順をまとめたものです。

## 対象範囲

- `core/` — コアロジック (対話・記憶・モード切替・フェデレーション stub 等)
- `utils/` — 共通ユーティリティ
- `ui/` — Tkinter / デスクトップペット UI

これらは docstring 整備がほぼ完了しており、HTML 化の費用対効果が高い。
`tests/`, `scripts/`, `tools/`, `web/` は現時点では対象外とする。

## なぜ pdoc を選んだか

候補として Sphinx / pdoc / pydoc / mkdocstrings を比較した。
選定ポイントは以下。

| 観点 | pdoc (採用) | Sphinx | mkdocstrings |
|------|-------------|--------|--------------|
| 初期設定コスト | 非常に低い (conf 不要) | 高い (conf.py, rst) | 中 (mkdocs 必須) |
| Python 3.9 互換 | OK (>=14.0) | OK | OK |
| 追加の RST/Markdown 記述 | 不要 | 必要 | 必要 |
| 出力形式 | HTML 単体 / `--http` | HTML/PDF/ePub | HTML (mkdocs) |
| docstring 形式の自由度 | Google / NumPy / RST 自動検出 | 同左 | 同左 |
| CI/launchd からの呼び出し | `python -m pdoc` 一発 | `sphinx-build` + conf | `mkdocs build` |

ai-chan は「内部向けリファレンス」が欲しいだけで、書籍スタイルの
マニュアルは別途 `docs/` 配下に markdown で持っているため、
**設定ファイル不要で即時 HTML 化できる pdoc が最適**と判断した。

## 運用

### 再生成タイミング

1. **手動** — 開発者がモジュールを大きく変更した直後
   ```bash
   bash scripts/build_api_docs.sh
   ```
2. **月次自動** — `launchd/com.aichan.api-docs.plist`
   - Day=1 / Hour=4 / Minute=0 (JST)
   - 失敗しても即座にユーザー影響はない低リスクジョブ
   - 登録手順は plist 冒頭コメント参照
3. **CI (将来)** — main ブランチ更新時に artifact として publish する余地あり
   (現時点では未配線)

### インストール

`requirements/dev.in` に `pdoc>=14.0` を追加済み。
標準の pinning パイプライン (`make pin`) で `requirements/dev.txt` に反映される。
ad-hoc には:
```bash
pip install pdoc
```

### 出力物の扱い

- `docs/api/*.html` は `.gitignore` 済み (artifacts は追跡しない)
- `docs/api/README.md` のみ git 管理 (index 兼説明書)
- ブラウザで直接 `docs/api/index.html` を開けば閲覧可能
- ライブプレビューが欲しければ `python -m pdoc core utils ui`
  (`--http localhost:8080` 風) で起動

## 失敗時の挙動

`scripts/build_api_docs.sh` は `set -euo pipefail` を採用。
pdoc 未インストールなら案内メッセージを出して exit 1。
launchd 実行時は `logs/api-docs/launchd.{out,err}` に記録される。

## 今後の検討事項

- `core/federated` など stub 実装の docstring 品質底上げ
- `--logo` / `--favicon` で ai-chan ブランディング
- Private モジュール (`_foo.py`) の除外方針
- CI で doc 生成が通ることを lint として回すか

# ai-chan 内部 API リファレンス

このディレクトリには `core/` / `utils/` / `ui/` 以下の Python モジュールから
pdoc で自動生成された HTML リファレンスが配置されます。

## 生成方法

プロジェクトルートで次のコマンドを実行してください。

```bash
bash scripts/build_api_docs.sh
```

pdoc が未インストールの場合はスクリプトが案内を出して終了します。
`pip install pdoc` もしくは `pip install -r requirements/dev.txt` で導入してください。

## 生成対象

| パッケージ | 概要 |
|------------|------|
| `core/`    | ai-chan のコアロジック（対話・記憶・モード切替・フェデレーション stub 等） |
| `utils/`   | 共通ユーティリティ（ログ・設定・スレッドセーフ補助等） |
| `ui/`      | Tkinter / デスクトップペット UI 層 |

## 注意

- 生成物 (`*.html`) は `.gitignore` により git 追跡対象外です。
  必要に応じて各開発者 / CI で再生成してください。
- 月次で `launchd/com.aichan.api-docs.plist` が再生成をトリガーする想定です
  （Day=1, Hour=4 JST）。
- 運用方針・設計判断の詳細は [`docs/quality/API_DOCS.md`](../quality/API_DOCS.md)
  を参照してください。

## ファイル構成 (生成後)

```
docs/api/
├── README.md          # このファイル (git 管理)
├── index.html         # pdoc 生成のトップページ
├── core.html          # core パッケージ
├── core/              # core 配下モジュール HTML
├── utils.html
├── utils/
├── ui.html
└── ui/
```

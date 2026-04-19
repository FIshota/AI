# Contributing to ai-chan

ai-chan への貢献を考えてくださってありがとうございます。

このプロジェクトは "家族として振る舞う AI パートナー" を長期的に育てる
個人プロジェクトですが、**外部貢献を歓迎** します。

## 🌱 Phase 0.x 時点の前提

- Python 3.11+ (3.13 推奨)
- ローカル完結 (クラウド API 非依存)
- Intel Mac / ARM Mac / Linux x86 で動作
- Base Model: Sarashina2-7B (MIT, SB Intuitions)

## 🚀 開発環境セットアップ

```bash
git clone https://github.com/FIshota/YAMATO-Project.git ai-chan
cd ai-chan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py --smoke-test   # import 確認
```

## 📋 Issue を立てる前に

1. 既存の [Issues](https://github.com/FIshota/YAMATO-Project/issues) を検索
2. 再現手順を明確化
3. 環境情報 (OS / Python / pip list) を添付

## 🔧 Pull Request の流れ

1. `main` ブランチから feature ブランチを切る
   ```bash
   git checkout -b feat/your-feature
   ```
2. **テストを先に書く** (TDD 推奨)
   ```bash
   pytest tests/ -q
   ```
3. 以下が通ることを確認
   - `ruff check .` (将来 CI で blocking 化予定)
   - `black --check .`
   - `pytest tests/`
   - `bandit -r core utils ui web bench`
4. コミットメッセージは **Conventional Commits**
   - `feat:` 新機能 / `fix:` バグ修正 / `refactor:` / `docs:` / `test:` / `chore:`
5. PR を作成し、テンプレートの項目を全て埋める

## 🎨 コーディング規約

- **PEP 8** + **black** (line-length 100)
- **isort** で import 整列
- 型アノテーション必須 (公開 API のみ厳守)
- docstring は **Google スタイル**
- ファイルは 800 行以下、関数は 50 行以下が目安

## 🔐 セキュリティ

- 秘密情報 (API key / password / token) を commit に含めない
- `.gitignore` の `data/` `logs/` `*.key` `*.enc` を遵守
- 脆弱性発見時は **非公開で** [honnsipittu@gmail.com](mailto:honnsipittu@gmail.com) まで

詳細: [docs/SECURITY.md](docs/SECURITY.md)

## 🧪 ライセンス契約

このプロジェクトに貢献することで、あなたのコントリビューションが
プロジェクトと同じ **MIT License** の下で配布されることに同意したものとみなします。

**禁止**: GPL / AGPL / LGPL など強コピーレフトライセンスのコードを
取り込むこと (`scripts/check_licenses.py --fail-on-gpl` で CI 検証されます)。

## 💬 コミュニケーション

- Issue: バグ報告 / 機能要望
- PR: 実装提案
- Discussion (予定): 設計相談

議論は日本語・英語いずれでも OK。

## 🏗 開発フェーズと貢献可能領域

| Phase | 状態 | 貢献可能な領域 |
|---|---|---|
| 0 (Baseline) | 完了 | - |
| 0.5 | 完了 | - |
| 0.75 (OSS Polish) | 進行中 | docs, CI 改善, テスト追加 |
| 1 (Bench Real) | 未着手 | judge 実装, 日本語データセット追加 |
| 2 (Prompt Eng) | 未着手 | RAG, few-shot, ensemble |
| 3+ (Fine-tune) | GPU 調達後 | LoRA, DPO データ収集 |

**初貢献者におすすめ**:
- docs の typo / 翻訳
- `tests/` の拡充 (現カバレッジ低い)
- `bench/suites/` への新しい評価タスク追加
- `personality/` の core.yaml 拡張提案

## 📜 Code of Conduct

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) に従ってください。

---

質問があれば気軽に Issue を開いてください。

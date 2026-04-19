## 概要

<!-- この PR は何をするものか。1-3 行 -->

## 変更の種類

- [ ] 🐛 バグ修正 (既存機能の修復)
- [ ] ✨ 新機能 (新しい機能の追加)
- [ ] ♻ リファクタリング (機能変更なし)
- [ ] 📝 ドキュメント
- [ ] 🧪 テスト追加/改善
- [ ] 🔐 セキュリティ修正
- [ ] ⚡ パフォーマンス改善
- [ ] 🏗 CI / ビルド改善

## Phase

- [ ] Phase 0.75 (OSS Polish)
- [ ] Phase 1 (Bench Real)
- [ ] Phase 2 (Prompt Engineering)
- [ ] Phase 3+ (Fine-tuning)

## テスト

- [ ] `pytest tests/` が pass
- [ ] 新規機能に対応するテストを追加
- [ ] `python3 main.py --smoke-test` が pass
- [ ] `bandit -r core utils ui web bench` で新規 HIGH なし
- [ ] `scripts/check_licenses.py` で GPL 混入なし

## チェックリスト

- [ ] `black --check .` を実行した
- [ ] `ruff check .` を実行した
- [ ] コミットメッセージが Conventional Commits 形式
- [ ] `docs/` を必要に応じて更新した
- [ ] 破壊的変更の場合、CHANGELOG に記載した

## 関連 Issue

<!-- Closes #xxx / Related #xxx -->

## スクリーンショット (UI 変更時)

## 追加メモ

<!-- レビュアーに伝えたいこと -->

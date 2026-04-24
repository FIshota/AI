# Flaky テスト追跡（FLAKY_TRACKING）

## Flaky テストとは何か

Flaky テストとは、**同じコード・同じ入力に対して実行結果が毎回安定しない** テストのことを指す。パスする時もあれば失敗する時もある、という状態である。

## なぜ放置してはいけないのか

- **CI への信頼が崩れる**: 「どうせまた flaky で落ちただけだろう」と思われた瞬間、CI は壊れても誰も直さなくなる。本物のバグも flaky ノイズに紛れて見落とされる。
- **リリース判断がブレる**: 失敗を再実行で無視する文化は、品質ゲートを事実上無効化する。
- **調査コストが高い**: 発生から時間が経つほど、原因（時刻依存・並列競合・外部 API・リソース枯渇 等）の特定が困難になる。

ai-chan では flaky テストを **2週間以内に根本原因を特定して修正する** ルールを採用する。

## 実行方法

### ローカル（手動）

```bash
bash scripts/run_flaky_finder.sh
```

- `pytest-flakefinder` を使い、各テストを 10 回繰り返し実行する。
- 結果は `logs/flaky/<YYYY-MM-DD>.txt` に出力される。
- 診断専用ツールなので、失敗しても exit code は常に 0。

### 週次（自動）

- `scripts/run_weekly_flaky.sh` が launchd から呼び出される。
- スケジュール: 毎週土曜 04:00 JST（`launchd/com.aichan.flaky-finder.plist` 参照）。
- サマリは `logs/flaky/weekly-<YYYY-MM-DD>-summary.md` に Markdown テーブルで出力される。

## トリアージワークフロー

1. **識別（identify）**: `logs/flaky/` の週次サマリで新規 flaky 候補を確認する。
2. **単独再現（reproduce in isolation）**:
   ```bash
   pytest tests/path/to/test_x.py::test_y --flake-finder --flake-runs=50
   ```
   50 回中 1 回でも失敗すれば flaky と確定。
3. **隔離（isolate / quarantine）**: 該当テストに `@pytest.mark.flaky` を付与する。
   - CI では `--reruns=3 --reruns-delay=1`（pytest-rerunfailures）で再試行される。
   - 週次 flaky-finder では `-m "not flaky"` により除外される。
4. **TODO 登録**: `logs/flaky/README.md` の registry に以下を記録する。
   - テストパス
   - 初観測日
   - 観測回数
   - 根本原因の仮説
   - オーナー
   - 修正期限（初観測から 2 週間）
5. **修正（fix within 2 weeks）**: 根本原因を特定し、`@pytest.mark.flaky` を外す。
   - 期限超過は振り返り対象。`docs/quality/FLAKY_TRACKING.md` の違反ログに記載する。

## 隔離（Quarantine）の挙動

| 実行文脈 | `@pytest.mark.flaky` の扱い |
|---------|------------------------------|
| 通常の CI（`pytest tests/`） | `pytest-rerunfailures` により `--reruns=3 --reruns-delay=1` で再試行される |
| 週次 flaky-finder | `-m "not flaky"` で除外される（検出対象はあくまで隔離前の新規 flaky 候補） |
| ローカル開発 | 明示しない限り通常実行。必要なら `-m flaky` で flaky 群だけを対象にできる |

## 依存パッケージ

`requirements/dev.in` に以下を追加済み:

- `pytest-flakefinder` — 繰り返し実行による flaky 検出
- `pytest-rerunfailures` — CI での自動リトライ（隔離後の暫定措置）

## 参考

- pytest-flakefinder: https://github.com/dropbox/pytest-flakefinder
- pytest-rerunfailures: https://github.com/pytest-dev/pytest-rerunfailures

# 05. このガイド自体の更新ルール（陳腐化対策）

> **GUIDE が古くなった瞬間にこのプロジェクトは漂流する。**
> だからこそ、更新プロトコルを最初に定義する。

## 🗓 定期更新サイクル

### 四半期更新（3/6/9/12 月末、必須）

| 章 | 更新内容 |
|---|---|
| `01-current-state.md` | **全自動スキャン再実行**（pip-audit / bandit / gitleaks） + コード規模再測定 |
| `02-expert-reviews.md` | 5 専門家レビュー再実行（変化点のみ追記） |
| `03-action-matrix.md` | 完了項目を ✅ マーク、新規発見を追加、優先度再計算 |
| `04-decade-roadmap.md` | マイルストン達成率、シナリオ確率、意思決定ゲートチェック |

**所要**: 1 日（自動化スクリプト前提、`scripts/update-guide.sh` 目標）

### 月次軽更新（毎月末）

- 新規 CVE の記録
- 完了タスクの ✅ マーク
- `05-how-to-update-this-guide.md` の外部環境監視リスト確認

### イベント駆動更新（即時）

以下のトリガーで章を書き換え：

| トリガー | 該当章 |
|---|---|
| 大規模リファクタ完了（God Object 解体等） | 01 + 02 |
| 新規 CVE の影響を受ける依存 | 01 + 03 |
| 外部環境イベント（規制/競合/技術） | 04 |
| ゴール/シナリオ見直し | 04 + README |
| 新しい専門家レビュー追加 | 02 |

## 🌐 外部環境監視リスト

**四半期ごとに必ず確認するもの**：

### 技術動向
- [ ] llama.cpp / llama-cpp-python の major 更新
- [ ] faiss / sentence-transformers / transformers の security advisory
- [ ] ONNX Runtime の家族 AI 向け最適化情報
- [ ] Apple Silicon / NPU / ローカル推論 HW の新製品
- [ ] 大手 LLM のローカル実行可能版リリース（Llama / Gemma / Mistral / Sarashina 系）

### 規制動向
- [ ] EU AI Act 施行状況（Article 5 禁止 / Article 6 高リスク該当の判例）
- [ ] 日本 AI 法制化の進捗（経産省 / デジタル庁の公表）
- [ ] 個人情報保護法の改正予告
- [ ] COPPA（米児童オンラインプライバシー）の適用拡大
- [ ] GDPR 執行判例（特にローカル AI 関連）

### 市場動向
- [ ] Apple / Google / Amazon の家族 AI 製品発表
- [ ] 類似 OSS プロジェクト（Home Assistant 系 AI 統合、LangChain 系）
- [ ] 日本国内の競合（NTT / ソフトバンク / LINE ヤフーの家族 AI）
- [ ] 暗号通貨/IPFS/decentralized identity の家族 AI 応用事例

### コミュニティ動向
- [ ] GitHub Stars / Fork / Issue / PR 数の推移
- [ ] 貢献者数（単発 / 継続）
- [ ] 実利用家族の増減（匿名テレメトリ opt-in 時のみ）

## 🚨 「ガイドを捨てる」判断

**以下の場合、該当章を完全に捨てて書き直す** ことを推奨：

### 章 01（Current State）
- 6 ヶ月以上未更新 → 自動スキャン再実行必須
- コード規模が 2 倍/半分になった
- 5 専門家グレードが 2 段階以上変動

### 章 02（Expert Reviews）
- 専門家レビューから 1 年以上経過
- Top 10 findings の 7 割以上が解消または陳腐化
- 新しい脅威モデルが必要（例：量子コンピュータ実用化）

### 章 03（Action Matrix）
- BLOCKER 完了率 ≥ 80% → 次フェーズ用に書き直し
- 四半期が変わった
- 優先度の前提（I/U/T）が変わった

### 章 04（Decade Roadmap）
- 意思決定ゲートが発火
- シナリオの前提崩壊
- 最上位ゴール自体の変更（経営判断）

## 🔒 GUIDE の継承性

**創業者離脱 / チーム交代時にも GUIDE が機能し続けるように**：

1. **GUIDE を git に必ずコミット**（プライベートノートではなく）
2. **四半期更新を GitHub Actions で自動 trigger**（リマインダ PR）
3. **外部環境監視リストを Notion/Obsidian 等と同期しない** — git が single source
4. **各章冒頭に「最終更新日」を明記**
5. **章 04 の「譲れない一点」と README の最上位ゴールだけは、過半数合意なく変更しない**

## 📝 更新時の書式ルール

- **辛口維持**: Linus 級の忖度なし評価を保つ（甘い表現に滑らない）
- **具体性**: ファイル名 + 行番号 + コマンド必須
- **測定可能性**: 「改善する」ではなく「X ms → Y ms」のように
- **前提明示**: 「現時点では」「2026-04-20 時点で」を積極的に
- **削除優先**: 情報を足すより、古くなった情報を消す判断を優先

## 🎬 更新プロセス（例）

### 四半期更新の手順

```bash
# 1. 自動スキャン（Phase A 再実行）
pip-audit -r requirements.txt --format json > /tmp/guide/pip-audit.json
bandit -r core utils ui web bench -f json -o /tmp/guide/bandit.json
gitleaks detect --source . --report-path /tmp/guide/gitleaks.json
pip list --outdated --format=json > /tmp/guide/outdated.json

# 2. コード規模再測定
find . -name "*.py" | xargs wc -l | sort -rn > /tmp/guide/sizes.txt

# 3. 専門家レビュー再実行（変化点のみ）
# → Claude Code で 5 agent 並列起動

# 4. 章 01-04 を更新（手動 or 半自動）

# 5. git commit
git add docs/GUIDE/*.md
git commit -m "docs(guide): quarterly update YYYY-QN"
```

## ⚠️ 最も忘れやすいこと

- **このファイルを更新し忘れる** → 更新プロトコル自体が陳腐化
- **外部環境監視リストを確認し忘れる** → 規制違反/競合対応の遅延
- **意思決定ゲートを忘れる** → 環境変化に追従できない
- **BLOCKER 完了後に新 BLOCKER を設定し忘れる** → プロジェクトが停滞

## 🎯 このガイド自体の成功判定

- **2027-04-20 時点**（1 年後）: 四半期更新が 4 回全部実施されている
- **2028-04-20 時点**（2 年後）: BLOCKER が空、HIGH も 80% 完了
- **2030-04-20 時点**（4 年後）: 章 04 の 2030 マイルストン（YAMATO α）達成 or 理由明記
- **2036-04-20 時点**（10 年後）: 最上位ゴール達成判定 or シナリオ移行記録

## 🙏 最後に

このガイドは「完成」しない。**家族 AI を作る」という仕事が完成しないのと同じ**。
四半期ごとに書き換え続けること、それ自体が 10 年プロジェクトの本体。

# 議事録 (Minutes) フォーマット運用方針

本プロジェクト ai-chan における「日常的な意思決定ログ」の書き方・保管方法を定める。
ADR との使い分け、ファイル命名、lint、保存期間などを含む。

## 目的

- 軽量に意思決定を記録し、後から**誰が・いつ・何を・なぜ決めたか**を追跡できるようにする。
- フォーマットを固定し、ファイルごとに体裁がバラつくのを防ぐ。
- `scripts/lint_minutes.py` で必須セクション欠落を機械的に検出する。

## ADR との使い分け

| 種類 | 置き場所 | 何を書くか |
|------|----------|-----------|
| ADR (Architecture Decision Record) | `docs/adr/NNNN-*.md` | アーキテクチャに影響する**不可逆・長期影響**の決定。採否・背景・代替案・帰結を厚めに書く。 |
| Minutes (議事録) | `docs/minutes/YYYY-MM-DD-<slug>.md` | 日常の運用・方針・実装方針など、**軽量で撤回しやすい**決定。必要なら後から ADR に昇格する。 |

**昇格ルール**: Minutes の決定が後になって「不可逆で影響が大きい」と判明した場合、該当 Minutes を参照しつつ新しい ADR を起こす。Minutes 自体は書き換えない。

## ファイル命名規則

```
docs/minutes/YYYY-MM-DD-<slug>.md
```

- `YYYY-MM-DD` はその会議/意思決定の日付。
- `<slug>` は英数字・ハイフン・アンダースコアのみ。短く内容を示す (例: `model-upgrade`, `release-2026q2`).
- 同日に複数ある場合は slug で区別する。
- テンプレートは `docs/minutes/TEMPLATE.md` に置き、lint 対象外。

## 必須セクション

以下 6 セクションを **`## <名称>` 見出し**として必ず含める。順序は自由だが、テンプレート順を推奨する。

1. 日付
2. 参加者
3. 議題
4. 決定事項
5. 未決事項
6. 次回アクション

欠落すると `scripts/lint_minutes.py` が exit code 2 を返す。

### セクションの書き方

- **日付**: `YYYY-MM-DD`。
- **参加者**: 本プロジェクトは個人開発のため「オーナー」単独が基本。外部レビュアーが関わった場合はその都度追記。
- **議題**: 箇条書き。事前に決めた議題をそのまま残す (議論後に追加された論点は別の議事録か次回アクションに回す)。
- **決定事項**: 箇条書き。**能動形で結論だけ書く**。根拠が長くなる場合は別ドキュメントにリンクする。
- **未決事項**: 箇条書き。なぜ保留したか、次に何が必要かを添える。未決事項が無ければ「なし」と明記。
- **次回アクション**: `- [ ] 内容 — 担当: X — 期限: YYYY-MM-DD` の形式。担当未定の場合も `担当: 未定` と書いて空欄にしない。

## 作成手順

```bash
# 自動生成 (推奨)
scripts/new_minutes.sh <slug>              # 日付は今日
scripts/new_minutes.sh <slug> 2026-04-23   # 日付指定

# 手動の場合は TEMPLATE.md をコピーして命名規則に従うこと
cp docs/minutes/TEMPLATE.md docs/minutes/2026-04-23-foo.md
```

## Lint 実行

```bash
python scripts/lint_minutes.py                   # docs/minutes/ 全体
python scripts/lint_minutes.py docs/minutes/2026-04-23-foo.md
```

- exit 0: OK
- exit 2: 必須セクション欠落

CI に組み込む場合は pre-commit または lint ステップで `python scripts/lint_minutes.py` を呼ぶ。

## 保存期間と棚卸し

- **保存期間**: 原則**永久保存**する。容量は無視できるほど小さい。
- **撤回・訂正**: 一度書いた決定事項は**編集せず**、新しい議事録で差し戻す (追跡可能性を優先)。誤字などの軽微な修正は可。
- **年次棚卸し**: 毎年 4 月に未決事項を一覧し、解消済みのものは「解消日と参照先 ADR/Minutes」を末尾に追記する。

## 参考

- ADR 一覧: [`docs/adr/`](../adr/)
- テンプレート: [`docs/minutes/TEMPLATE.md`](../minutes/TEMPLATE.md)
- Lint スクリプト: [`scripts/lint_minutes.py`](../../scripts/lint_minutes.py)
- 生成スクリプト: [`scripts/new_minutes.sh`](../../scripts/new_minutes.sh)

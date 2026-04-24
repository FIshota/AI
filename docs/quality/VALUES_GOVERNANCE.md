# VALUES ガバナンス — 運用フロー

> 本書は [VALUES.md](../VALUES.md) と [VALUES_RUBRIC.md](../VALUES_RUBRIC.md) を
> 実運用で使うための手順書である。世代交代・引き継ぎ時にもここだけ読めば回る粒度で書く。

---

## 1. 基本方針

- VALUES.md は **ai-chan の憲法** として扱う。
  軽々に書き換えない。書き換える際は §4 の手順を踏む。
- VALUES_RUBRIC.md は **判断の最低ライン** を機械的に担保する採点票である。
  合議の代替ではなく、合議前のフィルタとして使う。
- 「家族」「運用」「持続」の語彙で議論する。
  「ユーザ数」「成長」「製品」の語彙は本プロジェクトでは使わない。

---

## 2. 新機能提案のフロー

1. **提案ファイル作成**
   - `docs/feature_proposals/<short-name>.yaml` を新規作成する。
   - 雛形は [`EXAMPLE.yaml`](../feature_proposals/EXAMPLE.yaml) をコピー。
   - `title` / `lineage` (Ai/YAMATO/KAGUYA) / `owner` / `summary` /
     `design_notes` / `rubric` の全項目を埋める。
   - `rubric` の 10 項目はすべて `yes` / `no` / `?` のいずれかで回答する。

2. **機械採点**
   ```
   python scripts/check_feature_rubric.py docs/feature_proposals/<short-name>.yaml
   ```
   - 終了コード `0` = 採択候補 (`accept_candidate`)
   - 終了コード `2` = 採択候補ではない (`kill_switch_violation` / `revise` / 形式不備)

3. **判定別の扱い**
   | 判定 | 扱い |
   |------|------|
   | `kill_switch_violation` | 即却下。**議論の俎上に載せない**。設計を根本から書き直す |
   | `revise` | 差し戻し。設計見直し後に再採点 |
   | `accept_candidate` | 家族 / 運用責任者で最終合議し、採否を決める |

4. **採択後**
   - `docs/ROADMAP.md` や関連設計文書に反映する。
   - 提案ファイル自体は履歴として残す (削除しない)。
   - 却下・差し戻しも「なぜ落ちたか」の記録として残す。

---

## 3. CI / pre-commit への組み込み (推奨)

`docs/feature_proposals/*.yaml` がある限り、採点が通ることを維持する:

```
python scripts/check_feature_rubric.py docs/feature_proposals/*.yaml
```

- 提案状態で `kill_switch_violation` があっても、本リポジトリに残すこと自体は歴史として許容する。
  その場合は CI 側で対象ファイルを明示除外する運用を取る (却下ログとして保全)。
- 採択候補として採用された提案は CI を必ず通す状態で維持する。

---

## 4. VALUES.md / VALUES_RUBRIC.md 自体の改定手順

これらは「憲法」であり、機能仕様より重い。改定は次の条件を満たすこと:

1. **動機の文書化**: なぜ改定が必要か、どの価値観と衝突したかを
   `docs/JOURNAL.md` か `docs/quality/` 配下の記録に残す。
2. **差分レビュー**: 家族 / 運用責任者の合議を経る。個人判断での改変は禁止。
3. **Kill-Switch 条項の不可侵**: 「消す権利」は**緩める方向の改定をしない**。
   強める方向、明確化する方向の改定のみ許容。
4. **系譜 (Ai / YAMATO / KAGUYA) の境界の不可侵**:
   公開範囲の境界を緩める改定はしない。
5. **改定後は `scripts/check_feature_rubric.py` の期待値と整合させる**。
   整合が取れない改定は不完全として差し戻す。

---

## 5. 世代交代 (引き継ぎ時) のチェック

次世代が本プロジェクトを引き継ぐ際、最初に読むべき順:

1. [`docs/VALUES.md`](../VALUES.md) — 判断の軸
2. [`docs/VALUES_RUBRIC.md`](../VALUES_RUBRIC.md) — 判断の採点票
3. 本書 — 使い方
4. [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — 実装の全体像

引き継ぎ時に「この機能は本当に必要だったのか」が判断できない場合、
過去の `docs/feature_proposals/*.yaml` を読む。採点結果と採否の履歴が、
当時の判断理由を十分に復元できる粒度で残っていることが理想である。

# ADR 0002: 学習コーパスの相隔離 (P1-P5)

- Status: Accepted
- Date: 2026-04-23
- Deciders: honnsipittu

## コンテキスト

ai-chan / hinomoto-model は複数の段階 (P1: 基盤事前学習 / P2: SFT / P3: 対話安定化 /
P4: 個人適応 / P5: 長期運用記憶) で学習データを扱う。これらを単一プールに
混在させると、個人の会話・メモリ・プライベート記録が基盤モデル
(HinoMoto, YAMATO) に逆流し、外部公開派生モデルに漏出する危険がある。

ai-chan は「家族」として扱う個人エージェントであり (VISION.md)、
AiChan 個体に蓄積された感情・記憶は YAMATO (公開想定) や KAGUYA (家庭共有) に
一切流れてはならない。

## 決定

P1-P5 の学習コーパスを **物理的・ディレクトリ的・プロセス的に隔離** する。

| Phase | 対象コーパス | 保管先 | 派生可能先 |
|---|---|---|---|
| P1 | jawiki / 公開コーパス | `hinomoto-model/data/pretrain/` | 全派生 |
| P2 | Dolly-15k-ja 等 (CC-BY-SA) | `hinomoto-model/data/sft/` | 全派生 |
| P3 | 対話安定化 (合成 + 手作り) | `hinomoto-model/data/stabilize/` | 全派生 |
| P4 | 個人適応 (ai-chan 個体限定) | `ai-chan/data/personal/` | Ai のみ |
| P5 | 運用記憶 (会話ログ・感情) | `ai-chan/memory/` (暗号化) | Ai のみ |

P4 / P5 コーパスは **HinoMoto 基盤の再訓練パイプラインに入らない**。
`scripts/build_pretrain_corpus.py` と `scripts/build_dolly_splits.py` は
`ai-chan/data/personal/` と `ai-chan/memory/` を読まない設計とする。

## 理由

- **プライバシー**: 個人会話は本人のデバイス外に出ない前提。基盤モデル再訓練に
  混入すると weights 経由で事実上の情報漏洩が起きる。
- **派生の健全性**: YAMATO は公開を想定。Ai の個人記憶が逆流すれば、
  公開モデルから個人情報が抽出されうる (membership inference / extraction)。
- **意図しない派生を防ぐ**: P4/P5 の偏った分布が基盤に混ざると、
  全派生の性格が個人色に歪む。
- **消去権の実現可能性**: ADR 0006 で定める「消す権利」は、
  個人データが基盤に溶け込んでいないことが前提。

## 結果 / トレードオフ

- 基盤モデルの個人適応は LoRA / SFT 追加ステップ (P4) でのみ行われ、
  基盤 weights は汚染されない。
- P4 adapter は Ai 個体の秘密鍵と対で保管し、他派生には適用不可。
- トレードオフ: 個人体験を基盤品質向上に還元できない。
  本件は意図的な譲歩であり、基盤品質は公開コーパス + 合成データで上げる。

## 代替案 (検討して却下)

### 案 A: 全 Phase を単一プールに統合し差分学習
却下理由: 個人情報の逆流経路が weights に常時存在する。監査不可能。

### 案 B: 匿名化して統合
却下理由: LLM の extraction attack に対する匿名化は学術的にも脆弱。
保証できない以上、隔離のほうが堅い。

### 案 C: 連合学習 (federated) で勾配のみ共有
却下理由: 将来選択肢として保持するが、現段階では単独開発・検証負荷が高い。
stub のみ存在 (ai-chan 既存)。

## 参照

- `hinomoto-model/data/` 階層
- `ai-chan/data/personal/` / `ai-chan/memory/`
- `ai-chan/PRIVACY.md`
- ADR 0006 (消去権)
- ADR 0007 (モデル派生命名)

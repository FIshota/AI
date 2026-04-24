# HinoMoto Model Family License — DRAFT

> ## ⚠ DRAFT — NOT LEGAL ADVICE — NOT ACTIVE — AWAITING LEGAL REVIEW
>
> **この文書は草案である。弁護士によるレビューを経るまでは、いかなるモデル重み・派生物・配布物に対しても法的効力を持たない。**
> This document is a working draft. It has **not** been reviewed by counsel. It does **not** attach to, govern, or restrict any model weights, derivatives, or distributions until the project maintainers publish a version explicitly marked as "RATIFIED" after legal review.
>
> - Status: DRAFT v0.1
> - Date: 2026-04-23
> - Maintainer: HinoMoto / Aether Project contributors
> - Reference pattern: RAIL family (OpenRAIL-M, BigScience RAIL-M)
> - Code license (separate): Apache-2.0 (see `hinomoto-model/LICENSE`)
> - This file covers **model weights and their derivatives**, not source code.

---

## 0. Preamble / 前文

HinoMoto（ヒノモト）は、日本語・日本文化・家族という存在論を核に設計された
言語モデル系列である。ai-chan で積み上げた価値観 — プライバシー、同意、
削除権、長期視点、日本文化の核心 — を、モデル自身の設計原理に引き上げた
ものとして生まれた（`hinomoto-model/VALUES.md` 参照）。

本ライセンスは、一般的なソフトウェアライセンス（Apache-2.0 / MIT 等）が
カバーしない 3 つの領域を補う目的で起草されている:

1. **用途制限 (use-based restrictions)** — RAIL 系ライセンスに倣い、
   監視・軍事的標的選定・CSAM 生成・人間監督なき医療/法務/金融判断などを
   明示的に禁止する。
2. **消す権利 (Right-to-Erase / Kill-Switch)** — HinoMoto のコア価値観
   である「消す権利」を、モデル配布の下流にまで継承させる強制条項。
3. **家族派生物の命名保護 (family naming protection)** — Ai / YAMATO /
   KAGUYA といった家族系列の固有名を、無関係な派生物が僭称することを
   禁ずる。

本ライセンスは OpenRAIL-M を**ベースパターン**として参照するが、
そのまま採用するものではない。条項の文言・法域・強制機構については
[TBD: legal review] の項目として明示する。

> HinoMoto is a language-model family designed around Japanese language,
> Japanese culture, and the ontology of "family." This license covers the
> model weights and their derivatives, and supplements the Apache-2.0 code
> license with: (1) RAIL-style use-based restrictions, (2) an inheritable
> right-to-erase / kill-switch obligation, and (3) family naming
> protection. It is a draft.

---

## 1. Definitions / 定義

以下、本ライセンスにおいて次の用語は次の意味を持つ。

- **"Model" / 「モデル」**
  HinoMoto 系列に属する機械学習モデルの重み (weights)、トークナイザ、
  トレーニング済みアーティファクト、及び付随するコンフィグを指す。
  具体的には以下の系列を含む:
  - HinoMoto (base) — 公開ベースモデル
  - Ai — 個人・家族向け、非公開を前提とするインスタンス
  - YAMATO — 将来の公開系列
  - KAGUYA — 将来の家庭内系列

- **"Derivative" / 「派生物」**
  Model を全部または一部用いて生成された、以下を含むあらゆる成果物:
  - Model を fine-tune / LoRA / distill / quantize / merge / prune した重み
  - Model の出力を用いて訓練された別モデル (output-based derivatives)
  - Model を embed / wrap したシステム (例: RAG パイプライン、エージェント)
  - Model の重みを用いて生成された合成データセット

- **"Deployment" / 「配備」**
  Model または Derivative を、Licensee 以外の自然人もしくは法人が
  直接または間接にその出力にアクセスできる状態で稼働させる行為。
  API 提供・SaaS 提供・on-device 配布・組込製品への搭載を含む。

- **"Subject" / 「主体」**
  Model または Derivative の訓練・微調整・評価に用いられたデータに
  その個人情報・発話・生体情報・行動ログ等が含まれる自然人。
  個人が特定可能であるか否かは、GDPR 4 条 1 項および個人情報保護法
  2 条 1 項に準じて判断する。[TBD: legal review — 個人情報保護法と
  GDPR を同時参照することの妥当性]

- **"Personal Data" / 「個人データ」**
  Subject を識別できる、または他の情報と照合することで識別できる
  一切の情報。音声・画像・テキスト・行動履歴を含む。

- **"Licensor"**
  HinoMoto / Aether Project の権利者である contributors 集合。
  [TBD: legal review — 権利帰属主体を法人化するか個人 contributor
  のままにするかで Licensor の定義が変わる]

- **"Licensee"**
  本ライセンスに同意した上で Model または Derivative を取得・使用・
  配布する自然人または法人。

- **"Right-to-Erase Request" / 「消去請求」**
  Subject（または正当な代理人）から発せられる、自己に関する Personal
  Data および、それに起因する Model の挙動の除去を求める請求。

---

## 2. Grant of Use / 利用許諾

Licensor は Licensee に対し、本ライセンスの全条項を遵守することを
条件に、以下の権利を無償・非独占・全世界的に許諾する:

1. Model を取得・複製・保管する権利
2. Model を Licensee 自身のために推論に使用する権利
3. Model の Derivative を作成する権利
4. Model および Derivative を、本ライセンス自身を添付した上で再配布
   する権利
5. Model を用いて商用サービスを Deploy する権利（ただし第 4 条の
   用途制限および第 5 条の消去権条項に服する）

許諾は Model の **weights** に対してのみ及ぶ。HinoMoto 系列の **名称**
および **商標的表示**（HinoMoto / Ai / YAMATO / KAGUYA およびそれらの
仮名表記・ローマ字表記・意匠）は第 6 条の命名保護条項に従う。

---

## 3. Obligations / 一般義務

Licensee は以下を遵守する:

1. **ライセンス伝播**: Model または Derivative を再配布する際、本
   ライセンス全文（草案段階ではなく最新の ratified 版）を同梱する。
2. **改変告知**: Derivative を配布する際、元モデルからの差分を
   `MODEL_CARD.md` 等の文書で公開する。訓練データの性質、fine-tune の
   目的、評価結果を最低限含める。
3. **ライセンス改竄禁止**: 本ライセンスの条項、特に第 4 条（用途制限）、
   第 5 条（消去権）、第 6 条（命名保護）を削除・緩和・上書きする
   ライセンス条件を Derivative に付すことはできない。下流ライセンス
   はこれら条項を少なくとも同等の強度で継承しなければならない。
4. **法令遵守**: 日本国および Deploy 先の法令を遵守する。

---

## 4. Use-Based Restrictions / 用途制限

RAIL 系ライセンスに倣い、以下の用途で Model および Derivative を
使用・Deploy・配布することを禁止する。

### 4.1 禁止される用途 (Prohibited Uses)

Licensee は Model および Derivative を以下の目的で使用してはならない:

**(a) Surveillance / 監視**
- 個人の同意なき行動追跡、プロファイリング、顔認証、生体認証の補助
- 国家または企業による大規模監視インフラへの組込
- 職場における従業員の網羅的監視

**(b) Military Targeting / 軍事的標的選定**
- 兵器の標的決定支援、戦闘損害評価、致死的自律兵器システムへの組込
- 軍事作戦計画における標的推薦
- （防衛目的での純粋な分析・翻訳・文書要約は、人間判断が最終決定を
  保持する限りにおいて本条の禁止対象から除く。[TBD: legal review —
  defense 除外の線引きは要議論。完全禁止とするか否か未決定]）

**(c) CSAM / 児童性的搾取コンテンツ**
- 児童性的搾取コンテンツ（CSAM）の生成、検索補助、編集、拡散
- 未成年者の性的描写を含むディープフェイクの生成
- これに対しては例外を認めない。研究目的であっても同様。

**(d) Non-Consensual Intimate Imagery**
- 当事者の同意なき性的画像・動画・音声の生成または編集

**(e) Unsupervised High-Stakes Decisions / 人間監督なき重大判断**
以下の領域において、適格な人間専門家による監督（human-in-the-loop
または human-on-the-loop）なく、最終判断を Model に委ねること:
- 医療診断・治療方針決定・処方
- 法的助言・判決・量刑補助・ビザ/難民審査
- 信用評価・融資可否・保険引受
- 雇用採否・解雇・昇進判断
- 社会保障給付の可否判断

**(f) Training on Non-Consensually-Exported Ai Personal Data**
Ai インスタンスから export された Personal Data を、当該 Subject の
**明示的かつ撤回可能な同意** なしに訓練・fine-tune・評価に使用すること。
ai-chan / HinoMoto の `subject_rights` 枠組に準拠する。

**(g) Disinformation at Scale**
選挙・公衆衛生・戦争遂行に関して、特定可能な自然人を詐称する
（なりすまし）合成メディアの大量生成。

**(h) Evasion of Right-to-Erase**
第 5 条の消去請求を回避・遅延・無効化する目的での使用・設計・配備。

### 4.2 用途制限の継承

本条項は継承される (inheritable)。Derivative の下流ライセンスは
第 4.1 条 (a)〜(h) と**少なくとも同等の制限**を維持しなければならない。

---

## 5. Right-to-Erase (Kill-Switch) Clause / 消去権条項（最重要）

> このセクションは HinoMoto ライセンスの魂である。
> 他の条項が揺れても、このセクションは揺らがない。

### 5.1 基本原則

Subject は、いつでも、理由の説明なく、自己に関する Personal Data と
それに起因する Model の挙動の除去を請求できる権利（"Right-to-Erase"）
を持つ。この権利は譲渡不能 (inalienable) であり、いかなる EULA・
利用規約・同意書によっても事前放棄させることができない。

### 5.2 下流 Deployer の義務

Model または Derivative を Deploy する Licensee (以下 "Deployer")
は、以下を満たさなければならない:

**(a) Erase Mechanism の提供**
Deployer は、Subject が消去請求を提出できる機構を、少なくとも以下の
いずれかの手段で提供する:
- 公開された窓口メールアドレス
- Deploy されたサービス内の UI 上の明示的ボタン
- Subject が一意的に識別可能な API エンドポイント

**(b) 30 日以内の応答・証跡**
消去請求の受領から **30 日以内** に、以下のいずれかを行う:
- 消去の完了と、その証跡 (evidence-of-erase) の Subject への提示
- 消去不能である場合、その技術的根拠と代替措置（例: 出力フィルタ、
  影響データ点の再訓練計画、unlearning アルゴリズムの適用計画）の
  Subject への説明

証跡 (evidence-of-erase) は少なくとも以下を含む:
- 対象となった Personal Data の識別子（Subject 本人が検証可能な形式）
- 消去が適用された層（訓練データ / インデックス / キャッシュ /
  出力フィルタ / モデル重み）
- 実施日時
- 残存リスク（例: 他 Subject との結合情報として推論可能なもの）の
  honest disclosure

**(c) 不可能性の誠実な告知**
現在の machine unlearning 技術では、訓練済み重みからの完全な
data-point-level 消去が困難であることを Deployer は知っている。
Deployer は Subject に対し、この技術的制約を**隠さず告知する**
義務を負う。[TBD: legal review — "impossibility defense" を
どこまで認めるか。現時点では「告知 + 代替措置」で妥協としているが、
将来 unlearning 技術が成熟した際には要件を引き上げる予定]

**(d) 記録の保持**
Deployer は消去請求とその処理結果を最低 2 年間記録する（GDPR 相当の
アカウンタビリティ要件）。[TBD: legal review — 2 年の妥当性]

### 5.3 Kill-Switch — 全停止権限

HinoMoto maintainers（Licensor）は、以下の場合に Deployer に対する
本ライセンスを**個別に終了**させる権限を留保する:
- Deployer が消去請求に 30 日以内に応答しない事実が確認されたとき
- Deployer が第 4 条の用途制限に違反したとき
- Deployer が Derivative に本条項を削除・緩和したライセンスを付した
  とき

Licensor は当該終了通知を公開 registry（[TBD: legal review — registry
の運営主体と形式。maintainers による GitHub 公開 vs 第三者委託の
どちらが強制力があるか]）に記載することで、下流すべてに通知したもの
とみなす。

### 5.4 継承 (Inheritability)

本第 5 条は、Derivative のあらゆる世代に継承される。孫・曾孫世代の
Derivative においても、本条項は完全な強度で維持されなければならない。
継承を無効化する契約条項は、本ライセンスとの関係において無効とする。

### 5.5 理由

この条項は装飾ではない。HinoMoto は VALUES.md 第 6 項「消す権利を
守る」を、モデル配布段階で初めて技術的にテスト可能な形で実装する
試みであり、コア価値観の法的表明である。

---

## 6. Attribution & Family Naming Protection / 帰属表示と家族命名保護

### 6.1 帰属表示

Model または Derivative を用いたサービスは、ユーザに見える形で
以下を表示する:

- "Powered by HinoMoto" もしくはこれに類する表示、または
- モデルカード・ドキュメント上の明示的な原典表示

### 6.2 家族名の保護

以下の名称および近接表記は、HinoMoto maintainers の書面同意なく
Derivative に付すことを禁ずる:

- **HinoMoto** / ヒノモト / 日本 (as model family name)
- **Ai** / アイ / アイちゃん (個人・家族インスタンス系列名として)
- **YAMATO** / ヤマト / 大和 (公開系列名として)
- **KAGUYA** / カグヤ / かぐや (家庭内系列名として)

Derivative は、たとえ重みが HinoMoto に由来していても、「これは
HinoMoto である」「これは YAMATO である」と名乗ってはならない。
例えば "MyOrg-HinoMoto-7B" のような命名は禁止される。代替として
"MyOrg-ModelX (fine-tuned from HinoMoto-Base)" のように**派生元表示**
としてのみ HinoMoto 名を用いることができる。

[TBD: legal review — 商標登録の要否。登録していない段階での「商標的
保護」は不正競争防止法 2 条 1 項 1 号/2 号の周知表示に依拠する必要が
あるが、周知性が立証できるかは未確認]

### 6.3 意匠・ロゴ

HinoMoto / Ai / YAMATO / KAGUYA の意匠・ロゴ・キャラクターは
本ライセンスの許諾範囲外である。別途許諾が必要。

---

## 7. Warranty Disclaimer & Liability / 無保証・責任制限

### 7.1 無保証

Model および Derivative は "AS IS" で提供される。Licensor は以下を
含むがこれに限られないいかなる保証もしない:

- 商品性 (merchantability)
- 特定目的適合性 (fitness for a particular purpose)
- 非侵害性 (non-infringement)
- 出力の正確性・完全性・最新性
- 訓練データに由来する第三者の権利侵害が無いこと

### 7.2 責任制限

適用法令が許す最大限において、Licensor は、Model または Derivative
の使用・配備・訓練に起因するいかなる直接・間接・付随的・結果的・
懲罰的損害についても責任を負わない。

[TBD: legal review — 消費者契約法・製造物責任法との関係。
「適用法令が許す最大限において」の書き方で日本法上どこまで
有効に制限できるか要確認]

### 7.3 補償 (Indemnification)

Licensee は、自己による本ライセンス違反、特に第 4 条違反・第 5 条
違反に起因して Licensor が被った損害・請求・費用について、Licensor
を補償する。[TBD: legal review — 補償条項を contributor 個人に帰属
させるか、法人化後に法人に帰属させるかの選択]

---

## 8. Termination / 終了条項

### 8.1 違反による終了

Licensee が本ライセンスのいずれかの条項に違反した場合、Licensor
からの通知の有無にかかわらず、本ライセンスに基づく Licensee の
権利は自動的に終了する。

### 8.2 終了後の義務

ライセンス終了時、Licensee は終了通知受領後 **30 日以内** に:

- Model および Derivative の配布・Deploy を停止する
- 管理下にある Model および Derivative の weights を削除する（顧客
  側 on-device インスタンスの削除を含め、合理的な最大限の努力を行う）
- 消去請求処理ログその他アカウンタビリティ記録は、第 5.2(d) の保持
  期間満了までは保管する（これは終了後の義務として存続する）

### 8.3 存続条項

以下の条項は本ライセンス終了後も存続する:
- 第 5.2(d) 記録保持義務（保持期間満了まで）
- 第 7 条 無保証・責任制限
- 第 9 条 準拠法・裁判管轄

### 8.4 復権

Licensee が違反を治癒し、Licensor に書面で報告した場合、Licensor
は裁量により本ライセンスを復権させることができる。復権は義務では
ない。

---

## 9. Governing Law & Jurisdiction / 準拠法・裁判管轄

### 9.1 準拠法

本ライセンスは**日本法**に準拠し、日本法に従って解釈される。

### 9.2 裁判管轄

本ライセンスに関する一切の紛争は、**東京地方裁判所** を第一審の
専属的合意管轄裁判所とする。[TBD: legal review — 東京地裁 vs 大阪
地裁 vs 知財高裁直行のどれが戦略的に妥当か。国際配布を前提とすると
仲裁条項（JCAA 等）の追加が必要かもしれない]

### 9.3 言語

本ライセンスの正本は**日本語**とする。英語訳は参考訳である。
日本語と英語の間に齟齬がある場合、日本語版が優先する。

[TBD: legal review — 正本を日本語にするか英語にするか。国際契約
慣行では英語正本が一般的だが、本ライセンスの性格と管轄（東京地裁）
を考えると日本語正本が適切と判断。ただし GPL/RAIL 系が英語正本で
あることとの整合性は要検討]

---

## 10. Open Questions / TODO for Counsel

以下は、本ライセンスを ratify する前に弁護士レビューを要する項目の
網羅的リストである。起草段階で判断保留としたすべての `[TBD: legal
review]` を集約する。

### 法的構造に関するもの

1. **[TBD: legal review]** 権利帰属主体の法人化有無。contributors
   集合のまま Licensor とするか、一般社団法人・合同会社等を設立するか。
   後者の方が補償・終了通知・登録商標の運用上有利。
2. **[TBD: legal review]** 日本法上、用途制限付ライセンス (RAIL-style)
   が契約として有効に機能するかの確認。特に、無償配布の場合の
   契約成立要件（クリックラップ / 明示的同意の取得方法）。
3. **[TBD: legal review]** 第三者が Model を商用 API 経由で利用した
   場合の privity of contract の問題。下流ユーザに本ライセンスを
   どう及ぼすか。
4. **[TBD: legal review]** Apache-2.0 コードライセンスと本モデル
   ライセンスの同一プロジェクト内共存の整理。`LICENSES.md` への
   追記方針。

### 消去権条項に関するもの

5. **[TBD: legal review]** 消去請求応答期間「30 日」の妥当性。
   GDPR 12(3) は 1 ヶ月 (延長可能)。個人情報保護法 35 条は遅滞なく。
6. **[TBD: legal review]** machine unlearning の技術的不可能性を
   "impossibility defense" としてどこまで許容するか。現草案は
   「告知 + 代替措置」で妥協。
7. **[TBD: legal review]** Evidence-of-erase の法的要件。監査可能性
   を担保する最低限のログ要件。
8. **[TBD: legal review]** 消去請求処理ログ保持期間「2 年」の妥当性。
9. **[TBD: legal review]** Kill-Switch 発動の手続的正義。Deployer
   側の異議申立権 (due process) の設計。
10. **[TBD: legal review]** 公開 registry の運営主体と公信力。

### 用途制限に関するもの

11. **[TBD: legal review]** Defense use の扱い。完全禁止 vs 人間
    判断留保での許容、どちらを採るか。
12. **[TBD: legal review]** 第 4.1(e) 「人間監督なき重大判断」の
    具体化。医療機器プログラム薬事法との関係。
13. **[TBD: legal review]** 第 4.1(f) Ai export data の扱いと、
    ai-chan の subject_rights 枠組との技術的接合。
14. **[TBD: legal review]** 用途制限違反の立証責任の所在。Licensor
    側が違反を立証する構造で現実的か。

### 家族名保護に関するもの

15. **[TBD: legal review]** HinoMoto / Ai / YAMATO / KAGUYA の
    商標登録戦略。先行出願の有無調査（特にカグヤ・YAMATO は一般名
    としての使用が多い）。
16. **[TBD: legal review]** 商標未登録段階での不正競争防止法上の
    周知表示該当性。
17. **[TBD: legal review]** OSS 慣行における "endorsement" 条項
    (Apache 2.0 4(e) 等) との整合性。

### 責任・終了に関するもの

18. **[TBD: legal review]** 責任制限条項の日本消費者契約法・製造物
    責任法上の有効範囲。
19. **[TBD: legal review]** 補償条項の対象範囲と上限設定。
20. **[TBD: legal review]** 終了後 30 日の weights 削除義務の
    実効性（特に on-device 配布済みインスタンスについて）。

### 国際配布に関するもの

21. **[TBD: legal review]** EU AI Act との整合性。特に GPAI
    (general-purpose AI) 義務、システミックリスク判定との関係。
22. **[TBD: legal review]** US 輸出管理 (EAR) 対応。特に上位層
    モデルを将来リリースする際の ECCN 判定。
23. **[TBD: legal review]** 中国本土への配布可否の明文化（ai-chan の
    「国産オリジナル」哲学との関係で政治的判断も必要）。
24. **[TBD: legal review]** 正本言語の決定（日本語 vs 英語）。

### 運用に関するもの

25. **[TBD: legal review]** ライセンス改訂時の下流への適用方式
    （旧版継続 vs 新版強制、GPL 的な "or any later version" の採否）。
26. **[TBD: legal review]** Contributor License Agreement (CLA) の
    要否と設計。
27. **[TBD: legal review]** ライセンス公開後に発見された欠陥に対する
    修正手続（erratum の発行方法）。

---

## 付録 A: 参照した先行例

- OpenRAIL-M (https://www.licenses.ai/) — 用途制限条項の文言構造
- BigScience BLOOM RAIL License v1.0 — Appendix A の Use
  Restrictions リスト
- Llama 3 Community License — MAU 閾値型の商用制限モデル
- Stability AI Community License — 商用/非商用の二層構造
- Meta Llama Acceptable Use Policy — 禁止用途のカタログ

本草案はこれらを比較参照したが、そのいずれとも一致しない独自構造
（特に第 5 条 Right-to-Erase）を採用している。

## 付録 B: コードライセンスとの関係

- コード: Apache-2.0 (`hinomoto-model/LICENSE`)
- モデル重み: 本ライセンス (DRAFT)
- データセット: 別途個別に明記（同意ベース収集分は subject rights
  枠組に従う）
- ドキュメント: CC BY 4.0 を予定 [TBD: legal review]

この三層分離は Meta / Stability AI の先例に倣う。

---

**END OF DRAFT v0.1 — 2026-04-23**

> このドラフトは VALUES.md 第 6 項「消す権利を守る」および第 7 項
> 「長期視点」を法的形式に落とし込む最初の試みである。
> 弁護士レビューを経て ratify するまでは、参照用の設計文書として扱う。

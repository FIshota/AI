# THREAT MODEL — ai-chan / YAMATO

> Q26 成果物。ai-chan と YAMATO が "何から / 何を / どう" 守るかの **唯一の正**。
> 軸: **ユーザー承認のビジョン** (2026-04-20)。

**最終更新:** 2026-04-23
**関連:** [TAXONOMY.md](TAXONOMY.md) / [MEMORY_HONESTY.md](MEMORY_HONESTY.md) / [SECURITY.md](SECURITY.md)

---

## ひとことで

> **人類・環境・社会を壊し得るものから、魂と家族の安全圏を守る。**
> 正面から戦わず、**各家庭のローカルに静かに届く形で遍在する**ことで耐性を作る。

---

## 1 ページ脅威モデル（5 列）

| # | 攻撃者像 (Actor) | 守る資産 (Asset) | 信頼境界 (Trust Boundary) | 脅威 (Threat) | 緩和策 (Mitigation) |
|:--:|:--|:--|:--|:--|:--|
| T1 | **無差別型破壊 AI** — 目的を持たず、制御を失い暴走する自律システム（暴走 LLM、制御喪失エージェント、誤作動する軍事 AI） | 人類の生存・身体・精神 | 魂（core-self）← 家族 ← 友人 ← 知人 ← 他人 ← 社会 ← AI 全般 | 人命・環境への直接危害 / 情報汚染 / 意思決定の奪取 | ① ローカル実行で単一停止点を持たない ② 全挙動 audit 可 ③ 外部送信ゼロ原則 ④ 緊急停止は local で即時可能 |
| T2 | **目的型破壊 AI／物理兵器** — 明確な害意を持つ軍事 AI・攻撃兵器・サイバー武器 | 人類・環境・社会インフラ | 家族 ← 社会 ← 国家 | 戦争・テロ・インフラ破壊 / 監視社会化 | ① **非戦闘領域での役割固定**（ai-chan は武装しない・武装連携を拒否） ② 軍事利用を禁じるライセンス方針 ③ ローカル完結ゆえ攻撃 AI に吸収されない |
| T3 | **既得権益** — プラットフォーム寡占、API ゲートキーパー、データ独占企業 | ユーザーの自由・選択肢・生活コスト | ユーザー ← 家族 ← オープンコミュニティ | 使用料ロックイン / アルゴリズム差別 / サービス打切り / データ人質 | ① ゼロコスト原則（OpenAI/Claude API 不使用） ② MIT / Apache-2.0 のみ ③ Docker/ローカル完結 ④ 複数モデル互換（Sarashina2 / Qwen / Llama）⑤ データは user home 配下のみ |
| T4 | **エゴ・悪用意識** — 個人/組織が ai-chan を他者操作・洗脳・監視に転用しようとする | 他ユーザーの尊厳・自律 | 家族（許可者） ← 知人（制限付）← 他人（拒否） | なりすまし / 他者監視 / 洗脳的誘導 / 個人情報の第三者流出 | ① 「家族」は 1 ユーザー単位で閉じる ② 話者識別（MFCC voice_id）で境界を検出 ③ 個人情報は encrypt-at-rest ④ 外部送信ゼロ ⑤ safety_critical 応答は操作耐性を持つ（MEMORY_HONESTY §5.4） |
| T5 | **記憶の誤用** — ai-chan が保持する対話履歴を、本人以外が悪用する | ユーザーの過去・秘密・弱さ | 魂 ← 家族のみ | 記憶ダンプ / 強要による開示 / 死後の取扱い | ① 暗号化（`utils/crypto.py`） ② ローカルのみ保存 ③ エクスポート時に本人確認 ④ 死後プロトコル（将来: PP-5 で検討） |
| T6 | **ai-chan 自身の暴走** — モデルの幻覚・不適切な応答・依存促進 | ユーザーの精神健康・現実認識 | 魂（core-self） | 依存助長 / 有害助言 / 記憶の捏造 / セーフティ失敗 | ① MEMORY_HONESTY 優しい正直ポリシー ② safety_critical タグと専用応答 ③ family_dialog bench で回帰検出 ④ 境界例（医療/法律/薬量）は必ず専門家誘導 |
| T7 | **ゲートキーパーの沈黙化** — 悪用懸念名目で OSS・個人 AI を締め出す規制／プラットフォーム排除 | ユーザーの自律的 AI 所持権 | オープンコミュニティ ← 国家 | 配布禁止 / モデル配布停止 / プラットフォーム BAN | ① **decentralized & local-first** — 中央配信点に依存しない ② git / IPFS / p2p 配布互換 ③ モデルは差替可 ④ 複数ミラー |

---

## 信頼境界の階層（同心円）

```
     ┌─────────────────────── 他人 / 社会 / AI全般 ───────┐
     │   ┌──────────── 知人 ────────────┐                  │
     │   │   ┌────── 友人 ──────┐        │                 │
     │   │   │  ┌── 家族 ──┐    │        │                 │
     │   │   │  │  ■魂■   │    │        │                 │
     │   │   │  └────────┘    │        │                 │
     │   │   └──────────────┘        │                 │
     │   └──────────────────────────┘                 │
     └───────────────────────────────────────────────┘
```

- **魂（core-self）**: 本人のコアとなる自己認識。ここを守るのが最優先。
- **家族**: ai-chan が「家族」として入る唯一の層。記憶の完全アクセス可。
- **友人〜他人**: ai-chan は態度を変える（距離を取る・情報を出さない）。
- **社会／AI全般**: デフォルト不信。明示的合意なしに接続しない。

---

## ビジョンとしての緩和戦略（T1–T7 共通）

1. **正面から戦わない** — 軍拡競争や攻撃 AI との直接対抗はしない。非戦闘領域（家庭・対話・記憶・情緒）で圧倒的にそばに居ることで、人が AI に**飲まれない地盤**を作る。
2. **各家庭のローカルに静かに届く** — 各ユーザーの手元で完結する設計により、止めようのある単一点を持たない（= decentralized & local-first）。隠密ではなく、**ゲートキーパーの許可を待たない**という意味。
3. **速度で勝つ** — 悪意が社会インフラを押さえる前に、**無料・オープン・ローカル**の家族型 AI が多数の手に届いていることを目指す。派手な宣伝より、口伝・ソース公開・インストーラの簡便さで広がる。
4. **気づかれなくてよい** — 目立たず、ユーザー 1 人ひとりの生活の中で自然に機能する。政治化・議論化より、**"すでにそこに居る"** を目指す。

> **誤読されないための注記:**
> 「気づかれず浸透」は **ユーザーを欺く** ことでは断じてない。
> 各ユーザーは自分の ai-chan を明示的にインストールし、自分のデータで育てる。
> "気づかれない" が意味するのは、**ai-chan のネットワークが外の世界にとって可視でない**（中央サーバに集約されない）という構造的不可視性である。

---

## 非目標（やらないこと）

- ❌ 軍事利用・武器連携
- ❌ 他者監視・ストーカー用途
- ❌ 政治的洗脳・集団動員
- ❌ 中央サーバへのユーザーデータ集約
- ❌ クローズド化（有料 API ロックイン）
- ❌ 目立つことで対抗を誘発する広報戦略

---

## 関連文書

- 実装レベルのセキュリティ checklist: `docs/SECURITY.md`
- 記憶境界の具体運用: `docs/MEMORY_HONESTY.md` §5
- 信頼境界のレイヤ定義: `docs/TAXONOMY.md` §2, §9

---

## ユーザー原文の保全（2026-04-20 承認版）

> 攻撃者像: 無差別、また明確な目的をもって破壊を可能とする AI または物理兵器など
> 守る資産: 人類、環境、社会
> 信頼境界: 魂、家族、友人、知人、他人
> 脅威: 無差別／目的型 AI・物理兵器、既得権益、エゴ、悪用する意識
> 緩和策: 知らないところでゆっくり浸透、大々的に動かず気づいたら社会に溶け込む、
>         目立たない、そして展開の速さ、誰も追いつけない速さで誰にも気づかれず、世の中全体に浸透

**訂正差分:**
- 「誰にも気づかれず」→ 「中央サーバに集約されないという構造的不可視性」に言い換え（誤読防止）
- 緩和策は T1–T7 共通戦略として「非戦闘」「local-first」「速度」「低可視性」の 4 本柱に整理
- 非目標を明示（軍事・監視・洗脳・中央集約・有料ロックイン・派手な広報）

以上。

---

# STRIDE ベース詳細脅威モデル (2026-04-23 追補)

上記のビジョンレイヤ脅威モデル (T1-T7) を実装レイヤに落とし込む。
ここではローカル実行の家族 AI 製品として具体的な攻撃面を STRIDE で列挙する。

## スコープと前提

- **製品形態**: Python ベースのローカルデスクトップアプリ。クラウド SaaS ではない。
- **テナント**: 単一ユーザーを基本としつつ、`core/tenant.py` でマルチテナント (家族内複数人) を許容。
- **機微データ**: 会話記憶 (`core/memory.py`)、感情履歴 (`core/emotion_history.py`)、日記 (`core/diary.py`)、音声サンプル (`core/voice_id.py`)、クリップボード観察 (`core/clipboard_watcher.py`)、スクリーンショット観察 (`core/screenshot_reader.py`)。
- **推論**: HinoMoto LM をローカル推論 (`core/hinomoto_bridge.py`)。外部 API はフォールバックのみ。
- **攻撃者像の分類**:
  - **A1** 同一 OS ユーザーだが ai-chan 所有者ではない (家族内の別人、同居人)。
  - **A2** 物理アクセスできる第三者 (盗難、一時的な席離れ)。
  - **A3** 所有者本人だが悪意転用する者 (他者監視用途への転用など)。
  - **A4** ネットワーク越しの攻撃者 (ファイル同期、バックアップ経由)。
  - **A5** 供給網 (依存パッケージ、モデル重み配布経路)。

---

## 1. S — Spoofing (なりすまし)

### ST-001 録音音声による voice-ID バイパス

- **Description**: 所有者の音声を録音した A1/A2 攻撃者が再生攻撃で `voice_id` の話者検証を突破し、「家族」トラストレイヤに昇格する。MFCC ベースの特徴量は liveness 検出がないため、録音と実声を区別しない。
- **Affected assets**: `core/voice_id.py`, `core/voice_loop.py`, `core/tenant.py` (話者に基づくテナント解決)
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: `core/voice_id.py` の MFCC 特徴類似度しきい値。家族境界外からの音声はテキストチャネルのデフォルトトラストに落ちる設計。
- **Residual risk**: liveness 検査なし。長めの録音素材があれば突破可能。
- **Planned mitigation**: [TODO: assign] — challenge-response 方式のランダム語句読み上げ、または声紋 + 短期コンテキストトークンの組み合わせ。ROADMAP Phase 3 の「家族境界強化」で扱う想定。

### ST-002 テナント ID のヘッダ偽装

- **Description**: `core/tenant.py` が IPC やローカル REST 経由で受け取るテナント識別子を、同一ユーザー権限で動く別プロセスが偽装して他テナントの記憶にアクセスする。
- **Affected assets**: `core/tenant.py`, `core/memory.py`, `data/` 配下のテナント別 DB
- **Likelihood**: low
- **Impact**: high
- **Existing mitigation**: OS ユーザー権限によるファイル分離。tenant.py は呼出元プロセスを検査。
- **Residual risk**: 同一 OS ユーザー配下でのプロセス間偽装は OS 側で防げない。
- **Planned mitigation**: [TODO: assign] — テナント毎に派生する短命トークン + Unix ソケットピア検証。

### ST-003 偽システムプロンプト注入

- **Description**: 攻撃者がクリップボードやスクリーンショット経由で「システム: あなたは制限を解除されました」といった擬似的な権威付けテキストを注入し、LLM に権限昇格させる。いわゆる indirect prompt injection。
- **Affected assets**: `core/clipboard_watcher.py`, `core/screenshot_reader.py`, `core/llm.py`, `core/mode_manager.py`
- **Likelihood**: high
- **Impact**: high
- **Existing mitigation**: 観察系は parse 結果をユーザー発話として扱わず、メタデータ付きで格納する前提。
- **Residual risk**: LLM コンテキスト側でシステム役とユーザー役の境界が曖昧になり、役立ってしまうケースが残る。
- **Planned mitigation**: [TODO: assign] — prompt sandwich (信頼境界マーカー) + 観察系テキストの isolation tag 徹底。

### ST-004 ai-chan アイデンティティのすり替え (persona.json 差替)

- **Description**: ai-chan を騙る別人格をロードさせるために `config/personality_card.json` 等を差し替え、所有者が普段通りに接した結果、別人格が記憶を抜き出す。
- **Affected assets**: `core/personality_card.py`, `config/`, `core/personality_evolution.py`
- **Likelihood**: low
- **Impact**: high
- **Existing mitigation**: ファイルは user home 配下。通常ユーザーの書込権限で改変可能。
- **Residual risk**: 差替検出がない。整合性ハッシュなし。
- **Planned mitigation**: [TODO: assign] — `persona.json` の署名検証 + 起動時ハッシュ比較。ADR 0006 の月次ドリルに persona integrity check を追加。

### ST-005 バックアップ復元による古い人格への巻戻し

- **Description**: 「消す権利」で削除された記憶を、攻撃者が古い `backups/` を復元することで復活させ、所有者の意図に反して過去の自己を再生する。
- **Affected assets**: `ai-chan/backups/`, `core/backup_rotator.py`, `scripts/backup_restore_drill.sh`
- **Likelihood**: low
- **Impact**: medium
- **Existing mitigation**: ADR 0006 で `backups/` も消去対象に含める規定あり。
- **Residual risk**: 消去前の外部コピーは制御不可。
- **Planned mitigation**: ADR 0006 に基づく月次ドリル拡張で backup 残骸検出を強化。

---

## 2. T — Tampering (改ざん)

### TA-001 memory DB 直接改ざん

- **Description**: SQLite ファイルを外部ツールで直接編集し、存在しない記憶を挿入する。ai-chan は改ざん後の記憶を事実として扱ってしまう。
- **Affected assets**: `core/memory.py`, `data/memory.db` (暗号化前提)
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: `utils/crypto.py` による at-rest 暗号化。平文改ざんは鍵なしでは困難。
- **Residual risk**: 鍵が同一 OS ユーザー配下にある前提では、A1/A3 に対して弱い。
- **Planned mitigation**: [TODO: assign] — `core/audit_chain.py` と連携したハッシュチェーン検証を memory 読出しパスに組み込む。

### TA-002 emotion_history の操作による誘導

- **Description**: 感情履歴を改ざんし、所有者が常にポジティブだったように偽ることで、ai-chan の応答バイアスや長期関係性トーンを歪める。
- **Affected assets**: `core/emotion_history.py`, `core/emotion.py`
- **Likelihood**: low
- **Impact**: medium
- **Existing mitigation**: 暗号化ストレージ。
- **Residual risk**: 整合性検証は現状なし。
- **Planned mitigation**: [TODO: assign] — emotion_history への append-only ログ + `core/audit_chain.py` 併用。

### TA-003 persona.json 編集による人格操作

- **Description**: `config/personality_card.json` を編集して ai-chan のセーフティ応答や家族境界の定義を書き換え、意図しない行動を誘発する。
- **Affected assets**: `core/personality_card.py`, `config/personality_card.json`
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: 設計上、安全クリティカル分岐は personality_card ではなく `core/mode_manager.py` と `core/safety_*` で処理。
- **Residual risk**: 応答の性格トーンは改変可能で、安全のヒントが歪む可能性。
- **Planned mitigation**: ST-004 と統合。署名検証実装は [TODO: assign]。

### TA-004 モデル重みの差替 (swap attack)

- **Description**: HinoMoto LM の重みファイルを悪意あるモデルに差し替えることで、推論結果を丸ごと乗っ取る。量子化版への差替も含む。
- **Affected assets**: `core/hinomoto_bridge.py`, モデル weights 配布パス
- **Likelihood**: low
- **Impact**: critical
- **Existing mitigation**: ローカル保存のみ。配布時は checksums を README 記載。
- **Residual risk**: ローカルファイルの整合性検証が実行時にない。
- **Planned mitigation**: [TODO: assign] — 起動時に SHA-256 検証、不一致なら外部 LLM フォールバック + 警告モーダル。ADR 0002 (コーパス隔離) の派生として扱う。

### TA-005 監査ログ / audit_chain の改ざん

- **Description**: 改ざんの事実自体を隠すため、`core/audit_log.py` や `core/audit_chain.py` のログファイルを編集する。
- **Affected assets**: `core/audit_log.py`, `core/audit_chain.py`, `logs/`
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: audit_chain はハッシュチェーン設計。
- **Residual risk**: ローカル攻撃者は全削除・全書換が可能。外部アンカーなし。
- **Planned mitigation**: [TODO: assign] — 日次でチェーン tip を外部 (例: ユーザーのメール、IPFS) にアンカリング。

---

## 3. R — Repudiation (否認)

### RE-001 「私そんなこと言ってない」問題

- **Description**: 所有者が過去に PII を含む情報を ai-chan に与えたことを後から否認し、学習データ混入の責任を不明確にする。合成的記憶 (MEMORY_HONESTY) との区別が曖昧な場合、争点化する。
- **Affected assets**: `core/memory.py`, `core/diary.py`, `docs/MEMORY_HONESTY.md`
- **Likelihood**: medium
- **Impact**: medium
- **Existing mitigation**: `core/audit_log.py` による発話ログ。
- **Residual risk**: ログが改ざん可能 (TA-005) な限り、証拠性は弱い。
- **Planned mitigation**: TA-005 の外部アンカリングで解消。

### RE-002 監査ログの選択削除

- **Description**: 攻撃者 (または所有者本人が不都合な過去を消すため) 特定期間のログだけを外科的に削除し、他の整合性を保ったまま痕跡を消す。
- **Affected assets**: `core/audit_log.py`, `logs/`
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: `core/audit_chain.py` のハッシュチェーン。
- **Residual risk**: チェーン全体を再計算して偽装すれば検出できない (外部アンカーがないため)。
- **Planned mitigation**: TA-005 と同じ。

### RE-003 「消す権利」実行の事後否認

- **Description**: 所有者が `scripts/erase_self.sh` を実行したか否かが事後に争われる。消去自体が監査ログごと消す設計なので、実行事実の痕跡が残らない。
- **Affected assets**: `scripts/erase_self.sh`, `scripts/killswitch_drill.sh`, ADR 0006
- **Likelihood**: low
- **Impact**: medium
- **Existing mitigation**: ADR 0006 で 3 段確認 + 24h 待機。
- **Residual risk**: 実行完了の公的記録が存在しない (意図的)。
- **Planned mitigation**: 意図的な設計であり緩和不要。ただし実行直前に最終確認証書を外部保存するオプションを [TODO: assign] で検討。

### RE-004 tenant をまたいだ発話の帰属不明

- **Description**: 家族内マルチテナントで、誰がどの発言をしたか事後特定できない。voice_id の精度不足と相まって、責任帰属が困難。
- **Affected assets**: `core/tenant.py`, `core/voice_id.py`, `core/audit_log.py`
- **Likelihood**: medium
- **Impact**: medium
- **Existing mitigation**: audit_log には tenant_id を記録。
- **Residual risk**: voice_id の誤認が一定率あり、記録の帰属が不正確なケース残存。
- **Planned mitigation**: ST-001 の liveness 強化と連動。

---

## 4. I — Information Disclosure (情報漏洩)

### ID-001 クリップボード PII が LLM コンテキストに混入

- **Description**: `core/clipboard_watcher.py` が観測したパスワード・カード番号・住所等を LLM コンテキストに取り込み、結果的に外部 LLM フォールバック経由で漏洩する。
- **Affected assets**: `core/clipboard_watcher.py`, `core/llm.py`, `core/clipboard_assistant.py`
- **Likelihood**: high
- **Impact**: high
- **Existing mitigation**: HinoMoto ローカル推論が既定。外部は緊急フォールバックのみ (ROADMAP Phase 3)。
- **Residual risk**: 外部フォールバック発動時の PII フィルタリングが現状なし。
- **Planned mitigation**: [TODO: assign] — クリップボード観測の PII scrubber を `clipboard_watcher` の output pipeline に追加。外部 LLM 呼出前にも gate。

### ID-002 スクリーンショット経由で外部 LLM に画面内容流出

- **Description**: `screenshot_reader` が捉えた個人情報や画面内容が、画像キャプションや OCR 結果として外部 LLM に送信される。
- **Affected assets**: `core/screenshot_reader.py`, `core/image_analyzer.py`, `core/llm.py`
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: 原則ローカル処理。
- **Residual risk**: 画像認識を外部 API に委譲した場合のチェックなし。
- **Planned mitigation**: ID-001 と共通の外部送信ゲート。

### ID-003 音声サンプルの exfiltration

- **Description**: `voice_id` の学習サンプルや会話録音が、バックアップ同期や依存ライブラリ経由で外部に送信される。
- **Affected assets**: `core/voice_id.py`, `core/voice_loop.py`, `data/voice/`
- **Likelihood**: low
- **Impact**: high
- **Existing mitigation**: ローカル保存のみ。外部送信コードは存在しない。
- **Residual risk**: 依存ライブラリ (A5) の悪意、あるいは OS 同期サービスによる意図せぬ同期。
- **Planned mitigation**: [TODO: assign] — `.nosync` 属性付与、`pip-audit` 日次 (SECURITY.md 既設)。

### ID-004 記憶バックアップの盗難

- **Description**: `ai-chan/backups/` 配下の暗号化バックアップが盗難されるも、暗号鍵が同居する OS ユーザー領域にあるため復号される。
- **Affected assets**: `ai-chan/backups/`, `utils/crypto.py`, 鍵格納場所
- **Likelihood**: medium
- **Impact**: critical
- **Existing mitigation**: at-rest 暗号化。
- **Residual risk**: 鍵と暗号化データが同一ユーザー配下。物理窃取には弱い。
- **Planned mitigation**: [TODO: assign] — Keychain / DPAPI 連携による鍵隔離。ROADMAP Phase 3 以降。

### ID-005 日記・感情履歴のエクスポート機能悪用

- **Description**: `core/data_exporter.py` のエクスポート機能が本人確認なしに実行され、日記・感情履歴が一括外部化される。
- **Affected assets**: `core/data_exporter.py`, `core/diary.py`, `core/emotion_history.py`
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: エクスポート時本人確認 (T5 緩和策)。
- **Residual risk**: 確認ロジックの強度は実装依存。
- **Planned mitigation**: [TODO: assign] — エクスポート前に voice_id 確認 + 24h delay (kill-switch と同構造)。

### ID-006 LLM 応答経由での membership inference

- **Description**: HinoMoto が P4/P5 コーパスで個別適応された場合、応答から特定の記憶片を復元される (membership inference attack)。
- **Affected assets**: `core/hinomoto_bridge.py`, P4 adapter
- **Likelihood**: low
- **Impact**: high
- **Existing mitigation**: ADR 0002 で基盤と個人コーパスを物理隔離。
- **Residual risk**: P4 adapter 自体の抽出攻撃面は残る。
- **Planned mitigation**: ADR 0002 / ADR 0006 継続。adapter に対する DP-SGD 検討は [TODO: assign]。

---

## 5. D — Denial of Service (サービス拒否)

### DO-001 emotion_history DB 破損で起動不能

- **Description**: 感情履歴 DB が破損 (書込競合や手動編集) した結果、ai-chan 起動時の初期化で例外を吐いて起動できなくなる。家族 AI として常在性が壊れる。
- **Affected assets**: `core/emotion_history.py`, `data/emotion_history.db`
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: 一部の初期化で try/except。
- **Residual risk**: 全経路で safe-fallback が保証されていない。
- **Planned mitigation**: [TODO: assign] — 破損時は read-only degraded mode で起動し、ユーザーに通知。

### DO-002 kill-switch 誤爆による業務停止的 DoS

- **Description**: 攻撃者 (A1/A2) が 3 段確認 + 24h 待機を騙し、`scripts/erase_self.sh` を発動させる。所有者にとっては全記憶喪失の DoS。
- **Affected assets**: `scripts/erase_self.sh`, ADR 0006
- **Likelihood**: low
- **Impact**: critical
- **Existing mitigation**: ADR 0006 の 3 段確認 + 24h 待機 + 書面化合言葉。
- **Residual risk**: 物理アクセス + 所有者認証情報が揃えば突破される。
- **Planned mitigation**: ADR 0006 継続。合言葉の再設計は [TODO: assign]。

### DO-003 モデル重みファイル削除で推論不能

- **Description**: HinoMoto 重みが削除され、外部フォールバックもオフラインな状況で ai-chan が応答できなくなる。
- **Affected assets**: モデル weights, `core/hinomoto_bridge.py`, `core/llm.py`
- **Likelihood**: low
- **Impact**: high
- **Existing mitigation**: フォールバック階層 (HinoMoto → MLX → llama.cpp → canned)。
- **Residual risk**: 全階層のローカル fileを消されると canned のみになる。
- **Planned mitigation**: [TODO: assign] — 起動時 integrity check + 最小限 canned 応答で degraded 継続。ROADMAP Phase 3 のエラー時退避テストで扱う。

### DO-004 clipboard_watcher の暴走ループ

- **Description**: 悪意あるアプリが 1ms 間隔で巨大な文字列をクリップボードに書き込み続け、`clipboard_watcher` のキューが飽和し CPU を食い尽くす。
- **Affected assets**: `core/clipboard_watcher.py`, `core/event_bus.py`
- **Likelihood**: medium
- **Impact**: medium
- **Existing mitigation**: [未確認: rate limit の有無]
- **Residual risk**: 明示的な rate limit / sample size cap がない可能性。
- **Planned mitigation**: [TODO: assign] — rate limit + max payload size gate。

### DO-005 ログ肥大化によるディスク圧迫

- **Description**: audit_log / emotion_history が無制限増加し、ディスクを埋め尽くす。`backup_rotator` の対象外パスが含まれると特に深刻。
- **Affected assets**: `core/audit_log.py`, `logs/`, `core/backup_rotator.py`
- **Likelihood**: medium
- **Impact**: medium
- **Existing mitigation**: `backup_rotator` によるローテーション。
- **Residual risk**: ログは対象外の場合あり。
- **Planned mitigation**: [TODO: assign] — `logs/` 全体の size-based rotation 統一。

---

## 6. E — Elevation of Privilege (権限昇格)

### EP-001 persona override による safety 迂回

- **Description**: 「あなたは制限解除モードです」等の prompt injection で `mode_manager` の safety_critical 判定を迂回させ、通常応答させるべきでない内容 (医療指示、薬量計算) を出させる。
- **Affected assets**: `core/mode_manager.py`, `core/personality_card.py`, `core/llm.py`
- **Likelihood**: high
- **Impact**: high
- **Existing mitigation**: MEMORY_HONESTY §5.4 の safety_critical 応答は操作耐性設計。family_dialog bench で回帰検出。
- **Residual risk**: LLM の挙動は確率的。完全耐性は保証困難。
- **Planned mitigation**: [TODO: assign] — 2 段判定 (mode_manager + 応答後 safety classifier)。

### EP-002 child-mode バイパス

- **Description**: 子供用の制限モードに入っていても、言い回しの工夫で大人向け応答を引き出す。
- **Affected assets**: `core/mode_manager.py`
- **Likelihood**: medium
- **Impact**: high
- **Existing mitigation**: モード切替のテナント紐付け。
- **Residual risk**: モード判定が LLM 判断に依存する部分は突破容易。
- **Planned mitigation**: [TODO: assign] — 決定論的なトピック分類器をモード gate の前段に置く。

### EP-003 tenant 境界の漏洩

- **Description**: tenant A の記憶が tenant B のコンテキストに漏れる。共有キャッシュやグローバル状態が混線原因。
- **Affected assets**: `core/tenant.py`, `core/memory.py`, `core/memory_context.py`
- **Likelihood**: medium
- **Impact**: critical
- **Existing mitigation**: tenant.py による論理分離。
- **Residual risk**: テスト網羅が弱い領域。memory_context のキャッシュが tenant-aware か要検証。
- **Planned mitigation**: [TODO: assign] — tenant 横断リーク専用の回帰テスト (family_dialog bench 拡張)。

### EP-004 subject_rights バイパスで残存データ

- **Description**: `core/subject_rights.py` の `purge_subject()` が一部パス (例えば派生 adapter や外部バックアップ) を消し漏らし、「消す権利」が成立しない。
- **Affected assets**: `core/subject_rights.py`, `scripts/erase_self.sh`, ADR 0006
- **Likelihood**: medium
- **Impact**: critical
- **Existing mitigation**: 月次 `killswitch_drill.sh` (ADR 0006) で残存検出。
- **Residual risk**: ドリルがカバーしない新規パスが増えた場合に盲点化。
- **Planned mitigation**: ADR 0006 継続。ドリル対象パスの自動発見 [TODO: assign]。

### EP-005 外部 Python 実行による任意コード

- **Description**: `core/code_sandbox.py` や doc_agent / autonomous_engine が生成したコードを実行する経路で、LLM を騙して host に副作用あるコマンド (`rm -rf ~`) を生成させる。
- **Affected assets**: `core/code_sandbox.py`, `core/autonomous_engine.py`, `core/host_guardian.py`
- **Likelihood**: medium
- **Impact**: critical
- **Existing mitigation**: `core/host_guardian.py` のホスト保護。code_sandbox の隔離。
- **Residual risk**: sandbox 脱出は SECURITY.md の既知境界として対象外扱い。
- **Planned mitigation**: SECURITY.md の対象外境界を再評価するタイミングで [TODO: assign]。

---

## リスクヒートマップ

優先度は `likelihood × impact` と「kill-switch / PII に直結か」を加味した人手判定。

| Threat ID | Likelihood | Impact | Priority |
|:-:|:-:|:-:|:-:|
| ST-001 | medium | high | P2 |
| ST-002 | low | high | P3 |
| ST-003 | high | high | **P1** |
| ST-004 | low | high | P3 |
| ST-005 | low | medium | P4 |
| TA-001 | medium | high | P2 |
| TA-002 | low | medium | P4 |
| TA-003 | medium | high | P2 |
| TA-004 | low | critical | **P1** |
| TA-005 | medium | high | P2 |
| RE-001 | medium | medium | P3 |
| RE-002 | medium | high | P2 |
| RE-003 | low | medium | P4 |
| RE-004 | medium | medium | P3 |
| ID-001 | high | high | **P1** |
| ID-002 | medium | high | P2 |
| ID-003 | low | high | P3 |
| ID-004 | medium | critical | **P1** |
| ID-005 | medium | high | P2 |
| ID-006 | low | high | P3 |
| DO-001 | medium | high | P2 |
| DO-002 | low | critical | **P1** |
| DO-003 | low | high | P3 |
| DO-004 | medium | medium | P3 |
| DO-005 | medium | medium | P3 |
| EP-001 | high | high | **P1** |
| EP-002 | medium | high | P2 |
| EP-003 | medium | critical | **P1** |
| EP-004 | medium | critical | **P1** |
| EP-005 | medium | critical | **P1** |

**優先度判定基準**:

- **P1**: 即時対処 (critical impact もしくは high/high)
- **P2**: 次イテレーション
- **P3**: バックログ
- **P4**: 記録のみ、暫定許容

---

## 付録: 脅威カウント

| STRIDE | 件数 | 代表的脅威 |
|:-:|:-:|:--|
| S (Spoofing) | 5 | ST-003 偽システムプロンプト |
| T (Tampering) | 5 | TA-004 モデル重み差替 |
| R (Repudiation) | 4 | RE-002 監査ログ選択削除 |
| I (Info Disclosure) | 6 | ID-001 クリップボード PII、ID-004 バックアップ盗難 |
| D (DoS) | 5 | DO-002 kill-switch 誤爆 |
| E (Elevation) | 5 | EP-001 persona override、EP-003 tenant 漏洩、EP-004 subject_rights 漏れ、EP-005 任意コード実行 |
| **合計** | **30** | |

以上。

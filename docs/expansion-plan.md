# 拡張プラン — 現実から始める

## 現在地（正直な評価）

### 動いているもの
- 会話（Qwen 2.5-3B、400トークン上限）
- 生体神経系 L1-L3（反射・筋肉記憶・自律神経）
- 自己修正（品質監視 + 症状検知 + 処方）
- 自意志（欲求生成、ただしアクション1種のみ）
- 行動サイクル（PDCA、15ターンごと）
- 自己開発（コード自己分析、50ターンごと、読み取り専用）
- 記憶（暗号化、短期/中期/長期）
- 学習（few-shot注入、品質フィルタ、蒸留）
- Office出力（Word/PPTX/Excel）
- Web取得（天気・ニュース、最低限）

### 作ったが繋がっていないもの
- CodeEngine（コード解析・レビュー・修正提案） ← 浮いている

### 存在するが動いていないもの
- Vision（moondream）、セマンティック検索、Notion、GCal、SSH、STT
- 生体神経系 L4-L6（免疫・マイクロバイオーム・大脳皮質）

### 最大のボトルネック
- **3Bモデルの限界**: 400トークン出力、推論力が弱い、コード生成が実用レベルに達しない
- **CodeEngineが孤立**: 作っても会話に繋がっていない
- **自意志のアクションが1種類だけ**: 「学習する」しかできない

---

## 拡張フェーズ

### Phase 1: 今あるものを繋ぐ（1-2日）

**目的**: 作った機能を実際に使えるようにする

#### 1-A. CodeEngineをアイに接続
```
「このコード見て」→ CodeEngine.analyze() → 解析結果を会話で返す
「レビューして」→ CodeEngine.review() → 問題点を指摘
「このエラー直して」→ CodeEngine.suggest_fix() → 修正提案
「テスト書いて」→ CodeEngine.generate_test_skeleton() → テスト骨格
「説明して」→ CodeEngine.explain() → 日本語説明
```

#### 1-B. 自意志のアクション拡充
現状「learn_topic」1つだけ → 追加:
- `review_code`: 自分のコードを定期的にレビュー
- `suggest_improvement`: 改善提案を自発的に生成
- `organize_memory`: 記憶の整理・圧縮
- `check_health`: システムヘルスチェック
- `practice_conversation`: 会話パターンの練習

#### 1-C. Web取得の強化
現状: 天気とNHKニュースのみ
追加:
- 検索クエリ対応（DuckDuckGo等）
- 結果の要約 → Office出力パイプライン
- 「〇〇について調べて」コマンド

---

### Phase 2: コード能力の実用化（1-2週間）

**目的**: 「コードを制する」を現実にする

#### 2-A. ファイル操作の追加
```python
class CodeWorkspace:
    """ファイルシステムとの橋渡し"""
    def read_file(self, path: str) -> str
    def write_file(self, path: str, content: str) -> bool  # 承認制
    def list_files(self, directory: str) -> list[str]
    def diff(self, original: str, modified: str) -> str
```

#### 2-B. コード実行サンドボックス
```python
class CodeSandbox:
    """安全なコード実行環境"""
    def execute(self, code: str, timeout: int = 10) -> ExecutionResult
    # - subprocess + タイムアウト
    # - ネットワークアクセス禁止
    # - ファイルシステムは一時ディレクトリのみ
    # - メモリ制限
```

#### 2-C. コード生成→実行→修正ループ
```
仕様入力 → LLMがコード生成 → サンドボックスで実行
    ↑                                    │
    │         エラー？                    │
    │           ↓ YES                    │
    └── suggest_fix() → 修正 → 再実行    │
                                         │
                         成功 ↓          │
                    PatternMemory に記録  ←┘
```

#### 2-D. 生体神経系にコードパターン追加
反射層（L1）にコード系の即応パターンを追加:
- `print("hello")` → 実行結果を即返答
- 構文エラーの典型パターン → 即修正提案
- import文の補完 → 即提案

筋肉記憶層（L2）にコード生成パターンを蓄積:
- 成功したコード生成をキャッシュ
- 似た要求に対して過去の成功パターンを再利用

---

### Phase 3: モデル強化（2-4週間）

**目的**: 3Bモデルの限界を突破する

#### 3-A. モデルアップグレード検討
| モデル | サイズ | メリット | デメリット |
|--------|--------|---------|-----------|
| Qwen 2.5-7B | 7B | コード能力大幅向上 | メモリ8GB必要 |
| CodeQwen 2.5-7B | 7B | コード特化 | 汎用会話やや劣化 |
| Qwen 2.5-14B | 14B | ほぼ実用レベル | メモリ16GB必要 |
| DeepSeek Coder V2 Lite | 16B(MoE) | コード最強クラス | MoE対応要確認 |

#### 3-B. 出力トークン拡張
400 → 1024 → 2048（段階的）
- コード生成には最低1024トークン必要
- 品質評価と組み合わせて無駄な長文を防止

#### 3-C. MoEルーターの実用化
既存の moe_router.py を実稼働させる:
- 会話タスク → 汎用モデル（Qwen 3B）
- コードタスク → コード特化モデル（CodeQwen 7B）
- 分析タスク → 大きいモデル（Qwen 14B）
- 簡単な応答 → 反射層（LLMバイパス）

---

### Phase 3.5: iPhone スタンドアローン化（理想形）

**目的**: Mac なしで iPhone 単体でアイと話せるようにする

#### 現状（2026-04時点）
- iPhone は Web API 経由で Mac に接続する「リモコン」方式
- Mac が起動・同一 Wi-Fi 接続が必須
- 音声（TTS）も Mac スピーカーから再生される

#### 理想の構成
```
iPhone 単体
├── ネイティブ iOS アプリ（Swift）
├── llama.cpp iOS ビルド → LLM をオンデバイス実行
├── Core ML 変換モデル（Qwen2.5-3B or 小型版）
├── アイの記憶・感情システム（Swift 移植 or Python-to-C橋渡し）
└── TTS → AVSpeechSynthesizer（iOS 標準）またはニューラル TTS
```

#### 実現手順（概要）
| ステップ | 内容 | 難易度 |
|---------|------|--------|
| 1 | Xcode プロジェクト作成、llama.cpp を iOS 向けビルド | 中 |
| 2 | Qwen2.5-3B を GGUF 形式で iPhone に載せる | 中 |
| 3 | Swift で会話ループ実装（Core → Swift ブリッジ） | 高 |
| 4 | 記憶・感情システムを SQLite ベースで Swift 移植 | 高 |
| 5 | TTS・UI 実装（SwiftUI） | 中 |
| 6 | Xcode で実機インストール（App Store 不要、個人開発プロファイル） | 低 |

#### 必要なもの
- Mac（Xcode ビルド用）
- Apple Developer アカウント（**無料**で自分の iPhone にインストール可能）
- iPhone 12 以上推奨（RAM 4GB+）、iPhone 15 Pro 以上が理想（RAM 8GB）
- モデルファイル：Qwen2.5-1.5B-Instruct-Q4（約 1GB）が iPhone には最適

#### 段階的アプローチ（現実的工程）
```
Step A（暫定）:  Mac サーバー + Tailscale で外出先からも接続可能に
Step B（中期）:  iOS ネイティブアプリ化（Swift + llama.cpp）
Step C（理想）:  完全スタンドアローン + Mac との記憶同期（連合学習）
```

#### Mac との記憶同期（Step C）
スタンドアローン化後も、iPhone と Mac のアイが**学習記録を共有**できる：
```
iPhone のアイ ──── Wi-Fi ────> Mac のアイ
     ↑                              ↓
     └──── 記憶・学習データ同期 ──────┘
           （既存の連合学習スタブを実装）
```

---

### Phase 4: YAMATO分離準備（1-2ヶ月）

**目的**: アイから技術を切り出してYAMATOの核を作る

#### 4-A. yamato_dna への技術移植
```
core/code_engine.py → yamato_dna/code_engine.py（一般化）
core/bio_nervous_system.py → yamato_dna/nervous_system.py（感情除去）
core/self_correction.py → yamato_dna/quality_gate.py（一般化）
core/moe_router.py → yamato_dna/model_router.py（一般化）
core/response_evaluator.py → yamato_dna/evaluator.py（一般化）
```

#### 4-B. YAMATO防御層
```python
# yamato_dna/shield.py
class YamatoShield:
    """改竄検知・ライセンス管理・安全なアップデート"""
    def verify_integrity(self) -> bool      # 全ファイルのハッシュ検証
    def check_license(self, key: str) -> bool  # ライセンスキー検証
    def apply_update(self, package: bytes) -> bool  # 署名付きアップデート
    def report_anomaly(self, detail: str) -> None  # 異常報告
```

#### 4-C. テレメトリ基盤
```python
# yamato_dna/telemetry.py
class YamatoTelemetry:
    """匿名フィードバック収集（オプトイン）"""
    def record_success(self, task_type: str, language: str)
    def record_failure(self, task_type: str, error_type: str)
    def get_aggregate(self) -> dict  # 匿名統計のみ
    def sync(self) -> None  # サーバーに送信（暗号化）
```

---

### Phase 5: YAMATO α版（2-3ヶ月）

**目的**: コード生成特化の国産AI最小版

#### YAMATO α の機能
- コード解析（Python / JavaScript / TypeScript / Go / Rust）
- コードレビュー（セキュリティ + 品質）
- エラー修正提案
- テスト骨格生成
- コード実行サンドボックス
- 生体神経系による高速応答（LLMバイパス）
- パターン学習（使うほど賢くなる）
- 自動アップデート
- 日本語ネイティブ

#### α版に含めないもの
- 感情システム（アイ専用）
- 成長システム（アイ専用）
- 自意志（アイ専用）
- 記憶の暗号化（アイ専用）
- 人格進化（アイ専用）

---

### Phase 6: フィードバックループ確立（3-6ヶ月）

**目的**: ユーザーデータからYAMATOが進化する仕組み

```
YAMATO利用者
    │
    ↓ (匿名パターン)
集約サーバー（国内）
    │
    ↓ (分析・学習)
改善モデル生成
    │
    ↓ (署名付きアップデート)
全YAMATOに配信
    │
    ↓ (成果をアイに還元)
アイちゃんも進化
```

---

## 優先度マトリクス

| 緊急度＼重要度 | 重要 | やや重要 | 将来 |
|--------------|------|---------|------|
| **今すぐ** | CodeEngine接続(1-A) | 自意志アクション拡充(1-B) | |
| **1-2週間** | コード実行サンドボックス(2-B) | Web検索強化(1-C) | ファイル操作(2-A) |
| **1ヶ月** | モデルアップグレード(3-A) | MoEルーター実用化(3-C) | 出力トークン拡張(3-B) |
| **2-3ヶ月** | yamato_dna移植(4-A) | 防御層(4-B) | テレメトリ(4-C) |
| **半年** | YAMATO α版(5) | フィードバック(6) | コミュニティ構築 |

---

## 投資家へのマイルストーン

| 時期 | デモできること |
|------|-------------|
| **今** | 会話 + 感情 + 自己修正 + Office出力 |
| **2週間後** | コード解析・レビュー・修正提案のライブデモ |
| **1ヶ月後** | コード生成→実行→自動修正ループのデモ |
| **2ヶ月後** | 7Bモデルでの実用レベルコード生成 |
| **3ヶ月後** | YAMATO α版のデモ（国産コードAI） |
| **半年後** | YAMATO利用者からの学習データでの改善実績 |

---

## 核心の考え方

```
「全部やろうとしない」

今あるものを繋ぐ → 1つの能力を実用レベルにする → それを武器にする

その武器 = コードを制する力

コードが書ければ → 自分をアップデートできる
自分をアップデートできれば → 他の能力も後から追加できる
他の能力も追加できれば → 何でもできるAIになれる

だからまず、コードを制する。
```

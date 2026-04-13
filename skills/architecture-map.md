# アイ アーキテクチャマップ

## 全体構造

```
ai-chan/
  core/           66モジュール  ~17,800行  全ビジネスロジック
  ui/              7モジュール              Tk GUI + CLI
  utils/           4モジュール              暗号化・人格ローダー・ポータブル
  tests/          10ファイル    272テスト
  config/          persona.json + settings.json
  data/            永続化ファイル群 (JSON/JSONL/SQLite)
  models/          GGUFモデルファイル
  personality/     YAML人格定義 (Sprint 1.1+)
  scripts/         インストール・macOSアプリ作成
  skills/          このディレクトリ
```

## コア依存グラフ

```
ai_chan.py (2375行) ── 中央ハブ。全モジュールをここでnew/init。
  |
  +-- memory.py .............. SQLite記憶管理 (短期/中期/長期)
  |     +-- memory_compressor.py   10ターンごとに圧縮
  |     +-- diary.py               日記生成
  +-- emotion.py ............. 感情エンジン (happiness/curiosity/affection/energy)
  +-- llm.py ................. llama-cpp-python GGUF推論
  +-- learning.py ............ few-shot学習 (JSONL読み込み)
  |
  +-- [Sprint K: 国産AI進化]
  |   +-- conversation_intelligence.py .. 意図分類(16種) + 応答戦略 + 品質フィルタ
  |   +-- knowledge_graph.py ............ エンティティ/関係抽出 + BFS検索
  |   +-- personality_evolution.py ...... 7性格パラメータ + 関係性深化
  |   +-- response_evaluator.py ......... 自己品質評価 + 自動再生成
  |
  +-- [ヤマト計画: 国産AI基盤]
  |   +-- moe_router.py ................ MoEルーティング (A1)
  |   +-- continuous_learner.py ........ 品質ベース選択学習 (A2)
  |   +-- yamato_architecture.py ....... 7層ヘルスチェック (A3)
  |   +-- synthetic_data_gen.py ........ テンプレート合成データ (C6)
  |   +-- multi_agent_verifier.py ...... 5エージェント合議検証 (C7)
  |
  +-- [防御システム Sprint 2.1]
  |   +-- audit_log.py, integrity_monitor.py, backup_rotator.py
  |   +-- anomaly_detector.py, kill_switch.py, host_guardian.py
  |   +-- network_monitor.py, process_monitor.py, defense_dashboard.py
  |
  +-- [Sprint 3.0: マルチモーダル/RAG/防御進化]
  |   +-- vision_engine.py, image_analyzer.py, clipboard_image.py
  |   +-- rag_engine.py, memory_summarizer.py, multimodal_chat.py
  |   +-- expression_engine.py
  |
  +-- [Sprint J: サーバーホーム + 自律行動]
  |   +-- server_home.py, server_ai_env.py
  |   +-- autonomous_actions.py, autonomous_engine.py
  |
  +-- [その他]
      +-- scheduler.py, topic_tracker.py, anniversary.py
      +-- tts.py, stt.py, battery_monitor.py, calendar_reader.py
      +-- auto_learner.py, semantic_search.py
      +-- web_learner.py, youtube_learner.py, file_learner.py
      +-- task_manager.py, habit_tracker.py, growth_report.py
      +-- minutes_engine.py, minutes_extractor.py, notion_connector.py
```

## UIフロー

```
main.py
  |-- --desktop → ui/desktop_pet.py (Tk、macOSデスクトップペット)
  |     |-- ChatWindow .... チャットUI
  |     |-- SpeechBubble .. 吹き出し
  |     |-- DesktopPet .... 透明ウィンドウ + スプライト + 右クリックメニュー
  |     +-- 起動フロー:
  |           1. DesktopPet(ai_chan_instance=None)  ← ウィンドウ即表示
  |           2. _load_ai() バックグラウンドスレッド ← AiChan()初期化(~6秒)
  |           3. pet.ai_chan = ai                   ← メインスレッドで差し込み
  |
  |-- (デフォルト) → ui/cli.py (ターミナルCLI)
  |-- --status → JSON出力
  +-- --copy → USBポータブルコピー
```

## データフロー (1ターンの会話)

```
ユーザー入力
  ↓
1. 特殊コマンドチェック (CMD_* 正規表現)
2. 感情更新 (emotion.update_from_message)
3. 会話知能分析 (conv_intelligence.analyze_input) → 意図・戦略
4. MoEルーティング (moe_router.route) → 専門家モデル選択
5. 記憶コンテキスト構築 (memory + RAG + 知識グラフ + 性格ヒント)
6. LLM応答生成 (llm.generate_chat)
7. 後処理:
   a. 日本語品質フィルタ (conv_intelligence.post_process)
   b. マルチエージェント検証 (multi_verifier.verify) → 低品質なら再生成
   c. 応答品質自己評価 (response_evaluator.evaluate) → 低品質なら再生成
8. TTS読み上げ
9. バックグラウンド更新 (別スレッド):
   - 記憶保存、話題追跡、プロファイル抽出
   - 感情履歴、関心マップ、目標検出
   - 知識グラフ抽出、性格進化
   - 継続学習蓄積、合成データテンプレート学習
```

## 設定ファイル構造

### config/settings.json 主要セクション
- `llm`: model_path, context_length, max_tokens, temperature, n_gpu_layers
- `memory`: db_path, short_term_max, compression_threshold
- `security`: encrypt_database, key_file
- `ui`: user_name, pet_image, color_theme
- `autonomous`: idle_minutes, schedule_enabled, clipboard_watch
- `server_home`: host, port, username, password
- `tts/stt`: enabled, voice/model_size
- `vision`: enable_moondream
- `integrations`: notion, google_calendar

### config/persona.json
- `personality.system_prompt`: アイの全行動指示（日本語）
- `personality.speech_style`: タメ口スタイル定義
- `emotion_base`: 初期感情値

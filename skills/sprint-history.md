# スプリント履歴と実装状況

> **注記 (2026-04-21 M7):** 以下に登場する `tests/test_sprint3.py` / `test_sprint3_ae.py` /
> `test_sprint_j.py` / `test_sprint_k.py` は M7 でドメイン命名にリネームされました。
> 新しいパスは以下の通り — 歴史記録としての旧ファイル名は本文内に残します。
>
> | 旧 | 新 |
> |---|---|
> | `test_sprint3.py` | `test_rag_and_life_assistant.py` |
> | `test_sprint3_ae.py` | `test_multimodal_and_defense.py` |
> | `test_sprint_j.py` | `test_server_ops_and_autonomous.py` |
> | `test_sprint_k.py` | `test_conversation_intelligence.py` |

## 完了スプリント一覧

### Sprint 0: 基盤構築
- [x] core/memory.py — SQLite記憶管理（短期/中期/長期/永久）
- [x] core/emotion.py — 感情エンジン（4軸: happiness/curiosity/affection/energy）
- [x] core/llm.py — llama-cpp-python GGUF推論（Phi-3-mini-4k-instruct-q4）
- [x] core/learning.py — few-shot擬似学習（JSONL）
- [x] ui/cli.py — ターミナルCLI
- [x] config/persona.json — アイの人格定義
- [x] config/settings.json — 全体設定

### Sprint 1.0: 生活アシスタント
- [x] core/memory_compressor.py — 記憶圧縮（10ターンごと）
- [x] core/topic_tracker.py — 話題追跡
- [x] core/scheduler.py — スケジュール管理
- [x] core/anniversary.py — 記念日管理
- [x] core/diary.py — 日記自動生成

### Sprint 1.1: 成長記録
- [x] core/emotion_history.py — 感情履歴
- [x] core/interest_map.py — 関心マップ
- [x] core/goal_tracker.py — 目標追跡
- [x] personality/*.yaml — YAML人格定義（persona.jsonからの移行）

### Sprint 1.2: 自律エンジン
- [x] core/autonomous_engine.py — 階層ジョブスケジューラ
- [x] core/auto_learner.py — 自動学習

### Sprint 1.3: 成長レポート
- [x] core/growth_report.py — 日次/週次成長レポート

### Sprint 2.0: マルチメディア学習
- [x] core/youtube_learner.py — YouTube学習
- [x] core/web_learner.py — Web学習
- [x] core/file_learner.py — ファイル学習
- [x] core/tts.py — 音声合成（macOS say/VOICEVOX）
- [x] core/stt.py — 音声認識（Whisper）
- [x] core/battery_monitor.py — バッテリー監視
- [x] core/calendar_reader.py — カレンダー読み込み
- [x] core/semantic_search.py — セマンティック検索
- [x] ui/desktop_pet.py — デスクトップペット（Tk）

### Sprint 2.1: 防御システム
- [x] core/audit_log.py — 監査ログ
- [x] core/integrity_monitor.py — ファイル整合性監視
- [x] core/backup_rotator.py — 自動バックアップ（日次/7世代）
- [x] core/anomaly_detector.py — 異常検知
- [x] core/kill_switch.py — 緊急停止（ロックダウン）
- [x] core/host_guardian.py — ホストPC防御

### Sprint 3.0: マルチモーダル/RAG/防御進化
- [x] core/vision_engine.py — 画像認識（Moondream/OCR）
- [x] core/image_analyzer.py — 画像解析
- [x] core/clipboard_image.py — クリップボード画像
- [x] core/rag_engine.py — RAG検索エンジン
- [x] core/memory_summarizer.py — 会話要約
- [x] core/multimodal_chat.py — マルチモーダルチャット
- [x] core/expression_engine.py — 表情変化エンジン
- [x] core/network_monitor.py — ネットワーク監視
- [x] core/process_monitor.py — プロセス監視
- [x] core/defense_dashboard.py — 防御ダッシュボード
- [x] core/task_manager.py — タスク管理
- [x] core/habit_tracker.py — 習慣トラッカー
- [x] core/minutes_engine.py — 議事録エンジン

### Sprint J: サーバーホーム + 自律行動
- [x] core/server_home.py — SSH/SFTP サーバー管理
- [x] core/server_ai_env.py — サーバーAI環境
- [x] core/autonomous_actions.py — 時間帯挨拶/独り言/日課
- [x] 5コマンドハンドラー: server_status, server_docker, server_sync, server_setup, proactive
- [x] tests/test_sprint_j.py — 41テスト

### Sprint K: 国産AI進化パック
- [x] core/conversation_intelligence.py — 意図分類(16種)/応答戦略/品質フィルタ
- [x] core/knowledge_graph.py — エンティティ抽出/関係推論/BFS検索
- [x] core/personality_evolution.py — 7性格パラメータ/関係性深化
- [x] core/response_evaluator.py — 自己品質評価/自動再生成
- [x] tests/test_sprint_k.py — 54テスト

### ヤマト計画 A+C: 国産AI基盤
- [x] core/moe_router.py — MoE専門家ルーティング (A1)
- [x] core/continuous_learner.py — 品質ベース継続学習 (A2)
- [x] core/yamato_architecture.py — 7層アーキテクチャ (A3)
- [x] core/synthetic_data_gen.py — 合成データ生成 (C6)
- [x] core/multi_agent_verifier.py — 5エージェント合議検証 (C7)
- [x] ai_chan.py統合: MoEルーティング、マルチ検証、継続学習、合成データフィードバック
- [x] ヤマトヘルスチェック: 全7層のヘルスチェック登録
- [x] 新コマンド5種: yamato_dash, moe_status, learning_status, synth_gen, verify_status
- [x] tests/test_yamato.py — 69テスト

## 未実装（ヤマト計画ロードマップ）

### Priority B（中期: 6-12ヶ月）
- [ ] B4: 分散推論基盤（複数マシンでモデル分割）
- [ ] B5: 自動評価ベンチマーク（品質の定量計測）

### Priority D（長期: 1-3年）
- [ ] D8: フェデレーション学習（複数インスタンスの知識共有）
- [ ] D9: モデルファインチューニング（LoRA/QLoRA）
- [ ] D10: 独自トークナイザー（日本語最適化）

## テスト統計

| テストファイル | テスト数 | 対象 |
|---------------|---------|------|
| test_yamato.py | 69 | ヤマト計画 A1/A2/A3/C6/C7 |
| test_sprint_k.py | 54 | Sprint K 知能/知識/性格/品質 |
| test_sprint_j.py | 41 | Sprint J サーバー/自律行動 |
| test_sprint3_ae.py | 32 | Sprint 3.0 防御進化 |
| test_sprint3.py | 21 | Sprint 3.0 マルチモーダル |
| test_defense.py | 20 | Sprint 2.1 防御システム |
| test_autonomous_engine.py | 10 | 自律エンジン |
| test_growth_report.py | 10 | 成長レポート |
| test_memory_long_term.py | 9 | 記憶の長期保存 |
| test_personality_migration.py | 6 | 人格YAML移行 |
| **合計** | **272** | |

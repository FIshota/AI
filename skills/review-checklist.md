# レビュー・検証チェックリスト

## 1. 新モジュール追加時の必須チェック

### コード品質
- [ ] dataclass に `to_dict()` メソッドがあるか
- [ ] `to_dict()` のキー名と dataclass フィールド名が一致するか（H4問題）
- [ ] `_load()` で `to_dict()` の出力を復元できるか（ラウンドトリップテスト）
- [ ] `threading.Lock()` を使用して並行アクセスを保護しているか
- [ ] ファイル永続化パスの `parent.mkdir(parents=True, exist_ok=True)` があるか

### ai_chan.py 統合
- [ ] `_init_components()` に try/except ブロックを追加したか
- [ ] except で `self.xxx = None` フォールバックを設定したか
- [ ] print で `[ModuleName] ✓` / `初期化失敗` ログを出力しているか
- [ ] 使用箇所で `getattr(self, "xxx", None)` ガードを入れたか
- [ ] コマンドパターン `CMD_XXX` を追加したか（正規表現）
- [ ] `_handle_commands()` にコマンドハンドラーを追加したか

### テスト
- [ ] `tests/test_xxx.py` を作成したか
- [ ] tmpdir を使って外部状態に依存しないテストか
- [ ] 永続化のラウンドトリップテスト（save → load → assert）があるか
- [ ] 境界値テストがあるか（空入力、長すぎる入力、スコア0/1）
- [ ] `python3 -m pytest tests/ -v` で全テスト通過するか

## 2. 会話フロー変更時のチェック

### 前処理（LLM呼び出し前）
- [ ] conv_analysis の結果を正しく参照しているか
- [ ] memory_context に追加する文字列が `max_chars` 制限内か
- [ ] None チェックを入れているか

### 後処理（LLM呼び出し後）
- [ ] response が空文字列の場合を考慮しているか
- [ ] 再生成ループは**1回まで**に制限されているか（無限ループ防止）
- [ ] Exception を catch して握りつぶしているか（会話が止まらないように）

### バックグラウンド更新（_batch_updates内）
- [ ] 全操作が try/except で囲まれているか
- [ ] メインスレッドの変数を直接変更していないか（`_ui`, `_resp` クロージャ変数を使う）
- [ ] 重い処理はない（ファイルI/OはOK、LLM呼び出しはNG）

## 3. UI (desktop_pet.py) 変更時のチェック

### Tk スレッドセーフティ
- [ ] バックグラウンドスレッドから直接 Tk ウィジェットを操作していないか
- [ ] `self.root.after(0, callback)` でメインスレッドに委譲しているか
- [ ] `winfo_exists()` チェックを入れているか

### macOS 互換性
- [ ] Python 3.13 + Tk 8.6 で動作するか
- [ ] `overrideredirect(True)` 環境でイベントが拾えるか
- [ ] 右クリックメニューは `ButtonPress-2/3` + `ButtonRelease-2/3` 両方バインドか

### 起動フロー
- [ ] `ai_chan is None` の場合のフォールバックがあるか
- [ ] `llm_loaded` が False の場合のフォールバックがあるか
- [ ] バックグラウンドスレッドが例外で死んでもUIは動き続けるか

## 4. 全体テスト実行手順

```bash
# 1. 単体テスト全実行
cd /Users/fujihiranoborudai/Downloads/agent/ai-chan
python3 -m pytest tests/ -v

# 2. AiChan初期化テスト（全モジュールロード確認）
python3 -c "
import sys; sys.path.insert(0, '.')
from core.ai_chan import AiChan
ai = AiChan(base_dir='.')
print(f'llm_loaded={ai.llm_loaded}')
print(f'Status: {ai.get_status()}')" 2>&1

# 3. デスクトップペット起動確認
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -u main.py --desktop

# 4. プロセス確認
ps aux | grep "[m]ain.py.*desktop"

# 5. ログ確認
tail -20 data/app.log
```

## 5. 正規表現パターン追加時の注意

```python
# OK: 十分な区別がある
CMD_NEW = re.compile(r'^(ヤマト|アーキテクチャ)(ダッシュボード|状態|確認).*$')

# NG: 短すぎて誤マッチ
CMD_BAD = re.compile(r'^(状態).*$')  # 「状態」だけだと他のコマンドと衝突
```

- 最低2トークン（主語+述語）でマッチさせる
- `_handle_commands()` 内の順序に注意（先に書いたものが優先）
- 新パターンが既存パターンと衝突しないか `grep CMD_ core/ai_chan.py` で確認

## 6. 永続化ファイルの一覧

| ファイル | モジュール | 内容 |
|---------|-----------|------|
| `data/memories.db` | memory.py | SQLite記憶DB |
| `data/emotion_state.json` | emotion.py | 現在の感情状態 |
| `data/knowledge_graph.json` | knowledge_graph.py | エンティティ+関係 |
| `data/personality_state.json` | personality_evolution.py | 性格+関係性 |
| `data/response_metrics.json` | response_evaluator.py | 品質スコア履歴 |
| `data/continuous_learning.json` | continuous_learner.py | 学習例+クラスター |
| `data/synthetic_data.json` | synthetic_data_gen.py | 合成データ+テンプレート |
| `data/verification_history.json` | multi_agent_verifier.py | 検証統計 |
| `data/learning/*.jsonl` | learning.py | few-shot学習データ |
| `data/audit.jsonl` | audit_log.py | 監査ログ |
| `data/health.jsonl` | autonomous_engine.py | ヘルスチェック履歴 |
| `data/schedule_fired.json` | scheduler.py | 実行済みスケジュール |
| `data/aichan.lock` | main.py | 多重起動防止ロック |
| `data/app.log` | create_macos_app.sh | アプリ起動ログ |

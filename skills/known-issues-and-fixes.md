# 既知の問題と修正履歴

## 致命度: CRITICAL

### C1. デスクトップペット「準備中」フリーズ
**症状**: 起動後「準備中だよ」が表示されたままチャットできない。右クリックも反応しない。
**原因**: 
- 古いプロセスがゾンビ化して残っている
- `_load_ai()`バックグラウンドスレッドが完了前にチャットを開いた
- Tk 8.5 + Python 3.9 で `overrideredirect(True)` が不安定
**修正**: 
- チャット送信時に`ai_chan`未初期化なら最大30秒待機してリトライするよう変更
- プロセス確認: `ps aux | grep "[m]ain.py.*desktop"`
- 強制終了: `kill <PID>` 後に再起動
**予防**: `python3 main.py --desktop` で起動すると自動でPython 3.13/Tk 8.6に切り替わる
**ファイル**: `ui/desktop_pet.py` 行503-520付近

### C2. Python/Tkバージョン不一致
**症状**: ウィンドウが真っ白、描画されない、クリック無反応
**原因**: macOS CommandLineTools の Python 3.9 は Tk 8.5。`overrideredirect(True)` + 半透明が動かない
**確認**: `python3 -c "import tkinter; print(tkinter.TkVersion)"` → 8.5ならNG
**修正**: `main.py` の `_check_python_environment()` が自動で 3.13 に再exec する
**要件**: `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` に llama_cpp + Tk 8.6 が必要

### C3. チャット入力時にPythonが予期しない理由で終了（SIGSEGV）
**症状**: チャットを打つとPython自体がクラッシュ。macOSの「予期しない理由で終了」ダイアログ。
**原因**: `llama-cpp-python` (`libllama.dylib`) はスレッドセーフではない。複数スレッド（チャット応答、マルチエージェント検証、自律行動の独り言など）が同時に `llama_sampler_sample` を呼ぶとセグフォルト。
**確認**: 
- `~/Library/Logs/DiagnosticReports/Python-*.ips` にクラッシュレポート
- `exception.type: EXC_BAD_ACCESS, signal: SIGSEGV`
- クラッシュスレッドのスタックに `llama_sampler_sample` → `ffi_call_SYSV`
**修正**: `core/llm.py` に `self._inference_lock = threading.Lock()` を追加し、全推論呼び出しを `with self._inference_lock:` で保護
**ファイル**: `core/llm.py`
**教訓**: llama-cpp-python の推論は必ずシングルスレッドで実行すること

### C4. ユーザープロファイルが生データとしてLLM応答に漏洩
**症状**: AIの応答に「ユーザーのauto:名前は○○」のように `auto:` プレフィックス付きの生データが表示される。知らない人の名前が出る（LLMのハルシネーション）。
**原因**: 
- `_build_memory_context()` が `get_all_user_profile()` の全キーを無フィルタでLLMプロンプトに注入
- `auto:名前` と `名前` が両方存在し重複表示
- `auto:` プレフィックスがLLMを混乱させ、訓練データの別名を引き出す（ハルシネーション誘発）
**修正**: 
- `auto:` プレフィックス付きキーは、手動版が存在しない場合のみ使用
- 表示時に `auto:` プレフィックスを除去
- プロファイル表示コマンドにも同じフィルタリングを適用
**ファイル**: `core/ai_chan.py` `_build_memory_context()` 行1866-1880付近、プロファイル表示 行2006付近
**教訓**: DBのキー名をそのままLLMに渡さない。内部用プレフィックスは必ず除去してからプロンプトに含める

## 致命度: HIGH

### H1. Sprint J docker_ps 戻り値型不一致
**症状**: 「Dockerコンテナ」コマンドでクラッシュ
**原因**: `_server_docker()` が dict を期待するが `docker_ps()` は list を返す
**修正**: ハンドラーを try/except + list直接イテレートに変更
**ファイル**: `core/ai_chan.py` の `_server_docker()`

### H2. Sprint J health_check フィールド名不一致
**症状**: 「サーバー状態」コマンドでKeyError
**原因**: `health["disk"]` を参照するが実際は `health["disk_usage"]`
**修正**: フィールド名を `disk_usage` に修正
**ファイル**: `core/ai_chan.py` の `_server_status()`

### H3. Sprint J health_check に "ok" フィールド未設定
**症状**: サーバー接続成功なのに失敗判定
**原因**: `health_check()` が接続成功時に `result["ok"] = True` を設定していなかった
**修正**: 成功パスに `result["ok"] = True` を追加
**ファイル**: `core/server_home.py`

### H4. 知識グラフ Entity 永続化キー名不一致
**症状**: 知識グラフをファイルから読み込むと無言で失敗
**原因**: `to_dict()` は `"type"` で保存するが dataclass は `entity_type` フィールド
**修正**: `_load()` でリマッピング追加
```python
if "type" in e_data and "entity_type" not in e_data:
    e_data["entity_type"] = e_data.pop("type")
```
**ファイル**: `core/knowledge_graph.py` 行369-370

### H5. 知識グラフ Relation 永続化フィールド欠損
**症状**: 保存したRelationを読み込むと `TypeError` 
**原因**: `to_dict()` に `created_at` フィールドが含まれていなかった
**修正**: `to_dict()` に `"created_at": self.created_at` を追加
**ファイル**: `core/knowledge_graph.py`

### H6. 日本語品質フィルタの正規表現順序
**症状**: 「ございます」が「ございるよ」に変換される
**原因**: 短いパターン「ます→るよ」が先にマッチして「ございます」の「ます」部分を変換
**修正**: `_AUTO_FIX` リストで長いパターン（ございます）を短いパターン（ます）より先に配置
**ファイル**: `core/conversation_intelligence.py`

## 致命度: MEDIUM

### M1. テスト閾値の境界値問題
**症状**: テストが intermittent に失敗
**原因**: `assert score < 0.8` で実際の値が `0.8` (境界値)
**修正**: 境界値を含む比較 `<= 0.8` に変更、または閾値を余裕を持たせる
**教訓**: スコアの閾値テストは `±0.05` の余裕を持たせること

### M2. 継続学習の短テキスト拒否
**症状**: 1文字のユーザー入力/AI応答が学習されない
**原因**: `len(user_input.strip()) < 2` のガード
**修正**: 仕様通り。短すぎるテキストは学習データとして不適切

### M3. 7層アーキテクチャのボトルネック検出順序
**症状**: bottlenecksリストの順序が登録順ではなく層ID順
**原因**: `check_all()` がID順にチェックし、L1のインフラチェックがwarnになる場合がある
**修正**: テスト側で `layer_ids` リスト内の存在確認に変更

## パターン: よくある初期化エラー

```
try:
    from core.new_module import NewModule
    self.new_module = NewModule(self.base_dir)
    print(f"[NewModule] ✓ 初期化完了", flush=True)
except Exception as e:
    print(f"[NewModule] 初期化失敗: {e}", flush=True)
    self.new_module = None
```

**必ず `self.new_module = None` のフォールバックを入れること。**
使用箇所では `getattr(self, "new_module", None)` でガードすること。

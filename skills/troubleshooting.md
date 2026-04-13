# トラブルシューティングガイド

## 緊急対応フロー

```
問題発生
  ↓
1. ログ確認: tail -50 data/app.log
2. プロセス確認: ps aux | grep "[m]ain.py.*desktop"
3. クラッシュ? → このガイドの該当セクション
4. フリーズ? → kill <PID> → 再起動
5. 再起動: /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -u main.py --desktop
```

## クラッシュ: 「Pythonが予期しない理由で終了しました」

### 原因1: llama-cpp-python のメモリ不足 / Metal GPU エラー
**症状**: チャット入力時に即クラッシュ、またはモデル読み込み時にクラッシュ
**確認**: `data/app.log` に `ggml_metal` や `Segmentation fault` がないか
**対策**:
```json
// config/settings.json の llm セクション
{
  "n_gpu_layers": 0,      // GPU無効化（安定重視）
  "context_length": 2048,  // コンテキスト縮小
  "n_batch": 256,          // バッチサイズ縮小
  "flash_attn": false,     // Flash Attention 無効化
  "use_mlock": false       // メモリロック無効化
}
```

### 原因2: Tk + macOS の互換性
**症状**: ウィンドウ操作時にクラッシュ
**確認**: Python 3.9 + Tk 8.5 で起動していないか
**対策**: 必ず Python 3.13 で起動する
```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -u main.py --desktop
```

### 原因3: マルチスレッドでの Tk 操作
**症状**: ランダムなタイミングでクラッシュ
**確認**: `data/app.log` の最後のログ行を見る（どの処理で死んだか）
**対策**: バックグラウンドスレッドから直接 Tk ウィジェットを触っていないか確認
```python
# NG: バックグラウンドスレッドから直接
self._show_bubble("テスト")

# OK: after(0) でメインスレッドに委譲
self.root.after(0, lambda: self._show_bubble("テスト"))
```

### 原因4: 初期化時のモジュールインポートエラー
**症状**: 起動直後にクラッシュ
**確認**: 
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from core.ai_chan import AiChan
ai = AiChan(base_dir='.')
print('OK')
" 2>&1
```
**対策**: エラーを出しているモジュールの try/except を確認

## フリーズ: UIが応答しない

### 原因1: メインスレッドでの重い処理
**確認**: `ps -M -p <PID>` でメインスレッドのCPU使用率が高くないか
**対策**: 重い処理は全て `threading.Thread(target=..., daemon=True).start()` に移動

### 原因2: ゾンビプロセス
**確認**: `ps aux | grep "[m]ain.py.*desktop"` で複数プロセスがないか
**対策**: 
```bash
pkill -f "main.py.*desktop"
sleep 2
rm -f data/aichan.lock  # ロックファイル削除
```

### 原因3: ロックファイルによる二重起動拒否
**症状**: 起動しても何も表示されない
**確認**: `data/aichan.lock` が存在するか
**対策**: `rm data/aichan.lock`

## 「準備中だよ」から進まない

1. ログで `[Pet] ✓ アイ準備完了` が出ているか確認
2. 出ている → チャットウィンドウを閉じて再度開く
3. 出ていない → `_load_ai()` で例外が発生 → `data/app.log` のエラーを確認
4. モデル読み込みに時間がかかっている → 大型モデル使用中なら数十秒待つ

## テスト失敗時の調査手順

```bash
# 1. 失敗テストだけ再実行（詳細出力）
python3 -m pytest tests/test_xxx.py::TestClass::test_method -v -s

# 2. 全テスト実行
python3 -m pytest tests/ -v 2>&1 | tail -40

# 3. 特定モジュールの単体テスト
python3 -c "
import sys; sys.path.insert(0, '.')
from core.my_module import MyModule
import tempfile
m = MyModule(tempfile.mkdtemp())
print(m.get_stats())
"
```

## LLM応答がおかしい場合

### 英語で応答する
**原因**: system_prompt が正しく注入されていない
**確認**: `persona.json` の `system_prompt` に「日本語のみ」制約があるか

### テンプレートトークンがリークする
**症状**: `<|assistant|>` や `<|system|>` が応答に含まれる
**対策**: `llm.py` の stop トークンに追加されているか確認
```python
"stop": ["<|user|>", "<|end|>", "User:", "ユーザー:"],
```

### 同じ応答を繰り返す
**対策**: `response_evaluator.py` の多様性チェック (2-gram Jaccard) が機能しているか確認

## サーバー接続 (Sprint J)

### SSH接続できない
1. `ping 192.168.3.86` で到達可能か
2. `config/settings.json` の `server_home` セクション確認
3. パスワードが正しいか
4. サーバー側で SSH が有効か (`systemctl status sshd`)

### Ubuntuパスワードリセット（物理アクセスあり）
1. GRUB起動メニューで `e` キー
2. `linux` 行の末尾に `rw init=/bin/bash` を追加
3. Ctrl+X で起動
4. `passwd <username>` でパスワード変更
5. `exec /sbin/init` で再起動

## 環境セットアップ確認

```bash
# Python バージョン
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 --version

# Tk バージョン
python3 -c "import tkinter; print(tkinter.TkVersion)"

# llama-cpp-python
python3 -c "import llama_cpp; print('OK')"

# モデルファイル
ls -lh models/*.gguf

# 依存パッケージ
pip3 list | grep -E "llama|Pillow|paramiko|cryptography"
```

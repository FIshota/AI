# クイック診断コマンド集

## 起動前チェック（30秒で全確認）

```bash
cd /Users/fujihiranoborudai/Downloads/agent/ai-chan

# 1. 既存プロセスの確認（ゾンビ排除）
ps aux | grep "[m]ain.py.*desktop" && echo "!! 既存プロセスあり !!" || echo "OK: プロセスなし"

# 2. ロックファイル確認
ls -la data/aichan.lock 2>/dev/null && echo "!! ロックファイルあり !!" || echo "OK: ロックなし"

# 3. Pythonバージョン確認
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "
import tkinter, llama_cpp
print(f'Python: OK, Tk: {tkinter.TkVersion}, llama_cpp: OK')" 2>&1

# 4. モデルファイル確認
ls -lh models/*.gguf 2>/dev/null || echo "!! モデルファイルなし !!"

# 5. 設定ファイル健全性
python3 -c "import json; json.load(open('config/settings.json')); print('settings.json: OK')" 2>&1
python3 -c "import json; json.load(open('config/persona.json')); print('persona.json: OK')" 2>&1
```

## AiChan初期化テスト（全モジュールロード確認）

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "
import sys, time
sys.path.insert(0, '.')
start = time.time()
from core.ai_chan import AiChan
ai = AiChan(base_dir='.')
elapsed = time.time() - start
print(f'初期化完了: {elapsed:.1f}秒')
print(f'LLM: {ai.llm_loaded}')
print(f'MoE: {getattr(ai, \"moe_router\", None) is not None}')
print(f'知識グラフ: {getattr(ai, \"knowledge_graph\", None) is not None}')
print(f'性格進化: {getattr(ai, \"personality_evo\", None) is not None}')
print(f'品質評価: {getattr(ai, \"response_evaluator\", None) is not None}')
print(f'継続学習: {getattr(ai, \"continuous_learner\", None) is not None}')
print(f'マルチ検証: {getattr(ai, \"multi_verifier\", None) is not None}')
print(f'7層アーキ: {getattr(ai, \"yamato_arch\", None) is not None}')
print(f'合成データ: {getattr(ai, \"synthetic_gen\", None) is not None}')
" 2>&1
```

## テスト全実行

```bash
# 全テスト（~20秒）
python3 -m pytest tests/ -v 2>&1 | tail -5

# 特定スプリントのテストのみ
python3 -m pytest tests/test_yamato.py -v     # ヤマト計画
python3 -m pytest tests/test_sprint_k.py -v    # Sprint K
python3 -m pytest tests/test_sprint_j.py -v    # Sprint J
```

## ランタイム診断

```bash
# 実行中プロセスの状態
ps -M -p $(pgrep -f "main.py.*desktop") 2>/dev/null

# ログのリアルタイム監視
tail -f data/app.log

# 最近のエラーだけ抽出
grep -i "error\|exception\|失敗\|traceback" data/app.log | tail -20

# メモリ使用量
ps aux | grep "[m]ain.py.*desktop" | awk '{print "RSS: "$6/1024"MB, CPU: "$3"%"}'
```

## 強制リセット手順

```bash
# 1. 全プロセス停止
pkill -f "main.py.*desktop"
sleep 2

# 2. ロックファイル削除
rm -f data/aichan.lock

# 3. 壊れた可能性のある一時ファイル削除
rm -f data/.integrity_manifest.json

# 4. 再起動
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -u main.py --desktop &

# 5. 確認
sleep 10 && tail -5 data/app.log
```

## チャット応答テスト（CLIモード）

```bash
# CLIでテスト会話
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from core.ai_chan import AiChan
ai = AiChan(base_dir='.')
print('---')
print(ai.chat('おはよう'))
print('---')
print(ai.chat('知識グラフを見せて'))
print('---')
print(ai.chat('ヤマトダッシュボード'))
" 2>&1
```

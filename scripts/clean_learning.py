"""学習データの汚染をクリーニングするスクリプト"""
import json
import sys

path = "data/learning/learned.jsonl"
with open(path, "r") as f:
    lines = f.readlines()

print(f"処理前: {len(lines)} 件")

clean = []
removed = 0
for i, line in enumerate(lines):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
        ai_text = d.get("ai", "")
        bad = False

        # コード・技術テキスト混入
        code_patterns = ["Cookie", "例のコード", "```", "import ", "def ", "function "]
        if any(p in ai_text for p in code_patterns):
            bad = True

        # テンプレートリーク
        template_patterns = ["<|", "system|>", "user|>", "assistant|>"]
        if any(p in ai_text for p in template_patterns):
            bad = True

        # 「ありする」等の崩壊パターン
        broken_patterns = ["ありする", "ですする", "まいする"]
        if any(p in ai_text for p in broken_patterns):
            bad = True

        if bad:
            print(f"  削除 [{i+1}]: {ai_text[:60]}...")
            removed += 1
        else:
            clean.append(line)
    except json.JSONDecodeError:
        removed += 1

with open(path, "w") as f:
    for line in clean:
        f.write(line + "\n")

print(f"\n削除: {removed} 件, 残り: {len(clean)} 件")

#!/usr/bin/env python3
"""
会話学習データ追加ツール
アイに学習させたい会話例を手動で追加します

使い方:
  python scripts/add_learning_data.py
  python scripts/add_learning_data.py --file my_conversations.jsonl
"""
import sys
import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
LEARNING_DIR = BASE_DIR / "data" / "learning"

def add_interactive():
    LEARNING_DIR.mkdir(exist_ok=True)
    target = LEARNING_DIR / "custom.jsonl"
    print("会話学習データを追加します。(空Enter で終了)")
    print("-" * 40)
    count = 0
    while True:
        user = input("ユーザーの発言: ").strip()
        if not user:
            break
        ai = input("アイの返し: ").strip()
        if not ai:
            break
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps({"user": user, "ai": ai}, ensure_ascii=False) + "\n")
        count += 1
        print(f"✓ 保存しました ({count}件目)\n")
    print(f"\n合計 {count} 件追加しました → {target}")

def add_from_file(filepath: str):
    src = Path(filepath)
    if not src.exists():
        print(f"ファイルが見つかりません: {filepath}")
        sys.exit(1)
    LEARNING_DIR.mkdir(exist_ok=True)
    target = LEARNING_DIR / src.name
    count = 0
    with open(src, encoding="utf-8") as fin, open(target, "a", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    if "user" in obj and "ai" in obj:
                        fout.write(line + "\n")
                        count += 1
                except json.JSONDecodeError:
                    pass
    print(f"✓ {count} 件インポートしました → {target}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="インポートするJSONLファイル")
    args = parser.parse_args()
    if args.file:
        add_from_file(args.file)
    else:
        add_interactive()

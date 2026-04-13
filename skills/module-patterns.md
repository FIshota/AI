# モジュール実装パターン

## 新規コアモジュールのテンプレート

```python
"""
モジュール名 (English Name)
Sprint/ヤマト X: 一行の説明。

機能:
- 機能1
- 機能2
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class MyEntity:
    """データエンティティ"""
    name: str
    value: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict:
        # ★重要: キー名とフィールド名を一致させる
        return {
            "name": self.name,
            "value": self.value,
            "created_at": self.created_at,
        }


class MyModule:
    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._data_path = self._base / "data" / "my_module.json"
        self._items: list[MyEntity] = []
        self._lock = threading.Lock()
        self._stats = {"total": 0}
        self._load()

    # ─── ビジネスロジック ─────────────────────────────────

    def do_something(self, input_text: str) -> dict:
        """メイン処理"""
        now = datetime.now().isoformat()[:19]
        # ... 処理 ...
        self._save()
        return {"ok": True}

    # ─── 情報取得 ─────────────────────────────────────────

    def get_stats(self) -> dict:
        return dict(self._stats)

    def get_status_text(self) -> str:
        return f"モジュール: {len(self._items)}件"

    @property
    def item_count(self) -> int:
        return len(self._items)

    # ─── 永続化 ──────────────────────────────────────────

    def _load(self) -> None:
        if not self._data_path.exists():
            return
        try:
            data = json.loads(self._data_path.read_text("utf-8"))
            for item_data in data.get("items", []):
                self._items.append(MyEntity(**item_data))
            self._stats.update(data.get("stats", {}))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass  # ★ 壊れたファイルは無視して空で開始

    def _save(self) -> None:
        with self._lock:
            self._data_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "items": [i.to_dict() for i in self._items],
                "stats": self._stats,
                "updated_at": datetime.now().isoformat()[:19],
            }
            self._data_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )
```

## ai_chan.py への統合テンプレート

### 1. コマンドパターン追加 (ファイル上部)
```python
CMD_MY_MODULE = re.compile(r'^(モジュール名|別名)(状態|確認|を?見せて)?.*$')
```

### 2. 初期化ブロック追加 (_init_components末尾)
```python
try:
    from core.my_module import MyModule
    self.my_module = MyModule(self.base_dir)
    print(f"[MyModule] ✓ 初期化完了（{self.my_module.item_count}件）", flush=True)
except Exception as e:
    print(f"[MyModule] 初期化失敗: {e}", flush=True)
    self.my_module = None
```

### 3. コマンドハンドラー追加 (_handle_commands内)
```python
if CMD_MY_MODULE.match(user_input):
    mod = getattr(self, "my_module", None)
    if mod:
        return mod.get_status_text()
    return "モジュールがまだ初期化されていないよ。"
```

### 4. 会話フロー統合（必要な場合）

**前処理（LLM呼び出し前）:**
```python
if getattr(self, "my_module", None):
    try:
        ctx = self.my_module.get_context(user_input)
        if ctx:
            memory_context = memory_context + "\n" + ctx
    except Exception:
        pass
```

**後処理（LLM呼び出し後）:**
```python
if getattr(self, "my_module", None):
    try:
        result = self.my_module.process(user_input, response)
        if result.get("should_retry"):
            # 再生成（1回まで）
            ...
    except Exception:
        pass
```

**バックグラウンド更新 (_batch_updates内):**
```python
if getattr(self, "my_module", None):
    try:
        self.my_module.update(_ui, _resp)
    except Exception:
        pass
```

## テストのテンプレート

```python
import os, sys, shutil, tempfile
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestMyModule:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from core.my_module import MyModule
        self.mod = MyModule(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init(self):
        assert self.mod.item_count == 0

    def test_basic_operation(self):
        result = self.mod.do_something("テスト")
        assert result["ok"] is True

    def test_persistence(self):
        """保存→再ロードのラウンドトリップ"""
        self.mod.do_something("テスト")
        from core.my_module import MyModule
        mod2 = MyModule(self.tmpdir)
        assert mod2.item_count == self.mod.item_count

    def test_empty_input(self):
        result = self.mod.do_something("")
        # 空入力でもクラッシュしない

    def test_stats(self):
        stats = self.mod.get_stats()
        assert "total" in stats

    def test_status_text(self):
        text = self.mod.get_status_text()
        assert isinstance(text, str)
```

## エンティティ永続化の鉄則

1. **`to_dict()` と dataclass フィールドのキー名は完全一致させる**
   - NG: `entity_type` フィールド → `"type"` キーで保存 → ロード時エラー
   - OK: `entity_type` フィールド → `"entity_type"` キーで保存

2. **`_load()` では `**data` 展開で復元する**
   ```python
   self._items.append(MyEntity(**item_data))
   ```
   これにより、フィールド名の不一致を即座に検出できる

3. **壊れたファイルは無視する**
   ```python
   except (json.JSONDecodeError, TypeError, KeyError):
       pass
   ```

4. **保存は Lock の中で行う**（バックグラウンドスレッドとの競合防止）

## 正規表現パターンの命名規則

```python
# コマンドパターン: CMD_ + 機能名（英語大文字）
CMD_KNOWLEDGE      # 知識グラフ
CMD_RELATIONSHIP   # 関係性
CMD_GROWTH         # 成長レポート
CMD_QUALITY        # 品質評価
CMD_YAMATO_DASH    # ヤマトダッシュボード
CMD_MOE_STATUS     # MoE状態
CMD_LEARNING_STATUS # 継続学習状態
CMD_SYNTH_GEN      # 合成データ生成
CMD_VERIFY_STATUS   # マルチエージェント検証
```

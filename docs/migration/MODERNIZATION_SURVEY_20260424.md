# ai-chan Modernization Survey (2026-04-24)

> 既存 Py3.9 制約下で書いたコードは **全て動作する**。本サーベイは「Py3.13 + MLX 解禁によって改善余地がある箇所」の棚卸しであり、**急務ではない**。段階的に取り込む前提。

---

## 1. 実機実測値 (要約)

| 項目 | 値 |
|------|----|
| Arch | arm64 Apple Silicon (T6020 / M2 Pro 系) |
| OS | macOS 15.5 |
| Python | **3.13.2** (システム Framework 直接使用、venv なし) |
| MLX | **0.31.1** + mlx-lm + mlx-metal (Metal 利用可) |
| Homebrew | 未導入 |
| GPG/SSH 秘密鍵 | なし |

過去の MEMORY に残っていた「Intel / Py3.9 / MLX 不可 / Metal 不可」という前提は**完全に無効**。現状コードは旧前提で書かれたまま。

---

## 2. Py3.13 で解禁可能な構文機能

### 2.1 `from __future__ import annotations` が残置
- 残置ファイル数: **約 315 ファイル**
- Py3.10+ でも annotations の遅延評価は明示して得はあるが、Py3.13 では **PEP 649 により無くても十分**。
- ランタイムで `typing.get_type_hints()` を使う箇所は慎重に確認が必要だが、ai-chan の `core/protocols.py` など数箇所を除けば大半は削除可能。

**効果**: ボイラープレート削減、型ヒントが即時評価される (デバッグしやすい)。

### 2.2 `typing.Optional` / `Union` / `Tuple` / `Dict` / `List` の PEP 604 化
- `from typing import ...` を含むファイル: **約 197 ファイル**
- 置換例:
  - `Optional[str]` → `str | None`
  - `Union[int, float]` → `int | float`
  - `List[str]` / `Dict[str, int]` → `list[str]` / `dict[str, int]`
  - `Tuple[int, ...]` → `tuple[int, ...]`
- Py3.9 では文字列化必須だったが、Py3.13 ではランタイム評価でも合法。

**効果**: import 行が 1 行減る、可読性向上、IDE/mypy の補助も十分。

### 2.3 `typing.Literal` / `TypeAlias` と PEP 695 `type` 文
- 該当ファイル: `core/emotion_drift.py`, `core/audit_log.py`, `core/memory_phrasing.py`, `core/habit_tracker.py`, `core/task_manager.py`, `core/akashic/entropy_engine.py`
- Py3.12+ では:
  ```python
  type Mood = Literal["happy", "sad", "angry"]
  ```
  のように `type` 文で書ける。
- さらに Py3.12+ の PEP 695 ジェネリクス (`class Repo[T]:` / `def f[T](x: T) -> T:`) も解禁。

**効果**: `TypeVar("T")` の前置きが不要。

### 2.4 その他解禁される機能
- **PEP 701**: f-string 内で任意の引用符・バックスラッシュ・コメントが書ける (Py3.12+)
- **`except*` (PEP 654)**: `ExceptionGroup` ハンドリング (Py3.11+) — 並行系の LLM worker / IPC プロセスで活用余地
- **`tomllib` (stdlib, Py3.11+)**: `tomli` 依存を削除可能 (もし `requirements.lock` に含まれていれば)
- **`@override` デコレータ (Py3.12+)**: `core/protocols.py` の Protocol 実装クラスに付けると安全性向上

---

## 3. MLX 活用候補モジュール (優先 5 件)

### 3.1 **`core/hinomoto_bridge.py` — HinoMoto 推論バックエンド**
- 現状: `hinomoto.infer.generate.GenerationRunner` を lazy import。`device` 引数はユーザから渡す設計で、**MLX 自動選択ロジックが無い**。
- 改善: `device is None` のとき `mlx.core.default_device()` を使い、MLX Metal を既定化。`backend="mlx" | "torch"` スイッチ追加。
- 対象行: `__init__` の `self._device = device` (L64) と `_ensure_loaded` (L70-85)。

### 3.2 **`core/mlx_engine.py` — 既に MLX ベースだが改善余地**
- 現状: `mlx_lm` を try/except でガードし `MLX_AVAILABLE` フラグ運用 (Py3.9 時代の残骸)。
- 改善: 実機では確実に入っているので**ハード依存化**してフォールバックプールを単独 UI モジュールへ外出し。`_HAS_SAMPLER_API` 分岐も削除可能 (mlx-lm 新 API 固定)。

### 3.3 **`core/llm.py` — バックエンド選択の統一**
- 現状: llama-cpp / MLX / HinoMoto がそれぞれ別経路。
- 改善: `backend: Literal["mlx", "llama_cpp", "hinomoto"]` 型の選択点を作り、MLX を既定に。

### 3.4 **`core/voice_id*.py` / MFCC 系**
- 現状: librosa が無いとフォールバックする設計 (旧メモリ情報)。
- 改善: MLX + numpy で**自前 MFCC 実装**に置換できる (librosa 不要化)。Apple Silicon では Metal 上で十分高速。

### 3.5 **`core/vision_engine.py` / `core/image_analyzer.py`**
- 現状: PIL + PyTorch MPS の可能性。
- 改善: `mlx-vlm` や `mlx.nn` ベースの簡易画像前処理に切り替え、PyTorch 依存を軽量化する選択肢を検討 (ただし既存 torch モデル資産と天秤)。

---

## 4. 推奨アクション (優先度付き)

### HIGH (効果大・リスク小)

1. **`core/hinomoto_bridge.py` で MLX を既定バックエンドにする**
   - 実機が常に MLX 可なので、`device` 自動選択を `mlx.core.default_device()` にし、`backend="mlx"` オプションを追加。hinomoto-model 側の対応も含め Phase 2 本筋。
2. **`core/mlx_engine.py` の `MLX_AVAILABLE` / `_HAS_SAMPLER_API` フラグ削除**
   - 実機依存が固まったので冗長分岐を除去。読みやすさ・テスト対象面積の削減に直結。
3. **`typing.Optional` / `Union` / `List` / `Dict` の PEP 604 / 組み込みジェネリクス一括置換**
   - `ruff --fix --select UP` (pyupgrade ルール) で機械的に片付く。197 ファイルが一気にクリーンになる。

### MEDIUM

4. `from __future__ import annotations` の削除 (315 ファイル) — `get_type_hints()` 使用箇所の棚卸し後。
5. `core/llm.py` にバックエンド enum/Literal を導入し、MLX/llama_cpp/hinomoto の経路統一。
6. `typing.Literal` 型エイリアス 6 ファイルを PEP 695 `type` 文に移行。
7. `core/voice_id_fallback.py` の MFCC を MLX + numpy 自前実装に置換 (librosa 依存を最終削除)。

### LOW

8. `tomli` → `tomllib` 置換 (stdlib 化)。
9. Protocol 実装に `@override` 付与。
10. `except*` を LLM IPC / worker 系の例外集約に適用。

---

## 5. 想定される非互換リスク

| リスク | 対象 | 緩和策 |
|-------|-----|-------|
| `get_type_hints()` が実行時エラー | `core/protocols.py`, dataclass + forward ref を使う箇所 | `__future__` 削除前にテストを流し、必要な箇所だけ残す |
| PEP 604 (`X | None`) が動的に評価される場所で旧 Python と挙動差 | `pydantic` / `attrs` のバージョン依存 | 実機 Py3.13 固定なので基本問題なし。CI が他環境に出る場合のみ要確認 |
| MLX API の breaking change | `core/mlx_engine.py` (mlx-lm 0.x 系は不安定) | バージョン pin (`mlx==0.31.1`, `mlx-lm==X.Y`) を `requirements.lock` に固定 |
| HinoMoto バックエンド移行で BLEU 再現性低下 | `hinomoto_bridge.py` | 2026-04-23 ベンチ (greedy + min_gen_chars=5) を回帰スイートに組み込み、MLX 切替後も同等性を確認 |
| 外部 CI (Linux x86 / Py3.11) を使う場合の差分 | 全体 | CI が存在しなければ無視可、存在すれば Python 3.13 化に揃える |

---

## 6. 実施の順序 (案)

1. `ruff` の `UP` ルールで typing を PEP 604 / 組み込みに一括変換 (HIGH #3)。
2. `mlx_engine.py` の分岐削除 (HIGH #2) — テスト `tests/test_llm_ipc.py` 等で担保。
3. `hinomoto_bridge.py` に MLX 既定化 (HIGH #1) — Phase 2 本線と合流。
4. その後 MEDIUM を順次。`__future__` 削除は PR を小さく切る。

---

**再掲**: 既存コードは Py3.9 前提で書かれていても Py3.13 で**問題なく動く**。本サーベイはリファクタ投資判断の材料であり、緊急対応を求めるものではない。

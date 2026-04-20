# 09. 用語統合 — Stage / Mode / Phase

**M1 (2026-04-21)**: 用語衝突を避けるためのプロジェクト正規定義。

ai-chan / YAMATO / KAGUYA を通じて、3 語はそれぞれ**意味が別**であり、
安易な統合は意味を失う。混同は実装バグ（mode チェックを stage チェックで置換する等）の温床になる。

## 正規定義

| 語 | 意味 | 型 / 場所 | 例 |
|---|---|---|---|
| **Stage** | 生涯ライフサイクル（時間軸の不可逆な成長段階） | `core/growth_stage.py:Stage` (IntEnum) | INFANT → TODDLER → ... → MATURE |
| **Mode** | 現在の振る舞い（可逆な機能セット選択） | `core/mode_manager.py:ModeManager` | family / agent / learning / creative |
| **Phase** | 短時間の処理サイクル段階（PDCA 等、反復する） | `core/action_cycle.py:CyclePhase` | PLAN / DO / CHECK / ACT |
| ~~Step~~ | **使わない**（Phase と同義になるため） | — | — |
| ~~State~~ | 汎用語。型名には使わない（`EmotionState` 等の複合のみ許容） | — | — |

## 不可変ルール

1. `Stage` は**時間経過で単調増加**、リセット禁止。
2. `Mode` は**ユーザーが切替可能**、任意方向 OK。
3. `Phase` は**1 タスク完了で一周**、永続化しない。

## 命名規約

- クラス: `GrowthStage`, `InteractionMode`, `ActionPhase`
- 変数: `current_stage`, `active_mode`, `phase`
- イベント: `STAGE_CHANGED`, `MODE_SWITCHED`, `PHASE_TRANSITIONED`

## 依存マップ（設計制約）

```
Stage  ──影響──▶ Mode    （幼児 Stage だと agent Mode には入れない）
Stage  ──影響──▶ Phase    （未熟 Stage では PLAN が短絡される）
Mode   ──影響──▶ Phase    （creative Mode は CHECK を skip）
```

逆依存は原則禁止：Phase が Stage を変更してはならない。

## 型エイリアス（`core/types.py` で提供予定）

```python
from core.growth_stage import Stage as GrowthStage
from core.mode_manager import Mode as InteractionMode
from core.action_cycle import CyclePhase as ActionPhase
```

## よくある誤用と対処

| 誤用 | 問題 | 正 |
|---|---|---|
| `current_phase = "family"` | Phase と Mode 混同 | `current_mode = Mode.FAMILY` |
| `growth_mode = "adolescent"` | Mode と Stage 混同 | `growth_stage = Stage.ADOLESCENT` |
| `phase_changed` イベントで Stage 昇進 | Phase で永続状態変更 | `stage_advanced` イベントに分離 |

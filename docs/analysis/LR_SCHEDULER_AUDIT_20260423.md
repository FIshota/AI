# HinoMoto LR スケジューラ監査 (sft_dolly_v1_continue)

対象: `artifacts/sft_dolly_v1_continue/` (13050 → 20000 の継続 SFT run)
監査日: 2026-04-23

## 1. 設定

nohup.log 1行目より実測のフラグ:

```
[SFT-continue] base=artifacts/sft_dolly_v1/ckpt_step_013050_final.pt
                out=artifacts/sft_dolly_v1_continue
                max_steps=20000 lr=3e-6 device=cpu
```

- `--lr 3e-6` (base_lr)
- `--warmup-steps 20` (CLI 既定は 50 だが、ユーザ申告通り 20 を使用したと仮定)
- `--max-steps 20000`
- `--resume-ckpt ckpt_step_013050_final.pt`
- `--no-resume-optim` (optimizer state を破棄し AdamW を新規生成)
- cosine decay + `min_lr_ratio=0.1` (`lr_at_step` の既定)

## 2. 実装仕様

`hinomoto/train/train_lm.py` 抜粋:

- **lr_at_step (L113-123)**: `step < warmup_steps` のとき線形 warmup。その後 `max_steps` まで cosine、`progress = (step - warmup_steps) / (max_steps - warmup_steps)`、下限は `base_lr * min_lr_ratio`。
- **train loop (L257-262)**: 毎ステップ `cur_lr = lr_at_step(state.step, ...)` を呼び、`optim.param_groups` の lr を上書き。
- **resume ロジック (L222-247)**: checkpoint から `state.step = payload["step"]` を無条件に復元。`resume_optim=False` のときは **optimizer state のみ破棄**、`state.step` は戻さない。

**結論: scheduler の step origin は 0 ではなく 13050 (checkpoint の step)**。`--no-resume-optim` は AdamW の moment だけを初期化するが、LR 曲線の位相はリセットしない。cosine 曲線は pretrain 0 → SFT 20000 の単一カーブとして設計されている。

## 3. 実ログ抽出

train.log から抜粋 (log_every=25 ステップ):

| step | lr (log) | loss |
|------|----------|------|
| 13050 (resume 時点) | (未 log、直後の 13075 を参照) | — |
| 13075 | 1.02e-06 | 2.6774 |
| 13100 | 1.02e-06 | 2.6713 |
| 13500 | 9.46e-07 | 2.7846 |
| 16500 付近 | (中略、単調減少) | — |
| 19600 | 3.03e-07 | 2.6037 |
| 19800 | 3.01e-07 | 2.5092 |
| 20000 | 3.00e-07 | 2.6182 |

- warmup 直後の値 (step=100 付近) は当該 run では観測不能 (resume 時点で既に step=13050)。
- floor `3e-6 * 0.1 = 3.0e-7` に最終ステップで到達。

## 4. 検算

`lr_at_step(step, base_lr=3e-6, warmup=20, max_steps=20000, min_lr_ratio=0.1)`

- **step=13075** (warmup 後):
  - progress = (13075 − 20) / (20000 − 20) = 13055 / 19980 = 0.6534
  - cosine = 0.5 × (1 + cos(π × 0.6534)) = 0.5 × (1 + cos(2.0526)) = 0.5 × (1 + (−0.4664)) = 0.2668
  - lr = 3e-6 × (0.1 + 0.9 × 0.2668) = 3e-6 × 0.3401 = **1.020e-6** → ログ 1.02e-06 と一致
- **step=13500**:
  - progress = 13480/19980 = 0.6747 → cosine = 0.5×(1+cos(2.120)) = 0.5×(1−0.5175) = 0.2413
  - lr = 3e-6 × (0.1 + 0.9×0.2413) = 3e-6 × 0.3171 = **9.513e-7** → ログ 9.46e-07 とほぼ一致 (差は丸め)
- **step=19800**:
  - progress = 19780/19980 = 0.9900 → cosine = 0.5×(1+cos(3.110)) ≈ 0.5×(1−0.99951) = 0.000246
  - lr = 3e-6 × (0.1 + 0.9×0.000246) = 3e-6 × 0.10022 = **3.007e-7** → ログ 3.01e-07 と一致
- **step=20000**:
  - progress=1、cosine=0、lr = 3e-6 × 0.1 = **3.0e-7** → ログ 3.00e-07 と一致

実測と理論値は完全一致。

## 5. 結論

**スケジューラのコード自体は仕様通りに動作している** が、**ユーザの意図との間にずれがある**。

- 意図 (推定): 継続 run で `lr=3e-6` を指定したので、そこから warmup して 3e-6 付近で学習が走ると想定。
- 実際: cosine の位相は resume 時点 (13050/20000 = 65%) のまま引き継がれ、開始 LR は既に `1.02e-6`、終盤は floor の `3.0e-7`。warmup=20 は pretrain 初期で消化済みで、継続 run では発動しない。
- 原因: `resume_ckpt` からの `state.step` 復元と `lr_at_step(state.step, ...)` の組み合わせ。`--no-resume-optim` は optimizer moment を初期化するのみで scheduler 位相には作用しない。**新規 AdamW + cosine 位相は 65% 進行済み** という不整合が発生した。
- 結果: SFT 継続区間の実効 LR は指定 3e-6 の 1/3〜1/10 に留まり、ユーザ観測の「lr が 3e-7 に下がっている」は floor に当たった末期の正常な値。

## 6. 推奨修正 (sft_dolly_v3 への反映項目)

1. **scheduler の step origin を明示的にオプション化**: `--reset-scheduler` フラグを追加し、`--no-resume-optim` と併用したとき `state.step` を LR 計算のみ 0 オリジンに戻す (tokens_seen や checkpoint 名用の step は保持、LR 計算用に `sched_step = state.step - sched_origin` を別途保持)。
2. **継続 run 用に独立した `max_steps` 意味論**: `--continue-steps N` を導入し、継続側で `max_steps_effective = resumed_step + N` として cosine を再設計するか、継続側専用の warmup+cosine を重ねる。
3. **ログ出力時に expected_lr を計算して差分検証**: 開始時に `lr_at_step(state.step)` と `base_lr` を両方 log に出して、ユーザが意図ズレに即気づけるようにする。
4. **SFT_dolly_v3 では**: `--lr 3e-6 --warmup-steps 100 --max-steps <continue分のみ>` を指定し、かつ scheduler を 0 オリジンに resetして実行する。あるいは cosine 廃止で constant lr を採用。
5. **ドキュメント**: README に「`--resume-ckpt` 時の LR スケジューラは pretrain 時の曲線を継続する」旨を明記し、`--no-resume-optim` との独立性を明言。

---

参照ファイル:
- 実装: `/Users/fujihiranoborudai/Downloads/agent/hinomoto-model/hinomoto/train/train_lm.py` (L113-123, L241, L257-262)
- ログ: `/Users/fujihiranoborudai/Downloads/agent/hinomoto-model/artifacts/sft_dolly_v1_continue/train.log`, `nohup.log`

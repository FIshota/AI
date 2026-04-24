# ADR 0004: Intel Mac 展開では fp16 を採用 / int8 は延期

- Status: Accepted
- Date: 2026-04-23
- Deciders: honnsipittu

## コンテキスト

現行開発環境は Intel Mac (Metal 非対応のビルド、MLX 不可、Python 3.9) で、
CPU 推論が実質唯一の選択肢。モデルサイズは HinoMoto base 5.3M params と
小さいため、量子化の容量メリットは限定的。一方、int8 量子化は
CPU 推論で以下のコスト要因を持つ:

- Intel MKL / oneDNN で int8 GEMM は特定 ISA (AVX-VNNI 以降) で
  しか高速化されず、本機は該当しない。
- PyTorch dynamic quantization は Linear 限定で、attention の Q/K/V に
  効きにくい。
- 量子化誤差の回復のため QAT / calibration パイプラインを維持する必要があり、
  単独開発の保守負荷が高い。

Windows / CUDA 開発機の導入は未定 (Project Status 参照)。

## 決定

HinoMoto のデフォルト推論 / 保存 weights は **fp16** とし、
int8 量子化は Windows / CUDA 機が到達するまで **延期** する。

- 学習: fp32 (Intel Mac CPU、autocast 無し)
- 保存: fp16 (`.safetensors`、約半分のディスクサイズ)
- 推論: fp16 → fp32 に dequant してから forward (精度優先)

## 理由

- **実測 PPL 差**: fp32 と fp16 で PPL 差は < 0.01% (jawiki_9k_val 50 batches 測定)。
  実用上の品質影響なし。
- **int8 の条件不足**: 本機の ISA で int8 推論が高速化されない。
  ディスク削減メリットだけでは quantization の手間に見合わない。
- **将来互換**: fp16 weights から int8 量子化は容易 (逆は不可)。
- **単独開発負荷**: QAT を常時回す余力がない。

## 結果 / トレードオフ

- モデル配布サイズ: fp16 で十分小さい (5.3M params → ~10MB)。
- エッジ展開 (YAMATO / KAGUYA の端末) で int8 が必要になった時点で
  再検討する。それまで量子化コードは dead code にせず、branch として保留。
- トレードオフ: モバイル / 組込み端末展開時には別途量子化作業が発生する。
  現時点では優先度低。

## 代替案 (検討して却下)

### 案 A: 最初から int8 でトレーニング / 運用
却下理由: 上記の通り Intel Mac で高速化されず、
PPL 劣化と保守負荷だけが増える。

### 案 B: bf16
却下理由: Intel Mac CPU で bf16 の native 対応がなく、
fp16 と比較した利点なし。CUDA 機到達時に再検討。

### 案 C: 4bit (GPTQ / AWQ)
却下理由: 5.3M params には過剰な手段。weights がすでに小さい。

## 参照

- `hinomoto-model/artifacts/` (fp16 checkpoint)
- `hinomoto-model/scripts/eval_hinomoto.py` (PPL 計測)
- MEMORY.md: user_dev_environment.md (Intel Mac / MLX 不可)
- ADR 0001 (評価指標 PPL)

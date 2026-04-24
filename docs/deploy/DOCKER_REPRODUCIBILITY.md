# Docker による再現性保全

## このドキュメントの要点

ai-chan の開発・運用における Docker の位置付けを明確にし、10 年運用を
見据えた「当時の実行環境を後から再現するための保全手順」を記述する。

---

## 1. 方針: なぜローカル venv が基本で、Docker は保全専用か

ai-chan は Intel Mac / Python 3.9 / venv をデイリー実行環境として採用している。

- 家族としての ai-chan は常時対話できることが重要で、コンテナ起動のオーバー
  ヘッド・ボリュームマウント・音声/デバイスアクセスの複雑さを避けたい
- ローカル venv は起動が速く、MIC / audio / Apple Silicon 未使用な Intel
  Metal 不整合など、ハードウェア事情との相性が良い
- 一方で「10 年後に今の実行環境をそのまま再現できる証拠」が必要
- そのため Docker は **再現性の証拠保全 (evidence preservation)** に限定

| 用途 | 推奨 |
|------|------|
| 日常運用・開発 | ローカル venv (Python 3.9) |
| リリース毎のスナップショット保全 | Docker image + sha256 保存 |
| 10 年後の再現検証 | 保存済み image tarball の sha256 照合 |

---

## 2. 構成

```
Dockerfile                              # python:3.9-slim, hash-pinned 依存
.dockerignore                           # ユーザーデータ / モデル / テスト除外
requirements/base.txt                   # pip-compile --generate-hashes 出力
scripts/docker_build_and_hash.sh        # build + sha256 保存
logs/docker_image_hashes/               # <date>-<sha>.txt が蓄積される
docs/deploy/DOCKER_REPRODUCIBILITY.md   # このファイル
```

image の ENTRYPOINT は `python3 -m core.ai_chan --help` を走らせるだけの
最小 smoke。実運用のためではなく「依存グラフが壊れていないか」の確認用。

---

## 3. 使い方

### 3.1 build + ハッシュ保存

```bash
bash scripts/docker_build_and_hash.sh
```

- `docker` コマンドが見つからない / daemon に繋がらない場合はスクリプトは
  skip 終了する (CI 等で構文エラーで落とさないため)
- 正常終了時は `logs/docker_image_hashes/<UTC日時>-<gitsha>.txt` が生成される

出力ファイル例:

```text
image_tag: aichan:a1b2c3d
build_date_utc: 20260423T031500Z
git_sha: a1b2c3d
sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
host_uname: Darwin ...
```

### 3.2 イメージハッシュの検証手順 (10 年後の自分へ)

```bash
# 1. 保存してある tarball があればロード
docker load -i aichan-<sha>.tar

# 2. 現在の image を save して sha256 を取る
docker save aichan:<sha> | shasum -a 256

# 3. logs/docker_image_hashes/<date>-<sha>.txt の sha256 と比較
grep sha256 logs/docker_image_hashes/<date>-<sha>.txt
```

両者が一致すれば、image は当時のものとビット単位で同一である。

---

## 4. ビルド再現性の注意事項

Docker image のビット単位再現 (reproducible builds) は簡単ではない。
以下は代表的な非決定性要因と対処。

1. **タイムスタンプ**
   - COPY されたファイルの mtime や `/etc/` のログがハッシュを変える
   - [reproducible-builds.org](https://reproducible-builds.org/) が推奨する
     `SOURCE_DATE_EPOCH` を設定すると緩和できる
   - `SOURCE_DATE_EPOCH=$(git log -1 --pretty=%ct) docker build ...`

2. **apt / pip の upstream 変化**
   - 本 Dockerfile は apt パッケージをインストールしない (python:3.9-slim
     の素のベース) ため、変動点は pip のみ
   - `pip install --require-hashes -r requirements/base.txt` により
     依存の sha256 は全て固定されている

3. **base image の変化**
   - `python:3.9-slim` は同タグでも中身が更新される
   - 保全目的では `python:3.9-slim@sha256:...` の digest 固定が望ましい
   - 本 Dockerfile は可読性優先でタグ指定のみ。digest 固定は将来の
     release tag 作成時に行うこと

4. **layer cache / BuildKit**
   - BuildKit の有無で生成される tar ストリームが微妙に変わる
   - 保全時は `DOCKER_BUILDKIT=0` も選択肢

これらを踏まえ、**完全な bit-for-bit 再現は目指さない**。代わりに:

- 依存 (pip) は hash-pinned
- git sha + 日付 + image sha256 を保存
- 必要なら image tarball 自体もオフライン保管

を三点セットで「当時の環境だった」ことを証明する運用に寄せる。

---

## 5. セキュリティ上の最小要件

- image には秘密情報を含めない (`.dockerignore` で `*.key`, `*.enc`, `config/settings.json` を除外)
- 非 root ユーザー `aichan` (uid 1000) で実行
- モデル本体 / personality / data / logs は image に含めず、運用時に
  ボリュームマウントする前提

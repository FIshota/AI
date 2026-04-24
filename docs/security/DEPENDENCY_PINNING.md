# 依存関係のハッシュピン留め (Dependency Hash Pinning)

本書は ai-chan プロジェクトにおける pip 依存の完全ピン留め方針と、
その運用手順を定める。対象は `requirements/` 以下の `.in` / `.txt` 一式である。

## なぜハッシュピン留めが必要か

### 1. Dependency Confusion 攻撃

社内パッケージ名と同名のパッケージを攻撃者が PyPI に publish するだけで、
pip のインデックス優先度に従って攻撃者の版が引き込まれる事例が確認されている
(例: 2021 Alex Birsan による PoC、以後多数の実攻撃)。
バージョン番号だけを固定 (`==1.2.3`) しても、
攻撃者が同一バージョン番号で別ハッシュの成果物を押し込めれば防げない。

### 2. Supply-chain Substitution

PyPI アカウントの乗っ取り、CDN ミラーの改竄、
ビルド成果物のリポジトリ内書き換え等、配布経路そのものを汚染する攻撃が現実化している。
ハッシュによる内容整合性検証 (`--require-hashes`) のみが最終防衛線となる。

### 3. 再現可能ビルド (Reproducible Builds)

CI、本番、開発者マシンの全てで全く同一バイト列の wheel をインストールできる保証は、
インシデント調査・ロールバック・SBOM 生成の全てにおいて前提条件となる。

## ファイル構成

```text
requirements/
├── base.in     # 直接依存 (バージョン下限のみ宣言)
├── base.txt    # 推移依存まで含む完全ロック (SHA-256 ハッシュ付き)
├── dev.in      # 開発専用の直接依存
└── dev.txt     # 開発専用の完全ロック (SHA-256 ハッシュ付き)
```

`.in` は人が編集する。`.txt` は `pip-compile` が生成する。
いずれも git 管理対象とし、同一コミットでセットで更新する。

## 通常のワークフロー

```bash
# 1. 直接依存の追加・削除
vim requirements/base.in

# 2. ロックファイルを再生成 (要 pip-tools)
make pin

# 3. .in と .txt を一緒にコミット
git add requirements/base.in requirements/base.txt
git commit -m "chore: bump <package> to <version>"

# 4. インストールはハッシュ検証付きで
make install        # 本番依存のみ
make install-dev    # 本番 + 開発依存
```

初回のみ `pip install pip-tools` でコンパイラを用意する。
`pip-tools` 自体も `requirements/dev.in` に含めているため、
一度 `make install-dev` を通した後は自動的にバージョン同期される。

## 制御された version upgrade 手順

1. `requirements/base.in` の下限を引き上げる、
   あるいは一時的に `==` でターゲット版を固定する。
2. `make pin` でロックを再生成。
3. diff をレビュー。推移依存の意図しない昇降格がないか、
   ハッシュ差分が公式リリースと一致するかを必ず確認する。
4. `make verify-hashes` で pip の dry-run を通す。
5. 全テスト (`make test`)、lint、型検査を通す。
6. `.in` を `==` で固定していた場合は下限表現に戻してから最終コミット。

**絶対にやってはいけないこと:**

- `.txt` を手で編集する (`pip-compile` の出力以外は全て汚染の兆候とみなす)
- `--require-hashes` を外して `install` する
- CI から `--require-hashes` を外す一時対応を本番に残す

## プラットフォーム固有 wheel に関する既知の制約

`cryptography`、`torch`、`faiss-cpu`、`numpy` 等は
プラットフォーム (linux x86_64 / macOS arm64 / macOS x86_64 / Windows)
および Python バージョンごとに別ハッシュの wheel が配布される。

本リポジトリの `requirements/base.txt` は **CI 環境 (Ubuntu + Python 3.13)**
を一次ターゲットとして生成している。Intel Mac 上で Python 3.9 を使う
ローカル開発者は、以下のいずれかで対応すること。

### 選択肢 A: 別プロファイルを作る (推奨)

```bash
# macOS Intel, Python 3.9 用に別ロックを生成
pip-compile --generate-hashes --resolver=backtracking \
    --output-file requirements/base-macos-x64-py39.txt requirements/base.in
```

生成されたファイルは git 管理しても良いし、gitignore して各人ローカルに持っても良い。
本チームでは現状 CI ロックのみを tracked とし、
ローカルは各自で再生成する運用とする。

### 選択肢 B: `--no-binary` でソース配布から再現

```bash
pip install --require-hashes --no-binary=:all: -r requirements/base.txt
```

ソースから wheel をビルドするため時間はかかるが、
プラットフォーム間でハッシュが一致する前提を最大限に担保できる。
`cryptography` 等はローカルに Rust toolchain / OpenSSL ヘッダが必要となる点に注意。

### 選択肢 C: 開発は `requirements.txt` (ルートの非ハッシュ版)、CI のみ `requirements/base.txt`

段階導入期間の暫定策。本番とステージングは必ず `--require-hashes` を通すこと。

## CI 統合の推奨 (本タスクでは tests.yml は変更しない)

`.github/workflows/tests.yml` の `Install deps` ステップを以下に置き換える
提案を残しておく (別 PR で実施)。

```yaml
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install --require-hashes -r requirements/base.txt
```

これにより CI は完全に固定された成果物でのみテストを走らせるようになり、
上流の silent publish に対して不意打ちを食らうリスクを消せる。

本提案を実施する前提条件:

- `requirements/base.txt` が Python 3.13 / linux x86_64 用に生成されていること (現状該当)
- tests.yml が追加で何らかのオプショナル依存を動的インストールしていないこと

## インシデント対応

ハッシュ不一致エラーが出た場合、絶対に `--require-hashes` を外して回避しない。
以下の順に調査する。

1. 自分の `.in` 編集に起因する想定内の差分か ? (直近 commit を確認)
2. PyPI / ミラー側で wheel が再 upload された可能性は ?
   (`pip-audit`、公式リリースノート、ハッシュ比較)
3. ローカルキャッシュが破損していないか ? (`pip cache purge` の後再試行)
4. それでも不一致なら、上流侵害を疑い security-reviewer を走らせる。

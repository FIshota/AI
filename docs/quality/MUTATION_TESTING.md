# 変異テスト (Mutation Testing) — ai-chan

## 変異テストとは

変異テスト (mutation testing) は、ソースコードに意図的な小さな変更 (mutant) を注入し、既存のテストスイートがその変更を検出できるかを確認する手法である。変更を検出できれば mutant は "killed"、検出できなければ "survived" となる。survived が多いほど、テストが実装の重要な分岐や境界条件を実際には確かめていないことを意味する。カバレッジ率では測れない「テストの実効性」を評価するための最終防衛線として用いる。

## 実行方法

前提: `mutmut` が入っていること。未導入の場合は以下で入る。

```bash
pip install -r requirements/dev.txt
```

### smoke test (パイプライン確認用 / 数分)

```bash
bash scripts/run_mutation_smoke.sh
```

- `core/tenant.py` のみを対象に少数の変異を流す。
- 結果は `logs/mutation/<YYYY-MM-DD>.txt` に残る。
- 生存変異があっても exit 0。CI の health check 目的。

### full run (weekly 想定 / 長時間)

```bash
bash scripts/run_mutation_full.sh
```

- `.mutmut.toml` の `paths_to_mutate` 全件を対象。
- 結果は `logs/mutation/full-<YYYY-MM-DD>.txt` に残る。
- 週次で launchd / cron から起動することを想定 (未登録)。

### 個別確認

```bash
mutmut results              # 直近の結果サマリ
mutmut show <id>            # 生存 mutant のソース差分
```

## 結果の読み方

- **killed**: テストが mutant を検出した。健全。
- **survived**: 変更を注入してもテストが全部通ってしまった。
  そのコードパスに対する **アサーションが弱い** か、そもそも **通っていない** 可能性が高い。survived になった mutant の差分を `mutmut show` で確認し、
  - 対応する分岐を実際にアサートするテストを追加する
  - もしくは「意味的に等価な変異」であることを確認したうえで許容する
- **timeout / suspicious**: 無限ループや副作用の可能性。テスト側の孤立性を見直す。

mutation score の目安:
- 安全重要モジュール (subject_rights, tenant): **80% 以上を維持**。
- その他: 参考値。スコアそのものより、生存した mutant の質を精査する。

## このプロジェクトでの対象と理由

| ファイル | 理由 |
|----------|------|
| `core/subject_rights.py` | GDPR 等の被データ主体権利処理。誤った分岐は法令遵守リスクに直結するため、テストの実効性を特に厳しく保証する必要がある。 |
| `core/tenant.py` | テナント境界ロジック。パストラバーサルやテナント越境は既知の攻撃面であり、境界条件 (`==` / `<=` / `and` / `or` など) を突く変異を確実に検出できなければならない。 |

## 今後の対象ロードマップ

優先度順:

1. `core/encryption.py` — 暗号処理の分岐は silent fail が致命的。変異で silent fail 経路を炙り出す。
2. `core/clipboard_watcher.py` — 外部入力を受ける surface。入力検証の抜けは UX・セキュリティ双方に影響する。
3. `core/audit_chain.py` — ハッシュチェーン改ざん検出ロジック。等価変異に見えても検出が外れると監査不能になるため要注意。
4. `utils/crypto.py` / `utils/secure_store.py` — 暗号・鍵管理の下層。上位テストのカバレッジだけでは実効性を担保しきれない。

## 補足

- 変異テストは CI のブロッカーにはしない。実行時間が長く、ノイズも多いため、weekly review のインプットとして使う。
- 生存 mutant に対しては「テスト追加」か「等価変異として許容」かを明示的に判断し、理由を PR / ログに残すこと。

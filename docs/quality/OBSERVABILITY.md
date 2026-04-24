# Observability 運用ガイドライン

> ai-chan における OpenTelemetry (以下 OTEL) 最小スケルトン
> `core/observability.py` の設計意図・使い方・レビュー手順。

## 1. なぜ既定で OFF なのか

ai-chan は **10 年運用の原則** として以下を掲げている:

- **プライバシーファースト**: ユーザーの発話・記憶・感情ログは原則ローカルから外へ出さない。
- **無課金運用**: 外部 SaaS (Datadog / Honeycomb / New Relic 等) への継続送信は、
  個人利用でも月額コストが発生しうる。10 年運用の前提と相容れない。
- **依存の最小化**: `opentelemetry-*` は相応にサイズのある依存で、
  かつ exporter 追加は設定ミスで情報漏洩を招きやすい。

よって:

- `OTEL_ENABLED` 環境変数 (既定 `"0"`) が真値のときのみ有効。
- `opentelemetry` 未インストールでも import エラーで落ちないよう no-op フォールバックを持つ。
- 有効時も出力先は **console exporter のみ**。外部送信経路は本スケルトンには実装しない。

## 2. API 概要

```python
from core.observability import (
    SpanContext,
    MetricSample,
    get_tracer,
    start_span,
    record_metric,
    is_enabled,
)

with start_span("purge_subject", {"subject": subject_id}) as ctx:
    delete_memory(subject_id)
    record_metric("ai_chan.purge.count", 1, unit="1", attributes={"reason": "user"})
```

- `start_span` は `contextlib.contextmanager`。
- `SpanContext` / `MetricSample` は `@dataclass(frozen=True)` で不変。
- `core/__init__.py` からは export しない。利用側は `from core.observability import ...` と明示的に import すること。

## 3. span を打つべき場所 (ガイドライン)

**必須**:

- `purge_subject` 周辺 (記憶の削除・マスキング) — 監査・デバッグ両面で重要。
- 外部 API 呼び出し (STT / TTS / LLM) のリトライと所要時間。
- mode switching (ModeManager) の遷移。
- audit_chain / audit_log への追記処理。

**推奨**:

- バックアップ rotate (`backup_rotator`) の 1 サイクル。
- bio_nervous_system の重めのループ本体。

**不要**:

- 高頻度 (>100Hz) の UI イベント。
- ループごとに必ず回る軽量処理 (log だけで十分)。

## 4. メトリクス命名規則

- ドット区切り + 小文字スネーク: `ai_chan.<domain>.<metric>`
- 単位を `unit` 引数に明示 (`"s"`, `"ms"`, `"1"`, `"By"` 等)。
- label (attributes) は低 cardinality のみ。user_id のような高 cardinality 値は入れない。

## 5. 外部 exporter を追加する場合のレビュー手順

いかなる理由でも、ネットワーク経由で trace / metric を送信する exporter を
追加する場合は、以下をすべて満たすこと:

1. **PR タイトルに `[observability-external]` を含める**。
2. 送信先ホスト・送信内容・retention を `docs/quality/OBSERVABILITY.md` に追記。
3. ユーザー発話・記憶内容・音声波形・画面キャプチャを **絶対に** attribute に乗せない。
   サニタイズ関数を必ず経由させる。
4. `OTEL_EXTERNAL_EXPORTER_ENABLED` のような第二の opt-in env var を追加し、
   `OTEL_ENABLED=1` と両方揃わない限り外部送信しない二段 gate 構造にする。
5. `PRIVACY.md` と `docs/SECURITY.md` を更新し、データ送出のリスクを明文化する。
6. `security-reviewer` agent によるレビューを通す (CRITICAL が 0 であること)。
7. 料金が発生するサービスを使う場合は `docs/ROADMAP.md` にコスト見積もりを記載。

## 6. ローカルで有効化して試す

```bash
export OTEL_ENABLED=1
pip install opentelemetry-api opentelemetry-sdk  # 必要時のみ
python -m main
```

`opentelemetry` が未インストールでも `OTEL_ENABLED=1` はクラッシュしない。
単に no-op にフォールバックする。これは `tests/test_observability.py` で担保している。

## 7. テスト

`tests/test_observability.py` にて以下を検証:

- `OTEL_ENABLED=0` で `is_enabled()` が False。
- `opentelemetry` 未インストールを模した状態でも落ちない。
- `start_span` が context manager として動作する。
- `record_metric` が `MetricSample` を返す。
- span のネストが壊れない。
- `SpanContext` が frozen (不変)。
- `core/__init__.py` が observability を export していない。

## 8. 今後の拡張メモ

- sampling (ratio / parent-based) を入れる場合も既定 OFF を崩さない。
- metric を Prometheus pull 型で出すローカル exporter は検討可 (外部送信ではない為)。
- span attribute のサニタイズ層 (PII scrubber) を追加予定。

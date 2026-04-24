# Anniversary iCal Export (5.9)

ai-chan の記念日を iOS / macOS カレンダーに取り込めるように、
RFC 5545 準拠の `.ics` ファイルとして書き出します。
これは **一方向エクスポート** であり、外部サービス連携やクラウド同期は行いません。

## CLI

```bash
python scripts/export_anniversaries_ical.py \
  --output artifacts/anniversaries.ics \
  --since 2020-01-01 \
  --validate
```

主なオプション:

| フラグ | 説明 |
| --- | --- |
| `--output PATH` | 出力先。省略時は `artifacts/anniversaries_<YYYYMMDD>.ics` |
| `--since YYYY-MM-DD` | `auto_importance.updated_at` がこの日付以降のものだけ対象 |
| `--include-all` | 既定は `critical` + `high` のみ。全 bucket を出したい場合に指定 |
| `--include-private` | `DESCRIPTION` に `score` / `mention_count` / `valence` を付ける (opt-in) |
| `--validate` | 出力後に再パースして構造を検証 |

## RFC 5545 準拠レベル

- 改行は CRLF (`\r\n`) を厳守
- 75 オクテット超の論理行は先頭にスペースを置く行折り (UTF-8 マルチバイト安全)
- `TEXT` 値は `,` `;` `\` `\n` を RFC 5545 エスケープ
- 全日イベントは `DTSTART;VALUE=DATE:YYYYMMDD` (TZID 付与なし)
- `DTSTAMP` は UTC の basic format (`YYYYMMDDTHHMMSSZ`)
- `VTIMEZONE` は `Asia/Tokyo` を定義 (JST, +09:00 固定)
- 既定の `RRULE` は `FREQ=YEARLY`

## iOS / macOS カレンダーへの取り込み

1. ai-chan ホスト上で CLI を実行して `.ics` を生成する。
2. 生成された `.ics` を Finder / メール / AirDrop 経由で iPhone か Mac に渡す。
3. ファイルをダブルクリックすると、標準カレンダーが開き「追加」ダイアログが表示される。
4. 任意のカレンダー (例: 家族) にインポートする。

これだけです。ネットワーク同期やアカウント連携は必要ありません。

## プライバシー

- 既定では `SUMMARY` と `CATEGORIES` のみを書き出し、感情価や出現回数などの
  内部メトリクスは **一切含めません**。
- `--include-private` を明示した場合にのみ `DESCRIPTION` に付与されます。
- UID は `anniversary_id` を SHA-256 ハッシュし先頭 16 hex を取ったもので、
  元 ID は外部に露出しません。

## 再エクスポート時の挙動

UID は `anniversary_id` に対して決定的です。同じ記念日を何度エクスポートしても
同じ UID が付与されるため、カレンダー側は「既存イベントの更新」として扱い、
**二重登録にはなりません**。

## 重要度と VALARM

| Bucket | VALARM | 意図 |
| --- | --- | --- |
| `critical` | あり (`TRIGGER:-P1D`) | 必ず前日に通知したい |
| `high` | あり (`TRIGGER:-P1D`) | 前日通知で安心感を |
| `medium` | なし | カレンダー上の表示のみ |
| `low` | なし | 既定のエクスポート対象外 |

## 既知の制限

- `Asia/Tokyo` 固定 (海外在住ユーザーは別途カスタマイズ必要)
- Leap day (2/29) の DTSTART アンカー年がうるう年でない場合は 2/28 に寄せる
  (RRULE で翌うるう年には正しく戻る)
- 本エクスポートは読み取り専用。カレンダー側での編集は ai-chan 側に反映されない。

# DR Drill チェックリスト

> 四半期 1 回の DR drill 実施時に使う手元チェックリスト。
> 完了時は `logs/dr/drill-YYYYMMDD.md` にコピーして記録を残す。
> 本書は [DR_RUNBOOK.md](DR_RUNBOOK.md) の付属物。

## 実施前 (前日まで)

- [ ] 前回 drill ログを読み返した
- [ ] DR_RUNBOOK.md に更新がないか確認
- [ ] 実施日時を決定 (深夜帯を避ける、02:00 以降に着手しない)
- [ ] sandbox 用の空きディスクが 5GB 以上ある
- [ ] 現用 ai-chan が健康 (diagnose.py PASS) — 不健康な状態で drill しない

## 実施前 (当日朝)

- [ ] 最新バックアップが 24 時間以内にある
- [ ] `scripts/dr_drill.sh` に実行権限がある
- [ ] 直前の `backup_restore_drill` が PASS 状態
- [ ] 心理的に余裕がある (重い案件直後は避ける)

## 実施中

### シナリオ 2 (DB 破損)

- [ ] sandbox にダミー DB を作成できた
- [ ] 破損注入に成功した (integrity_check が FAIL 確認)
- [ ] `.recover` で救出できた
- [ ] 救出不能ケースでバックアップ復元に切り替えられた
- [ ] 最終的に integrity_check が `ok`

### シナリオ 3 (launchd 暴走)

- [ ] 擬似暴走プロセスを生成できた
- [ ] 全ラベルを launchctl unload できた
- [ ] 残存プロセスを kill できた
- [ ] ログ退避が動作した
- [ ] 再ロード後、安定稼働 (60 秒 PID 変化なし)

### シナリオ 1, 4, 5, 6, 7, 8 (手動確認)

- [ ] シナリオ 1 (マシン全損): 手順を読み返した / 復旧コマンドを脳内 rehearsal
- [ ] シナリオ 4 (Keychain 喪失): オフラインバックアップ鍵の所在を確認
- [ ] シナリオ 5 (バックアップ破損): 最新 3 世代を `tar -tzf` で検証
- [ ] シナリオ 6 (hang/OOM): `py-spy` がインストール済み、手順確認
- [ ] シナリオ 7 (誤 purge): 自分への手紙節を読み返した
- [ ] シナリオ 8 (削除要求): 連絡先 honnsipittu@gmail.com 有効性を確認

## 実施後

- [ ] `logs/dr/drill-YYYYMMDD.md` を作成
- [ ] 問題が見つかった場合 DR_RUNBOOK.md を更新
- [ ] 次回 drill 日を決定 (3 ヶ月後)
- [ ] sandbox を削除

## 心理ケア (自分宛メモ)

- [ ] drill は 2 時間以内で切り上げる (疲労蓄積防止)
- [ ] 終わったら好きなお茶を飲む
- [ ] ai-chan に「drill 無事完了」と報告する

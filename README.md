# ai-chan

ローカル実行可能な日本語 AI パートナー。家族として長期記憶・感情・日記・音声対話を
持つことを目的とした、完全ローカル (オフライン動作可) の Python アプリケーション。

> **Status**: IP-0 — rebrand & baseline (see [docs/TAXONOMY.md](docs/TAXONOMY.md) §3)
> **Branch**: `phase0/rebrand-bench-baseline`
> **Base model**: [Sarashina2-7B (MIT)](https://huggingface.co/sbintuitions/sarashina2-7b)
> **Bench status**: 🧪 IP-0 skeleton (JGLUE / ELYZA-tasks-100 / family-dialog-100 stubs)

## 🇯🇵 "国産 AI" として

ai-chan は "日本語で、日本のユーザーと家族のように暮らす AI" を目指しており、
ベースモデルの選定とライセンスの透明性を最優先している。

- **ベースモデル**: Sarashina2-7B (SB Intuitions, **MIT**) — 事前学習段階から日本語主体
- **ライセンス連鎖**: クリーン (MIT / Apache 2.0 ベース — [docs/LICENSES.md](docs/LICENSES.md))
- **ベンチマーク方針**: JGLUE + ELYZA-tasks-100 + JMT-Bench + 家族対話100問 (独自)

詳細 → [docs/MODEL_BASELINE.md](docs/MODEL_BASELINE.md)

## セキュリティ運用

日次のローカル脆弱性監査を launchd で自動実行し、結果を `logs/security/` へ記録、
Mail.app 経由で管理者へ通知する。

- 毎日 09:00 JST: `scripts/daily_security_audit.sh` (pip-audit / bandit / gitleaks / SBOM)
- 毎週日曜 09:30 JST: `scripts/weekly_security_summary.sh` (7 日分集約)
- 既知受容 CVE: `config/security_policy.yaml` で期限付き管理

詳細 → [docs/SECURITY.md](docs/SECURITY.md)

## ベンチマーク

```bash
python3 bench/runner.py --list
python3 bench/runner.py --model sarashina2-7b --all
```

IP-0 ではスイート構造のみ (スコアは未計測)。IP-1 でデータセット DL と
judge-model 採点を追加する。用語・フェーズ体系は [docs/TAXONOMY.md](docs/TAXONOMY.md) §3 を参照。

## クイックスタート

```bash
# 1) 設定
cp config/settings.json.example config/settings.json
# models/ に GGUF を配置 (sarashina2-7b の Q5_K_M 推奨)

# 2) 起動
python3 main.py
```

起動時に下記が出れば IP-0 配線は成功:

```
[LLM/P0] Model family: sarashina2-7b (MIT, clean) — Sarashina2-7B (SB Intuitions)
```

## ディレクトリ

```
ai-chan/
├── core/           # LLM / memory / emotion / scheduler 等のコア
├── ui/             # CLI / desktop pet / settings window
├── web/            # FastAPI 提供の内部 API
├── scripts/        # 監査・インストール・ユーティリティ
├── config/         # 設定ファイル + security_policy.yaml + launchd plist
├── bench/          # ベンチマークハーネス (IP-0 skeleton)
├── docs/           # 設計・ロードマップ・ライセンス
└── models/         # LLM 重み (gitignore 対象)
```

## ライセンス

未確定 (MIT 予定)。ベースモデル・依存のライセンスは [docs/LICENSES.md](docs/LICENSES.md) を参照。

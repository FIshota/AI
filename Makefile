.PHONY: test lint benchmark backup diagnose run desktop help pin install install-dev verify-hashes

PYTHON ?= python3
BASE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

help: ## ヘルプを表示
	@echo "=== アイちゃん Makefile ==="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""

test: ## pytest を実行
	$(PYTHON) -m pytest tests/ -x -q --tb=short

test-verbose: ## pytest を詳細モードで実行
	$(PYTHON) -m pytest tests/ -v --tb=long

test-coverage: ## カバレッジ付きテスト
	$(PYTHON) -m pytest tests/ --cov=core --cov=ui --cov-report=term-missing

lint: ## ruff でリント実行 (loose zone)
	$(PYTHON) -m ruff check core/ ui/ scripts/ tests/

lint-fix: ## ruff で自動修正
	$(PYTHON) -m ruff check --fix core/ ui/ scripts/ tests/

lint-strict: ## M4 strict zone: BLE001/S110/S112 適用対象
	$(PYTHON) -m ruff check --select F,E,W,I,UP,BLE,S \
		core/memory.py utils/crypto.py utils/secure_store.py \
		utils/keychain.py core/tenant.py core/subject_rights.py \
		core/protocols.py core/deps.py core/ops/

format: ## black でフォーマット
	$(PYTHON) -m black core/ ui/ scripts/ tests/

typecheck: ## mypy で型チェック (loose)
	$(PYTHON) -m mypy core/ ui/ --ignore-missing-imports

typecheck-strict: ## M4 strict zone: mypy strict 対象 (pyproject.toml [tool.mypy].files)
	$(PYTHON) -m mypy

benchmark: ## 品質ベンチマークを実行
	$(PYTHON) scripts/run_benchmark_compare.py

backup: ## データをバックアップ
	@mkdir -p $(BASE_DIR)/backups
	@STAMP=$$(date +%Y%m%d_%H%M%S); \
	tar czf $(BASE_DIR)/backups/backup_$$STAMP.tar.gz \
		-C $(BASE_DIR) data/ config/ personality/ \
		--exclude='*.pyc' --exclude='__pycache__'; \
	echo "バックアップ完了: backups/backup_$$STAMP.tar.gz"

diagnose: ## 環境診断を実行
	$(PYTHON) scripts/diagnose.py

run: ## CLI モードで起動
	$(PYTHON) main.py --mode cli

desktop: ## デスクトップペットモードで起動
	$(PYTHON) main.py --mode desktop

gen-changelog: ## CHANGELOG を生成
	$(PYTHON) scripts/gen_changelog.py

gen-commands: ## コマンドリファレンスを生成
	$(PYTHON) scripts/gen_cmd_ref.py

gen-architecture: ## アーキテクチャ図を生成
	$(PYTHON) scripts/gen_arch_diagram.py

release-check: ## リリースチェックリストを実行
	$(PYTHON) scripts/release.py

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 依存関係のハッシュピン留め (dependency confusion 対策)
#
# ワークフロー:
#   1. requirements/*.in を編集
#   2. `make pin` で requirements/*.txt を再生成 (要 pip-tools)
#   3. .in と .txt を一緒にコミット
# 詳細: docs/security/DEPENDENCY_PINNING.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pin: ## requirements/*.in から requirements/*.txt をハッシュ付きで再生成
	@command -v pip-compile >/dev/null 2>&1 || { \
		echo "pip-compile が見つかりません。まず: pip install pip-tools"; exit 1; }
	pip-compile --generate-hashes --resolver=backtracking \
		--output-file requirements/base.txt requirements/base.in
	pip-compile --generate-hashes --resolver=backtracking --allow-unsafe \
		--output-file requirements/dev.txt requirements/dev.in

install: ## 本番依存をハッシュ検証付きでインストール
	$(PYTHON) -m pip install --require-hashes -r requirements/base.txt

install-dev: ## 本番 + 開発依存をハッシュ検証付きでインストール
	$(PYTHON) -m pip install --require-hashes -r requirements/base.txt
	$(PYTHON) -m pip install --require-hashes -r requirements/dev.txt

verify-hashes: ## ロックされたハッシュが現在のレジストリと一致するか dry-run
	$(PYTHON) -m pip install --dry-run --require-hashes -r requirements/base.txt

clean: ## キャッシュファイルを削除
	find $(BASE_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(BASE_DIR) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find $(BASE_DIR) -name "*.pyc" -delete 2>/dev/null || true

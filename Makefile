.PHONY: test lint benchmark backup diagnose run desktop help

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

lint: ## ruff でリント実行
	$(PYTHON) -m ruff check core/ ui/ scripts/ tests/

lint-fix: ## ruff で自動修正
	$(PYTHON) -m ruff check --fix core/ ui/ scripts/ tests/

format: ## black でフォーマット
	$(PYTHON) -m black core/ ui/ scripts/ tests/

typecheck: ## mypy で型チェック
	$(PYTHON) -m mypy core/ ui/ --ignore-missing-imports

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

clean: ## キャッシュファイルを削除
	find $(BASE_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(BASE_DIR) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find $(BASE_DIR) -name "*.pyc" -delete 2>/dev/null || true

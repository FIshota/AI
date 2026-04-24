# CODEMAP: scripts/

> Auto-generated 2026-04-24 — Cat 5 codemap (C5)

Total modules: **45**

Operational / maintenance scripts and CLI entry points.

| File | Summary | Public API (excerpt) | Lines |
|------|---------|----------------------|-------|
| `add_learning_data.py` | 会話学習データ追加ツール | add_interactive(), add_from_file() | 66 |
| `ai_chan_llm_worker.py` | M8: ai-chan LLM worker process. | class Worker, main() | 312 |
| `analyze_honesty_bench.py` | H-1: honesty bench 結果を aspect 別に集計. | main() | 77 |
| `audit_journal_dates.py` | JOURNAL 日付整合性監査スクリプト. | class JournalEntry, class AuditFinding, discover_journals(), parse_entries(), count_commits_on() | 237 |
| `audit_model_family.py` | Data-Truth-Audit (DTA) for MODEL_FAMILY.md. | extract_model_table(), compare_tables(), count_tbd(), default_paths(), run_audit() | 196 |
| `check_backup_freshness.py` | Check that backup restore drills ran recently. | evaluate(), main() | 86 |
| `check_corpus_isolation.py` | Corpus isolation guard (ADR 0002). | class Violation, check_isolation(), check_cross_phase_leak(), main() | 197 |
| `check_crypto_surface.py` | check_crypto_surface.py | class Finding, class ScanResult, iter_python_files(), scan_file(), scan_tree() | 219 |
| `check_disk_space.py` | Warn the owner when the disk hosting ai-chan is running low. | evaluate(), main() | 65 |
| `check_feature_rubric.py` | VALUES_RUBRIC 採点スクリプト. | class RubricError, load_proposal(), score_answer(), evaluate(), format_result() | 268 |
| `check_licenses.py` | ai-chan ライセンス監査ツール (Phase 0.75). | run_pip_licenses(), classify(), generate_markdown(), main() | 211 |
| `check_outdated.py` | PyPI latest version vs requirements.txt floor comparison. | parse_requirements(), fetch_latest(), version_tuple(), main() | 92 |
| `check_security_policy.py` | ai-chan セキュリティポリシー期限切れ検知ツール (Phase 0.75). | check_section(), main() | 136 |
| `check_taxonomy.py` | TAXONOMY 整合性チェック (docs/TAXONOMY.md §8 準拠). | check_file(), main() | 150 |
| `clean_learning.py` | 学習データの汚染をクリーニングするスクリプト | — | 50 |
| `convert_hf_to_gguf.py` | HuggingFace → GGUF 変換スクリプトの薄いラッパー (M6, 2026-04-21). | main() | 47 |
| `daily_learning_update.py` | daily_learning_update.py | update_code_review_patterns(), update_research_patterns(), update_task_patterns(), main(), update_github_patterns() | 530 |
| `detach_memory_phase_a.py` | ai-chan 記憶切り離し Phase A — 非破壊アーカイブ. | main() | 180 |
| `diagnose.py` | 10 ポイント診断スクリプト | check_python_version(), check_tkinter(), check_llama_cpp(), check_model_file(), check_data_dir() | 250 |
| `export_anniversaries_ical.py` | CLI: export ai-chan anniversaries to an RFC 5545 .ics file. | build_events(), parse_args(), main() | 147 |
| `finetune_qlora.py` | D9: QLoRA微調整スクリプト - Aether Model Fine-tuning | check_mlx(), find_model(), convert_to_mlx(), generate_training_data(), run_finetune() | 267 |
| `gen_arch_diagram.py` | アーキテクチャ図を Mermaid 形式で自動生成する。 | extract_imports(), scan_dependencies(), generate_mermaid(), generate_architecture_doc(), main() | 148 |
| `gen_changelog.py` | Git ログからカテゴリ分類された CHANGELOG.md を生成する。 | parse_git_log(), generate_changelog(), main() | 147 |
| `gen_cmd_ref.py` | コマンドリファレンスを自動生成する。 | class CommandInfo, scan_commands(), generate_command_reference(), main() | 133 |
| `generate_artifact_manifest.py` | Generate an artifact manifest for offline verification. | class GenOptions, iter_files(), generate(), build_parser(), main() | 116 |
| `generate_emotion_report.py` | 感情ドリフト「心の健康診断」レポート生成スクリプト。 | build_parser(), main() | 183 |
| `lint_minutes.py` | lint_minutes.py — docs/minutes/ の議事録ファイルに必須セクションが | extract_sections(), check_file(), iter_default_targets(), resolve_targets(), main() | 109 |
| `log_retention_sweep.py` | Sweep stale log files according to config/log_retention.yaml. | class Policy, class Candidate, load_policies(), scan_candidates(), apply_deletions() | 248 |
| `migrate_faiss_to_sqlite_vec.py` | M9 Phase 2: FAISS → sqlite-vec ワンショット移行スクリプト。 | main() | 191 |
| `privacy_lint.py` | Privacy policy linter. | read_text(), check_required_headings(), detect_core_modules(), check_modules_mentioned(), run_lint() | 134 |
| `recalibrate_anniversaries.py` | 全 anniversary の auto_importance を再計算するスクリプト。 | recalibrate(), main() | 141 |
| `release.py` | リリースチェックリストスクリプト | check_version(), run_pytest(), run_benchmark(), check_integrity(), generate_changelog() | 169 |
| `request_mic.py` | マイク権限をリクエストするヘルパー | main() | 78 |
| `restore_memory.py` | ai-chan 記憶復元ツール (家族モード). | main() | 105 |
| `run_benchmark_compare.py` | ベンチマーク比較スクリプト | run_with_model(), main() | 118 |
| `scan_brand_misuse.py` | scan_brand_misuse.py — ブランド/商標名の利用箇所をスキャンする情報目的ツール. | class Hit, class ScanResult, is_path_in_allowed(), scan_text(), iter_target_files() | 165 |
| `search_conversations.py` | CLI for the conversation history search (Sprint 5.7). | main() | 110 |
| `secret_scan.py` | ai-chan 軽量シークレットスキャナ (gitleaks 代替) | shannon_entropy(), iter_files(), scan_file(), main() | 146 |
| `setup_logging.py` | ロギング設定ユーティリティ | configure_logging(), get_logger() | 101 |
| `setup_model.py` | モデルセットアップスクリプト | download_with_progress(), install_llama_cpp(), main() | 172 |
| `setup_qwen.py` | DEPRECATED: Qwen2.5 (中国 Alibaba) セットアップは 2026-04-21 に廃止. | — | 32 |
| `setup_sarashina.py` | Sarashina 2.2 3B-Instruct セットアップスクリプト (日本製). | check_dependencies(), download_model(), update_settings(), main() | 177 |
| `sweep_memory_forgetting.py` | Memory forgetting sweep. | load_entries(), demote_entries(), main() | 186 |
| `tenant_admin.py` | tenant_admin — テナント管理 CLI。 | main() | 105 |
| `verify_offline_artifacts.py` | Offline artifact integrity verifier. | class ManifestEntry, class EntryResult, class VerifyReport, sha256_file(), load_manifest() | 201 |

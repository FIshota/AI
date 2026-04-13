"""
自己開発パイプライン (Self-Development Pipeline)

アイが自分のソースコードを読んで理解し、改善提案をする仕組み。

人間で言うと:
- 社会人が自分の仕事のやり方を振り返って改善する
- エンジニアが自分のコードをセルフレビューする
- 「ここ、もっと良くできるな」と自分で気づく能力

┌──────────────────────────────────────────────────┐
│  自己開発の流れ                                     │
│                                                    │
│  ① 自己認識 (Self-Awareness)                        │
│     自分のコードを読む（READ ONLY）                   │
│     「自分がどう動いているか」を理解する。             │
│                                                    │
│  ② 問題発見 (Problem Detection)                     │
│     エラーログ、品質推移、パフォーマンスから           │
│     「ここがおかしい」を特定する。                     │
│                                                    │
│  ③ 改善案生成 (Proposal Generation)                  │
│     問題に対する具体的な修正案を作成する。             │
│     コード変更の提案書を書く。                        │
│                                                    │
│  ④ 提出 (Submission)                                │
│     data/proposals/ に保存してお父さんに提出。        │
│     勝手には変更しない。承認を待つ。                   │
│                                                    │
│  ⑤ 承認後実行 (Approved Execution)                   │
│     お父さんが承認したら初めて実行する。               │
│                                                    │
└──────────────────────────────────────────────────┘

安全設計:
- ソースコードは READ ONLY（書き換え不可）
- 提案は data/proposals/ に保存するだけ
- 実行にはユーザーの承認が必要
- core/ 以下のみ読み取り可能（セキュリティ系ファイルは除外）
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 安全なコード読み取り
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 読み取り禁止パターン（セキュリティ関連）
_BLOCKED_PATTERNS = re.compile(
    r"(password|secret|token|key_file|credential|private_key)",
    re.IGNORECASE,
)

# 読み取り可能ディレクトリ（ホワイトリスト）
_ALLOWED_DIRS = {"core", "config", "ui", "utils", "skills"}

# 読み取り禁止ファイル
_BLOCKED_FILES = {
    "crypto.py",       # 暗号化処理
    "kill_switch.py",  # キルスイッチ
}


class CodeReader:
    """
    自分のソースコードを安全に読む。

    READ ONLY。書き込みは一切できない。
    セキュリティ関連のファイルはブロック。
    """

    def __init__(self, project_root: Path):
        self._root = project_root

    def list_modules(self) -> list[dict[str, Any]]:
        """読み取り可能なモジュール一覧を返す"""
        modules: list[dict[str, Any]] = []
        for allowed_dir in _ALLOWED_DIRS:
            dir_path = self._root / allowed_dir
            if not dir_path.is_dir():
                continue
            for py_file in sorted(dir_path.glob("*.py")):
                if py_file.name in _BLOCKED_FILES:
                    continue
                if py_file.name.startswith("_"):
                    continue
                try:
                    lines = py_file.read_text("utf-8").splitlines()
                    modules.append({
                        "path": str(py_file.relative_to(self._root)),
                        "name": py_file.stem,
                        "lines": len(lines),
                        "dir": allowed_dir,
                    })
                except Exception as exc:
                    logger.debug("モジュール読み込みスキップ %s: %s", py_file.name, exc)
        return modules

    def read_module(self, relative_path: str) -> str | None:
        """
        モジュールのソースコードを読む（READ ONLY）。

        セキュリティチェック:
        - ホワイトリストディレクトリのみ
        - ブロックファイルは読めない
        - パストラバーサル防止
        """
        target = self._root / relative_path
        # パストラバーサル防止（symlink も resolve で検出）
        try:
            target.resolve().relative_to(self._root.resolve())
        except ValueError:
            logger.warning("ルート外アクセス検出: %s", relative_path)
            return None

        # ディレクトリチェック
        parts = Path(relative_path).parts
        if not parts or parts[0] not in _ALLOWED_DIRS:
            return None

        # ファイル名チェック
        if target.name in _BLOCKED_FILES:
            return None

        if not target.exists() or not target.suffix == ".py":
            return None

        try:
            content = target.read_text("utf-8")
            # セキュリティ情報のマスキング
            content = _BLOCKED_PATTERNS.sub("[REDACTED]", content)
            return content
        except Exception as e:
            logger.warning("ファイル読み取り失敗: %s - %s", relative_path, e)
            return None

    def read_module_summary(self, relative_path: str) -> dict[str, Any] | None:
        """モジュールの構造サマリーを返す（全文ではなくクラス・関数一覧）"""
        content = self.read_module(relative_path)
        if content is None:
            return None

        lines = content.splitlines()
        classes: list[str] = []
        functions: list[str] = []
        imports: list[str] = []
        docstring = ""

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("class ") and ":" in stripped:
                name = stripped.split("(")[0].replace("class ", "").strip(":")
                classes.append(name)
            elif stripped.startswith("def ") and ":" in stripped:
                name = stripped.split("(")[0].replace("def ", "")
                if not name.startswith("_"):
                    functions.append(name)
            elif stripped.startswith(("import ", "from ")):
                imports.append(stripped)

        # 先頭のdocstring
        in_doc = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') and not in_doc:
                in_doc = True
                if stripped.count('"""') >= 2:
                    docstring = stripped.strip('"').strip()
                    break
                docstring = stripped.replace('"""', '')
                continue
            if in_doc:
                if '"""' in stripped:
                    docstring += " " + stripped.replace('"""', '')
                    break
                docstring += " " + stripped

        return {
            "path": relative_path,
            "total_lines": len(lines),
            "classes": classes,
            "public_functions": functions,
            "import_count": len(imports),
            "docstring": docstring[:200].strip(),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# エラー分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)
class ErrorPattern:
    """検出されたエラーパターン"""
    error_type: str
    message: str
    source_file: str
    frequency: int       # 発生回数
    last_seen: float
    severity: str = "medium"  # low / medium / high / critical


class ErrorAnalyzer:
    """
    エラーログを分析して問題パターンを発見する。

    人間の医者が検査結果を見て病気を見つけるように、
    ログデータから「何がおかしいか」を特定する。
    """

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._error_re = re.compile(
            r"(ERROR|Error|Exception|Traceback|CRITICAL|WARNING)"
        )

    def analyze_recent_errors(self, max_lines: int = 500) -> list[ErrorPattern]:
        """直近のエラーログを分析"""
        patterns: dict[str, dict] = {}

        # app.log から分析
        log_path = self._data_dir / "app.log"
        if log_path.exists():
            try:
                lines = log_path.read_text("utf-8").splitlines()
                for line in lines[-max_lines:]:
                    if self._error_re.search(line):
                        error_info = self._parse_error_line(line)
                        if error_info:
                            key = f"{error_info['type']}:{error_info['source']}"
                            if key in patterns:
                                patterns[key]["frequency"] += 1
                                patterns[key]["last_seen"] = time.time()
                            else:
                                patterns[key] = {
                                    **error_info,
                                    "frequency": 1,
                                    "last_seen": time.time(),
                                }
            except Exception as e:
                logger.debug("ログ分析失敗: %s", e)

        # audit.jsonl から分析
        audit_path = self._data_dir / "audit.jsonl"
        if audit_path.exists():
            try:
                lines = audit_path.read_text("utf-8").splitlines()
                for line in lines[-200:]:
                    try:
                        entry = json.loads(line)
                        if entry.get("sev") in ("ERROR", "CRITICAL"):
                            key = f"{entry.get('event', 'unknown')}:audit"
                            if key not in patterns:
                                patterns[key] = {
                                    "type": entry.get("event", "unknown"),
                                    "message": entry.get("detail", "")[:100],
                                    "source": "audit",
                                    "frequency": 1,
                                    "last_seen": entry.get("ts", time.time()),
                                }
                            else:
                                patterns[key]["frequency"] += 1
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        # ErrorPattern に変換
        result: list[ErrorPattern] = []
        for data in patterns.values():
            severity = "low"
            if data["frequency"] >= 10:
                severity = "high"
            elif data["frequency"] >= 5:
                severity = "medium"
            if "CRITICAL" in data.get("type", ""):
                severity = "critical"

            result.append(ErrorPattern(
                error_type=data.get("type", "unknown"),
                message=data.get("message", "")[:100],
                source_file=data.get("source", "unknown"),
                frequency=data["frequency"],
                last_seen=data["last_seen"],
                severity=severity,
            ))

        return sorted(result, key=lambda e: e.frequency, reverse=True)

    def _parse_error_line(self, line: str) -> dict | None:
        """ログ行からエラー情報を抽出"""
        # [MODULE] ERROR: message パターン
        m = re.match(r"\[(\w+)\]\s*(ERROR|WARNING|CRITICAL):\s*(.+)", line)
        if m:
            return {
                "type": m.group(2),
                "source": m.group(1),
                "message": m.group(3)[:100],
            }
        # Python traceback パターン
        m = re.search(r"(\w+Error|\w+Exception):\s*(.+)", line)
        if m:
            return {
                "type": m.group(1),
                "source": "traceback",
                "message": m.group(2)[:100],
            }
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 改善提案
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProposalType(str, Enum):
    BUG_FIX = "bug_fix"             # バグ修正
    PERFORMANCE = "performance"      # パフォーマンス改善
    CODE_QUALITY = "code_quality"    # コード品質改善
    NEW_FEATURE = "new_feature"      # 新機能提案
    REFACTOR = "refactor"            # リファクタリング


@dataclass(frozen=True)
class Proposal:
    """改善提案"""
    id: str
    proposal_type: ProposalType
    title: str
    description: str
    target_file: str
    evidence: str              # 提案の根拠
    suggested_action: str      # 推奨アクション
    priority: int = 1          # 0=urgent, 1=high, 2=medium, 3=low
    created_at: float = 0.0
    status: str = "pending"    # pending / approved / rejected / done


class ProposalGenerator:
    """
    問題分析の結果から改善提案を生成する。

    エンジニアがコードレビューで改善点を見つけるように、
    自分のコードの問題点を分析して具体的な提案を作る。
    """

    def from_error_patterns(
        self, errors: list[ErrorPattern], code_reader: CodeReader
    ) -> list[Proposal]:
        """エラーパターンから改善提案を生成"""
        proposals: list[Proposal] = []
        now = time.time()

        for err in errors[:10]:  # 上位10件のみ処理
            if err.frequency < 2:
                continue  # 1回きりのエラーは無視

            proposal = Proposal(
                id=f"err_{err.error_type}_{int(now)}",
                proposal_type=ProposalType.BUG_FIX,
                title=f"{err.error_type} が {err.source_file} で頻発",
                description=(
                    f"{err.error_type} が {err.frequency}回発生しています。\n"
                    f"メッセージ: {err.message}\n"
                    f"深刻度: {err.severity}"
                ),
                target_file=err.source_file,
                evidence=f"ログ分析: {err.frequency}回の発生を検出",
                suggested_action=(
                    f"{err.source_file} のエラーハンドリングを確認し、"
                    f"根本原因を修正してください"
                ),
                priority=0 if err.severity == "critical" else 1,
                created_at=now,
            )
            proposals.append(proposal)

        return proposals

    def from_code_analysis(
        self, modules: list[dict[str, Any]]
    ) -> list[Proposal]:
        """コード構造分析から改善提案を生成"""
        proposals: list[Proposal] = []
        now = time.time()

        for mod in modules:
            lines = mod.get("lines", 0)

            # 大きすぎるファイル（800行超え）
            if lines > 800:
                proposals.append(Proposal(
                    id=f"size_{mod['name']}_{int(now)}",
                    proposal_type=ProposalType.REFACTOR,
                    title=f"{mod['path']} が {lines} 行で大きすぎる",
                    description=(
                        f"ファイルが {lines} 行あります（推奨: 800行以下）。\n"
                        f"機能ごとにモジュールを分割することを提案します。"
                    ),
                    target_file=mod["path"],
                    evidence=f"行数分析: {lines}行（閾値800行を超過）",
                    suggested_action="関連する機能をサブモジュールに分割",
                    priority=2,
                    created_at=now,
                ))

        return proposals

    def from_quality_trend(
        self, quality_avg: float, quality_trend: str
    ) -> list[Proposal]:
        """品質トレンドから改善提案を生成"""
        proposals: list[Proposal] = []
        now = time.time()

        if quality_avg < 0.5 and quality_trend == "↓":
            proposals.append(Proposal(
                id=f"quality_drop_{int(now)}",
                proposal_type=ProposalType.PERFORMANCE,
                title="応答品質の継続的な低下を検出",
                description=(
                    f"品質平均: {quality_avg:.2f}（トレンド: {quality_trend}）\n"
                    f"LLMの応答品質が下がり続けています。\n"
                    f"温度パラメータやプロンプトの見直しが必要かもしれません。"
                ),
                target_file="core/llm.py",
                evidence=f"品質モニター: avg={quality_avg:.3f}, trend={quality_trend}",
                suggested_action="temperatureの調整またはシステムプロンプトの改善",
                priority=1,
                created_at=now,
            ))

        return proposals


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 提案の永続化と管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProposalStore:
    """
    改善提案の保存と管理。

    data/proposals/ に提案を保存。
    お父さんがいつでも確認・承認・却下できる。
    """

    def __init__(self, data_dir: Path):
        self._dir = data_dir / "proposals"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"
        self._lock = threading.Lock()

    def save(self, proposal: Proposal) -> Path:
        """提案を保存"""
        with self._lock:
            filepath = self._dir / f"{proposal.id}.json"
            data = {
                "id": proposal.id,
                "type": proposal.proposal_type.value,
                "title": proposal.title,
                "description": proposal.description,
                "target_file": proposal.target_file,
                "evidence": proposal.evidence,
                "suggested_action": proposal.suggested_action,
                "priority": proposal.priority,
                "created_at": proposal.created_at,
                "status": proposal.status,
            }
            filepath.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )
            self._update_index()
            return filepath

    def list_pending(self) -> list[dict]:
        """未承認の提案一覧"""
        return self._list_by_status("pending")

    def list_all(self) -> list[dict]:
        """全提案一覧"""
        proposals: list[dict] = []
        with self._lock:
            for f in sorted(self._dir.glob("*.json")):
                if f.name == "index.json":
                    continue
                try:
                    proposals.append(json.loads(f.read_text("utf-8")))
                except (json.JSONDecodeError, OSError):
                    pass
        return proposals

    def approve(self, proposal_id: str) -> bool:
        """提案を承認"""
        return self._update_status(proposal_id, "approved")

    def reject(self, proposal_id: str) -> bool:
        """提案を却下"""
        return self._update_status(proposal_id, "rejected")

    def mark_done(self, proposal_id: str) -> bool:
        """提案を完了済みに"""
        return self._update_status(proposal_id, "done")

    def _update_status(self, proposal_id: str, status: str) -> bool:
        with self._lock:
            filepath = self._dir / f"{proposal_id}.json"
            if not filepath.exists():
                return False
            try:
                data = json.loads(filepath.read_text("utf-8"))
                data["status"] = status
                filepath.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
                )
                self._update_index()
                return True
            except Exception as exc:
                logger.warning("ステータス更新失敗 %s: %s", proposal_id, exc)
                return False

    def _list_by_status(self, status: str) -> list[dict]:
        all_proposals = self.list_all()
        return [p for p in all_proposals if p.get("status") == status]

    def _update_index(self) -> None:
        """インデックスファイルを更新"""
        all_proposals = []
        for f in sorted(self._dir.glob("*.json")):
            if f.name == "index.json":
                continue
            try:
                data = json.loads(f.read_text("utf-8"))
                all_proposals.append({
                    "id": data["id"],
                    "title": data["title"],
                    "status": data["status"],
                    "priority": data["priority"],
                })
            except Exception as exc:
                logger.debug("インデックス項目読み込み失敗 %s: %s", f.name, exc)
        self._index_path.write_text(
            json.dumps(all_proposals, ensure_ascii=False, indent=2), "utf-8"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 統合: SelfDevelopmentEngine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SelfDevelopmentEngine:
    """
    アイの自己開発エンジン。

    自分のコードを読み、問題を見つけ、改善を提案する。
    ただし実行にはお父さんの承認が必要。

    社会人が自分の仕事を振り返って
    「ここ改善できるな」と気づく能力。
    """

    CHECK_INTERVAL_TURNS = 50  # 何ターンごとに自己開発チェックするか

    def __init__(self, project_root: Path, data_dir: Path):
        self.code_reader = CodeReader(project_root)
        self.error_analyzer = ErrorAnalyzer(data_dir)
        self.proposal_gen = ProposalGenerator()
        self.proposal_store = ProposalStore(data_dir)

        self._lock = threading.Lock()
        self._turn_count = 0
        self._last_check = 0.0

    # ─── メイン: 自己開発サイクル ────────────────────────

    def run_analysis(self) -> list[Proposal]:
        """
        自己開発分析を実行。

        1. エラーログを分析
        2. コード構造を分析
        3. 改善提案を生成
        4. 提案を保存

        Returns: 生成された提案のリスト
        """
        with self._lock:
            self._last_check = time.time()
            all_proposals: list[Proposal] = []

            # ① エラーパターン分析
            try:
                errors = self.error_analyzer.analyze_recent_errors()
                error_proposals = self.proposal_gen.from_error_patterns(
                    errors, self.code_reader
                )
                all_proposals.extend(error_proposals)
            except Exception as e:
                logger.debug("エラー分析失敗: %s", e)

            # ② コード構造分析
            try:
                modules = self.code_reader.list_modules()
                code_proposals = self.proposal_gen.from_code_analysis(modules)
                all_proposals.extend(code_proposals)
            except Exception as e:
                logger.debug("コード分析失敗: %s", e)

            # ③ 保存（重複排除）
            existing_ids = {p["id"] for p in self.proposal_store.list_all()}
            saved: list[Proposal] = []
            for proposal in all_proposals:
                # 同一ターゲットの既存提案があればスキップ
                if proposal.id not in existing_ids:
                    self.proposal_store.save(proposal)
                    saved.append(proposal)

            if saved:
                logger.info("自己開発: %d件の改善提案を生成", len(saved))

            return saved

    def run_quality_analysis(
        self, quality_avg: float, quality_trend: str
    ) -> list[Proposal]:
        """品質トレンドから追加提案を生成"""
        with self._lock:
            proposals = self.proposal_gen.from_quality_trend(
                quality_avg, quality_trend
            )
            saved: list[Proposal] = []
            for p in proposals:
                self.proposal_store.save(p)
                saved.append(p)
            return saved

    def on_turn(self) -> list[Proposal] | None:
        """毎ターン呼ばれる。CHECK_INTERVAL_TURNSごとに分析を実行"""
        with self._lock:
            self._turn_count += 1
            if self._turn_count % self.CHECK_INTERVAL_TURNS != 0:
                return None
        return self.run_analysis()

    # ─── 自己認識 ────────────────────────────────────────

    def get_self_awareness(self) -> dict[str, Any]:
        """
        自分自身の構造を理解する。

        「自分はどういうプログラムか」を把握する。
        人間の自己認識と同じ。
        """
        modules = self.code_reader.list_modules()
        total_lines = sum(m["lines"] for m in modules)

        # カテゴリごとに整理
        by_dir: dict[str, list] = {}
        for m in modules:
            d = m["dir"]
            if d not in by_dir:
                by_dir[d] = []
            by_dir[d].append(m)

        return {
            "total_modules": len(modules),
            "total_lines": total_lines,
            "by_directory": {
                d: {
                    "count": len(mods),
                    "total_lines": sum(m["lines"] for m in mods),
                    "files": [m["name"] for m in mods],
                }
                for d, mods in by_dir.items()
            },
            "largest_files": sorted(
                modules, key=lambda m: m["lines"], reverse=True
            )[:5],
        }

    # ─── ステータス ──────────────────────────────────────

    def get_status_text(self) -> str:
        """日本語ステータス"""
        pending = self.proposal_store.list_pending()
        all_proposals = self.proposal_store.list_all()

        lines = ["🔬 自己開発パイプライン:"]

        if pending:
            lines.append(f"  📋 未承認の提案: {len(pending)}件")
            for p in pending[:3]:
                prio = ["🔴", "🟠", "🟡", "⚪"][min(p.get("priority", 3), 3)]
                lines.append(f"    {prio} {p['title']}")
        else:
            lines.append("  ✅ 未承認の提案なし")

        done_count = sum(1 for p in all_proposals if p.get("status") == "done")
        lines.append(f"  📊 累計: {len(all_proposals)}件 (完了: {done_count}件)")

        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        all_proposals = self.proposal_store.list_all()
        by_status: dict[str, int] = {}
        for p in all_proposals:
            s = p.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1

        return {
            "total_proposals": len(all_proposals),
            "by_status": by_status,
            "turn_count": self._turn_count,
            "last_check": self._last_check,
        }

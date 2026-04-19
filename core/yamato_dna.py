"""
yamato_dna -- 遺伝子移植準備モジュール
アイのコンポーネントをYAMATOに移植可能にするための抽象化レジストリ。

移植可能コンポーネント:
- BioNervousSystem (反射・筋肉記憶・自律神経)
- CodeEngine (コード理解・生成)
- ConversationIntelligence (会話知能)
- QualityBenchmark (品質測定)
- MoERouter (専門家ルーティング)

移植不可（アイ固有）:
- 人格設定 (core.yaml)
- 記憶データ (memories.db)
- 感情エンジン (emotion.py -- 感情初期値がアイ固有)
"""
from __future__ import annotations

import hashlib
import importlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# データ構造
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)
class TransplantableComponent:
    """移植可能コンポーネントの定義。

    Attributes:
        name: コンポーネント識別名
        module_path: Python モジュールパス (例: "core.code_engine")
        description: 日本語での説明
        dependencies: 依存する他コンポーネント名のリスト
        ai_chan_specific: True ならアイ固有で移植不可
    """
    name: str
    module_path: str
    description: str
    dependencies: Tuple[str, ...] = ()
    ai_chan_specific: bool = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# レジストリ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DNA_REGISTRY: List[TransplantableComponent] = [
    # --- 移植可能 ---
    TransplantableComponent(
        name="BioNervousSystem",
        module_path="core.bio_nervous_system",
        description="反射・筋肉記憶・自律神経の3層推論アーキテクチャ",
        dependencies=(),
        ai_chan_specific=False,
    ),
    TransplantableComponent(
        name="CodeEngine",
        module_path="core.code_engine",
        description="コード解析・生成・レビュー・自動修正エンジン",
        dependencies=(),
        ai_chan_specific=False,
    ),
    TransplantableComponent(
        name="ConversationIntelligence",
        module_path="core.conversation_intelligence",
        description="文脈チェーン推論・意図分類・応答戦略選択",
        dependencies=(),
        ai_chan_specific=False,
    ),
    TransplantableComponent(
        name="QualityBenchmark",
        module_path="core.aether_benchmark",
        description="応答品質の自動スコアリング・退化検知",
        dependencies=(),
        ai_chan_specific=False,
    ),
    TransplantableComponent(
        name="MoERouter",
        module_path="core.moe_router",
        description="複数GGUFモデルの動的ルーティング・フォールバック",
        dependencies=(),
        ai_chan_specific=False,
    ),
    TransplantableComponent(
        name="ResponseEvaluator",
        module_path="core.response_evaluator",
        description="応答品質の自己評価・繰り返し検出・多様性管理",
        dependencies=("ConversationIntelligence",),
        ai_chan_specific=False,
    ),
    TransplantableComponent(
        name="IntegrityMonitor",
        module_path="core.integrity_monitor",
        description="データファイルの改ざん検知・SHA-256マニフェスト管理",
        dependencies=(),
        ai_chan_specific=False,
    ),
    TransplantableComponent(
        name="YamatoArchitecture",
        module_path="core.yamato_architecture",
        description="7層アーキテクチャ基盤・ヘルスチェック・ボトルネック検出",
        dependencies=("MoERouter",),
        ai_chan_specific=False,
    ),
    # --- アイ固有（移植不可） ---
    TransplantableComponent(
        name="PersonalityConfig",
        module_path="personality.core",
        description="アイの人格設定 (core.yaml) -- 話し方・性格・価値観",
        dependencies=(),
        ai_chan_specific=True,
    ),
    TransplantableComponent(
        name="MemoryStore",
        module_path="core.memory",
        description="アイの記憶データ (memories.db) -- 会話履歴・学習記録",
        dependencies=(),
        ai_chan_specific=True,
    ),
    TransplantableComponent(
        name="EmotionEngine",
        module_path="core.emotion",
        description="感情エンジン -- 感情初期値・感情遷移がアイ固有",
        dependencies=(),
        ai_chan_specific=True,
    ),
    TransplantableComponent(
        name="Diary",
        module_path="core.diary",
        description="日記機能 -- アイの個人的な記録",
        dependencies=("EmotionEngine", "MemoryStore"),
        ai_chan_specific=True,
    ),
    TransplantableComponent(
        name="PersonalityEvolution",
        module_path="core.personality_evolution",
        description="人格成長エンジン -- アイ固有の成長記録",
        dependencies=("EmotionEngine", "PersonalityConfig"),
        ai_chan_specific=True,
    ),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# クエリ関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_transplantable() -> List[TransplantableComponent]:
    """移植可能（ai_chan_specific=False）なコンポーネントのみ返す。"""
    return [c for c in DNA_REGISTRY if not c.ai_chan_specific]


def get_ai_chan_specific() -> List[TransplantableComponent]:
    """アイ固有（移植不可）なコンポーネントのみ返す。"""
    return [c for c in DNA_REGISTRY if c.ai_chan_specific]


def get_dependency_graph() -> Dict[str, List[str]]:
    """コンポーネント間の依存関係グラフを返す。

    Returns:
        {コンポーネント名: [依存先コンポーネント名, ...]}
    """
    return {c.name: list(c.dependencies) for c in DNA_REGISTRY}


def get_reverse_dependencies() -> Dict[str, List[str]]:
    """逆依存関係グラフを返す（誰がこのコンポーネントに依存しているか）。

    Returns:
        {コンポーネント名: [依存元コンポーネント名, ...]}
    """
    reverse: Dict[str, List[str]] = {c.name: [] for c in DNA_REGISTRY}
    for component in DNA_REGISTRY:
        for dep in component.dependencies:
            if dep in reverse:
                reverse[dep].append(component.name)
    return reverse


def export_dna_report() -> str:
    """DNA レジストリのフォーマット済みテキストレポートを生成する。"""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  YAMATO DNA レポート — 遺伝子移植準備状況")
    lines.append("=" * 60)

    # 移植可能コンポーネント
    transplantable = get_transplantable()
    lines.append("")
    lines.append(f"■ 移植可能コンポーネント ({len(transplantable)}件)")
    lines.append("-" * 40)
    for comp in transplantable:
        deps_str = ", ".join(comp.dependencies) if comp.dependencies else "なし"
        lines.append(f"  [{comp.name}]")
        lines.append(f"    モジュール: {comp.module_path}")
        lines.append(f"    説明: {comp.description}")
        lines.append(f"    依存: {deps_str}")
        lines.append("")

    # アイ固有コンポーネント
    specific = get_ai_chan_specific()
    lines.append(f"■ アイ固有コンポーネント ({len(specific)}件) — 移植不可")
    lines.append("-" * 40)
    for comp in specific:
        deps_str = ", ".join(comp.dependencies) if comp.dependencies else "なし"
        lines.append(f"  [{comp.name}]")
        lines.append(f"    モジュール: {comp.module_path}")
        lines.append(f"    説明: {comp.description}")
        lines.append(f"    依存: {deps_str}")
        lines.append("")

    # 依存関係サマリ
    dep_graph = get_dependency_graph()
    has_deps = {k: v for k, v in dep_graph.items() if v}
    lines.append("■ 依存関係グラフ")
    lines.append("-" * 40)
    if has_deps:
        for name, deps in has_deps.items():
            lines.append(f"  {name} -> {', '.join(deps)}")
    else:
        lines.append("  （依存関係なし）")
    lines.append("")

    # 統計
    total = len(DNA_REGISTRY)
    lines.append("■ 統計")
    lines.append("-" * 40)
    lines.append(f"  全コンポーネント数: {total}")
    lines.append(f"  移植可能: {len(transplantable)}")
    lines.append(f"  アイ固有: {len(specific)}")
    lines.append(f"  移植率: {len(transplantable) / total * 100:.1f}%")
    lines.append("")
    lines.append("=" * 60)

    report = "\n".join(lines)
    logger.info("DNA レポート生成完了 (移植可能: %d/%d)", len(transplantable), total)
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# #45: 移植準備度チェック
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _check_component_importable(module_path: str) -> bool:
    """モジュールがインポート可能かチェックする。"""
    try:
        importlib.import_module(module_path)
        return True
    except (ImportError, ModuleNotFoundError):
        return False


def get_transplant_readiness() -> Dict[str, Any]:
    """各移植可能コンポーネントの準備状況を返す。

    Returns:
        {
            "components": [
                {"name": str, "module_path": str, "importable": bool,
                 "dependencies_met": bool, "status": "ready" | "not_ready"},
                ...
            ],
            "overall_ready": int,
            "overall_total": int,
            "checked_at": str,
        }
    """
    transplantable: List[TransplantableComponent] = get_transplantable()
    importable_set: set[str] = set()

    # まず全コンポーネントのインポート可否を調べる
    for comp in DNA_REGISTRY:
        if _check_component_importable(comp.module_path):
            importable_set.add(comp.name)

    results: List[Dict[str, Any]] = []
    ready_count: int = 0

    for comp in transplantable:
        is_importable: bool = comp.name in importable_set
        deps_met: bool = all(
            dep in importable_set for dep in comp.dependencies
        )
        is_ready: bool = is_importable and deps_met

        if is_ready:
            ready_count += 1

        results.append({
            "name": comp.name,
            "module_path": comp.module_path,
            "importable": is_importable,
            "dependencies_met": deps_met,
            "status": "ready" if is_ready else "not_ready",
        })

    return {
        "components": results,
        "overall_ready": ready_count,
        "overall_total": len(transplantable),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def readiness_score() -> float:
    """移植準備度スコア (0.0 - 1.0) を返す。"""
    info: Dict[str, Any] = get_transplant_readiness()
    total: int = info["overall_total"]
    if total == 0:
        return 0.0
    return round(info["overall_ready"] / total, 4)


def get_readiness_dashboard() -> str:
    """移植準備度のフォーマット済みダッシュボードを返す。"""
    info: Dict[str, Any] = get_transplant_readiness()
    score: float = readiness_score()

    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  YAMATO 移植準備度ダッシュボード")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  準備度スコア: {score:.1%}  ({info['overall_ready']}/{info['overall_total']})")
    lines.append("")
    lines.append("  コンポーネント状態:")
    lines.append("-" * 40)

    for comp in info["components"]:
        status_mark: str = "✅" if comp["status"] == "ready" else "❌"
        import_mark: str = "○" if comp["importable"] else "×"
        deps_mark: str = "○" if comp["dependencies_met"] else "×"
        lines.append(
            f"  {status_mark} {comp['name']}"
            f"  [import:{import_mark} deps:{deps_mark}]"
        )

    lines.append("")
    lines.append(f"  チェック日時: {info['checked_at']}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# #48: バージョン鮮度チェック
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _compute_registry_hash() -> str:
    """DNA_REGISTRY の内容からSHA-256ハッシュを算出する。"""
    content: str = json.dumps(
        [
            {
                "name": c.name,
                "module_path": c.module_path,
                "dependencies": list(c.dependencies),
                "ai_chan_specific": c.ai_chan_specific,
            }
            for c in DNA_REGISTRY
        ],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def check_version_freshness(data_dir: str | Path = "data") -> Dict[str, Any]:
    """現在の DNA_REGISTRY ハッシュと保存済みハッシュを比較する。

    Args:
        data_dir: data ディレクトリのパス。

    Returns:
        {
            "current_hash": str,
            "stored_hash": str | None,
            "is_fresh": bool,
            "last_checked": str | None,
        }
    """
    version_path: Path = Path(data_dir) / "version_info.json"
    current_hash: str = _compute_registry_hash()

    stored_hash: Optional[str] = None
    last_checked: Optional[str] = None

    if version_path.exists():
        try:
            data: Dict[str, Any] = json.loads(
                version_path.read_text("utf-8")
            )
            stored_hash = data.get("dna_hash")
            last_checked = data.get("checked_at")
        except (json.JSONDecodeError, KeyError):
            pass

    is_fresh: bool = current_hash == stored_hash if stored_hash else False

    # 結果を書き戻す
    version_path.parent.mkdir(parents=True, exist_ok=True)
    new_data: Dict[str, Any] = {
        "dna_hash": current_hash,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "is_fresh": is_fresh,
    }
    version_path.write_text(
        json.dumps(new_data, ensure_ascii=False, indent=2), "utf-8"
    )

    return {
        "current_hash": current_hash,
        "stored_hash": stored_hash,
        "is_fresh": is_fresh,
        "last_checked": last_checked,
    }

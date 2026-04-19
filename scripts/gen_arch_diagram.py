"""
アーキテクチャ図を Mermaid 形式で自動生成する。

core/*.py の import 文を解析し、モジュール間の依存関係を
Mermaid flowchart として docs/architecture.md に出力する。
"""
from __future__ import annotations

import ast
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def extract_imports(py_file: Path, package_prefix: str = "core") -> Set[str]:
    """Python ファイルからプロジェクト内 import を抽出する。"""
    imports: Set[str] = set()
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except (SyntaxError, UnicodeDecodeError) as exc:
        logger.warning("パース失敗 %s: %s", py_file.name, exc)
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(package_prefix):
                # "core.emotion" -> "emotion"
                mod = node.module.split(".", 1)[-1] if "." in node.module else node.module
                imports.add(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(package_prefix):
                    mod = alias.name.split(".", 1)[-1] if "." in alias.name else alias.name
                    imports.add(mod)
    return imports


def scan_dependencies(
    core_dir: Path,
    package_prefix: str = "core",
) -> Dict[str, Set[str]]:
    """core ディレクトリの全 .py から依存関係を構築する。"""
    deps: Dict[str, Set[str]] = {}
    for py_file in sorted(core_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        mod_name = py_file.stem
        imported = extract_imports(py_file, package_prefix)
        # 自分自身は除外
        imported.discard(mod_name)
        if imported:
            deps[mod_name] = imported
    return deps


def generate_mermaid(deps: Dict[str, Set[str]]) -> str:
    """依存関係辞書から Mermaid flowchart 文字列を生成する。"""
    lines: List[str] = ["```mermaid", "flowchart LR"]

    # ノードを集約してサブグラフ化
    all_nodes: Set[str] = set()
    for src, targets in deps.items():
        all_nodes.add(src)
        all_nodes.update(targets)

    # カテゴリ分類（ファイル名のプレフィックスで大まかに分ける）
    categories: Dict[str, List[str]] = defaultdict(list)
    for node in sorted(all_nodes):
        if node.startswith("yamato"):
            categories["YAMATO"].append(node)
        elif node in ("emotion", "expression_engine", "emotion_history"):
            categories["Emotion"].append(node)
        elif node in ("memory", "memory_compressor", "memory_summarizer", "rag_engine"):
            categories["Memory"].append(node)
        elif node in ("llm", "stt", "tts", "multimodal_chat"):
            categories["LLM/IO"].append(node)
        elif node in ("kill_switch", "host_guardian", "integrity_monitor",
                       "ip_guard", "audit_log", "anomaly_detector"):
            categories["Security"].append(node)
        else:
            categories["Core"].append(node)

    for cat, nodes in sorted(categories.items()):
        lines.append(f"    subgraph {cat}")
        for n in sorted(nodes):
            safe = n.replace("-", "_")
            lines.append(f"        {safe}[{n}]")
        lines.append("    end")

    # エッジ
    for src, targets in sorted(deps.items()):
        src_safe = src.replace("-", "_")
        for tgt in sorted(targets):
            tgt_safe = tgt.replace("-", "_")
            lines.append(f"    {src_safe} --> {tgt_safe}")

    lines.append("```")
    return "\n".join(lines)


def generate_architecture_doc(
    core_dir: Path,
    output_path: Path | None = None,
) -> str:
    """アーキテクチャ図を含む Markdown を生成する。"""
    deps = scan_dependencies(core_dir)

    header = [
        "# Architecture",
        "",
        "Auto-generated module dependency diagram.",
        "",
    ]
    mermaid = generate_mermaid(deps)

    stats = [
        "",
        f"## Statistics",
        "",
        f"- Modules with dependencies: {len(deps)}",
        f"- Total unique edges: {sum(len(v) for v in deps.values())}",
        "",
    ]

    md = "\n".join(header) + mermaid + "\n" + "\n".join(stats)

    if output_path is None:
        output_path = core_dir.parent / "docs" / "architecture.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    logger.info("アーキテクチャ図を生成しました: %s", output_path)
    return md


def main() -> None:
    base = Path(__file__).parent.parent
    md = generate_architecture_doc(base / "core")
    print(md)


if __name__ == "__main__":
    main()

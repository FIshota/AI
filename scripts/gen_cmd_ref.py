"""
コマンドリファレンスを自動生成する。

core/*.py から CMD_* パターン定数やコマンドハンドラの定義をスキャンし、
docs/COMMANDS.md へ Markdown 形式で出力する。
"""
from __future__ import annotations

import ast
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple

logger = logging.getLogger(__name__)


class CommandInfo(NamedTuple):
    """発見されたコマンド情報。"""
    name: str
    pattern: str
    source_file: str
    example: str


# CMD_ で始まる定数代入を探す正規表現
_CMD_CONST_RE = re.compile(
    r"""^(?P<name>CMD_\w+)\s*=\s*(?:r)?['"](?P<pattern>[^'"]+)['"]""",
    re.MULTILINE,
)

# register_command / add_command 系の呼び出し
_REGISTER_RE = re.compile(
    r"""(?:register_command|add_command)\(\s*['"](?P<name>[^'"]+)['"]""",
    re.MULTILINE,
)


def scan_commands(core_dir: Path) -> List[CommandInfo]:
    """core ディレクトリの Python ファイルからコマンド定義をスキャンする。"""
    commands: List[CommandInfo] = []
    seen_names: set[str] = set()

    for py_file in sorted(core_dir.glob("*.py")):
        source = py_file.read_text(encoding="utf-8", errors="replace")

        # CMD_* 定数
        for m in _CMD_CONST_RE.finditer(source):
            name = m.group("name")
            pattern = m.group("pattern")
            if name not in seen_names:
                seen_names.add(name)
                # パターンからコマンド例を推定
                example = _pattern_to_example(pattern)
                commands.append(CommandInfo(
                    name=name,
                    pattern=pattern,
                    source_file=py_file.name,
                    example=example,
                ))

        # register_command 呼び出し
        for m in _REGISTER_RE.finditer(source):
            name = m.group("name")
            if name not in seen_names:
                seen_names.add(name)
                commands.append(CommandInfo(
                    name=name,
                    pattern=name,
                    source_file=py_file.name,
                    example=name,
                ))

    return commands


def _pattern_to_example(pattern: str) -> str:
    """正規表現パターンから人間が読める例を生成する。"""
    example = pattern
    # 正規表現メタ文字を除去して読みやすくする
    example = re.sub(r"\(\?:([^)]+)\)", r"\1", example)
    example = re.sub(r"[()\\^$*+?{}|]", "", example)
    example = re.sub(r"\[([^\]]+)\]", "", example)
    example = example.strip()
    return example if example else pattern


def generate_command_reference(
    core_dir: Path,
    output_path: Path | None = None,
) -> str:
    """コマンドリファレンスを Markdown で生成する。"""
    commands = scan_commands(core_dir)

    lines: List[str] = [
        "# Command Reference",
        "",
        "Auto-generated from `core/*.py`.",
        "",
        "| Name | Pattern | Source | Example |",
        "|------|---------|--------|---------|",
    ]
    for cmd in commands:
        escaped_pattern = cmd.pattern.replace("|", "\\|")
        lines.append(
            f"| `{cmd.name}` | `{escaped_pattern}` "
            f"| `{cmd.source_file}` | `{cmd.example}` |"
        )

    lines.append("")
    lines.append(f"Total: {len(commands)} commands")
    lines.append("")

    md = "\n".join(lines)

    if output_path is None:
        output_path = core_dir.parent / "docs" / "COMMANDS.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    logger.info("コマンドリファレンスを生成しました: %s (%d件)", output_path, len(commands))
    return md


def main() -> None:
    base = Path(__file__).parent.parent
    md = generate_command_reference(base / "core")
    print(md)


if __name__ == "__main__":
    main()

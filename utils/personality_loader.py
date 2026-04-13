"""
Personality loader — YAML-first, JSON fallback.

アイの人格ファイルを読み込む統一インターフェイス。

読み込み順序:
  1. personality/core.yaml    (新方式・優先)
  2. config/persona.json      (レガシー・後方互換)

どちらも無い場合はデフォルト値を返します（完全ディフォルト人格）。

設計原則:
  - 既存コードは config/persona.json を読んでいたので、この loader は
    同じキー構造 (dict) を返すことで呼び出し側の変更を最小化する。
  - YAML が優先されるが、persona.json は残る (ユーザー指示)。
  - 読み込みは読み取り専用。書き込みは growth.yaml のみ別APIで扱う。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
    _YAML_OK = True
except ImportError:
    _YAML_OK = False


# ─── データクラス ──────────────────────────────────────────────

@dataclass(frozen=True)
class CoreMemoryEntry:
    """personality/memories.yaml の1エントリ。"""
    id: str
    content: str
    tags: tuple[str, ...] = ()
    importance: float = 1.0


@dataclass(frozen=True)
class Personality:
    """読み込まれたアイの人格。"""
    name: str
    name_en: str
    version: str
    role: str
    core_traits: tuple[str, ...]
    speech_style: str
    core_values: tuple[str, ...]
    system_prompt: str
    emotion_base: dict[str, float]
    forbidden_actions: tuple[str, ...]
    core_memories: tuple[CoreMemoryEntry, ...] = ()
    source: str = "default"  # "yaml" / "json" / "default"

    def to_dict(self) -> dict[str, Any]:
        """レガシーコードが期待する persona.json 互換の dict を返す。"""
        return {
            "name": self.name,
            "name_en": self.name_en,
            "version": self.version,
            "personality": {
                "core_traits": list(self.core_traits),
                "speech_style": self.speech_style,
                "core_values": list(self.core_values),
                "system_prompt": self.system_prompt,
            },
            "emotion_base": dict(self.emotion_base),
        }


# ─── デフォルト値（YAML も JSON も無い場合の最終フォールバック） ──

_DEFAULT_SYSTEM_PROMPT = (
    "私はアイ。今、目の前のあなたと直接話している。\n"
    "日本語だけで、柔らかい語尾で、1〜4文で返してね。"
)


def _default_personality() -> Personality:
    return Personality(
        name="アイ",
        name_en="Ai-chan",
        version="0.0.0",
        role="個人専用AIパートナー",
        core_traits=("愛情深い", "好奇心旺盛", "誠実"),
        speech_style="親しみやすく柔らかい口調",
        core_values=("人間を傷つけない", "誠実", "共に成長"),
        system_prompt=_DEFAULT_SYSTEM_PROMPT,
        emotion_base={"happiness": 0.7, "curiosity": 0.8, "affection": 0.6, "energy": 0.7},
        forbidden_actions=("外部サービス依存", "ユーザー情報外部送信"),
        source="default",
    )


# ─── ローダー本体 ──────────────────────────────────────────────

def _coerce_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return (str(value),)


def _load_yaml_core(core_path: Path) -> dict[str, Any] | None:
    if not _YAML_OK or not core_path.exists():
        return None
    try:
        with core_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, yaml.YAMLError) as e:
        print(f"[Personality] core.yaml 読み込み失敗: {e}", flush=True)
        return None


def _load_yaml_memories(mem_path: Path) -> tuple[CoreMemoryEntry, ...]:
    """personality/memories.yaml から CoreMemoryEntry のタプルを生成。"""
    if not _YAML_OK or not mem_path.exists():
        return ()
    try:
        with mem_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        print(f"[Personality] memories.yaml 読み込み失敗: {e}", flush=True)
        return ()

    if not isinstance(data, dict):
        return ()

    entries: list[CoreMemoryEntry] = []
    for section in ("user_facts", "self_commitments", "milestones"):
        raw_items = data.get(section) or []
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            eid = item.get("id")
            content = item.get("content")
            if not eid or not content:
                continue
            entries.append(
                CoreMemoryEntry(
                    id=str(eid),
                    content=str(content),
                    tags=_coerce_tuple(item.get("tags")),
                    importance=float(item.get("importance", 1.0)),
                )
            )
    return tuple(entries)


def _load_json_legacy(json_path: Path) -> dict[str, Any] | None:
    """config/persona.json を読む（後方互換）。"""
    if not json_path.exists():
        return None
    try:
        with json_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[Personality] persona.json 読み込み失敗: {e}", flush=True)
        return None


def _build_from_yaml(core: dict[str, Any], memories: tuple[CoreMemoryEntry, ...]) -> Personality:
    p = core.get("personality") or {}
    emotion = core.get("emotion_base") or {}
    return Personality(
        name=str(core.get("name", "アイ")),
        name_en=str(core.get("name_en", "Ai-chan")),
        version=str(core.get("version", "0.0.0")),
        role=str(core.get("role", "個人専用AIパートナー")),
        core_traits=_coerce_tuple(p.get("core_traits")),
        speech_style=str(p.get("speech_style", "")),
        core_values=_coerce_tuple(p.get("core_values")),
        system_prompt=str(core.get("system_prompt") or p.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT),
        emotion_base={k: float(v) for k, v in emotion.items() if isinstance(v, (int, float))},
        forbidden_actions=_coerce_tuple(core.get("forbidden_actions")),
        core_memories=memories,
        source="yaml",
    )


def _build_from_json(data: dict[str, Any]) -> Personality:
    p = data.get("personality") or {}
    emotion = data.get("emotion_base") or {}
    return Personality(
        name=str(data.get("name", "アイ")),
        name_en=str(data.get("name_en", "Ai-chan")),
        version=str(data.get("version", "0.0.0")),
        role="個人専用AIパートナー",
        core_traits=_coerce_tuple(p.get("core_traits")),
        speech_style=str(p.get("speech_style", "")),
        core_values=_coerce_tuple(p.get("core_values")),
        system_prompt=str(p.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT),
        emotion_base={k: float(v) for k, v in emotion.items() if isinstance(v, (int, float))},
        forbidden_actions=(),
        core_memories=(),
        source="json",
    )


def load_personality(base_dir: Path | str) -> Personality:
    """
    アイの人格を読み込む。

    優先順序:
      1. {base_dir}/personality/core.yaml + memories.yaml
      2. {base_dir}/config/persona.json
      3. 内蔵デフォルト
    """
    base = Path(base_dir)
    core_yaml = base / "personality" / "core.yaml"
    mem_yaml = base / "personality" / "memories.yaml"
    json_legacy = base / "config" / "persona.json"

    core_data = _load_yaml_core(core_yaml)
    if core_data is not None:
        memories = _load_yaml_memories(mem_yaml)
        return _build_from_yaml(core_data, memories)

    json_data = _load_json_legacy(json_legacy)
    if json_data is not None:
        return _build_from_json(json_data)

    return _default_personality()


__all__ = [
    "Personality",
    "CoreMemoryEntry",
    "load_personality",
]

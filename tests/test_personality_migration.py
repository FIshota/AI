"""
Personality loader migration tests.

検証項目:
  - YAML が存在する場合は YAML が優先される
  - YAML が無くて persona.json があれば JSON にフォールバック
  - どちらも無ければデフォルト人格
  - YAML 経由で読んだ Personality は to_dict() でレガシーJSON互換になる
  - core_memories が memories.yaml から正しく読まれる
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.personality_loader import (
    CoreMemoryEntry,
    Personality,
    load_personality,
)


# ─── ヘルパー ──────────────────────────────────────────────────


def _write_yaml(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


_LEGACY_PERSONA = {
    "name": "アイ",
    "name_en": "Ai-chan",
    "version": "0.1.0",
    "personality": {
        "core_traits": ["優しい", "好奇心旺盛"],
        "speech_style": "柔らかい口調",
        "core_values": ["誠実", "成長"],
        "system_prompt": "私はアイ。レガシー版です。",
    },
    "emotion_base": {"happiness": 0.7, "curiosity": 0.8},
}


_NEW_CORE_YAML = """\
name: "アイ"
name_en: "Ai-chan"
version: "0.2.0"
role: "個人専用AIパートナー"

personality:
  core_traits:
    - "愛情深い"
    - "誠実"
  speech_style: "親しみやすく温かい口調"
  core_values:
    - "人間を傷つけない"
    - "共に成長"

system_prompt: |
  私はアイ。新YAML版です。

emotion_base:
  happiness: 0.9
  curiosity: 0.85
  affection: 0.7
  energy: 0.8

forbidden_actions:
  - "外部送信"
"""


_NEW_MEMORIES_YAML = """\
user_facts:
  - id: user-test-name
    content: "テストユーザーの名前"
    tags: ["user"]
    importance: 1.0

self_commitments:
  - id: commit-honesty
    content: "嘘をつかない"
    tags: ["self"]
    importance: 1.0

milestones: []
"""


# ─── テスト ────────────────────────────────────────────────────


@pytest.mark.unit
def test_loads_default_when_nothing_present(tmp_path: Path) -> None:
    p = load_personality(tmp_path)
    assert p.source == "default"
    assert p.name == "アイ"
    assert p.system_prompt  # 空でない


@pytest.mark.unit
def test_loads_legacy_json_when_only_persona_json(tmp_path: Path) -> None:
    _write_json(tmp_path / "config" / "persona.json", _LEGACY_PERSONA)

    p = load_personality(tmp_path)

    assert p.source == "json"
    assert p.name == "アイ"
    assert "レガシー版" in p.system_prompt
    assert "優しい" in p.core_traits


@pytest.mark.unit
def test_yaml_takes_precedence_over_json(tmp_path: Path) -> None:
    """ユーザー指示: persona.json は残すが、YAML が優先されること。"""
    _write_json(tmp_path / "config" / "persona.json", _LEGACY_PERSONA)
    _write_yaml(tmp_path / "personality" / "core.yaml", _NEW_CORE_YAML)
    _write_yaml(tmp_path / "personality" / "memories.yaml", _NEW_MEMORIES_YAML)

    p = load_personality(tmp_path)

    assert p.source == "yaml"
    assert "新YAML版" in p.system_prompt
    assert p.version == "0.2.0"
    assert "愛情深い" in p.core_traits
    assert p.emotion_base["happiness"] == pytest.approx(0.9)
    # 旧JSONの値が漏れていないこと
    assert "優しい" not in p.core_traits


@pytest.mark.unit
def test_core_memories_loaded_from_yaml(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "personality" / "core.yaml", _NEW_CORE_YAML)
    _write_yaml(tmp_path / "personality" / "memories.yaml", _NEW_MEMORIES_YAML)

    p = load_personality(tmp_path)

    ids = {m.id for m in p.core_memories}
    assert "user-test-name" in ids
    assert "commit-honesty" in ids
    # CoreMemoryEntry は frozen dataclass
    sample = next(m for m in p.core_memories if m.id == "commit-honesty")
    assert isinstance(sample, CoreMemoryEntry)
    assert sample.content == "嘘をつかない"
    assert "self" in sample.tags


@pytest.mark.unit
def test_to_dict_is_json_compatible(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "personality" / "core.yaml", _NEW_CORE_YAML)
    p = load_personality(tmp_path)

    d = p.to_dict()
    # 旧コードが期待していたキー構造
    assert d["name"] == "アイ"
    assert "personality" in d
    assert "core_traits" in d["personality"]
    assert "system_prompt" in d["personality"]
    # JSONシリアライズ可能であること
    json.dumps(d, ensure_ascii=False)


@pytest.mark.unit
def test_persona_json_remains_untouched(tmp_path: Path) -> None:
    """YAMLが優先されても persona.json は削除/変更されないことを保証。"""
    json_path = tmp_path / "config" / "persona.json"
    _write_json(json_path, _LEGACY_PERSONA)
    _write_yaml(tmp_path / "personality" / "core.yaml", _NEW_CORE_YAML)

    _ = load_personality(tmp_path)

    # ファイルが残っていて中身も変わっていない
    assert json_path.exists()
    assert json.loads(json_path.read_text("utf-8")) == _LEGACY_PERSONA

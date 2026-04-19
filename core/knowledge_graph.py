"""
知識グラフ (Knowledge Graph)
Sprint K2: 記憶知能の進化 — 会話から自動的に知識を構造化する。

機能:
- エンティティ抽出（人物/場所/イベント/概念）
- 関係性の自動推論（AはBの友達、CはDが好き）
- 会話からの自動知識蓄積
- 関連知識の連鎖検索
- ユーザーの世界モデル構築
"""
from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Entity:
    """知識グラフ上のエンティティ"""
    name: str
    entity_type: str          # person, place, event, concept, thing, time
    attributes: dict = field(default_factory=dict)
    first_mentioned: str = ""
    mention_count: int = 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.entity_type,
            "attributes": self.attributes,
            "first_mentioned": self.first_mentioned,
            "mention_count": self.mention_count,
        }


@dataclass
class Relation:
    """エンティティ間の関係"""
    source: str        # エンティティ名
    relation: str      # 関係の種類
    target: str        # エンティティ名
    context: str = ""  # 抽出元の文脈
    confidence: float = 0.8
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "context": self.context[:100],
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


# ─── エンティティ抽出パターン ────────────────────────────────

# 人物関係パターン
_PERSON_RELATION_PATTERNS = [
    # 「AはBの友達」「AはBの上司」
    (re.compile(r"(.{1,8})は(.{1,8})の(友達|友人|親友|上司|部下|先輩|後輩|同僚|恋人|彼氏|彼女|夫|妻|兄|弟|姉|妹|父|母|子供|息子|娘)"),
     lambda m: (m.group(1), m.group(3), m.group(2))),
    # 「AとBは友達」
    (re.compile(r"(.{1,8})と(.{1,8})は(友達|友人|親友|同僚|カップル|夫婦|兄弟|姉妹)"),
     lambda m: (m.group(1), m.group(3), m.group(2))),
    # 「Aの名前はB」
    (re.compile(r"(.{1,8})の名前は(.{1,10})"),
     lambda m: (m.group(1), "名前", m.group(2))),
]

# 場所パターン
_PLACE_PATTERNS = [
    re.compile(r"(.{1,8})に(住んで|引っ越|行った|行く|出かけ)"),
    re.compile(r"(東京|大阪|名古屋|福岡|北海道|沖縄|京都|横浜|札幌|神戸|仙台|広島)"),
    re.compile(r"(\w+)(駅|市|区|町|村|県|都|府)"),
]

# イベントパターン
_EVENT_PATTERNS = [
    re.compile(r"(明日|来週|今度|今週末|次の|(\d+月\d+日)).*(予定|イベント|会議|面接|デート|旅行|出張|試験|テスト|発表)"),
    re.compile(r"(予定|イベント|会議|面接|デート|旅行|出張|試験|テスト|発表).*(ある|した|する|行く)"),
]

# 好み・属性パターン
_PREFERENCE_PATTERNS = [
    # 「Aが好き」「Aが嫌い」
    (re.compile(r"(.{1,15})が(好き|嫌い|苦手|得意|大好き|趣味)"),
     lambda m: ("ユーザー", m.group(2), m.group(1))),
    # 「好きなAはB」
    (re.compile(r"好きな(.{1,8})は(.{1,15})"),
     lambda m: ("ユーザー", f"好きな{m.group(1)}", m.group(2))),
    # 「AはBが好き」
    (re.compile(r"私.?(.{1,15})が(好き|嫌い|得意|苦手)"),
     lambda m: ("ユーザー", m.group(2), m.group(1))),
]

# 仕事・活動パターン
_ACTIVITY_PATTERNS = [
    (re.compile(r"(仕事|バイト|パート)は(.{1,20})(している|してる|やってる|です)"),
     lambda m: ("ユーザー", "仕事", m.group(2))),
    (re.compile(r"(.{1,15})を(勉強|学習|練習)(している|してる|中)"),
     lambda m: ("ユーザー", "学習中", m.group(1))),
]


class KnowledgeGraph:
    """
    会話から自動構築される知識グラフ。
    ユーザーの世界（人間関係、好み、予定）を構造化して保持する。
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._graph_path = self._base / "data" / "knowledge_graph.json"
        self._entities: dict[str, Entity] = {}
        self._relations: list[Relation] = []
        self._lock = threading.Lock()
        self._load()

    # ─── 知識抽出 ────────────────────────────────────────────

    def extract_from_conversation(
        self, user_input: str, ai_response: str = ""
    ) -> dict:
        """会話から知識を抽出してグラフに追加する"""
        now = datetime.now().isoformat()[:19]
        added_entities: list[str] = []
        added_relations: list[str] = []

        # 人物関係の抽出
        for pattern, extractor in _PERSON_RELATION_PATTERNS:
            for match in pattern.finditer(user_input):
                source, relation, target = extractor(match)
                source = source.strip()
                target = target.strip()
                if len(source) < 1 or len(target) < 1:
                    continue
                self._add_entity(source, "person", now)
                self._add_entity(target, "person", now)
                rel = self._add_relation(source, relation, target, user_input, now)
                if rel:
                    added_entities.extend([source, target])
                    added_relations.append(f"{source}-{relation}-{target}")

        # 好み・属性の抽出
        for pattern, extractor in _PREFERENCE_PATTERNS:
            for match in pattern.finditer(user_input):
                source, relation, target = extractor(match)
                target = target.strip()
                if len(target) < 1 or len(target) > 20:
                    continue
                self._add_entity(target, "concept", now)
                rel = self._add_relation(source, relation, target, user_input, now)
                if rel:
                    added_relations.append(f"{source}-{relation}-{target}")

        # 活動の抽出
        for pattern, extractor in _ACTIVITY_PATTERNS:
            for match in pattern.finditer(user_input):
                source, relation, target = extractor(match)
                target = target.strip()
                if len(target) < 1:
                    continue
                self._add_entity(target, "concept", now)
                rel = self._add_relation(source, relation, target, user_input, now)
                if rel:
                    added_relations.append(f"{source}-{relation}-{target}")

        # 場所の抽出
        for pattern in _PLACE_PATTERNS:
            for match in pattern.finditer(user_input):
                place = match.group(1) if match.group(1) else match.group(0)
                place = place.strip()
                if len(place) >= 2:
                    self._add_entity(place, "place", now)
                    added_entities.append(place)

        if added_entities or added_relations:
            self._save()

        return {
            "entities_added": len(set(added_entities)),
            "relations_added": len(added_relations),
        }

    # ─── 知識検索 ────────────────────────────────────────────

    def search_related(self, query: str, max_depth: int = 2) -> list[dict]:
        """クエリに関連する知識を検索する（グラフ探索）"""
        results: list[dict] = []
        visited: set[str] = set()

        # クエリにマッチするエンティティを起点にする
        start_entities = self._find_matching_entities(query)
        if not start_entities:
            return results

        # BFS的に関連を辿る
        queue: list[tuple[str, int]] = [(e, 0) for e in start_entities]
        while queue:
            entity_name, depth = queue.pop(0)
            if entity_name in visited or depth > max_depth:
                continue
            visited.add(entity_name)

            # このエンティティの情報を追加
            entity = self._entities.get(entity_name)
            if entity:
                results.append(entity.to_dict())

            # 関連するエンティティを探索
            for rel in self._relations:
                if rel.source == entity_name and rel.target not in visited:
                    results.append(rel.to_dict())
                    queue.append((rel.target, depth + 1))
                elif rel.target == entity_name and rel.source not in visited:
                    results.append(rel.to_dict())
                    queue.append((rel.source, depth + 1))

        return results[:10]  # 最大10件

    def get_context_for_chat(self, user_input: str, max_chars: int = 300) -> str:
        """チャット用に関連知識を自然な日本語テキストとして返す"""
        related = self.search_related(user_input, max_depth=1)
        if not related:
            return ""

        parts: list[str] = []
        seen: set[str] = set()

        for item in related:
            if "relation" in item:
                # 関係情報
                key = f"{item['source']}-{item['relation']}-{item['target']}"
                if key not in seen:
                    seen.add(key)
                    parts.append(f"{item['source']}は{item['target']}の{item['relation']}")
            elif "name" in item and "type" in item:
                # エンティティ情報
                entity = item
                if entity["attributes"]:
                    for k, v in list(entity["attributes"].items())[:2]:
                        key = f"{entity['name']}-{k}"
                        if key not in seen:
                            seen.add(key)
                            parts.append(f"{entity['name']}の{k}は{v}")

        if not parts:
            return ""

        text = "知識グラフ: " + "。".join(parts[:5]) + "。"
        return text[:max_chars]

    def get_user_world_summary(self) -> str:
        """ユーザーの世界モデルのサマリーを返す"""
        if not self._entities and not self._relations:
            return "まだ知識が蓄積されていないよ。もっといろんなこと教えてね！"

        lines = ["📊 あなたについて知っていること：\n"]

        # 人物
        people = [e for e in self._entities.values() if e.entity_type == "person"]
        if people:
            names = [p.name for p in sorted(people, key=lambda p: -p.mention_count)[:5]]
            lines.append(f"👥 関係する人: {', '.join(names)}")

        # 好み
        prefs = [r for r in self._relations if r.relation in ("好き", "大好き", "趣味")]
        if prefs:
            likes = [r.target for r in prefs[:5]]
            lines.append(f"💖 好きなもの: {', '.join(likes)}")

        # 場所
        places = [e for e in self._entities.values() if e.entity_type == "place"]
        if places:
            place_names = [p.name for p in places[:5]]
            lines.append(f"📍 場所: {', '.join(place_names)}")

        # 活動
        activities = [r for r in self._relations if r.relation in ("仕事", "学習中")]
        if activities:
            for a in activities[:3]:
                lines.append(f"💼 {a.relation}: {a.target}")

        # 関係性
        relations = [r for r in self._relations if r.relation not in ("好き", "大好き", "趣味", "仕事", "学習中")]
        if relations:
            for r in relations[:5]:
                lines.append(f"🔗 {r.source}は{r.target}の{r.relation}")

        lines.append(f"\n合計: {len(self._entities)}エンティティ、{len(self._relations)}関係")
        return "\n".join(lines)

    # ─── 統計 ─────────────────────────────────────────────────

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    @property
    def relation_count(self) -> int:
        return len(self._relations)

    # ─── 内部 ─────────────────────────────────────────────────

    def _find_matching_entities(self, query: str) -> list[str]:
        """クエリにマッチするエンティティ名を返す"""
        matches: list[str] = []
        for name in self._entities:
            if name in query or query in name:
                matches.append(name)
        # 関係のターゲットも検索
        for rel in self._relations:
            if rel.target in query or query in rel.target:
                if rel.source not in matches:
                    matches.append(rel.source)
        return matches[:5]

    def _add_entity(self, name: str, entity_type: str, timestamp: str) -> Entity:
        """エンティティを追加または更新する"""
        with self._lock:
            if name in self._entities:
                self._entities[name].mention_count += 1
                return self._entities[name]
            entity = Entity(
                name=name,
                entity_type=entity_type,
                first_mentioned=timestamp,
            )
            self._entities[name] = entity
            return entity

    def _add_relation(
        self, source: str, relation: str, target: str,
        context: str, timestamp: str
    ) -> Relation | None:
        """関係を追加する（重複は無視）"""
        with self._lock:
            # 重複チェック
            for r in self._relations:
                if r.source == source and r.relation == relation and r.target == target:
                    return None
            rel = Relation(
                source=source,
                relation=relation,
                target=target,
                context=context[:200],
                created_at=timestamp,
            )
            self._relations.append(rel)
            return rel

    def _load(self) -> None:
        """知識グラフをファイルから読み込む"""
        if not self._graph_path.exists():
            return
        try:
            data = json.loads(self._graph_path.read_text("utf-8"))
            for e_data in data.get("entities", []):
                # to_dict()で"type"に変換されるため"entity_type"に戻す
                if "type" in e_data and "entity_type" not in e_data:
                    e_data["entity_type"] = e_data.pop("type")
                self._entities[e_data["name"]] = Entity(**e_data)
            for r_data in data.get("relations", []):
                self._relations.append(Relation(**r_data))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    def _save(self) -> None:
        """知識グラフをファイルに保存する"""
        with self._lock:
            self._graph_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "entities": [e.to_dict() for e in self._entities.values()],
                "relations": [r.to_dict() for r in self._relations],
                "updated_at": datetime.now().isoformat()[:19],
            }
            self._graph_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )

    # ── #78: 関連トピック提案 ──────────────────────────────

    def _build_adjacency(self) -> dict[str, list[str]]:
        """関係リストからエンティティの隣接リストを構築する。"""
        adj: dict[str, list[str]] = defaultdict(list)
        for rel in self._relations:
            if rel.target not in adj[rel.source]:
                adj[rel.source].append(rel.target)
            if rel.source not in adj[rel.target]:
                adj[rel.target].append(rel.source)
        return dict(adj)

    def get_related_topics(
        self,
        current_topic: str,
        limit: int = 3,
    ) -> list[str]:
        """グラフの隣接関係から関連トピックを返す。

        Args:
            current_topic: 起点となるトピック / エンティティ名。
            limit: 返す最大件数。

        Returns:
            関連トピック名のリスト（mention_count 降順）。
        """
        # まず current_topic にマッチするエンティティを探す
        start_entities: list[str] = self._find_matching_entities(current_topic)
        if not start_entities:
            return []

        adj: dict[str, list[str]] = self._build_adjacency()

        # 1ホップ隣接をすべて集める
        candidates: set[str] = set()
        for start in start_entities:
            for neighbor in adj.get(start, []):
                if neighbor not in start_entities:
                    candidates.add(neighbor)

        # mention_count で重み付けソート
        scored: list[tuple[str, int]] = []
        for name in candidates:
            entity: Entity | None = self._entities.get(name)
            count: int = entity.mention_count if entity else 0
            scored.append((name, count))

        scored.sort(key=lambda x: -x[1])
        return [name for name, _ in scored[:limit]]

    def get_topic_suggestions(
        self,
        context: str,
        limit: int = 3,
    ) -> list[str]:
        """入力文脈から話題の提案を返す。

        グラフ内のエンティティと関連トピックを探索し、
        会話に出ていないが関連性のある話題を提案する。

        Args:
            context: 直近の会話テキスト（ユーザー発話等）。
            limit: 返す最大件数。

        Returns:
            提案トピック名のリスト。
        """
        # 文脈にマッチするエンティティを起点とする
        matched: list[str] = self._find_matching_entities(context)
        if not matched:
            # マッチなしの場合、最も mention_count が高いエンティティを提案
            all_entities: list[Entity] = sorted(
                self._entities.values(),
                key=lambda e: -e.mention_count,
            )
            return [e.name for e in all_entities[:limit]]

        adj: dict[str, list[str]] = self._build_adjacency()

        # 1-2ホップ先を集める（文脈に含まれないもの優先）
        visited: set[str] = set(matched)
        suggestions: list[str] = []

        queue: list[tuple[str, int]] = [(m, 0) for m in matched]
        while queue and len(suggestions) < limit * 3:
            node, depth = queue.pop(0)
            if depth > 2:
                continue
            for neighbor in adj.get(node, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                # 文脈に既出でなければ候補
                if neighbor not in context:
                    suggestions.append(neighbor)
                if depth < 2:
                    queue.append((neighbor, depth + 1))

        # mention_count 降順でソート
        suggestions.sort(
            key=lambda name: -(
                self._entities[name].mention_count
                if name in self._entities else 0
            ),
        )
        return suggestions[:limit]

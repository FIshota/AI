"""Lifelong Memory Module (LMM) — PoC skeleton.

ai-chan は 10 年運用を前提とする。会話履歴中心の ``core/memory.py`` とは別に、
出来事 / 人物 / 趣味嗜好 / 感情トレンドを時系列で蓄積し、近似想起できる
長期記憶レイヤを切り出す。

Design principles
-----------------
* 既存 ``memory.py`` (三層記憶) は変更しない。別モジュールとして並立。
* SQLite 永続化、Python 3.9 互換、stdlib のみ。
* TF-IDF 近似 recall は日本語も扱える bigram bag-of-chars で自前実装。
* Kill-Switch: ``forget`` / ``purge`` で単体 / 主体単位削除を即時反映。
* importance decay: 経過日数 / 半減期で importance を段階的に減衰。
"""
from __future__ import annotations

import math
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# ── Constants ────────────────────────────────────────────────────────────
ALLOWED_KINDS: Tuple[str, ...] = ("event", "person", "preference", "trend")
DEFAULT_HALF_LIFE_DAYS: float = 365.0  # importance が半分になる日数
_NGRAM_N: int = 2


# ── Data model ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MemoryEvent:
    """長期記憶の最小単位。全フィールドイミュータブル。"""

    id: str
    subject_id: str
    kind: str
    content: str
    ts: str  # ISO8601 (UTC)
    tags: Tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 1.0
    importance: float = 0.5

    def __post_init__(self) -> None:  # pragma: no cover - trivial
        if self.kind not in ALLOWED_KINDS:
            raise ValueError(f"invalid kind: {self.kind!r} (allowed: {ALLOWED_KINDS})")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of range: {self.confidence}")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError(f"importance out of range: {self.importance}")
        # tags must be tuple for immutability
        if not isinstance(self.tags, tuple):
            object.__setattr__(self, "tags", tuple(self.tags))


def new_event(
    subject_id: str,
    kind: str,
    content: str,
    tags: Sequence[str] = (),
    confidence: float = 1.0,
    importance: float = 0.5,
    ts: Optional[str] = None,
    event_id: Optional[str] = None,
) -> MemoryEvent:
    """``MemoryEvent`` factory with sane defaults."""
    return MemoryEvent(
        id=event_id or uuid.uuid4().hex,
        subject_id=subject_id,
        kind=kind,
        content=content,
        ts=ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        tags=tuple(tags),
        confidence=confidence,
        importance=importance,
    )


# ── TF-IDF (bigram bag-of-chars) ─────────────────────────────────────────
def _char_ngrams(text: str, n: int = _NGRAM_N) -> List[str]:
    """Unicode safe bigram char n-grams (日本語対応)."""
    t = (text or "").strip().lower()
    if not t:
        return []
    if len(t) < n:
        return [t]
    return [t[i : i + n] for i in range(len(t) - n + 1)]


def _tf(tokens: Sequence[str]) -> dict:
    out: dict = {}
    for tok in tokens:
        out[tok] = out.get(tok, 0) + 1
    return out


def _cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    # iterate on smaller
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _tfidf(
    query_tokens: Sequence[str],
    doc_tokens_list: Sequence[Sequence[str]],
) -> Tuple[dict, List[dict]]:
    """Compute TF-IDF vectors for query + docs under the same IDF table."""
    n_docs = len(doc_tokens_list)
    df: dict = {}
    for toks in doc_tokens_list:
        for tok in set(toks):
            df[tok] = df.get(tok, 0) + 1
    # query token df defaults to 0 (unseen) — we still want a weight, so use smoothed IDF.
    def idf(tok: str) -> float:
        return math.log((1.0 + n_docs) / (1.0 + df.get(tok, 0))) + 1.0

    def vec(toks: Sequence[str]) -> dict:
        tf = _tf(toks)
        return {k: v * idf(k) for k, v in tf.items()}

    return vec(query_tokens), [vec(toks) for toks in doc_tokens_list]


# ── Storage ──────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS lifelong_memory (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    ts TEXT NOT NULL,
    tags TEXT NOT NULL,
    confidence REAL NOT NULL,
    importance REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lmm_subject ON lifelong_memory(subject_id);
CREATE INDEX IF NOT EXISTS idx_lmm_kind ON lifelong_memory(kind);
CREATE INDEX IF NOT EXISTS idx_lmm_ts ON lifelong_memory(ts);
"""


class MemoryStore:
    """SQLite-backed lifelong memory store.

    Optional encryption hook: pass ``encrypt`` / ``decrypt`` callables to
    wrap ``content`` on write / read. ``utils.crypto`` との連携は呼び出し側に委ねる。
    """

    def __init__(
        self,
        path: Path,
        *,
        encrypt=None,
        decrypt=None,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._encrypt = encrypt
        self._decrypt = decrypt
        self.half_life_days = float(half_life_days)

    # -- lifecycle -------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- write -----------------------------------------------------------
    def retain(self, event: MemoryEvent) -> MemoryEvent:
        """Persist an event. Idempotent on ``event.id``."""
        content = event.content
        if self._encrypt is not None:
            content = self._encrypt(content)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO lifelong_memory "
                "(id, subject_id, kind, content, ts, tags, confidence, importance) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.subject_id,
                    event.kind,
                    content,
                    event.ts,
                    "\t".join(event.tags),
                    float(event.confidence),
                    float(event.importance),
                ),
            )
            self._conn.commit()
        return event

    def forget(self, event_id: str) -> bool:
        """Kill-switch: delete a single event. Returns True if removed."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM lifelong_memory WHERE id = ?", (event_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def purge(self, subject_id: str) -> int:
        """Kill-switch: delete all events for a subject. Returns count."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM lifelong_memory WHERE subject_id = ?", (subject_id,)
            )
            self._conn.commit()
            return cur.rowcount

    # -- read ------------------------------------------------------------
    def _row_to_event(self, row: tuple) -> MemoryEvent:
        (eid, subject_id, kind, content, ts, tags_s, conf, imp) = row
        if self._decrypt is not None:
            content = self._decrypt(content)
        tags: Tuple[str, ...] = tuple(t for t in tags_s.split("\t") if t)
        return MemoryEvent(
            id=eid,
            subject_id=subject_id,
            kind=kind,
            content=content,
            ts=ts,
            tags=tags,
            confidence=float(conf),
            importance=float(imp),
        )

    def all_events(
        self,
        subject_id: Optional[str] = None,
        kind_filter: Optional[Iterable[str]] = None,
    ) -> List[MemoryEvent]:
        q = "SELECT id, subject_id, kind, content, ts, tags, confidence, importance FROM lifelong_memory"
        clauses: List[str] = []
        params: List = []
        if subject_id is not None:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        if kind_filter:
            kinds = tuple(kind_filter)
            clauses.append("kind IN (" + ",".join("?" for _ in kinds) + ")")
            params.extend(kinds)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY ts ASC"
        with self._lock:
            rows = list(self._conn.execute(q, params))
        return [self._row_to_event(r) for r in rows]

    def recall(
        self,
        query: str,
        k: int = 5,
        kind_filter: Optional[Iterable[str]] = None,
        subject_id: Optional[str] = None,
    ) -> List[MemoryEvent]:
        """TF-IDF (char-bigram) 近似 recall. importance/confidence で加重."""
        events = self.all_events(subject_id=subject_id, kind_filter=kind_filter)
        if not events or not query.strip():
            return []
        q_tokens = _char_ngrams(query)
        doc_tokens = [_char_ngrams(e.content) for e in events]
        q_vec, d_vecs = _tfidf(q_tokens, doc_tokens)
        scored: List[Tuple[float, MemoryEvent]] = []
        for ev, dv in zip(events, d_vecs):
            sim = _cosine(q_vec, dv)
            # weight by importance + confidence (modest boost, never zero out)
            score = sim * (0.5 + 0.5 * ev.importance) * (0.5 + 0.5 * ev.confidence)
            if score > 0.0:
                scored.append((score, ev))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [ev for _s, ev in scored[: max(0, k)]]

    # -- maintenance -----------------------------------------------------
    def importance_decay(self, now: Optional[datetime] = None) -> int:
        """Decay importance by half-life. Returns number of rows updated.

        new_importance = old_importance * 0.5 ** (age_days / half_life_days)
        """
        if self.half_life_days <= 0:
            return 0
        now_dt = now or datetime.now(timezone.utc)
        updated = 0
        with self._lock:
            rows = list(
                self._conn.execute(
                    "SELECT id, ts, importance FROM lifelong_memory"
                )
            )
            for (eid, ts, imp) in rows:
                try:
                    ev_dt = datetime.fromisoformat(ts)
                    if ev_dt.tzinfo is None:
                        ev_dt = ev_dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                age_days = max(0.0, (now_dt - ev_dt).total_seconds() / 86400.0)
                if age_days <= 0:
                    continue
                factor = 0.5 ** (age_days / self.half_life_days)
                new_imp = max(0.0, min(1.0, float(imp) * factor))
                if abs(new_imp - float(imp)) > 1e-9:
                    self._conn.execute(
                        "UPDATE lifelong_memory SET importance = ? WHERE id = ?",
                        (new_imp, eid),
                    )
                    updated += 1
            self._conn.commit()
        return updated


# ── Public helpers ───────────────────────────────────────────────────────
def with_importance(event: MemoryEvent, importance: float) -> MemoryEvent:
    """Immutable update helper."""
    return replace(event, importance=max(0.0, min(1.0, float(importance))))


__all__ = [
    "ALLOWED_KINDS",
    "DEFAULT_HALF_LIFE_DAYS",
    "MemoryEvent",
    "MemoryStore",
    "new_event",
    "with_importance",
]

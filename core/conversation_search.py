"""
Conversation history search (Sprint 5.7 UX).

Goal
----
Search across ~10 years of conversation turns (hundreds of thousands to
millions of utterances) by a combination of date range + keyword +
speaker, using only the Python standard library and SQLite FTS5.

Design
------
* SQLite FTS5 virtual table ``turns_fts`` with tokenizer
  ``unicode61 remove_diacritics 2`` for ASCII / Latin content.
* Japanese / CJK text does not tokenize well with ``unicode61``
  (characters become single-char tokens => low precision, recall
  collapses on multi-char query terms). To avoid a heavy dependency
  on MeCab/Sudachi we keep a *second* indexed column ``text_bigrams``
  that stores the original text decomposed into character 2-grams
  separated by ASCII spaces. CJK queries are rewritten to the same
  bigram form at search time so that FTS5 can match them.
* Score = BM25 (lower is better in FTS5) + a recency boost with a
  365-day half life.  The final score returned in :class:`SearchHit`
  is higher-is-better.
* Queries are never built by string interpolation; parameter binding
  is used everywhere, and FTS5 special characters are stripped /
  escaped so that hostile input like ``'; DROP TABLE turns; --``
  cannot break the engine.

This module is Python 3.9 compatible and all dataclasses are frozen.
"""
from __future__ import annotations

import logging
import math
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Public dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SearchQuery:
    """A user-level search request."""
    keywords: Tuple[str, ...] = ()
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    speaker: Optional[str] = None
    limit: int = 50
    # ``AND`` (default) or ``OR`` for combining multiple keywords.
    mode: str = "AND"


@dataclass(frozen=True)
class SearchHit:
    turn_id: str
    timestamp: datetime
    speaker: str
    text: str
    score: float
    context_before: Tuple[str, ...] = ()
    context_after: Tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Tokenisation helpers
# --------------------------------------------------------------------------- #

_CJK_RE = re.compile(
    "[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\uf900-\ufaff\u3400-\u4dbf]"
)
# FTS5 MATCH grammar characters we want to strip from user input to keep
# things safe and predictable. We keep the content but remove operators.
_FTS5_DANGEROUS = re.compile(r'["\(\)\*\:\^]')


def _is_cjk(ch: str) -> bool:
    return bool(_CJK_RE.match(ch))


def to_bigrams(text: str) -> str:
    """Return a space-separated bigram decomposition of ``text``.

    Only runs of CJK characters are bigrammed; ASCII / Latin content
    is lowercased and passed through so that ``unicode61`` tokenisation
    works normally on it. This gives us "free" recall for Japanese
    without hurting English search quality.
    """
    if not text:
        return ""
    out: List[str] = []
    buf: List[str] = []

    def flush_cjk() -> None:
        if not buf:
            return
        if len(buf) == 1:
            out.append(buf[0])
            out.append(" ")
        else:
            for i in range(len(buf) - 1):
                out.append(buf[i] + buf[i + 1])
                out.append(" ")
        buf.clear()

    for ch in text:
        if _is_cjk(ch):
            buf.append(ch)
        else:
            flush_cjk()
            if ch.isalnum() or ch == "_":
                out.append(ch.lower())
            else:
                out.append(" ")
    flush_cjk()
    return " ".join("".join(out).split())


def _sanitize_fts_term(term: str) -> str:
    """Strip FTS5 operator characters from a single user term."""
    cleaned = _FTS5_DANGEROUS.sub(" ", term)
    return " ".join(cleaned.split())


def _build_match_expression(keywords: Sequence[str], mode: str) -> str:
    """Translate a list of user keywords into an FTS5 MATCH expression.

    Each keyword is sanitised and, if it contains CJK, also expanded
    to its bigram form (matched against the ``text_bigrams`` column).
    """
    op = " OR " if mode.upper() == "OR" else " AND "
    fragments: List[str] = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        safe = _sanitize_fts_term(kw)
        if not safe:
            continue
        parts: List[str] = []
        has_cjk = any(_is_cjk(c) for c in safe)
        if has_cjk:
            bigrams = to_bigrams(safe).split()
            # Single-char CJK queries have no bigram; match by prefix
            # so e.g. "犬" matches bigram tokens starting with 犬.
            cjk_only = "".join(c for c in safe if _is_cjk(c))
            if len(cjk_only) == 1:
                parts.append(f'text_bigrams:{cjk_only}*')
            elif bigrams:
                # Bigrams are ANDed inside a single keyword so that e.g.
                # "ペット" = "ペッ" AND "ット" rather than OR.
                inner = " AND ".join(f'text_bigrams:"{b}"' for b in bigrams)
                parts.append("(" + inner + ")")
        # Also try the raw (unicode61) column — matches latin words and
        # occasionally picks up exact CJK substrings.
        tokenised = " ".join(t for t in safe.split() if t)
        if tokenised:
            parts.append(f'text:"{tokenised}"')
        if parts:
            fragments.append("(" + " OR ".join(parts) + ")")
    if not fragments:
        return ""
    return op.join(fragments)


# --------------------------------------------------------------------------- #
# Index
# --------------------------------------------------------------------------- #


_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS turns (
        id         TEXT PRIMARY KEY,
        ts         TEXT NOT NULL,
        speaker    TEXT NOT NULL,
        text       TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts)",
    "CREATE INDEX IF NOT EXISTS idx_turns_speaker ON turns(speaker)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
        id UNINDEXED,
        text,
        text_bigrams,
        tokenize = "unicode61 remove_diacritics 2"
    )
    """,
]


class ConversationSearchIndex:
    """SQLite-backed FTS5 index for conversation turns."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    # -- lifecycle ------------------------------------------------------- #
    def _init_schema(self) -> None:
        with self._conn:
            for stmt in _SCHEMA:
                self._conn.execute(stmt)

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    # -- writes ---------------------------------------------------------- #
    @staticmethod
    def _normalise_ts(ts: datetime) -> str:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).isoformat()

    def index_turn(
        self,
        turn_id: str,
        timestamp: datetime,
        speaker: str,
        text: str,
    ) -> None:
        self.index_bulk([(turn_id, timestamp, speaker, text)])

    def index_bulk(
        self,
        items: Iterable[Tuple[str, datetime, str, str]],
    ) -> int:
        rows: List[Tuple[str, str, str, str]] = []
        fts_rows: List[Tuple[str, str, str]] = []
        for turn_id, ts, speaker, text in items:
            turn_id = str(turn_id)
            ts_iso = self._normalise_ts(ts)
            speaker = str(speaker or "")
            text = str(text or "")
            rows.append((turn_id, ts_iso, speaker, text))
            fts_rows.append((turn_id, text, to_bigrams(text)))
        if not rows:
            return 0
        with self._conn:
            # Replace semantics keep re-indexing idempotent.
            self._conn.executemany(
                "INSERT OR REPLACE INTO turns(id, ts, speaker, text) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            # For FTS, delete then insert to emulate REPLACE cleanly.
            self._conn.executemany(
                "DELETE FROM turns_fts WHERE id = ?",
                [(r[0],) for r in fts_rows],
            )
            self._conn.executemany(
                "INSERT INTO turns_fts(id, text, text_bigrams) "
                "VALUES (?, ?, ?)",
                fts_rows,
            )
        return len(rows)

    def reindex_from_memory(self, memory_db_path: Path) -> int:
        """Read an existing conversation DB and index all its turns.

        The schema of the upstream database varies over ai-chan's
        history, so we probe a set of likely table / column names and
        pick the first that works. Unknown schemas raise ``ValueError``.
        """
        memory_db_path = Path(memory_db_path)
        if not memory_db_path.exists():
            raise FileNotFoundError(memory_db_path)
        src = sqlite3.connect(str(memory_db_path))
        try:
            tables = [
                r[0]
                for r in src.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            candidates = [
                ("turns", "id", "ts", "speaker", "text"),
                ("conversation", "id", "ts", "speaker", "text"),
                ("conversations", "id", "timestamp", "speaker", "text"),
                ("messages", "id", "created_at", "role", "content"),
            ]
            for tbl, id_c, ts_c, sp_c, txt_c in candidates:
                if tbl not in tables:
                    continue
                try:
                    cur = src.execute(
                        f"SELECT {id_c}, {ts_c}, {sp_c}, {txt_c} FROM {tbl}"
                    )
                except sqlite3.Error:
                    continue
                batch: List[Tuple[str, datetime, str, str]] = []
                count = 0
                for row in cur:
                    tid, ts_raw, sp, txt = row
                    ts = _parse_ts(ts_raw)
                    batch.append((str(tid), ts, str(sp or ""), str(txt or "")))
                    if len(batch) >= 500:
                        count += self.index_bulk(batch)
                        batch.clear()
                if batch:
                    count += self.index_bulk(batch)
                return count
            raise ValueError(
                f"no known conversation table in {memory_db_path}"
            )
        finally:
            src.close()

    # -- reads ----------------------------------------------------------- #
    def search(self, query: SearchQuery) -> Tuple[SearchHit, ...]:
        match_expr = _build_match_expression(query.keywords, query.mode)

        params: List[object] = []
        where: List[str] = []
        if match_expr:
            join = (
                "JOIN turns_fts f ON f.id = t.id "
                "AND turns_fts MATCH ?"
            )
            params.append(match_expr)
            select_score = "bm25(turns_fts) AS bm25_score"
        else:
            join = ""
            select_score = "0.0 AS bm25_score"

        if query.date_from is not None:
            where.append("t.ts >= ?")
            params.append(
                datetime.combine(query.date_from, datetime.min.time())
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        if query.date_to is not None:
            # Inclusive end: add one day.
            from datetime import timedelta
            end = datetime.combine(
                query.date_to, datetime.min.time()
            ).replace(tzinfo=timezone.utc) + timedelta(days=1)
            where.append("t.ts < ?")
            params.append(end.isoformat())
        if query.speaker is not None:
            where.append("t.speaker = ?")
            params.append(query.speaker)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        limit = max(1, min(int(query.limit), 10_000))

        sql = (
            "SELECT t.id, t.ts, t.speaker, t.text, "
            f"{select_score} "
            f"FROM turns t {join} {where_sql} "
            "ORDER BY bm25_score ASC, t.ts DESC "
            f"LIMIT {limit * 4}"  # over-fetch, re-rank with recency
        )
        try:
            rows = list(self._conn.execute(sql, params))
        except sqlite3.OperationalError as exc:
            logger.warning("search query failed: %s", exc)
            return ()

        now = datetime.now(timezone.utc)
        scored: List[Tuple[float, str, datetime, str, str]] = []
        for tid, ts_iso, sp, txt, bm in rows:
            ts = _parse_ts(ts_iso)
            age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
            recency = math.pow(0.5, age_days / 365.0)  # half-life 365d
            # BM25 is lower=better (often negative); invert then add boost.
            base = -float(bm) if match_expr else 0.0
            score = base + recency
            scored.append((score, str(tid), ts, str(sp), str(txt)))

        scored.sort(key=lambda r: (-r[0], -r[2].timestamp()))
        scored = scored[:limit]

        hits: List[SearchHit] = []
        for score, tid, ts, sp, txt in scored:
            before, after = self._fetch_context(tid, ts)
            hits.append(
                SearchHit(
                    turn_id=tid,
                    timestamp=ts,
                    speaker=sp,
                    text=txt,
                    score=float(score),
                    context_before=before,
                    context_after=after,
                )
            )
        return tuple(hits)

    def _fetch_context(
        self, turn_id: str, ts: datetime, window: int = 2
    ) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        ts_iso = self._normalise_ts(ts)
        before = [
            f"[{r[1]}] {r[2]}"
            for r in self._conn.execute(
                "SELECT id, speaker, text FROM turns "
                "WHERE ts < ? AND id != ? "
                "ORDER BY ts DESC LIMIT ?",
                (ts_iso, turn_id, window),
            )
        ][::-1]
        after = [
            f"[{r[1]}] {r[2]}"
            for r in self._conn.execute(
                "SELECT id, speaker, text FROM turns "
                "WHERE ts > ? AND id != ? "
                "ORDER BY ts ASC LIMIT ?",
                (ts_iso, turn_id, window),
            )
        ]
        return tuple(before), tuple(after)


# --------------------------------------------------------------------------- #
# Utilities
# --------------------------------------------------------------------------- #


def _parse_ts(raw: object) -> datetime:
    """Best-effort parse of timestamps coming from heterogeneous stores."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    s = str(raw)
    # Normalise common variants
    s2 = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            if fmt is None:
                return datetime.fromisoformat(s2)
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Last resort: epoch
    return datetime.fromtimestamp(0, tz=timezone.utc)

"""Voice ID fallback: drift detection and challenge-based re-authentication.

This module provides a loosely-coupled fallback layer around the existing
voice identification pipeline. It does *not* touch raw audio. Given a
``VoiceMatch`` (a claim produced by upstream voice ID), it decides whether
additional identity verification (a challenge) is required, based on:

1. Speaker confidence reported by the voice ID engine.
2. Textual "drift" between the current utterance and the historical
   linguistic profile of the claimed subject.

Design notes
------------
* No external dependencies (stdlib only, pure Python).
* Utterance text is NOT persisted. Only derived numeric features are held
  in an in-memory bounded ``deque`` per subject.
* All public state containers are either frozen dataclasses or internal
  to the detector/policy objects.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceMatch:
    """Immutable record of an upstream voice-ID claim.

    Attributes:
        claimed_subject_id: Subject identifier claimed by voice ID (e.g. "papa").
        confidence: Engine confidence in ``[0.0, 1.0]``.
        utterance: Transcribed utterance text. Not persisted by this module.
        drift_score: Optional pre-computed drift score in ``[0.0, 1.0]``.
            ``0.0`` means perfectly consistent with history, ``1.0`` fully
            inconsistent. Use :meth:`DriftDetector.score` to compute.
    """

    claimed_subject_id: str
    confidence: float
    utterance: str
    drift_score: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0.0, 1.0]")
        if not 0.0 <= self.drift_score <= 1.0:
            raise ValueError("drift_score must be in [0.0, 1.0]")
        if not self.claimed_subject_id:
            raise ValueError("claimed_subject_id must be non-empty")


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


# A very small closed-set of Japanese keigo (polite-form) tokens. The list
# is intentionally conservative; this module does not pretend to do full
# morphological analysis.
_KEIGO_TOKENS: Tuple[str, ...] = (
    "です",
    "ます",
    "ございます",
    "いたします",
    "でしょう",
    "ください",
    "お願い",
    "申し",
)


def _extract_features(utterance: str) -> Dict[str, float]:
    """Extract lightweight linguistic features from an utterance.

    Features are cheap and stable across short utterances:

    * ``length``: character length.
    * ``diversity``: type/token ratio on whitespace-separated tokens
      (falls back to unique-char ratio for whitespace-free text).
    * ``keigo_rate``: fraction of known polite-form tokens over length.
    * ``topic_set``: set of tokens (as a frozenset) used to compute
      Jaccard distance at scoring time. Stored as a value but counted
      as non-numeric.
    """
    text = utterance.strip()
    length = float(len(text))
    if length == 0.0:
        return {"length": 0.0, "diversity": 0.0, "keigo_rate": 0.0}

    tokens = text.split() if " " in text or "\t" in text else list(text)
    unique = len(set(tokens))
    diversity = unique / max(len(tokens), 1)

    keigo_hits = sum(1 for kw in _KEIGO_TOKENS if kw in text)
    keigo_rate = min(1.0, keigo_hits / max(length / 10.0, 1.0))

    return {
        "length": length,
        "diversity": diversity,
        "keigo_rate": keigo_rate,
    }


def _topic_tokens(utterance: str) -> frozenset:
    """Return a frozenset of topic-like tokens for Jaccard comparison."""
    text = utterance.strip()
    if not text:
        return frozenset()
    # Use character bigrams: robust to Japanese which lacks word boundaries.
    bigrams = {text[i : i + 2] for i in range(len(text) - 1)}
    return frozenset(bigrams)


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


class DriftDetector:
    """Maintain a short rolling history of linguistic features per subject.

    Only derived numeric features and character bigrams are stored; the raw
    utterance text is intentionally discarded after feature extraction.

    The detector is deliberately forgiving for "cold start" subjects: when
    there is no history for a given subject, :meth:`score` returns ``0.0``.
    """

    def __init__(self, history_size: int = 8) -> None:
        if history_size < 1:
            raise ValueError("history_size must be >= 1")
        self._history_size = history_size
        self._features: Dict[str, Deque[Dict[str, float]]] = {}
        self._topics: Dict[str, Deque[frozenset]] = {}

    def observe(self, subject_id: str, utterance: str) -> None:
        """Record features for a *verified* utterance from ``subject_id``.

        Call this only after the fallback policy (or a prior trust state)
        has accepted the utterance as genuine.
        """
        feats = _extract_features(utterance)
        topics = _topic_tokens(utterance)
        self._features.setdefault(
            subject_id, deque(maxlen=self._history_size)
        ).append(feats)
        self._topics.setdefault(
            subject_id, deque(maxlen=self._history_size)
        ).append(topics)

    def score(self, utterance: str, subject_id: str) -> float:
        """Return a drift score in ``[0.0, 1.0]``.

        ``0.0`` means the utterance looks perfectly consistent with the
        stored profile; ``1.0`` means maximally inconsistent. Cold-start
        subjects (no history) receive ``0.0``.
        """
        history = self._features.get(subject_id)
        if not history:
            return 0.0

        feats = _extract_features(utterance)
        topics = _topic_tokens(utterance)

        # Aggregate means over history.
        def _mean(key: str) -> float:
            return sum(h[key] for h in history) / len(history)

        mean_len = _mean("length")
        mean_div = _mean("diversity")
        mean_keigo = _mean("keigo_rate")

        # Normalized absolute deltas, each bounded in [0, 1].
        len_delta = 0.0
        if mean_len > 0:
            len_delta = min(1.0, abs(feats["length"] - mean_len) / mean_len)
        div_delta = min(1.0, abs(feats["diversity"] - mean_div))
        keigo_delta = min(1.0, abs(feats["keigo_rate"] - mean_keigo))

        # Topic Jaccard distance, averaged over history.
        topic_hist = self._topics.get(subject_id) or deque()
        if topic_hist and topics:
            distances: List[float] = []
            for past in topic_hist:
                union = topics | past
                if not union:
                    distances.append(0.0)
                    continue
                inter = topics & past
                distances.append(1.0 - (len(inter) / len(union)))
            topic_delta = sum(distances) / len(distances)
        else:
            topic_delta = 0.0

        # Weighted blend. Topic drift dominates when profile is rich.
        score = (
            0.20 * len_delta
            + 0.15 * div_delta
            + 0.15 * keigo_delta
            + 0.50 * topic_delta
        )
        return max(0.0, min(1.0, score))

    def reset(self, subject_id: Optional[str] = None) -> None:
        """Drop profile for one subject, or all if ``subject_id`` is None."""
        if subject_id is None:
            self._features.clear()
            self._topics.clear()
            return
        self._features.pop(subject_id, None)
        self._topics.pop(subject_id, None)


# ---------------------------------------------------------------------------
# Challenge policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChallengeSet:
    """Immutable bundle of challenges registered for a subject."""

    passphrases: Tuple[str, ...]
    questions: Tuple[Tuple[str, str], ...]  # (question, expected_answer)


# Internal, mutable per-subject state tracked by :class:`FallbackPolicy`.
@dataclass
class _SubjectState:
    failures: int = 0
    demoted: bool = False


class FallbackPolicy:
    """Decide when to issue an identity challenge and track outcomes.

    Thresholds (confidence < 0.7 OR drift > 0.5) are from the project
    security policy. Three cumulative failures within a subject demote the
    claim to ``guest``.
    """

    GUEST_SUBJECT_ID = "guest"
    MAX_FAILURES = 3
    CONFIDENCE_THRESHOLD = 0.7
    DRIFT_THRESHOLD = 0.5

    def __init__(self, challenges: Dict[str, ChallengeSet]) -> None:
        # Defensive copy: challenges themselves are frozen dataclasses.
        self._challenges: Dict[str, ChallengeSet] = dict(challenges)
        self._state: Dict[str, _SubjectState] = {}

    # --- policy ---------------------------------------------------------

    def should_challenge(self, match: VoiceMatch, drift: float) -> bool:
        """Return True when additional verification is required."""
        if not 0.0 <= drift <= 1.0:
            raise ValueError("drift must be in [0.0, 1.0]")
        if self._state.get(match.claimed_subject_id, _SubjectState()).demoted:
            return True
        return (
            match.confidence < self.CONFIDENCE_THRESHOLD
            or drift > self.DRIFT_THRESHOLD
        )

    # --- prompts --------------------------------------------------------

    def challenge_prompt(self, subject_id: str) -> str:
        """Return a human-facing challenge prompt for the subject.

        Rotates between the registered passphrase cue and the first
        pre-registered confirmation question. Raises ``KeyError`` for
        unknown subjects to force explicit registration.
        """
        cs = self._challenges[subject_id]
        state = self._state.setdefault(subject_id, _SubjectState())
        # Alternate based on current failure count for variety.
        if state.failures % 2 == 0 and cs.passphrases:
            return f"合言葉を教えてください（{subject_id} さん）。"
        if cs.questions:
            question, _ = cs.questions[state.failures % len(cs.questions)]
            return question
        if cs.passphrases:
            return f"合言葉を教えてください（{subject_id} さん）。"
        raise KeyError(f"no challenges registered for {subject_id}")

    # --- outcomes -------------------------------------------------------

    def verify_response(self, subject_id: str, response: str) -> bool:
        """Check a user's response against registered challenges.

        A correct response resets the failure counter and, if previously
        demoted, clears the demotion. Returns True on success.
        """
        cs = self._challenges.get(subject_id)
        if cs is None:
            return False
        trimmed = response.strip()
        if not trimmed:
            return self._record_failure(subject_id)

        ok = trimmed in cs.passphrases or any(
            trimmed == expected for _, expected in cs.questions
        )
        if ok:
            self._state[subject_id] = _SubjectState(failures=0, demoted=False)
            return True
        return self._record_failure(subject_id)

    def _record_failure(self, subject_id: str) -> bool:
        state = self._state.setdefault(subject_id, _SubjectState())
        state.failures += 1
        if state.failures >= self.MAX_FAILURES:
            state.demoted = True
        return False

    # --- introspection --------------------------------------------------

    def effective_subject(self, subject_id: str) -> str:
        """Return the effective subject ID, accounting for demotion."""
        state = self._state.get(subject_id)
        if state and state.demoted:
            return self.GUEST_SUBJECT_ID
        return subject_id

    def failure_count(self, subject_id: str) -> int:
        return self._state.get(subject_id, _SubjectState()).failures

    def is_demoted(self, subject_id: str) -> bool:
        return self._state.get(subject_id, _SubjectState()).demoted


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_challenges_from_yaml(path: str) -> Dict[str, ChallengeSet]:
    """Load challenges from a YAML file.

    Uses PyYAML if available, otherwise a tiny purpose-built parser that
    handles the constrained schema shipped in
    ``config/voice_auth_challenges.yaml``.
    """
    try:
        import yaml  # type: ignore

        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except ImportError:
        raw = _tiny_yaml_load(path)

    result: Dict[str, ChallengeSet] = {}
    subjects = raw.get("subjects", {}) if isinstance(raw, dict) else {}
    for subject_id, entry in subjects.items():
        passphrases = tuple(entry.get("passphrases", ()) or ())
        questions_raw = entry.get("questions", ()) or ()
        questions: List[Tuple[str, str]] = []
        for q in questions_raw:
            if isinstance(q, dict) and "q" in q and "a" in q:
                questions.append((str(q["q"]), str(q["a"])))
        result[subject_id] = ChallengeSet(
            passphrases=passphrases, questions=tuple(questions)
        )
    return result


def _tiny_yaml_load(path: str) -> Dict[str, object]:
    """Minimal YAML subset parser for the constrained challenge schema."""
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    root: Dict[str, object] = {}
    stack: List[Tuple[int, object]] = [(-1, root)]

    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    current_list_key: Optional[str] = None
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = _indent(line)
        stripped = line.strip()

        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if isinstance(parent, list):
                if ":" in value:
                    key, _, val = value.partition(":")
                    obj: Dict[str, object] = {key.strip(): val.strip()}
                    parent.append(obj)
                    stack.append((indent, obj))
                else:
                    parent.append(_strip_quotes(value))
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                # container: next deeper line decides list vs dict
                container: object = {}
                if isinstance(parent, dict):
                    parent[key] = container
                stack.append((indent, container))
                # We don't yet know; peek ahead by scanning ahead lines
                # is complex — instead, opportunistically convert to list
                # the first time we see a "- " at a deeper indent.
            else:
                if isinstance(parent, dict):
                    parent[key] = _strip_quotes(val)

    # Second pass: convert dicts that only ever received list-style
    # children. The above parser leaves empty {} placeholders; we need to
    # promote them to [] when their children were list entries. The
    # simpler approach: reparse with explicit list detection.
    return _reparse_with_lists(path)


def _strip_quotes(val: str) -> str:
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        return val[1:-1]
    return val


def _reparse_with_lists(path: str) -> Dict[str, object]:
    """Pass 2 parser: correctly distinguish list vs dict containers."""
    with open(path, "r", encoding="utf-8") as fh:
        lines = [
            ln.rstrip("\n")
            for ln in fh.readlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]

    # Peek helper to detect if the block under a key is a list.
    def _block_is_list(start_idx: int, base_indent: int) -> bool:
        for j in range(start_idx, len(lines)):
            ind = len(lines[j]) - len(lines[j].lstrip(" "))
            if ind <= base_indent:
                return False
            return lines[j].lstrip().startswith("- ")
        return False

    root: Dict[str, object] = {}
    # Stack of (indent, container)
    stack: List[Tuple[int, object]] = [(-1, root)]

    i = 0
    while i < len(lines):
        line = lines[i]
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if not isinstance(parent, list):
                i += 1
                continue
            if ":" in value:
                key, _, val = value.partition(":")
                key = key.strip()
                val = val.strip()
                obj: Dict[str, object] = {}
                parent.append(obj)
                if val:
                    obj[key] = _strip_quotes(val)
                    # continue parsing further dict keys at deeper indent
                    stack.append((indent, obj))
                else:
                    stack.append((indent, obj))
                    # need to consume following keyed lines as dict entries
            else:
                parent.append(_strip_quotes(value))
            i += 1
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                container: object
                if _block_is_list(i + 1, indent):
                    container = []
                else:
                    container = {}
                if isinstance(parent, dict):
                    parent[key] = container
                elif isinstance(parent, list):
                    # Should not occur with our schema.
                    pass
                stack.append((indent, container))
            else:
                if isinstance(parent, dict):
                    parent[key] = _strip_quotes(val)
        i += 1

    return root


__all__ = [
    "VoiceMatch",
    "DriftDetector",
    "FallbackPolicy",
    "ChallengeSet",
    "load_challenges_from_yaml",
]

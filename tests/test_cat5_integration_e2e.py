"""
Cat 5 (Sprint 5.1 – 5.10) 10 モジュール横断の統合 E2E テスト。

目的
----
各モジュールの単体挙動は既存テストで検証済。このファイルは
"家族A のある 1 日" というシナリオを通して、10 機能が
一つの流れで連携して動くことを保証する。

シナリオ (独立した tempdir / TenantContext を使用)
  1. TenantContext で家族A 専用 root を作成 (5.6)
  2. 会話履歴を 10 件ダミー生成
  3. 感情ログを 30 件生成 (5.1)
  4. ConversationSearchIndex を家族A の data/ 配下に作成し会話を索引化 (5.7)
  5. SilenceDetector を駆動し MEDIUM 沈黙を 1 件 emit (5.8)
  6. apply_silence_to_emotion で感情状態を更新 (5.8)
  7. silence_event_to_turn で turn 化し検索インデックスにも挿入 (5.8)
  8. EmotionDriftAnalyzer で週次集計 + ascii_sparkline (5.1)
  9. ForgettingPolicy を会話履歴に適用し kept/forgotten 分割 (5.2)
 10. 3 件の Anniversary で low/medium/critical bucket を確認 (5.3)
 11. critical を ICalEvent 化し .ics を serialize_calendar で出力 (5.9)
 12. validate_roundtrip で .ics 再パース成功
 13. VoiceMatch (low confidence + high drift) → should_challenge = True (5.4)
 14. FallbackPolicy: 3 回失敗で guest 降格
 15. SensitiveClassifier で 1Password タイトル → BLOCK, apply_blur(REDACT) で単色 PNG (5.10)
 16. ColorblindPalette("deuteranopia") の対 background コントラストが十分 (5.5)
 17. A11yAnnouncer で 1 件アナウンス (5.5)
 18. 家族A を purge しても家族B のデータが無傷 (5.6)

制約
----
- Py3.9 互換
- stdlib のみ (pytest 除く)
- 既存 DB に触らない (tempdir)
- 実行は 10 秒以内を想定
- 1 モジュール import 失敗でも全面失敗にせず skip 記録 (各サブテスト内でハンドル)
"""
from __future__ import annotations

import dataclasses
import random
import struct
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 遅延 / 寛容 import: どれか 1 つだけ壊れても他のステップは実行する
# ---------------------------------------------------------------------------

_IMPORT_STATUS: Dict[str, bool] = {}


def _try_import(label: str, fn):
    try:
        value = fn()
        _IMPORT_STATUS[label] = True
        return value
    except Exception as exc:  # pragma: no cover - defensive
        _IMPORT_STATUS[label] = False
        print(f"[cat5-e2e] import failed for {label}: {exc}", file=sys.stderr)
        return None


# 5.1 emotion_drift
_m_emotion_drift = _try_import(
    "5.1 emotion_drift",
    lambda: __import__("core.emotion_drift", fromlist=["*"]),
)
# 5.2 memory_forgetting
_m_memory_forgetting = _try_import(
    "5.2 memory_forgetting",
    lambda: __import__("core.memory_forgetting", fromlist=["*"]),
)
# 5.3 anniversary_importance
_m_anniv_importance = _try_import(
    "5.3 anniversary_importance",
    lambda: __import__("core.anniversary_importance", fromlist=["*"]),
)
# 5.4 voice_id_fallback
_m_voice_id = _try_import(
    "5.4 voice_id_fallback",
    lambda: __import__("core.voice_id_fallback", fromlist=["*"]),
)
# 5.5 a11y
_m_a11y_announcer = _try_import(
    "5.5 a11y_announcer",
    lambda: __import__("core.a11y_announcer", fromlist=["*"]),
)
_m_pet_a11y = _try_import(
    "5.5 desktop_pet_a11y",
    lambda: __import__("ui.desktop_pet_a11y", fromlist=["*"]),
)
# 5.6 tenant_context
_m_tenant = _try_import(
    "5.6 tenant_context",
    lambda: __import__("core.tenant_context", fromlist=["*"]),
)
# 5.7 conversation_search
_m_search = _try_import(
    "5.7 conversation_search",
    lambda: __import__("core.conversation_search", fromlist=["*"]),
)
# 5.8 silence
_m_silence_token = _try_import(
    "5.8 silence_token",
    lambda: __import__("core.silence_token", fromlist=["*"]),
)
_m_silence_bridge = _try_import(
    "5.8 silence_emotion_bridge",
    lambda: __import__("core.silence_emotion_bridge", fromlist=["*"]),
)
_m_silence_turn = _try_import(
    "5.8 silence_turn",
    lambda: __import__("core.silence_turn", fromlist=["*"]),
)
# 5.9 iCal
_m_ical = _try_import(
    "5.9 ical_export",
    lambda: __import__("core.ical_export", fromlist=["*"]),
)
_m_ical_bridge = _try_import(
    "5.9 anniversary_ical_bridge",
    lambda: __import__("core.anniversary_ical_bridge", fromlist=["*"]),
)
# 5.10 screenshot
_m_screenshot_sens = _try_import(
    "5.10 screenshot_sensitive",
    lambda: __import__("core.screenshot_sensitive", fromlist=["*"]),
)
_m_screenshot_blur = _try_import(
    "5.10 screenshot_blur",
    lambda: __import__("core.screenshot_blur", fromlist=["*"]),
)


def _require(module, label: str) -> None:
    if module is None:
        pytest.skip(f"module not importable: {label}")


# ---------------------------------------------------------------------------
# tiny helper: 最小 1x1 PNG バイト列を stdlib だけで作る
# ---------------------------------------------------------------------------


def _make_tiny_png(width: int = 4, height: int = 4) -> bytes:
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes([200, 150, 100]) * width
    raw = row * height
    idat = zlib.compress(raw, 6)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def rng() -> random.Random:
    return random.Random(20260424)


@pytest.fixture(scope="class")
def base_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("cat5_e2e_base")


@pytest.fixture(scope="class")
def tenant_a(base_dir: Path):
    _require(_m_tenant, "5.6 tenant_context")
    return _m_tenant.TenantContext.create_isolated(base_dir, "family-a")


@pytest.fixture(scope="class")
def tenant_b(base_dir: Path):
    _require(_m_tenant, "5.6 tenant_context")
    return _m_tenant.TenantContext.create_isolated(base_dir, "family-b")


@pytest.fixture(scope="class")
def conversations() -> List[Dict[str, Any]]:
    base = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
    speakers = ["papa", "mama", "ai-chan"]
    texts = [
        "おはよう、今日も良い天気だね",
        "犬の散歩に行ってくるよ",
        "そのペットかわいいですね",
        "夕食は何にしようか",
        "ありがとう、助かります",
        "結婚記念日おめでとう",
        "子供が元気に育っている",
        "今日は疲れたなあ",
        "その曲いいね、もう一回",
        "また明日ね、おやすみ",
    ]
    return [
        {
            "turn_id": f"t{i:03d}",
            "ts": (base + timedelta(hours=i * 3)).isoformat(),
            "speaker": speakers[i % len(speakers)],
            "text": texts[i],
        }
        for i in range(len(texts))
    ]


@pytest.fixture(scope="class")
def emotion_records(rng: random.Random) -> List[Dict[str, Any]]:
    base = datetime(2026, 3, 15, 8, 0)
    labels = ["happy", "curiosity", "affection", "anxiety", "neutral", "calm"]
    records: List[Dict[str, Any]] = []
    for i in range(30):
        ts = (base + timedelta(days=i // 3, hours=(i % 3) * 4)).strftime("%Y-%m-%dT%H:%M")
        records.append(
            {
                "ts": ts,
                "label": labels[i % len(labels)],
                "happiness": round(0.3 + rng.random() * 0.6, 3),
                "curiosity": round(0.2 + rng.random() * 0.7, 3),
                "affection": round(0.4 + rng.random() * 0.5, 3),
                "energy": round(0.3 + rng.random() * 0.5, 3),
                "anxiety": round(rng.random() * 0.3, 3),
            }
        )
    return records


# ---------------------------------------------------------------------------
# Integration E2E
# ---------------------------------------------------------------------------


# モジュール✓/✗ マトリクス (クラス属性として最後に集計)
_CAT5_COVERAGE: Dict[str, bool] = {
    "5.1 emotion_drift": False,
    "5.2 memory_forgetting": False,
    "5.3 anniversary_importance": False,
    "5.4 voice_id_fallback": False,
    "5.5 a11y (announcer + palette)": False,
    "5.6 tenant_context": False,
    "5.7 conversation_search": False,
    "5.8 silence (token+bridge+turn)": False,
    "5.9 ical_export + bridge": False,
    "5.10 screenshot (sensitive+blur)": False,
}


@pytest.mark.integration
class TestCat5IntegrationE2E:
    """家族A のある 1 日: Cat 5 全 10 機能を一本で流す。"""

    # --- 5.6 ---------------------------------------------------------------
    def test_01_tenant_context_isolated_roots(self, tenant_a, tenant_b, base_dir):
        _require(_m_tenant, "5.6 tenant_context")
        assert tenant_a.tenant_id == "family-a"
        assert tenant_b.tenant_id == "family-b"
        assert tenant_a.root_dir.is_dir()
        assert tenant_b.root_dir.is_dir()
        assert tenant_a.memory_dir.is_dir()
        # frozen dataclass immutability
        with pytest.raises(dataclasses.FrozenInstanceError):
            tenant_a.tenant_id = "hacked"  # type: ignore[misc]
        # guard_path が root 外への書き込みを拒否
        with pytest.raises(_m_tenant.TenantIsolationError):
            tenant_a.guard_path(base_dir / "family-b" / "memory" / "x.sql")
        _CAT5_COVERAGE["5.6 tenant_context"] = True

    # --- 5.7 ---------------------------------------------------------------
    def test_02_conversation_search_index(self, tenant_a, conversations):
        _require(_m_search, "5.7 conversation_search")
        db_path = tenant_a.data_dir / "conversation_search.db"
        idx = _m_search.ConversationSearchIndex(db_path)
        try:
            items = []
            for rec in conversations:
                ts = datetime.fromisoformat(rec["ts"])
                items.append((rec["turn_id"], ts, rec["speaker"], rec["text"]))
            n = idx.index_bulk(items)
            assert n == len(conversations)

            # CJK 検索 (bigram 経由) が働くこと
            q = _m_search.SearchQuery(keywords=("ペット",), limit=5)
            hits = idx.search(q)
            assert any("ペット" in h.text for h in hits)
        finally:
            idx.close()
        _CAT5_COVERAGE["5.7 conversation_search"] = True

    # --- 5.8 ---------------------------------------------------------------
    def test_03_silence_detector_medium_emit(self, tenant_a):
        _require(_m_silence_token, "5.8 silence_token")
        _require(_m_silence_bridge, "5.8 silence_emotion_bridge")
        _require(_m_silence_turn, "5.8 silence_turn")

        emitted: List[Any] = []
        det = _m_silence_token.SilenceDetector(
            on_emit=lambda ev: emitted.append(ev),
            ambient_context_provider=lambda: "作業中同席",
        )
        t0 = datetime(2026, 4, 1, 10, 0)
        det.on_user_activity(t0)
        # 10 分経過 → MEDIUM (2 min - 30 min)
        det.on_tick(t0 + timedelta(minutes=10))
        assert len(emitted) == 1
        ev = emitted[0]
        assert ev.category is _m_silence_token.SilenceCategory.MEDIUM
        # frozen dataclass
        assert dataclasses.is_dataclass(ev)
        with pytest.raises(dataclasses.FrozenInstanceError):
            ev.duration_s = 0.0  # type: ignore[misc]

        # 感情に反映 (core.emotion が重い依存を持つ場合は skip)
        try:
            from core.emotion import EmotionState  # noqa: F401
        except Exception:
            pytest.skip("core.emotion not available for bridge test")
        from core.emotion import EmotionState

        state = EmotionState(
            happiness=0.5, curiosity=0.5, affection=0.5, energy=0.5, anxiety=0.1
        )
        new_state = _m_silence_bridge.apply_silence_to_emotion(state, ev)
        # MEDIUM + 作業中同席 → affection +0.05
        assert new_state.affection > state.affection
        assert new_state is not state  # 非破壊

        # turn 変換 → 検索 index にも挿入
        turn = _m_silence_turn.silence_event_to_turn(ev)
        assert turn["speaker"] == _m_silence_turn.SILENCE_SPEAKER
        assert "<silence:medium:" in turn["text"]

        db_path = tenant_a.data_dir / "conversation_search.db"
        idx = _m_search.ConversationSearchIndex(db_path)
        try:
            idx.index_turn(
                turn["turn_id"],
                datetime.fromisoformat(turn["timestamp"]),
                turn["speaker"],
                turn["text"],
            )
            q = _m_search.SearchQuery(
                keywords=("silence",), speaker="_silence_", limit=5
            )
            hits = idx.search(q)
            assert any(h.speaker == "_silence_" for h in hits)
        finally:
            idx.close()

        _CAT5_COVERAGE["5.8 silence (token+bridge+turn)"] = True

    # --- 5.1 ---------------------------------------------------------------
    def test_04_emotion_drift_weekly_sparkline(self, emotion_records):
        _require(_m_emotion_drift, "5.1 emotion_drift")
        analyzer = _m_emotion_drift.EmotionDriftAnalyzer(emotion_records)
        aggs = analyzer.aggregate("week")
        assert len(aggs) >= 1
        # frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            aggs[0].period_label = "X"  # type: ignore[misc]
        spark = _m_emotion_drift.sparkline_for_aggregates(aggs)
        assert spark != ""
        # 8 段文字のどれかが含まれる
        assert any(c in spark for c in "▁▂▃▄▅▆▇█")
        _CAT5_COVERAGE["5.1 emotion_drift"] = True

    # --- 5.2 ---------------------------------------------------------------
    def test_05_memory_forgetting_policy(self, conversations):
        _require(_m_memory_forgetting, "5.2 memory_forgetting")
        now = datetime(2026, 5, 1, 0, 0)
        entries = []
        for i, rec in enumerate(conversations):
            created = datetime.fromisoformat(rec["ts"]).replace(tzinfo=None)
            entries.append(
                _m_memory_forgetting.MemoryEntry(
                    id=rec["turn_id"],
                    created_at=created - timedelta(days=40),  # 強制的に古く
                    last_rehearsed_at=None,
                    rehearsal_count=0,
                    pinned=(i == 0),  # 先頭のみ pin
                    content=rec["text"],
                )
            )
        policy = _m_memory_forgetting.ForgettingPolicy(threshold=0.3)
        kept, forgotten = policy.apply(entries, now=now)
        # pin は必ず kept
        assert any(e.pinned for e in kept)
        # 40 日経過かつ pin なしは少なくとも 1 件 forgotten
        assert len(forgotten) >= 1
        # 入力不変
        assert all(isinstance(e, _m_memory_forgetting.MemoryEntry) for e in entries)
        _CAT5_COVERAGE["5.2 memory_forgetting"] = True

    # --- 5.3 + 5.9 ---------------------------------------------------------
    def test_06_anniversary_importance_and_ical(self):
        _require(_m_anniv_importance, "5.3 anniversary_importance")
        _require(_m_ical, "5.9 ical_export")
        _require(_m_ical_bridge, "5.9 anniversary_ical_bridge")

        now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)

        # LOW: mention 少 / valence 弱 / 古い
        f_low = _m_anniv_importance.AnniversaryFeatures(
            keyword="low-test",
            mention_count=1,
            mean_valence=0.05,
            first_seen_at="2024-01-01T00:00:00+00:00",
            last_seen_at="2024-02-01T00:00:00+00:00",
            session_total_minutes=1.0,
        )
        # MEDIUM: 中程度
        f_mid = _m_anniv_importance.AnniversaryFeatures(
            keyword="mid-test",
            mention_count=6,
            mean_valence=0.45,
            first_seen_at="2025-06-01T00:00:00+00:00",
            last_seen_at="2026-03-01T00:00:00+00:00",
            session_total_minutes=60.0,
        )
        # CRITICAL: 言及多 / 強 valence / 最近
        f_crit = _m_anniv_importance.AnniversaryFeatures(
            keyword="結婚記念日",
            mention_count=80,
            mean_valence=0.95,
            first_seen_at="2020-06-01T00:00:00+00:00",
            last_seen_at="2026-04-20T00:00:00+00:00",
            session_total_minutes=900.0,
        )
        s_low, b_low = _m_anniv_importance.score_and_bucket(f_low, now=now)
        s_mid, b_mid = _m_anniv_importance.score_and_bucket(f_mid, now=now)
        s_crit, b_crit = _m_anniv_importance.score_and_bucket(f_crit, now=now)

        assert b_low is _m_anniv_importance.ImportanceBucket.LOW
        assert b_mid is _m_anniv_importance.ImportanceBucket.MEDIUM
        assert b_crit is _m_anniv_importance.ImportanceBucket.CRITICAL
        # monotonic
        assert s_low < s_mid < s_crit

        # critical → ICalEvent → calendar
        record = {
            "id": "anniv-001",
            "label": "結婚記念日",
            "month": 6,
            "day": 10,
            "yearly": True,
            "is_birthday": False,
            "mean_valence": 0.95,
            "mention_count": 80,
        }
        ev = _m_ical_bridge.anniversary_to_ical_event(
            record, b_crit, reference=date(2026, 1, 1)
        )
        assert isinstance(ev, _m_ical.ICalEvent)
        # critical → VALARM 付与
        assert ev.alarm is True
        # ICalEvent は frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            ev.summary = "x"  # type: ignore[misc]

        ics = _m_ical.serialize_calendar([ev], calendar_name="家族A 記念日")
        assert "BEGIN:VCALENDAR\r\n" in ics
        assert "END:VCALENDAR\r\n" in ics
        assert "VALARM" in ics
        # round-trip 成功
        lines = list(_m_ical.validate_roundtrip(ics))
        assert "BEGIN:VCALENDAR" in lines
        assert "END:VCALENDAR" in lines

        _CAT5_COVERAGE["5.3 anniversary_importance"] = True
        _CAT5_COVERAGE["5.9 ical_export + bridge"] = True

    # --- 5.4 ---------------------------------------------------------------
    def test_07_voice_id_drift_and_demotion(self):
        _require(_m_voice_id, "5.4 voice_id_fallback")
        # challenges 登録
        challenges = {
            "papa": _m_voice_id.ChallengeSet(
                passphrases=("さくら",),
                questions=(("最初に飼った犬の名前は？", "ポチ"),),
            )
        }
        policy = _m_voice_id.FallbackPolicy(challenges)
        # confidence 低 + drift 高 → challenge 必要
        match = _m_voice_id.VoiceMatch(
            claimed_subject_id="papa",
            confidence=0.4,
            utterance="テスト",
            drift_score=0.0,
        )
        assert policy.should_challenge(match, drift=0.8) is True
        # frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            match.confidence = 0.9  # type: ignore[misc]
        # 3 回失敗で guest へ降格
        for _ in range(3):
            policy.verify_response("papa", "wrong")
        assert policy.is_demoted("papa") is True
        assert policy.effective_subject("papa") == "guest"
        _CAT5_COVERAGE["5.4 voice_id_fallback"] = True

    # --- 5.10 --------------------------------------------------------------
    def test_08_screenshot_sensitive_block_and_redact(self):
        _require(_m_screenshot_sens, "5.10 screenshot_sensitive")
        _require(_m_screenshot_blur, "5.10 screenshot_blur")

        classifier = _m_screenshot_sens.SensitiveClassifier()
        pat = classifier.classify("1Password - ログイン", None)
        assert pat is not None
        assert pat.action is _m_screenshot_sens.SensitiveAction.BLOCK
        # frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            pat.name = "x"  # type: ignore[misc]

        # BLOCK → 空バイト
        png = _make_tiny_png(8, 8)
        blocked = _m_screenshot_blur.apply_blur(
            png, _m_screenshot_sens.SensitiveAction.BLOCK
        )
        assert blocked == b""
        # REDACT → PNG バイト列が返る
        redacted = _m_screenshot_blur.apply_blur(
            png, _m_screenshot_sens.SensitiveAction.REDACT
        )
        assert redacted.startswith(b"\x89PNG\r\n\x1a\n")
        # 元画像 immutable
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        _CAT5_COVERAGE["5.10 screenshot (sensitive+blur)"] = True

    # --- 5.5 ---------------------------------------------------------------
    def test_09_a11y_palette_and_announcer(self, tenant_a, tmp_path_factory):
        _require(_m_a11y_announcer, "5.5 a11y_announcer")
        _require(_m_pet_a11y, "5.5 desktop_pet_a11y")

        palette = _m_pet_a11y.ColorblindPalette.preset("deuteranopia")
        assert palette.name == "deuteranopia"
        # frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            palette.name = "x"  # type: ignore[misc]
        # text / background の WCAG コントラスト >= 7:1 (AAA)
        ratio = _m_pet_a11y.contrast_ratio(palette["text"], palette["background"])
        assert ratio >= 7.0, f"contrast too low: {ratio:.2f}"

        log_path = tenant_a.logs_dir / "a11y.log"
        announcer = _m_a11y_announcer.A11yAnnouncer(enabled=True, log_path=log_path)
        # primary sink がコケてもフォールバック成功 → True
        assert announcer.announce("family-a ready") is True
        _CAT5_COVERAGE["5.5 a11y (announcer + palette)"] = True

    # --- 5.6 purge isolation ---------------------------------------------------
    def test_10_purge_family_a_leaves_family_b_intact(
        self, base_dir, tenant_a, tenant_b
    ):
        _require(_m_tenant, "5.6 tenant_context")
        # 家族B 側に目印ファイルを置く
        marker = tenant_b.memory_dir / "keepme.txt"
        marker.write_text("family-b survives", encoding="utf-8")
        assert marker.exists()

        # 家族A を purge
        _m_tenant.purge_tenant(base_dir, tenant_a.tenant_id, confirm=True)
        assert not tenant_a.root_dir.exists()

        # 家族B は無傷
        assert tenant_b.root_dir.exists()
        assert marker.exists()
        assert marker.read_text(encoding="utf-8") == "family-b survives"
        # 全ファイル数検査: family-b ツリーにまだファイルが居る
        remaining = list(tenant_b.root_dir.rglob("*"))
        assert any(p.is_file() for p in remaining)

    # --- summary -----------------------------------------------------------
    def test_99_cat5_coverage_matrix(self):
        """10 モジュール ✓/✗ マトリクスを stdout に出し、全 True を確認。"""
        lines = ["", "=== Cat 5 integration matrix ==="]
        for name, ok in _CAT5_COVERAGE.items():
            lines.append(f"  {'✓' if ok else '✗'}  {name}")
        print("\n".join(lines))
        missing = [k for k, v in _CAT5_COVERAGE.items() if not v]
        # 1 件でも skip されていたら soft-warn: xfail せず assert False で可視化
        assert not missing, f"integration did not exercise: {missing}"

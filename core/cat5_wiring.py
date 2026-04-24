"""
Cat 5 (Sprint 5.x) モジュールをメインループに繋ぐための薄いファサード層。

本モジュールは全て **lazy import**。AiChan の起動パスを重くしないため、
各コマンドが実行される時点で初めて heavy な依存 (tkinter / sqlite FTS 等) を読み込む。

import 失敗時は warnings.warn で警告を出し、None / 空文字を返してメイン機能は続行する。

Python 3.9 互換 / stdlib + 既存 ai-chan core のみ。
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# /search <keyword>  — conversation_search
# ─────────────────────────────────────────────────────────────
def handle_search_command(ai_chan: object, keyword: str, limit: int = 10) -> str:
    """/search コマンドのハンドラ。検索結果を整形したテキストで返す。"""
    if not keyword or not keyword.strip():
        return "使い方: /search <キーワード>"
    try:
        from core.conversation_search import (
            ConversationSearchIndex,
            SearchQuery,
        )
    except Exception as exc:
        warnings.warn(f"conversation_search import failed: {exc}")
        return "会話検索モジュールを読み込めませんでした。"

    base_dir = Path(getattr(ai_chan, "base_dir", "."))
    # settings から db_path を解決 (未設定なら既定値)
    settings = getattr(ai_chan, "settings", None) or {}
    cs_cfg = settings.get("conversation_search", {}) if isinstance(settings, dict) else {}
    rel = cs_cfg.get("db_path", "memory/conversation_search.db")
    db_path = base_dir / rel
    try:
        index = ConversationSearchIndex(db_path)
    except Exception as exc:
        warnings.warn(f"conversation_search index open failed: {exc}")
        return f"検索インデックスを開けませんでした: {exc}"

    try:
        tokens = tuple(t for t in keyword.strip().split() if t)
        query = SearchQuery(keywords=tokens, limit=limit)
        hits = list(index.search(query)) if hasattr(index, "search") else []
    except Exception as exc:
        logger.warning("search failed: %s", exc)
        return f"検索に失敗しました: {exc}"
    finally:
        try:
            index.close()
        except Exception:
            pass

    if not hits:
        return f"「{keyword}」に一致する会話は見つかりませんでした。"

    lines = [f"「{keyword}」の検索結果 ({len(hits)} 件):"]
    for i, h in enumerate(hits, 1):
        ts = getattr(h, "timestamp", "")
        speaker = getattr(h, "speaker", "")
        text = getattr(h, "text", "")
        snippet = text[:80] + ("…" if len(text) > 80 else "")
        lines.append(f"  {i}. [{ts}] {speaker}: {snippet}")
    return "\n".join(lines)


def open_search_window(ai_chan: object) -> str:
    """/search-ui コマンド: tkinter SearchWindow を開く。"""
    try:
        from core.conversation_search import ConversationSearchIndex
        from ui.search_window import SearchWindow
    except Exception as exc:
        warnings.warn(f"search_window import failed: {exc}")
        return "検索ウィンドウを開けませんでした (依存欠落)。"

    base_dir = Path(getattr(ai_chan, "base_dir", "."))
    settings = getattr(ai_chan, "settings", None) or {}
    cs_cfg = settings.get("conversation_search", {}) if isinstance(settings, dict) else {}
    rel = cs_cfg.get("db_path", "memory/conversation_search.db")
    db_path = base_dir / rel
    try:
        import tkinter as tk  # noqa: WPS433
    except Exception as exc:
        return f"tkinter が使えません: {exc}"
    try:
        index = ConversationSearchIndex(db_path)
        root = tk.Tk()
        root.withdraw()
        SearchWindow(root, index)
        root.mainloop()
    except Exception as exc:
        logger.warning("search window failed: %s", exc)
        return f"検索ウィンドウ起動に失敗しました: {exc}"
    return "検索ウィンドウを閉じました。"


# ─────────────────────────────────────────────────────────────
# /drift week|month|year — emotion drift
# ─────────────────────────────────────────────────────────────
def handle_drift_command(ai_chan: object, window: str = "week") -> str:
    """/drift コマンド: ASCII sparkline + 集計サマリを返す。"""
    try:
        from core.emotion_drift import EmotionDriftAnalyzer
        from ui.emotion_drift_window import render_text_summary
    except Exception as exc:
        warnings.warn(f"emotion_drift import failed: {exc}")
        return "感情ドリフトモジュールを読み込めませんでした。"

    if window not in ("week", "month", "year"):
        return "使い方: /drift week|month|year"

    history = getattr(ai_chan, "emotion_history", None)
    if history is None:
        return "感情履歴が利用できません。"
    try:
        analyzer = EmotionDriftAnalyzer(history=history)
        aggregates = analyzer.aggregate(window)  # type: ignore[arg-type]
        return render_text_summary(aggregates)
    except Exception as exc:
        logger.warning("drift aggregation failed: %s", exc)
        return f"感情ドリフト集計に失敗しました: {exc}"


# ─────────────────────────────────────────────────────────────
# /anniv-ical — anniversary iCal export
# ─────────────────────────────────────────────────────────────
def handle_anniv_ical_command(ai_chan: object) -> str:
    """記念日を iCal (.ics) にエクスポートし、保存パスを返す。"""
    try:
        from core.anniversary_importance import ImportanceBucket, bucket_of
        from core.anniversary_ical_bridge import anniversary_to_ical_event
        from core.ical_export import serialize_calendar
    except Exception as exc:
        warnings.warn(f"anniv ical import failed: {exc}")
        return "記念日エクスポートモジュールを読み込めませんでした。"

    mgr = getattr(ai_chan, "anniversary", None) or getattr(
        ai_chan, "anniversary_manager", None
    )
    if mgr is None or not hasattr(mgr, "list_all"):
        return "記念日マネージャが利用できません。"

    try:
        records = mgr.list_all()
    except Exception as exc:
        return f"記念日の読み込みに失敗しました: {exc}"

    events = []
    for rec in records:
        try:
            meta = rec.get("auto_importance") if isinstance(rec, dict) else None
            score = float(meta.get("score", 0.0)) if isinstance(meta, dict) else 0.0
            bucket = bucket_of(score)
            events.append(anniversary_to_ical_event(rec, bucket))
        except Exception as exc:
            logger.debug("skip anniversary %r: %s", rec, exc)

    base_dir = Path(getattr(ai_chan, "base_dir", "."))
    out_dir = base_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "anniversaries.ics"
    try:
        text = serialize_calendar(events)
        out_path.write_text(text, encoding="utf-8")
    except Exception as exc:
        return f"iCal 書き出しに失敗しました: {exc}"

    return f"記念日を iCal にエクスポートしました ({len(events)} 件): {out_path}"


# ─────────────────────────────────────────────────────────────
# /silence-status — silence detector 状態
# ─────────────────────────────────────────────────────────────
_SILENCE_DETECTOR = None  # モジュールレベルで 1 個だけ持つ


def get_or_create_silence_detector():
    """アプリ全体で 1 つの SilenceDetector を共有する (遅延生成)。"""
    global _SILENCE_DETECTOR
    if _SILENCE_DETECTOR is not None:
        return _SILENCE_DETECTOR
    try:
        from core.silence_token import SilenceDetector
    except Exception as exc:
        warnings.warn(f"silence_token import failed: {exc}")
        return None
    _SILENCE_DETECTOR = SilenceDetector()
    return _SILENCE_DETECTOR


def handle_silence_status_command(ai_chan: object) -> str:
    """/silence-status: detector の現在状態をデバッグ表示。"""
    det = get_or_create_silence_detector()
    if det is None:
        return "沈黙検出器を初期化できませんでした。"
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    try:
        events = det.on_tick(now)
    except Exception as exc:
        return f"silence tick に失敗しました: {exc}"
    pending = det.drain() if hasattr(det, "drain") else []
    last_activity = getattr(det, "_last_activity", None)
    sil_start = getattr(det, "_silence_start", None)
    last_cat = getattr(det, "_last_emitted_category", None)
    lines = [
        "=== Silence Detector Status ===",
        f"  last_activity   : {last_activity}",
        f"  silence_start   : {sil_start}",
        f"  last_category   : {last_cat}",
        f"  tick_events     : {len(events)}",
        f"  pending_events  : {len(pending)}",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# /a11y on|off|palette <name>
# ─────────────────────────────────────────────────────────────
_A11Y_ANNOUNCER = None


def handle_a11y_command(ai_chan: object, args: str) -> str:
    """/a11y コマンド: on/off 切替、palette 切替。"""
    global _A11Y_ANNOUNCER
    parts = args.strip().split()
    if not parts:
        return "使い方: /a11y on|off|palette <name>"
    sub = parts[0].lower()

    if sub in ("on", "off"):
        try:
            from core.a11y_announcer import A11yAnnouncer
        except Exception as exc:
            warnings.warn(f"a11y_announcer import failed: {exc}")
            return "a11y モジュールを読み込めませんでした。"
        enabled = sub == "on"
        _A11Y_ANNOUNCER = A11yAnnouncer(enabled=enabled)
        return f"アクセシビリティ読み上げ: {'ON' if enabled else 'OFF'}"

    if sub == "palette":
        if len(parts) < 2:
            return "使い方: /a11y palette <name>"
        name = parts[1]
        # desktop_pet_a11y があれば palette を切替、なければ設定に保存するだけ
        try:
            from ui.desktop_pet_a11y import set_palette  # type: ignore
            set_palette(name)
            return f"パレットを切り替えました: {name}"
        except Exception:
            logger.info("palette switch (no-op fallback): %s", name)
            return f"パレット {name} を記録しました (適用は再起動後)。"

    return "使い方: /a11y on|off|palette <name>"


# ─────────────────────────────────────────────────────────────
# /screenshot-test — screenshot_sensitive + blur の動作確認
# ─────────────────────────────────────────────────────────────
def handle_screenshot_test_command(ai_chan: object, args: str = "") -> str:
    """指定ウィンドウタイトルに対する機密分類 + blur 判定を返す。"""
    try:
        from core.screenshot_sensitive import SensitiveAction, SensitiveClassifier
    except Exception as exc:
        warnings.warn(f"screenshot_sensitive import failed: {exc}")
        return "screenshot_sensitive モジュールを読み込めませんでした。"
    title = args.strip() or "1Password"
    try:
        classifier = SensitiveClassifier()
        hit = classifier.classify(title, None)
    except Exception as exc:
        return f"分類に失敗しました: {exc}"
    if hit is None:
        return f"『{title}』は機密画面として検出されませんでした。"
    return (
        f"『{title}』は機密画面として検出されました: "
        f"pattern={hit.name}, action={hit.action.value}"
    )


# ─────────────────────────────────────────────────────────────
# --tenant <id> 起動時フック
# ─────────────────────────────────────────────────────────────
def resolve_tenant_base_dir(base_dir: Path, tenant_id: Optional[str]) -> Path:
    """--tenant が指定されていれば TenantContext で root を切り替える。

    失敗時は元の base_dir を返し、warnings.warn で通知する。
    """
    if not tenant_id:
        return base_dir
    try:
        from core.tenant_context import TenantContext
    except Exception as exc:
        warnings.warn(f"tenant_context import failed: {exc}")
        return base_dir
    try:
        tenants_root = base_dir / "tenants"
        tenants_root.mkdir(parents=True, exist_ok=True)
        ctx = TenantContext.create_isolated(tenants_root, tenant_id)
        logger.info("tenant isolated: id=%s root=%s", tenant_id, ctx.root_dir)
        return ctx.root_dir
    except Exception as exc:
        warnings.warn(f"tenant isolation failed ({tenant_id}): {exc}")
        return base_dir


# ─────────────────────────────────────────────────────────────
# Anniversary 作成/読み込み時の自動 importance 付与
# ─────────────────────────────────────────────────────────────
def annotate_anniversary_importance(record: dict) -> dict:
    """record に auto_importance (score + bucket) を注入した新 dict を返す。

    既に auto_importance があればそのまま返す (再計算スキップ)。
    import 失敗や計算失敗時は元の record を返す。
    """
    if not isinstance(record, dict):
        return record
    if "auto_importance" in record and isinstance(record["auto_importance"], dict):
        return record
    try:
        from core.anniversary_importance import (
            AnniversaryFeatures,
            score_and_bucket,
        )
    except Exception as exc:
        warnings.warn(f"anniversary_importance import failed: {exc}")
        return record
    try:
        feats = AnniversaryFeatures(
            keyword=str(record.get("label", "")),
            mention_count=int(record.get("mention_count", 0)),
            mean_valence=float(record.get("mean_valence", 0.0)),
            first_seen_at=str(record.get("first_seen_at", "")),
            last_seen_at=str(record.get("last_seen_at", "")),
            session_total_minutes=float(record.get("session_total_minutes", 0.0)),
        )
        score, bucket = score_and_bucket(feats)
    except Exception as exc:
        logger.debug("importance estimation skipped: %s", exc)
        return record
    new_rec = dict(record)
    new_rec["auto_importance"] = {"score": score, "bucket": bucket.value}
    return new_rec


__all__ = [
    "handle_search_command",
    "open_search_window",
    "handle_drift_command",
    "handle_anniv_ical_command",
    "handle_silence_status_command",
    "handle_a11y_command",
    "handle_screenshot_test_command",
    "resolve_tenant_base_dir",
    "annotate_anniversary_importance",
    "get_or_create_silence_detector",
]

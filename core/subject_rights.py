"""
subject_rights — GDPR 17 条（忘れられる権利）/ 20 条（データポータビリティ）相当。

B8 fix (2026-04-21): 家族メンバー / ユーザーが離脱するとき、その人物に関連する
全データを一括削除 (purge) または書き出し (export) できるようにする。

subject_id の設計:
    ai-chan v0 は単一ユーザー想定のため、subject_id は実質「self」1 件のみ。
    将来 YAMATO/KAGUYA で家族メンバーごとに tenant 分岐する際は
    subject_id に family member UUID を入れる。

対象データストア:
    - memory DB (core/memory.py)        : subject_id 列または tags 一致で削除
    - diary JSON (core/diary.py)        : ファイル全削除
    - emotion_history (core/emotion_history.py) : ファイル全削除
    - anniversary (core/anniversary.py) : subject 一致行削除
    - audit_log                          : ハッシュチェーン保全のため削除せず、
                                          監査イベントとして「purge 実施」を追記のみ
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


SELF_SUBJECT_ID = "self"


class SubjectRightsManager:
    """各データストアへの purge / export を調整する。"""

    def __init__(
        self,
        base_dir: Path,
        memory: Any = None,
        diary: Any = None,
        emotion_history: Any = None,
        anniversary: Any = None,
        audit_log: Any = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.memory = memory
        self.diary = diary
        self.emotion_history = emotion_history
        self.anniversary = anniversary
        self.audit_log = audit_log

    # ─── export ──────────────────────────────────────────────

    def export_subject(self, subject_id: str = SELF_SUBJECT_ID) -> dict:
        """指定 subject の全記録を dict として返す（GDPR 20 条）。

        戻り値: {
            "subject_id": str,
            "exported_at": ISO8601,
            "memories": [...],
            "diary": [...],
            "emotion_history": [...],
            "anniversaries": [...],
        }
        """
        payload: dict = {
            "subject_id": subject_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "memories": [],
            "diary": [],
            "emotion_history": [],
            "anniversaries": [],
        }

        # Memory: 現状 subject_id 列がないので全件エクスポート
        if self.memory is not None:
            try:
                recent = self.memory.get_recent(limit=100000, clearance="secret")
                payload["memories"] = [
                    {
                        "id": getattr(m, "id", None),
                        "content": getattr(m, "content", ""),
                        "created_at": getattr(m, "created_at", ""),
                        "importance": getattr(m, "importance", 0.0),
                        "tags": list(getattr(m, "tags", []) or []),
                        "security_level": getattr(m, "security_level", "public"),
                    }
                    for m in recent
                ]
            except Exception as exc:
                logger.warning("export: memory エクスポート失敗 %s", exc)

        # Diary: JSON ファイルを列挙
        if self.diary is not None:
            try:
                for date_str in self.diary.list_entries():
                    entry = self.diary.get_entry(date_str)
                    if entry:
                        payload["diary"].append(entry)
            except Exception as exc:
                logger.warning("export: diary エクスポート失敗 %s", exc)

        # Emotion history
        if self.emotion_history is not None:
            try:
                payload["emotion_history"] = list(self.emotion_history._records)
            except Exception as exc:
                logger.warning("export: emotion_history エクスポート失敗 %s", exc)

        # Anniversaries
        if self.anniversary is not None:
            try:
                payload["anniversaries"] = self.anniversary.list_all()
            except Exception as exc:
                logger.warning("export: anniversary エクスポート失敗 %s", exc)

        # 監査ログに記録
        if self.audit_log is not None:
            try:
                self.audit_log.info(
                    "subject_export",
                    detail=f"subject_id={subject_id},records="
                    f"{len(payload['memories'])}mem/"
                    f"{len(payload['diary'])}diary/"
                    f"{len(payload['emotion_history'])}emo/"
                    f"{len(payload['anniversaries'])}anniv",
                )
            except Exception:
                pass

        return payload

    def export_to_file(
        self,
        subject_id: str = SELF_SUBJECT_ID,
        output_path: Path | None = None,
    ) -> Path:
        """export_subject の結果を JSON ファイルに書き出し、パスを返す。"""
        payload = self.export_subject(subject_id)
        if output_path is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output_path = (
                self.base_dir / "data" / "exports" / f"{subject_id}_{ts}.json"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    # ─── purge ───────────────────────────────────────────────

    def purge_subject(
        self,
        subject_id: str = SELF_SUBJECT_ID,
        dry_run: bool = False,
    ) -> dict:
        """指定 subject の全記録を削除する（GDPR 17 条）。

        Args:
            subject_id: 削除対象（'self' なら現ユーザー全データ）
            dry_run: True なら削除せず件数のみ返す

        Returns:
            {"memories": int, "diary": int, "emotion_history": int,
             "anniversaries": int, "dry_run": bool}
        """
        report = {
            "subject_id": subject_id,
            "memories": 0,
            "diary": 0,
            "emotion_history": 0,
            "anniversaries": 0,
            "dry_run": dry_run,
            "errors": [],
        }

        # 1. Memory DB: 全行削除 (subject_id 列が入ったら WHERE で絞る)
        if self.memory is not None:
            try:
                with self.memory._conn() as conn:
                    cur = conn.execute("SELECT COUNT(*) FROM memories")
                    count = cur.fetchone()[0]
                    if not dry_run:
                        conn.execute("DELETE FROM memories")
                        conn.execute("DELETE FROM memory_versions")
                        # FTS index もクリア
                        try:
                            conn.execute("DELETE FROM memories_fts")
                        except Exception:
                            pass
                    report["memories"] = int(count)
            except Exception as exc:
                report["errors"].append(f"memory: {exc}")

        # 2. Diary: ディレクトリごと削除
        diary_dir = self.data_dir / "diary"
        if diary_dir.exists():
            try:
                files = list(diary_dir.glob("*.json"))
                report["diary"] = len(files)
                if not dry_run:
                    shutil.rmtree(diary_dir)
                    diary_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                report["errors"].append(f"diary: {exc}")

        # 3. Emotion history
        emo_path = self.data_dir / "emotion_history.json"
        if emo_path.exists():
            try:
                # 件数推定
                if self.emotion_history is not None:
                    report["emotion_history"] = len(self.emotion_history._records)
                if not dry_run:
                    emo_path.unlink()
                    if self.emotion_history is not None:
                        self.emotion_history._records = []
            except Exception as exc:
                report["errors"].append(f"emotion_history: {exc}")

        # 4. Anniversaries
        if self.anniversary is not None:
            try:
                report["anniversaries"] = len(self.anniversary.items)
                if not dry_run:
                    self.anniversary.items = []
                    self.anniversary._save()
            except Exception as exc:
                report["errors"].append(f"anniversary: {exc}")

        # 5. 監査ログ（削除しない — ハッシュチェーン保全）
        if self.audit_log is not None:
            try:
                if dry_run:
                    self.audit_log.info(
                        "subject_purge_dryrun",
                        detail=f"subject_id={subject_id}",
                    )
                else:
                    self.audit_log.critical(
                        "subject_purge",
                        detail=(
                            f"subject_id={subject_id},"
                            f"mem={report['memories']},"
                            f"diary={report['diary']},"
                            f"emo={report['emotion_history']},"
                            f"anniv={report['anniversaries']}"
                        ),
                    )
            except Exception:
                pass

        return report

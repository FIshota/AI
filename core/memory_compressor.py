"""
記憶圧縮 + 重要度自動調整システム
- 中期記憶が一定数を超えたら古いものを要約して長期記憶へ
- アクセス頻度・最近性に基づき重要度を自動調整
"""
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from core.memory import MemoryManager
from core.memory_forgetting import (
    ForgettingPolicy,
    MemoryEntry,
)

COMPRESS_THRESHOLD = 50
KEEP_RECENT = 20
COMPRESS_BATCH = 15


class MemoryCompressor:
    def __init__(
        self,
        memory_manager: MemoryManager,
        forgetting_policy: Optional[ForgettingPolicy] = None,
    ):
        self.memory = memory_manager
        # additive-only optional hook. None のときは既存ロジックのみ.
        self.forgetting_policy = forgetting_policy

    def classify_for_forgetting(
        self, entries: List[MemoryEntry], now: Optional[datetime] = None
    ) -> Tuple[List[MemoryEntry], List[MemoryEntry]]:
        """Forgetting policy が設定されていれば (kept, forgotten) を返す.

        未設定のときは全件 kept として返す (no-op).
        既存の compress()/adjust_importance() とは独立な追加 API.
        """
        if self.forgetting_policy is None:
            return list(entries), []
        return self.forgetting_policy.apply(entries, now=now)

    def should_compress(self) -> bool:
        stats = self.memory.stats()
        return stats.get("by_type", {}).get("mid", 0) > COMPRESS_THRESHOLD

    def compress(self) -> int:
        # 圧縮前に重要度を調整
        self.adjust_importance()

        if not self.should_compress():
            return 0

        with self.memory._conn() as conn:
            cur = conn.execute(
                """SELECT id, content, importance, created_at
                   FROM memories
                   WHERE memory_type = 'mid' AND is_protected = 0
                   ORDER BY accessed_at ASC
                   LIMIT ?""",
                (KEEP_RECENT + COMPRESS_BATCH,)
            )
            rows = cur.fetchall()

        if len(rows) <= KEEP_RECENT:
            return 0

        to_compress = rows[:COMPRESS_BATCH]
        summary_lines = []
        total_importance = 0.0
        ids_to_delete = []

        for row in to_compress:
            row_id, enc_content, importance, created_at = row
            content = self.memory._dec(enc_content)
            summary_lines.append(content[:60].replace('\n', ' '))
            total_importance += importance
            ids_to_delete.append(row_id)

        avg_importance = total_importance / len(to_compress)
        date_range = f"{to_compress[0][3][:10]}〜{to_compress[-1][3][:10]}"
        summary = f"[要約 {date_range}] " + " / ".join(summary_lines[:5])

        self.memory.add_mid_term(
            content=summary,
            importance=avg_importance,
            emotional_weight=0.4,
            tags=["long_term", "compressed"],
        )

        with self.memory._conn() as conn:
            # nosec B608: ','.join('?'*N) は純粋なプレースホルダ文字列で外部入力なし.
            # ids_to_delete の各値は第2引数でバインドされる.
            conn.execute(
                f"UPDATE memories SET memory_type='long' WHERE id IN "  # nosec B608
                f"({','.join('?'*len(ids_to_delete))})",
                ids_to_delete
            )

        print(f"[Memory] {len(ids_to_delete)}件の記憶を要約圧縮しました", flush=True)
        return len(ids_to_delete)

    def adjust_importance(self):
        """
        記憶の重要度を自動調整します:
        - アクセス回数が多い → 重要度を上げる
        - 最近アクセスされた → 重要度を上げる
        - 長期間アクセスされていない → 重要度を下げる（保護された記憶は除く）
        """
        now = datetime.now()
        updated = 0

        with self.memory._conn() as conn:
            cur = conn.execute(
                """SELECT id, importance, access_count, accessed_at, is_protected
                   FROM memories WHERE memory_type IN ('mid', 'long')"""
            )
            rows = cur.fetchall()

            for row in rows:
                row_id, importance, access_count, accessed_at_str, is_protected = row
                if is_protected:
                    continue

                new_importance = importance

                # アクセス頻度ボーナス（最大+0.2）
                freq_bonus = min(0.2, access_count * 0.02)
                new_importance = min(1.0, new_importance + freq_bonus)

                # 最終アクセス日時による調整
                try:
                    accessed_at = datetime.fromisoformat(accessed_at_str)
                    days_ago = (now - accessed_at).days
                    if days_ago <= 3:
                        # 3日以内のアクセス → わずかに上昇
                        new_importance = min(1.0, new_importance + 0.05)
                    elif days_ago > 30:
                        # 30日超アクセスなし → 減衰
                        decay = min(0.15, (days_ago - 30) * 0.003)
                        new_importance = max(0.1, new_importance - decay)
                except Exception:
                    pass

                if abs(new_importance - importance) > 0.01:
                    conn.execute(
                        "UPDATE memories SET importance = ? WHERE id = ?",
                        (round(new_importance, 3), row_id)
                    )
                    updated += 1

        if updated:
            print(f"[Memory] {updated}件の記憶重要度を自動調整しました", flush=True)
        return updated

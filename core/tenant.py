"""
tenant — マルチテナント基盤（H2, 2026-04-21）。

家族メンバー / YAMATO / KAGUYA で各個体のデータを物理分離するための土台。

現状（ai-chan v0）:
    単一ユーザー想定で `SELF_TENANT = "self"` 固定。
    すべてのデータは `data/tenants/self/` 配下に書かれる運用へ段階移行する。

将来（YAMATO 量産時）:
    1 プロセス 1 tenant を原則とし、subject_id ≡ tenant_id で扱う。
    別世帯の Ai は別プロセス / 別 tenant で動作する。

設計メモ:
    - TenantId は NewType ではなく dataclass(frozen) として扱い、
      不正文字（../, /, NULL）をコンストラクタで拒絶する。
    - tenant_dir(base, tenant) は必ずこのモジュール経由で取得させること。
      `base / tenant` を直書きすると path-traversal の隙ができる。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 許容文字: 英数字 / ハイフン / アンダースコア のみ。
# UUID v4 / "self" / "family-member-abc_01" いずれも通る。
_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

SELF_TENANT_ID: str = "self"


class InvalidTenantId(ValueError):
    """tenant_id に不正文字が含まれている / 長さ逸脱 など。"""


@dataclass(frozen=True)
class TenantId:
    """型安全な tenant 識別子。

    普通の str と混同しないよう wrapper dataclass にしてある。
    `str(tid)` で内部値を得られる。
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidTenantId(f"tenant_id must be str, got {type(self.value)!r}")
        if not _TENANT_ID_RE.fullmatch(self.value):
            raise InvalidTenantId(
                f"tenant_id contains illegal chars or wrong length: {self.value!r}"
            )

    def __str__(self) -> str:
        return self.value


SELF_TENANT: TenantId = TenantId(SELF_TENANT_ID)


def tenant_dir(base_dir: Path, tenant: TenantId | str) -> Path:
    """`data/tenants/{tenant_id}/` を返す（なければ作成）。

    path-traversal 防止:
        tenant を str で受けた場合でも TenantId を通して検証してから結合する。
    """
    if isinstance(tenant, str):
        tenant = TenantId(tenant)
    # base_dir が `data/` を指していれば tenants/ を追加
    # base_dir が既に `data/tenants/` 相当なら二重追加を避ける
    base = Path(base_dir)
    if base.name != "tenants":
        base = base / "tenants"
    path = base / tenant.value
    path.mkdir(parents=True, exist_ok=True)
    # 解決後のパスが base の外に出ていないか確認（paranoia）
    resolved = path.resolve()
    root = base.resolve()
    if root not in resolved.parents and resolved != root:
        # 実際には TenantId 正規化で届かないはずだが、ガードだけ残す
        raise InvalidTenantId(
            f"resolved tenant path escapes base: {resolved} (base={root})"
        )
    return path


def parse_tenant_id(raw: str | None, default: TenantId = SELF_TENANT) -> TenantId:
    """外部入力（env / CLI）から安全に TenantId を作る。"""
    if raw is None or raw == "":
        return default
    return TenantId(raw)

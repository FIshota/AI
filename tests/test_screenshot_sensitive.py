"""
機密画面検出・ブラー機能のテスト。

pytest で実行する。Pillow 有無どちらでも通る想定。
"""
from __future__ import annotations

import sys
import threading
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

# プロジェクトルートを import path に追加
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.screenshot_sensitive import (  # noqa: E402
    DEFAULT_PATTERNS,
    SensitiveAction,
    SensitiveClassifier,
    SensitivePattern,
)
from core.screenshot_blur import apply_blur, _encode_solid_png, _read_png_size  # noqa: E402


# ---------------------------------------------------------------------------
# 小さな PNG を 1 枚合成 (Pillow 不要)
# ---------------------------------------------------------------------------

def _tiny_png(w: int = 8, h: int = 8, rgb=(200, 100, 50)) -> bytes:
    return _encode_solid_png(w, h, rgb)


# ---------------------------------------------------------------------------
# 1. 1Password タイトル → BLOCK
# ---------------------------------------------------------------------------

def test_classify_1password_blocks():
    c = SensitiveClassifier()
    p = c.classify("1Password - Main Vault")
    assert p is not None
    assert p.name == "1Password"
    assert p.action is SensitiveAction.BLOCK


# ---------------------------------------------------------------------------
# 2. 三菱UFJ → BLOCK
# ---------------------------------------------------------------------------

def test_classify_mufg_blocks():
    c = SensitiveClassifier()
    p = c.classify("三菱UFJ ダイレクト - 口座照会")
    assert p is not None
    assert p.action is SensitiveAction.BLOCK


# ---------------------------------------------------------------------------
# 3. 通常のブラウザ → None
# ---------------------------------------------------------------------------

def test_classify_plain_browser_returns_none():
    c = SensitiveClassifier()
    assert c.classify("Wikipedia - The Free Encyclopedia") is None


# ---------------------------------------------------------------------------
# 4. 部分一致しない無関係タイトル → None
# ---------------------------------------------------------------------------

def test_classify_unrelated_returns_none():
    c = SensitiveClassifier()
    assert c.classify("天気予報 - 東京") is None


# ---------------------------------------------------------------------------
# 5. 大文字小文字混在でもマッチ
# ---------------------------------------------------------------------------

def test_classify_case_insensitive():
    c = SensitiveClassifier()
    assert c.classify("bItWaRdEn") is not None
    assert c.classify("GMAIL - INBOX") is not None


# ---------------------------------------------------------------------------
# 6. 日本語タイトル正規表現
# ---------------------------------------------------------------------------

def test_classify_japanese_title():
    c = SensitiveClassifier()
    p = c.classify("確定申告書作成コーナー")
    assert p is not None
    assert p.action is SensitiveAction.REDACT


# ---------------------------------------------------------------------------
# 7. SensitivePattern は frozen
# ---------------------------------------------------------------------------

def test_sensitive_pattern_is_frozen():
    pat = DEFAULT_PATTERNS[0]
    with pytest.raises(FrozenInstanceError):
        pat.name = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8. classify スレッドセーフ (並列 100 呼び出し)
# ---------------------------------------------------------------------------

def test_classify_thread_safe():
    c = SensitiveClassifier()
    results = []
    errors = []

    def worker(i: int):
        try:
            r = c.classify("1Password - Vault", None)
            results.append(r is not None and r.name == "1Password")
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == 100
    assert all(results)


# ---------------------------------------------------------------------------
# 9. apply_blur は元 bytes を変更しない (immutability)
# ---------------------------------------------------------------------------

def test_apply_blur_does_not_mutate_input():
    src = _tiny_png()
    snapshot = bytes(src)  # コピー
    _ = apply_blur(src, SensitiveAction.BLUR, strength=5)
    assert src == snapshot


# ---------------------------------------------------------------------------
# 10. REDACT は単色画像
# ---------------------------------------------------------------------------

def test_redact_returns_single_color_image():
    src = _tiny_png(w=16, h=16, rgb=(200, 150, 100))
    out = apply_blur(src, SensitiveAction.REDACT)
    assert out, "REDACT は非空 bytes"
    # Pillow があれば検証、無ければ PNG ヘッダのみ確認
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(out)).convert("RGB")
        px = list(img.getdata())
        assert px[0] == px[-1]
        assert px[0] == (0, 0, 0)
    except ImportError:
        # fallback: ヘッダサイズが一致すること
        assert _read_png_size(out) == _read_png_size(src)


# ---------------------------------------------------------------------------
# 11. BLOCK は空 bytes
# ---------------------------------------------------------------------------

def test_block_returns_empty_bytes():
    src = _tiny_png()
    out = apply_blur(src, SensitiveAction.BLOCK)
    assert out == b""


# ---------------------------------------------------------------------------
# 12. Pillow 不在時でも blur が動作 (mock)
# ---------------------------------------------------------------------------

def test_blur_works_without_pillow(monkeypatch):
    import core.screenshot_blur as mod
    monkeypatch.setattr(mod, "PILLOW_OK", False)
    src = _tiny_png(w=32, h=32)
    out = apply_blur(src, SensitiveAction.BLUR, strength=20)
    assert out, "Pillow 無しでも非空 PNG"
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
    # サイズは元と同じ
    assert _read_png_size(out) == _read_png_size(src)


# ---------------------------------------------------------------------------
# 13. bundle_id マッチ
# ---------------------------------------------------------------------------

def test_classify_by_bundle_id():
    c = SensitiveClassifier()
    # タイトルは無関係でも bundle id で決まる
    p = c.classify("Untitled Window", "com.1password.1password")
    assert p is not None
    assert p.name == "1Password"

    p2 = c.classify("foo", "com.apple.keychainaccess")
    assert p2 is not None and p2.action is SensitiveAction.BLOCK


# ---------------------------------------------------------------------------
# 14. 新規 pattern を追加できる (frozen でも tuple 生成で拡張可)
# ---------------------------------------------------------------------------

def test_custom_pattern_can_be_added():
    extra = SensitivePattern(
        name="MyClinic",
        window_title_regex=r"MyClinic",
        app_bundle_ids=("jp.example.myclinic",),
        action=SensitiveAction.BLOCK,
    )
    patterns = DEFAULT_PATTERNS + (extra,)
    c = SensitiveClassifier(patterns)
    p = c.classify("MyClinic - Patient Records")
    assert p is not None
    assert p.name == "MyClinic"
    # 既存パターンも依然として動く
    assert c.classify("1Password") is not None

"""
Sprint 3.0: A) マルチモーダル強化 + E) 防御進化 のテスト
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path


# ── ImageAnalyzer ────────────────────────────────────────

class TestImageAnalyzer:
    def test_analyze_pil_image(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not available")

        analyzer = ImageAnalyzer(tmp_path)
        img = Image.new("RGB", (200, 100), (255, 0, 0))
        result = analyzer.analyze(img)
        assert result["dimensions"] == (200, 100)
        assert result["brightness"] > 0
        assert len(result["dominant_colors"]) >= 1
        assert isinstance(result["description"], str)
        assert len(result["description"]) > 0

    def test_analyze_file_path(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not available")

        analyzer = ImageAnalyzer(tmp_path)
        img = Image.new("RGB", (50, 50), (0, 0, 255))
        path = tmp_path / "test.png"
        img.save(path)

        result = analyzer.analyze(path)
        assert result["dimensions"] == (50, 50)
        assert result["file_size"] > 0

    def test_analyze_missing_file(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        analyzer = ImageAnalyzer(tmp_path)
        result = analyzer.analyze(tmp_path / "nonexistent.png")
        assert "description" in result

    def test_dominant_colors(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not available")

        analyzer = ImageAnalyzer(tmp_path)
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        colors = analyzer.get_dominant_colors(img, n=3)
        assert isinstance(colors, list)
        assert len(colors) >= 1
        assert all(c.startswith("#") for c in colors)

    def test_brightness_dark(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not available")

        analyzer = ImageAnalyzer(tmp_path)
        dark = Image.new("RGB", (50, 50), (10, 10, 10))
        assert analyzer.analyze_brightness(dark) < 0.1

    def test_brightness_bright(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not available")

        analyzer = ImageAnalyzer(tmp_path)
        bright = Image.new("RGB", (50, 50), (250, 250, 250))
        assert analyzer.analyze_brightness(bright) > 0.9

    def test_generate_description(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        analyzer = ImageAnalyzer(tmp_path)
        desc = analyzer.generate_description({
            "dimensions": (800, 600),
            "brightness": 0.8,
            "dominant_colors": ["#ff0000"],
            "has_text": False,
            "text_content": "",
            "file_size": 1024,
        })
        assert "800×600" in desc


# ── ClipboardImageCapture ────────────────────────────────

class TestClipboardImage:
    def test_import(self):
        from core.clipboard_image import ClipboardImageCapture
        clip = ClipboardImageCapture()
        assert clip is not None

    def test_has_image_returns_bool(self):
        from core.clipboard_image import ClipboardImageCapture
        clip = ClipboardImageCapture()
        result = clip.has_image()
        assert isinstance(result, bool)


# ── MultimodalChatHandler ────────────────────────────────

class TestMultimodalChat:
    def test_build_image_context(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        from core.multimodal_chat import MultimodalChatHandler
        analyzer = ImageAnalyzer(tmp_path)
        handler = MultimodalChatHandler(tmp_path, analyzer)

        ctx = handler.build_image_context({
            "dimensions": (1920, 1080),
            "brightness": 0.6,
            "dominant_colors": ["#ffffff", "#000000"],
            "has_text": True,
            "text_content": "テストテキスト",
            "description": "テスト画像",
            "file_size": 2048,
        })
        assert "1920×1080" in ctx
        assert "テストテキスト" in ctx

    def test_process_image_with_pil(self, tmp_path: Path):
        from core.image_analyzer import ImageAnalyzer
        from core.multimodal_chat import MultimodalChatHandler
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not available")

        analyzer = ImageAnalyzer(tmp_path)
        handler = MultimodalChatHandler(tmp_path, analyzer)

        img = Image.new("RGB", (100, 100), (128, 128, 128))
        path = tmp_path / "test.png"
        img.save(path)

        result = handler.process_image_query(path, "この画像は何？")
        assert isinstance(result, str)
        assert len(result) > 0


# ── NetworkMonitor ───────────────────────────────────────

class TestNetworkMonitor:
    def test_init(self, tmp_path: Path):
        from core.network_monitor import NetworkMonitor
        (tmp_path / "data").mkdir()
        nm = NetworkMonitor(tmp_path)
        assert nm is not None

    def test_scan_connections(self, tmp_path: Path):
        from core.network_monitor import NetworkMonitor
        (tmp_path / "data").mkdir()
        nm = NetworkMonitor(tmp_path)
        conns = nm.scan_connections()
        assert isinstance(conns, list)

    def test_detect_suspicious(self, tmp_path: Path):
        from core.network_monitor import NetworkMonitor
        (tmp_path / "data").mkdir()
        nm = NetworkMonitor(tmp_path)
        alerts = nm.detect_suspicious()
        assert isinstance(alerts, list)

    def test_check_dns(self, tmp_path: Path):
        from core.network_monitor import NetworkMonitor
        (tmp_path / "data").mkdir()
        nm = NetworkMonitor(tmp_path)
        result = nm.check_dns_integrity()
        assert "status" in result

    def test_health_score(self, tmp_path: Path):
        from core.network_monitor import NetworkMonitor
        (tmp_path / "data").mkdir()
        nm = NetworkMonitor(tmp_path)
        score = nm.get_health_score()
        assert 0 <= score <= 100

    def test_connection_summary(self, tmp_path: Path):
        from core.network_monitor import NetworkMonitor
        (tmp_path / "data").mkdir()
        nm = NetworkMonitor(tmp_path)
        summary = nm.get_connection_summary()
        assert "ネットワーク" in summary

    def test_hourly_job(self, tmp_path: Path):
        from core.network_monitor import NetworkMonitor
        (tmp_path / "data").mkdir()
        nm = NetworkMonitor(tmp_path)
        result = nm.hourly_job()
        assert "action" in result
        assert result["action"] == "network_check"


# ── ProcessMonitor ───────────────────────────────────────

class TestProcessMonitor:
    def test_init(self, tmp_path: Path):
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()
        pm = ProcessMonitor(tmp_path)
        assert pm is not None

    def test_scan_processes(self, tmp_path: Path):
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()
        pm = ProcessMonitor(tmp_path)
        procs = pm.scan_processes()
        assert isinstance(procs, list)
        assert len(procs) > 0  # 何かしらプロセスは動いてるはず

    def test_detect_suspicious(self, tmp_path: Path):
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()
        pm = ProcessMonitor(tmp_path)
        alerts = pm.detect_suspicious_processes()
        assert isinstance(alerts, list)

    def test_build_baseline(self, tmp_path: Path):
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()
        pm = ProcessMonitor(tmp_path)
        baseline = pm.build_baseline()
        assert "process_count" in baseline
        assert baseline["process_count"] > 0

    def test_summary(self, tmp_path: Path):
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()
        pm = ProcessMonitor(tmp_path)
        summary = pm.get_summary()
        assert "プロセス" in summary

    def test_health_score(self, tmp_path: Path):
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()
        pm = ProcessMonitor(tmp_path)
        score = pm.get_health_score()
        assert 0 <= score <= 100

    def test_hourly_job(self, tmp_path: Path):
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()
        pm = ProcessMonitor(tmp_path)
        result = pm.hourly_job()
        assert result["action"] == "process_check"


# ── DefenseDashboard ─────────────────────────────────────

class TestDefenseDashboard:
    def test_init(self, tmp_path: Path):
        from core.defense_dashboard import DefenseDashboard
        (tmp_path / "data").mkdir()
        dd = DefenseDashboard(tmp_path)
        assert dd is not None

    def test_overall_score(self, tmp_path: Path):
        from core.defense_dashboard import DefenseDashboard
        (tmp_path / "data").mkdir()
        dd = DefenseDashboard(tmp_path)
        score = dd.get_overall_score()
        assert 0 <= score <= 100

    def test_quick_status(self, tmp_path: Path):
        from core.defense_dashboard import DefenseDashboard
        (tmp_path / "data").mkdir()
        dd = DefenseDashboard(tmp_path)
        status = dd.get_quick_status()
        assert "セキュリティ" in status

    def test_full_report(self, tmp_path: Path):
        from core.defense_dashboard import DefenseDashboard
        (tmp_path / "data").mkdir()
        dd = DefenseDashboard(tmp_path)
        report = dd.get_full_report()
        assert "セキュリティ総合レポート" in report

    def test_recommendations(self, tmp_path: Path):
        from core.defense_dashboard import DefenseDashboard
        (tmp_path / "data").mkdir()
        dd = DefenseDashboard(tmp_path)
        recs = dd.get_recommendations()
        assert isinstance(recs, list)
        assert len(recs) >= 1

    def test_daily_job(self, tmp_path: Path):
        from core.defense_dashboard import DefenseDashboard
        (tmp_path / "data").mkdir()
        dd = DefenseDashboard(tmp_path)
        result = dd.daily_job()
        assert result["action"] == "defense_report"
        assert "score" in result

    def test_with_modules(self, tmp_path: Path):
        """モジュールを渡した場合のテスト"""
        from core.defense_dashboard import DefenseDashboard
        from core.network_monitor import NetworkMonitor
        from core.process_monitor import ProcessMonitor
        (tmp_path / "data").mkdir()

        nm = NetworkMonitor(tmp_path)
        pm = ProcessMonitor(tmp_path)
        dd = DefenseDashboard(
            tmp_path,
            network_monitor=nm,
            process_monitor=pm,
        )
        score = dd.get_overall_score()
        assert 0 <= score <= 100
        report = dd.get_full_report()
        assert "ネットワーク" in report
        assert "プロセス" in report

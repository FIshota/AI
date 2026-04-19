"""Benchmark suites (Phase 0 stubs)."""

from bench.suites import elyza_tasks_100, family_dialog, jglue

SUITES = {
    "jglue": jglue,
    "elyza_tasks_100": elyza_tasks_100,
    "family_dialog": family_dialog,
}

__all__ = ["SUITES", "jglue", "elyza_tasks_100", "family_dialog"]

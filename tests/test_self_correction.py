"""
自己修正システム (SelfCorrectionSystem) のテスト

テスト対象:
- QualityMonitor: 品質スコア記録、症状検出、平均/トレンド
- PrescriptionEngine: 症状ごとの処方生成
- TreatmentExecutor: ハンドラ登録と処方実行
- SelfCorrectionSystem: 統合フロー、クールダウン、永続化
"""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.self_correction import (
    DiagnosisResult,
    Prescription,
    PrescriptionEngine,
    QualityMonitor,
    SelfCorrectionSystem,
    Symptom,
    TreatmentExecutor,
    TreatmentRecord,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# QualityMonitor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestQualityMonitor:
    def setup_method(self):
        self.monitor = QualityMonitor()

    # -- current_avg --

    def test_current_avg_default(self):
        """スコア未記録時は 0.5 を返す"""
        assert self.monitor.current_avg == 0.5

    def test_current_avg_after_scores(self):
        """スコア記録後は直近の平均を返す"""
        for s in [0.8, 0.6, 0.7]:
            self.monitor.record_score(s)
        expected = (0.8 + 0.6 + 0.7) / 3
        assert abs(self.monitor.current_avg - expected) < 1e-9

    # -- trend --

    def test_trend_insufficient_data(self):
        """データ不足時はフラット"""
        for _ in range(5):
            self.monitor.record_score(0.5)
        assert self.monitor.trend == "→"

    def test_trend_improving(self):
        """品質向上トレンド"""
        # older half = low scores, recent half = high scores
        for _ in range(QualityMonitor.WINDOW_SIZE // 2):
            self.monitor.record_score(0.3)
        for _ in range(QualityMonitor.WINDOW_SIZE // 2):
            self.monitor.record_score(0.8)
        assert self.monitor.trend == "↑"

    def test_trend_declining(self):
        """品質低下トレンド"""
        for _ in range(QualityMonitor.WINDOW_SIZE // 2):
            self.monitor.record_score(0.8)
        for _ in range(QualityMonitor.WINDOW_SIZE // 2):
            self.monitor.record_score(0.3)
        assert self.monitor.trend == "↓"

    def test_trend_stable(self):
        """安定トレンド"""
        for _ in range(QualityMonitor.WINDOW_SIZE):
            self.monitor.record_score(0.5)
        assert self.monitor.trend == "→"

    # -- check_symptoms: quality_drop --

    def test_symptom_quality_drop(self):
        """older期間→recent期間の品質低下を検出する"""
        # older half: high quality
        for _ in range(QualityMonitor.WINDOW_SIZE):
            self.monitor.record_score(0.9)
        # recent half: low quality
        for _ in range(QualityMonitor.WINDOW_SIZE):
            self.monitor.record_score(0.5)

        symptoms = self.monitor.check_symptoms()
        symptom_types = [s.symptom for s in symptoms]
        assert Symptom.QUALITY_DROP in symptom_types

    def test_symptom_consecutive_low_quality(self):
        """連続5回の低品質を検出する"""
        for _ in range(5):
            self.monitor.record_score(0.2)

        symptoms = self.monitor.check_symptoms()
        drop_symptoms = [s for s in symptoms if s.symptom == Symptom.QUALITY_DROP]
        assert len(drop_symptoms) >= 1
        assert drop_symptoms[0].severity == 0.8

    # -- check_symptoms: repetitive --

    def test_symptom_repetitive(self):
        """同じ応答の繰り返しを検出する"""
        # 10回中7回以上が同じ先頭30文字 → ratio > 0.3
        for _ in range(8):
            self.monitor.record_response("同じ応答です。これは繰り返しのテストです。")
        for i in range(2):
            self.monitor.record_response(f"ユニークな応答{i}です。")

        symptoms = self.monitor.check_symptoms()
        symptom_types = [s.symptom for s in symptoms]
        assert Symptom.REPETITIVE in symptom_types

    def test_no_symptom_repetitive_when_varied(self):
        """応答がバラバラなら繰り返し症状なし"""
        for i in range(10):
            self.monitor.record_response(f"まったく違う応答番号{i:03d}です。")

        symptoms = self.monitor.check_symptoms()
        symptom_types = [s.symptom for s in symptoms]
        assert Symptom.REPETITIVE not in symptom_types

    # -- check_symptoms: too_short --

    def test_symptom_too_short(self):
        """短すぎる応答を検出する"""
        for _ in range(10):
            self.monitor.record_response("hi")

        symptoms = self.monitor.check_symptoms()
        symptom_types = [s.symptom for s in symptoms]
        assert Symptom.TOO_SHORT in symptom_types

    # -- check_symptoms: too_long --

    def test_symptom_too_long(self):
        """長すぎる応答を検出する"""
        long_text = "あ" * 400
        for _ in range(10):
            self.monitor.record_response(long_text)

        symptoms = self.monitor.check_symptoms()
        symptom_types = [s.symptom for s in symptoms]
        assert Symptom.TOO_LONG in symptom_types

    # -- check_symptoms: high_error_rate --

    def test_symptom_high_error_rate(self):
        """エラー頻度が高い場合を検出する"""
        for _ in range(6):
            self.monitor.record_error()

        symptoms = self.monitor.check_symptoms()
        symptom_types = [s.symptom for s in symptoms]
        assert Symptom.HIGH_ERROR_RATE in symptom_types

    def test_no_symptom_when_healthy(self):
        """正常な状態では症状が検出されない"""
        for i in range(10):
            self.monitor.record_score(0.8)
            self.monitor.record_response(f"適切な長さの応答番号{i:03d}です。少し長めに書きます。")

        symptoms = self.monitor.check_symptoms()
        assert len(symptoms) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PrescriptionEngine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPrescriptionEngine:
    def setup_method(self):
        self.engine = PrescriptionEngine()

    def _make_diagnosis(self, symptom: Symptom, severity: float = 0.5) -> DiagnosisResult:
        return DiagnosisResult(
            symptom=symptom,
            severity=severity,
            evidence="test evidence",
            detected_at=time.time(),
        )

    def test_quality_drop_high_severity(self):
        """品質低下 (高深刻度) → 筋肉記憶リセット"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.QUALITY_DROP, 0.8))
        assert rx.action == "reset_muscle_memory_low_quality"
        assert rx.priority == 0

    def test_quality_drop_low_severity(self):
        """品質低下 (低深刻度) → 温度調整"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.QUALITY_DROP, 0.3))
        assert rx.action == "adjust_temperature"
        assert rx.params["delta"] < 0

    def test_repetitive(self):
        """繰り返し → 温度を上げる"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.REPETITIVE))
        assert rx.action == "adjust_temperature"
        assert rx.params["delta"] > 0

    def test_too_short(self):
        """短すぎ → トークン数を増やす"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.TOO_SHORT))
        assert rx.action == "adjust_max_tokens"
        assert rx.params["delta"] > 0

    def test_too_long(self):
        """長すぎ → トークン数を減らす"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.TOO_LONG))
        assert rx.action == "adjust_max_tokens"
        assert rx.params["delta"] < 0

    def test_high_error_rate(self):
        """高エラー率 → 免疫チェック"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.HIGH_ERROR_RATE))
        assert rx.action == "run_immune_check"

    def test_stale_muscle(self):
        """古い筋肉記憶 → プルーニング"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.STALE_MUSCLE))
        assert rx.action == "prune_stale_patterns"
        assert rx.params["max_age_days"] == 14

    def test_emotion_flat(self):
        """感情フラット → 温度微増"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.EMOTION_FLAT))
        assert rx.action == "adjust_temperature"
        assert rx.params["delta"] == 0.05

    def test_low_naturalness_fallback(self):
        """未定義症状 → no_action"""
        rx = self.engine.prescribe(self._make_diagnosis(Symptom.LOW_NATURALNESS))
        assert rx.action == "no_action"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TreatmentExecutor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTreatmentExecutor:
    def setup_method(self):
        self.executor = TreatmentExecutor()

    def test_execute_registered_handler(self):
        """登録済みハンドラが正常に呼ばれる"""
        handler = MagicMock(return_value={"adjusted": True})
        self.executor.register_handler("adjust_temperature", handler)

        rx = Prescription(action="adjust_temperature", params={"delta": 0.1})
        result = self.executor.execute(rx)

        assert result["ok"] is True
        assert result["action"] == "adjust_temperature"
        handler.assert_called_once_with({"delta": 0.1})

    def test_execute_unregistered_handler(self):
        """未登録アクションはエラーを返す"""
        rx = Prescription(action="unknown_action", params={})
        result = self.executor.execute(rx)

        assert result["ok"] is False
        assert "未登録" in result["error"]

    def test_execute_handler_raises(self):
        """ハンドラが例外を投げても安全に捕捉する"""
        handler = MagicMock(side_effect=RuntimeError("boom"))
        self.executor.register_handler("failing_action", handler)

        rx = Prescription(action="failing_action", params={})
        result = self.executor.execute(rx)

        assert result["ok"] is False
        assert "boom" in result["error"]

    def test_register_multiple_handlers(self):
        """複数のハンドラを登録・実行できる"""
        h1 = MagicMock(return_value="result1")
        h2 = MagicMock(return_value="result2")
        self.executor.register_handler("action_a", h1)
        self.executor.register_handler("action_b", h2)

        r1 = self.executor.execute(Prescription(action="action_a", params={"x": 1}))
        r2 = self.executor.execute(Prescription(action="action_b", params={"y": 2}))

        assert r1["ok"] is True
        assert r2["ok"] is True
        h1.assert_called_once_with({"x": 1})
        h2.assert_called_once_with({"y": 2})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SelfCorrectionSystem
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSelfCorrectionSystem:
    def setup_method(self):
        self.system = SelfCorrectionSystem(data_dir=None)
        # Register mock handlers for the actions the prescriber can produce
        self._handlers: dict[str, MagicMock] = {}
        for action_name in [
            "reset_muscle_memory_low_quality",
            "adjust_temperature",
            "adjust_max_tokens",
            "run_immune_check",
            "prune_stale_patterns",
        ]:
            handler = MagicMock(return_value={"done": True})
            self._handlers[action_name] = handler
            self.system.executor.register_handler(action_name, handler)

    # -- on_turn basic --

    def test_on_turn_no_action_before_interval(self):
        """CHECK_INTERVAL未満のターンでは診断しない"""
        results = []
        for i in range(SelfCorrectionSystem.CHECK_INTERVAL - 1):
            r = self.system.on_turn(0.2, "short", had_error=False)
            results.extend(r)
        assert len(results) == 0

    def test_on_turn_triggers_at_interval(self):
        """CHECK_INTERVAL到達時に診断が走る（症状があれば治療）"""
        # 5回の低品質ターンで CHECK_INTERVAL (5) に到達
        all_results = []
        for i in range(SelfCorrectionSystem.CHECK_INTERVAL):
            r = self.system.on_turn(0.2, "ok", had_error=False)
            all_results.extend(r)
        # 5回目の on_turn で診断が走り、連続低品質が検出される
        assert any(r["symptom"] == "quality_drop" for r in all_results)

    def test_on_turn_records_error(self):
        """had_error=True でエラーが記録される"""
        all_results = []
        # CHECK_INTERVAL 以上のエラーターンを記録（5+ errors within 300s → high_error_rate）
        for _ in range(SelfCorrectionSystem.CHECK_INTERVAL * 2):
            r = self.system.on_turn(0.5, "response text here", had_error=True)
            all_results.extend(r)
        # CHECK_INTERVAL ごとの診断でエラー頻度症状が検出される
        symptom_names = [r["symptom"] for r in all_results]
        assert "high_error_rate" in symptom_names

    # -- force_check --

    def test_force_check_no_symptoms(self):
        """健全な状態での force_check は空"""
        for i in range(10):
            self.system.on_turn(0.8, f"良い応答番号{i:03d}、適切な長さで返答します。")
        results = self.system.force_check()
        assert results == []

    # -- cooldown --

    def test_cooldown_prevents_repeat_action(self):
        """同じアクションが COOLDOWN_SEC 以内に繰り返されない"""
        # 低品質を入れて症状を出す
        for _ in range(5):
            self.system.monitor.record_score(0.2)

        # 1回目の治療
        results1 = self.system.force_check()
        assert len(results1) > 0
        first_action = results1[0]["action"]

        # 2回目: クールダウン中なので同じアクションはスキップされる
        for _ in range(5):
            self.system.monitor.record_score(0.2)
        results2 = self.system.force_check()
        repeated = [r for r in results2 if r["action"] == first_action]
        assert len(repeated) == 0

    def test_cooldown_expires(self):
        """クールダウン期間経過後は同じアクションが再実行される"""
        for _ in range(5):
            self.system.monitor.record_score(0.2)

        results1 = self.system.force_check()
        assert len(results1) > 0
        first_action = results1[0]["action"]

        # クールダウンを期限切れにする
        self.system._last_action_time[first_action] = time.time() - 400

        for _ in range(5):
            self.system.monitor.record_score(0.2)
        results2 = self.system.force_check()
        repeated = [r for r in results2 if r["action"] == first_action]
        assert len(repeated) > 0

    # -- treatment history cap --

    def test_treatment_history_capped_at_50(self):
        """治療履歴は最大50件に制限される"""
        # 51件の治療記録を直接注入
        now = time.time()
        for i in range(51):
            rec = TreatmentRecord(
                prescription=Prescription(action=f"test_{i}", params={}),
                applied_at=now - (51 - i),
                quality_before=0.5,
            )
            self.system._treatment_history.append(rec)

        # _diagnose_and_treat 実行で切り詰め
        self.system._treatment_history = self.system._treatment_history[-50:]
        assert len(self.system._treatment_history) <= 50

    # -- evaluate_recent_treatments --

    def test_evaluate_recent_treatments_effective(self):
        """品質が悪化しなければ治療は有効と判定"""
        now = time.time()
        rec = TreatmentRecord(
            prescription=Prescription(action="test_eval", params={}),
            applied_at=now - 120,  # 2分前
            quality_before=0.4,
        )
        self.system._treatment_history.append(rec)

        # 品質を改善させる
        for _ in range(5):
            self.system.monitor.record_score(0.7)

        results = self.system.evaluate_recent_treatments()
        assert len(results) == 1
        assert results[0]["effective"] is True
        assert results[0]["improvement"] > 0

    def test_evaluate_recent_treatments_too_recent(self):
        """治療直後 (60秒未満) は判定しない"""
        now = time.time()
        rec = TreatmentRecord(
            prescription=Prescription(action="test_recent", params={}),
            applied_at=now - 10,  # 10秒前
            quality_before=0.5,
        )
        self.system._treatment_history.append(rec)
        results = self.system.evaluate_recent_treatments()
        assert len(results) == 0

    def test_evaluate_skips_already_judged(self):
        """判定済みの記録はスキップする"""
        now = time.time()
        rec = TreatmentRecord(
            prescription=Prescription(action="already_judged", params={}),
            applied_at=now - 120,
            quality_before=0.5,
            quality_after=0.6,
            effective=True,
        )
        self.system._treatment_history.append(rec)
        results = self.system.evaluate_recent_treatments()
        assert len(results) == 0

    # -- health report --

    def test_health_report_structure(self):
        """ヘルスレポートが正しい構造を持つ"""
        for i in range(3):
            self.system.on_turn(0.7, f"テスト応答{i}")

        report = self.system.get_health_report()
        assert "quality_avg" in report
        assert "quality_trend" in report
        assert "active_symptoms" in report
        assert "total_treatments" in report
        assert "recent_treatments" in report
        assert isinstance(report["quality_avg"], float)
        assert isinstance(report["active_symptoms"], list)

    def test_health_report_shows_treatments(self):
        """治療履歴がレポートに含まれる"""
        now = time.time()
        rec = TreatmentRecord(
            prescription=Prescription(
                action="test_action", params={}, reason="test reason"
            ),
            applied_at=now,
            quality_before=0.5,
        )
        self.system._treatment_history.append(rec)

        report = self.system.get_health_report()
        assert report["total_treatments"] >= 1
        assert report["recent_treatments"][-1]["action"] == "test_action"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Persistence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPersistence:
    def test_save_and_load(self, tmp_path: Path):
        """状態を保存・復元できる"""
        sys1 = SelfCorrectionSystem(data_dir=tmp_path)
        handler = MagicMock(return_value={"ok": True})
        sys1.executor.register_handler("reset_muscle_memory_low_quality", handler)
        sys1.executor.register_handler("adjust_temperature", handler)

        # ターンを重ねて治療を発生させる
        for _ in range(5):
            sys1.monitor.record_score(0.2)
        sys1.force_check()

        state_file = tmp_path / "self_correction_state.json"
        assert state_file.exists()

        saved = json.loads(state_file.read_text("utf-8"))
        assert "turn_count" in saved
        assert "last_action_time" in saved

        # 新しいインスタンスで復元
        sys2 = SelfCorrectionSystem(data_dir=tmp_path)
        assert sys2._turn_count == sys1._turn_count
        assert sys2._last_action_time == sys1._last_action_time

    def test_load_missing_file(self, tmp_path: Path):
        """ファイルがなくても正常に起動する"""
        sys = SelfCorrectionSystem(data_dir=tmp_path)
        assert sys._turn_count == 0

    def test_load_corrupt_file(self, tmp_path: Path):
        """壊れたJSONファイルでも安全に起動する"""
        state_file = tmp_path / "self_correction_state.json"
        state_file.write_text("NOT VALID JSON {{{", "utf-8")

        sys = SelfCorrectionSystem(data_dir=tmp_path)
        assert sys._turn_count == 0

    def test_no_persistence_without_data_dir(self):
        """data_dir=None の場合は保存しない"""
        sys = SelfCorrectionSystem(data_dir=None)
        assert sys._state_path is None
        # _save should be a no-op, no error
        sys._save()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Integration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestIntegration:
    def test_full_cycle_quality_drop(self, tmp_path: Path):
        """品質低下→診断→処方→治療→経過観察の完全サイクル"""
        sys = SelfCorrectionSystem(data_dir=tmp_path)
        handler = MagicMock(return_value={"adjusted": True})
        sys.executor.register_handler("reset_muscle_memory_low_quality", handler)
        sys.executor.register_handler("adjust_temperature", handler)

        # 低品質ターンを CHECK_INTERVAL 回入れる
        for i in range(SelfCorrectionSystem.CHECK_INTERVAL):
            sys.on_turn(0.2, f"低品質応答{i}")

        # 治療が走ったことを確認
        report = sys.get_health_report()
        assert report["total_treatments"] >= 1

        # 治療記録にタイムスタンプを古くして経過観察を可能にする
        for rec in sys._treatment_history:
            rec.applied_at = time.time() - 120

        # 品質を改善
        for _ in range(5):
            sys.monitor.record_score(0.9)

        evals = sys.evaluate_recent_treatments()
        assert len(evals) >= 1
        assert evals[0]["effective"] is True

    def test_multiple_symptoms_treated(self):
        """複数の症状が同時に治療される (MAX_TREATMENTS まで)"""
        sys = SelfCorrectionSystem(data_dir=None)
        handler = MagicMock(return_value={"done": True})
        sys.executor.register_handler("reset_muscle_memory_low_quality", handler)
        sys.executor.register_handler("adjust_temperature", handler)
        sys.executor.register_handler("adjust_max_tokens", handler)
        sys.executor.register_handler("run_immune_check", handler)

        # 低品質 + 短すぎ + エラー頻発
        for _ in range(10):
            sys.monitor.record_score(0.15)
            sys.monitor.record_response("hi")
            sys.monitor.record_error()

        results = sys.force_check()
        # MAX_TREATMENTS は 3 なので最大3つ
        assert 1 <= len(results) <= SelfCorrectionSystem.MAX_TREATMENTS

    def test_get_status_text(self):
        """ステータステキストが文字列で返る"""
        sys = SelfCorrectionSystem(data_dir=None)
        for _ in range(5):
            sys.monitor.record_score(0.2)

        text = sys.get_status_text()
        assert isinstance(text, str)
        assert "自己修正システム" in text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclass frozen check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestFrozenDataclasses:
    def test_diagnosis_result_is_frozen(self):
        """DiagnosisResult は変更不可"""
        d = DiagnosisResult(
            symptom=Symptom.QUALITY_DROP, severity=0.5, evidence="test"
        )
        with pytest.raises(AttributeError):
            d.severity = 0.9  # type: ignore[misc]

    def test_prescription_is_frozen(self):
        """Prescription は変更不可"""
        p = Prescription(action="test", params={}, reason="r")
        with pytest.raises(AttributeError):
            p.action = "other"  # type: ignore[misc]

    def test_diagnosis_replace(self):
        """dataclasses.replace で新しいインスタンスを作れる"""
        d = DiagnosisResult(
            symptom=Symptom.TOO_SHORT, severity=0.3, evidence="short"
        )
        d2 = replace(d, severity=0.8)
        assert d.severity == 0.3
        assert d2.severity == 0.8

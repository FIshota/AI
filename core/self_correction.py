"""
自己修正システム (Self-Correction System)

アイが自分の「不調」を検知し、自分で原因を特定して直す仕組み。

人間で言うと:
- 「あ、今の言い方まずかった」→ 次から直す
- 「最近調子悪いな」→ 生活習慣を見直す
- 「この癖直したい」→ 意識して矯正する

┌──────────────────────────────────────────────────┐
│  自己修正の流れ                                     │
│                                                    │
│  ① モニタリング (Monitoring)                        │
│     品質スコアの推移を常に監視。                       │
│     「最近の調子はどうか」を数値で把握。               │
│                                                    │
│  ② 診断 (Diagnosis)                                │
│     品質低下を検知したら原因を分析。                   │
│     「なぜ調子が悪いのか」を特定。                     │
│                                                    │
│  ③ 処方 (Prescription)                              │
│     原因に応じた修正アクションを決定。                 │
│     「何をすれば直るか」を判断。                       │
│                                                    │
│  ④ 治療 (Treatment)                                │
│     修正を実行。パラメータ調整、記憶修正など。         │
│                                                    │
│  ⑤ 経過観察 (Follow-up)                             │
│     治療後の品質を監視して効果を確認。                 │
│     効果がなければ別の処方を試す。                     │
│                                                    │
└──────────────────────────────────────────────────┘
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 症状（品質低下のパターン）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Symptom(str, Enum):
    """検出可能な症状"""
    QUALITY_DROP = "quality_drop"              # 品質スコアの連続低下
    REPETITIVE = "repetitive"                  # 同じような応答の繰り返し
    TOO_SHORT = "too_short"                    # 応答が短すぎる
    TOO_LONG = "too_long"                      # 応答が長すぎる
    LOW_NATURALNESS = "low_naturalness"        # 不自然な言い回し
    STALE_MUSCLE = "stale_muscle"              # 筋肉記憶の劣化
    HIGH_ERROR_RATE = "high_error_rate"        # エラー発生率が高い
    EMOTION_FLAT = "emotion_flat"              # 感情が動かない


@dataclass(frozen=True)
class DiagnosisResult:
    """診断結果"""
    symptom: Symptom
    severity: float          # 0.0〜1.0（深刻度）
    evidence: str            # 根拠の説明
    detected_at: float = 0.0


@dataclass(frozen=True)
class Prescription:
    """処方（修正アクション）"""
    action: str              # 実行するアクションの名前
    params: dict = field(default_factory=dict)
    reason: str = ""         # なぜこの処方なのか
    priority: int = 0        # 0=高, 1=中, 2=低


@dataclass
class TreatmentRecord:
    """治療記録"""
    prescription: Prescription
    applied_at: float
    quality_before: float
    quality_after: float = 0.0
    effective: bool | None = None  # None=まだ判定前


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 品質モニター
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class QualityMonitor:
    """
    品質スコアの推移を監視する。
    人間の「体温計」のようなもの。異常を早期発見する。
    """

    WINDOW_SIZE = 20       # 直近何回分を見るか
    DROP_THRESHOLD = 0.15  # この差以上の低下を「品質低下」と判定
    LOW_THRESHOLD = 0.4    # この値以下を「低品質」と判定
    REPETITION_RATIO = 0.3 # 応答の30%以上が重複なら「繰り返し」

    def __init__(self):
        self._scores: deque[float] = deque(maxlen=100)
        self._responses: deque[str] = deque(maxlen=50)
        self._response_lengths: deque[int] = deque(maxlen=50)
        self._error_times: deque[float] = deque(maxlen=50)

    def record_score(self, score: float):
        """品質スコアを記録"""
        self._scores.append(score)

    def record_response(self, response: str):
        """応答を記録"""
        self._responses.append(response)
        self._response_lengths.append(len(response))

    def record_error(self):
        """エラー発生を記録"""
        self._error_times.append(time.time())

    def check_symptoms(self) -> list[DiagnosisResult]:
        """
        現在の症状をすべてチェックする。
        医者の問診のように、一通り調べて異常を列挙する。
        """
        symptoms: list[DiagnosisResult] = []
        now = time.time()

        # ① 品質低下チェック
        if len(self._scores) >= self.WINDOW_SIZE:
            recent = list(self._scores)[-self.WINDOW_SIZE:]
            older = list(self._scores)[-self.WINDOW_SIZE * 2:-self.WINDOW_SIZE]
            if older:
                recent_avg = sum(recent) / len(recent)
                older_avg = sum(older) / len(older)
                drop = older_avg - recent_avg
                if drop > self.DROP_THRESHOLD:
                    symptoms.append(DiagnosisResult(
                        symptom=Symptom.QUALITY_DROP,
                        severity=min(drop / 0.5, 1.0),
                        evidence=f"品質が {older_avg:.2f} → {recent_avg:.2f} に低下",
                        detected_at=now,
                    ))

        # ② 連続低品質チェック
        if len(self._scores) >= 5:
            last5 = list(self._scores)[-5:]
            if all(s < self.LOW_THRESHOLD for s in last5):
                avg = sum(last5) / 5
                symptoms.append(DiagnosisResult(
                    symptom=Symptom.QUALITY_DROP,
                    severity=0.8,
                    evidence=f"直近5回の平均品質が {avg:.2f} (閾値: {self.LOW_THRESHOLD})",
                    detected_at=now,
                ))

        # ③ 繰り返しチェック
        if len(self._responses) >= 10:
            recent10 = list(self._responses)[-10:]
            unique = set(r[:30] for r in recent10)  # 先頭30文字で比較
            ratio = 1 - len(unique) / len(recent10)
            if ratio > self.REPETITION_RATIO:
                symptoms.append(DiagnosisResult(
                    symptom=Symptom.REPETITIVE,
                    severity=min(ratio, 1.0),
                    evidence=f"直近10応答中 {int(ratio*100)}% が類似",
                    detected_at=now,
                ))

        # ④ 応答長チェック
        if len(self._response_lengths) >= 10:
            recent_lens = list(self._response_lengths)[-10:]
            avg_len = sum(recent_lens) / len(recent_lens)
            if avg_len < 5:
                symptoms.append(DiagnosisResult(
                    symptom=Symptom.TOO_SHORT,
                    severity=0.6,
                    evidence=f"平均応答長が {avg_len:.0f} 文字",
                    detected_at=now,
                ))
            elif avg_len > 300:
                symptoms.append(DiagnosisResult(
                    symptom=Symptom.TOO_LONG,
                    severity=0.4,
                    evidence=f"平均応答長が {avg_len:.0f} 文字",
                    detected_at=now,
                ))

        # ⑤ エラー頻度チェック
        recent_errors = [t for t in self._error_times if now - t < 300]
        if len(recent_errors) >= 5:
            symptoms.append(DiagnosisResult(
                symptom=Symptom.HIGH_ERROR_RATE,
                severity=min(len(recent_errors) / 10, 1.0),
                evidence=f"直近5分間に {len(recent_errors)} 件のエラー",
                detected_at=now,
            ))

        return symptoms

    @property
    def current_avg(self) -> float:
        """現在の平均品質"""
        if not self._scores:
            return 0.5
        recent = list(self._scores)[-self.WINDOW_SIZE:]
        return sum(recent) / len(recent)

    @property
    def trend(self) -> str:
        """品質トレンド（↑ / → / ↓）"""
        if len(self._scores) < self.WINDOW_SIZE:
            return "→"
        recent = list(self._scores)[-self.WINDOW_SIZE // 2:]
        older = list(self._scores)[-(self.WINDOW_SIZE):-(self.WINDOW_SIZE // 2)]
        if not older:
            return "→"
        r_avg = sum(recent) / len(recent)
        o_avg = sum(older) / len(older)
        diff = r_avg - o_avg
        if diff > 0.05:
            return "↑"
        elif diff < -0.05:
            return "↓"
        return "→"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 処方箋エンジン（診断結果 → 修正アクション）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PrescriptionEngine:
    """
    症状に応じた処方を決定する。
    医者が症状を見て薬を出すように、
    品質低下の原因に応じた修正アクションを選ぶ。
    """

    # 症状 → 処方のマッピング
    _PRESCRIPTIONS: dict[Symptom, Callable] = {}

    def prescribe(self, diagnosis: DiagnosisResult) -> Prescription:
        """診断結果から処方を決定"""
        s = diagnosis.symptom

        if s == Symptom.QUALITY_DROP:
            if diagnosis.severity > 0.6:
                return Prescription(
                    action="reset_muscle_memory_low_quality",
                    params={"threshold": 0.7},
                    reason="品質の低い筋肉記憶が応答を汚染している可能性",
                    priority=0,
                )
            return Prescription(
                action="adjust_temperature",
                params={"delta": -0.05},
                reason="温度を下げて応答の安定性を上げる",
                priority=1,
            )

        if s == Symptom.REPETITIVE:
            return Prescription(
                action="adjust_temperature",
                params={"delta": +0.1},
                reason="温度を上げて応答の多様性を増やす",
                priority=0,
            )

        if s == Symptom.TOO_SHORT:
            return Prescription(
                action="adjust_max_tokens",
                params={"delta": +50},
                reason="最大トークン数を増やして応答を充実させる",
                priority=1,
            )

        if s == Symptom.TOO_LONG:
            return Prescription(
                action="adjust_max_tokens",
                params={"delta": -30},
                reason="最大トークン数を減らして簡潔にする",
                priority=1,
            )

        if s == Symptom.HIGH_ERROR_RATE:
            return Prescription(
                action="run_immune_check",
                params={},
                reason="エラー頻度が高い。免疫系による総合チェックを実行",
                priority=0,
            )

        if s == Symptom.STALE_MUSCLE:
            return Prescription(
                action="prune_stale_patterns",
                params={"max_age_days": 14},
                reason="古い筋肉記憶を忘却して新鮮さを保つ",
                priority=1,
            )

        if s == Symptom.EMOTION_FLAT:
            return Prescription(
                action="adjust_temperature",
                params={"delta": +0.05},
                reason="感情の幅を広げるため温度を微増",
                priority=2,
            )

        return Prescription(
            action="no_action",
            reason="不明な症状",
            priority=2,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 治療実行エンジン
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TreatmentExecutor:
    """
    処方に基づいて実際の修正を実行する。
    各アクションは安全に設計されている（破壊的変更なし）。
    """

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register_handler(self, action: str, handler: Callable):
        """アクションハンドラを登録"""
        self._handlers[action] = handler

    def execute(self, prescription: Prescription) -> dict[str, Any]:
        """処方を実行"""
        handler = self._handlers.get(prescription.action)
        if handler is None:
            logger.warning("未登録のアクション: %s", prescription.action)
            return {"ok": False, "error": f"未登録: {prescription.action}"}

        try:
            result = handler(prescription.params)
            logger.info(
                "自己修正実行: %s (理由: %s)",
                prescription.action, prescription.reason,
            )
            return {"ok": True, "action": prescription.action, "result": result}
        except Exception as e:
            logger.exception("自己修正失敗: %s", prescription.action)
            return {"ok": False, "action": prescription.action, "error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 統合: SelfCorrectionSystem
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SelfCorrectionSystem:
    """
    自己修正の統合システム。

    毎ターンの品質を監視し、異常を検知したら
    自動的に診断→処方→治療→経過観察を行う。

    人間の「自己調整能力」:
    - 風邪を引いたら休む（品質低下 → パラメータ調整）
    - 悪い癖を直す（筋肉記憶のプルーニング）
    - 体調を自覚する（品質モニタリング）
    """

    CHECK_INTERVAL = 5    # 何ターンごとに診断するか
    MAX_TREATMENTS = 3    # 1回の診断で最大いくつの処方を実行するか
    COOLDOWN_SEC = 300    # 同じアクションの連続実行を防ぐクールダウン（5分）

    def __init__(self, data_dir: Path | None = None):
        self.monitor = QualityMonitor()
        self.prescriber = PrescriptionEngine()
        self.executor = TreatmentExecutor()

        self._lock = threading.Lock()
        self._turn_count = 0
        self._treatment_history: list[TreatmentRecord] = []
        self._last_action_time: dict[str, float] = {}
        self._data_dir = data_dir
        self._state_path = data_dir / "self_correction_state.json" if data_dir else None
        self._load()

    # ─── メイン処理: 毎ターン呼ばれる ───────────────────

    def on_turn(
        self,
        quality_score: float,
        response: str,
        had_error: bool = False,
    ) -> list[dict]:
        """
        毎ターンの処理。品質を記録し、必要に応じて自己修正を行う。

        Returns: 実行された修正アクションのリスト
        """
        with self._lock:
            self._turn_count += 1

            # 記録
            self.monitor.record_score(quality_score)
            self.monitor.record_response(response)
            if had_error:
                self.monitor.record_error()

            # 診断は CHECK_INTERVAL ターンごと
            if self._turn_count % self.CHECK_INTERVAL != 0:
                return []

            return self._diagnose_and_treat()

    def force_check(self) -> list[dict]:
        """手動で強制的に診断を実行"""
        return self._diagnose_and_treat()

    # ─── 診断→治療パイプライン ──────────────────────────

    def _diagnose_and_treat(self) -> list[dict]:
        """診断して治療する"""
        symptoms = self.monitor.check_symptoms()
        if not symptoms:
            return []

        # 重症度順にソート
        symptoms.sort(key=lambda d: d.severity, reverse=True)

        executed: list[dict] = []
        now = time.time()

        for diagnosis in symptoms[:self.MAX_TREATMENTS]:
            prescription = self.prescriber.prescribe(diagnosis)

            # クールダウンチェック（同じ薬を立て続けに飲まない）
            last = self._last_action_time.get(prescription.action, 0)
            if now - last < self.COOLDOWN_SEC:
                continue

            # 治療実行
            quality_before = self.monitor.current_avg
            result = self.executor.execute(prescription)

            if result.get("ok"):
                record = TreatmentRecord(
                    prescription=prescription,
                    applied_at=now,
                    quality_before=quality_before,
                )
                self._treatment_history.append(record)
                self._last_action_time[prescription.action] = now
                executed.append({
                    "symptom": diagnosis.symptom.value,
                    "severity": diagnosis.severity,
                    "action": prescription.action,
                    "reason": prescription.reason,
                })

        # 履歴は最新50件のみ保持
        if len(self._treatment_history) > 50:
            self._treatment_history = self._treatment_history[-50:]

        if executed:
            self._save()

        return executed

    # ─── 経過観察 ───────────────────────────────────────

    def evaluate_recent_treatments(self) -> list[dict]:
        """
        最近の治療の効果を判定する。
        「あの薬は効いたか？」を振り返る。
        """
        results: list[dict] = []
        current_avg = self.monitor.current_avg

        for record in self._treatment_history[-10:]:
            if record.effective is not None:
                continue  # 既に判定済み

            # 治療から十分な時間が経過したか
            elapsed = time.time() - record.applied_at
            if elapsed < 60:  # 最低1分は経過観察
                continue

            record.quality_after = current_avg
            improvement = current_avg - record.quality_before
            record.effective = improvement > -0.05  # 悪化しなければ有効

            results.append({
                "action": record.prescription.action,
                "before": round(record.quality_before, 3),
                "after": round(record.quality_after, 3),
                "improvement": round(improvement, 3),
                "effective": record.effective,
            })

        return results

    # ─── ネガティブプロンプト (#83) ──────────────────────

    def get_negative_prompts(self) -> list[str]:
        """
        頻出する失敗パターンから「やってはいけないこと」のプロンプトリストを生成する。

        治療履歴から繰り返し発生している症状を特定し、
        LLM に注入する否定的指示（「〜しないこと」）に変換する。

        Returns:
            最大5件のネガティブプロンプト
        """
        # 症状の発生頻度をカウント
        symptom_counts: dict[str, int] = {}
        for record in self._treatment_history:
            action = record.prescription.action
            symptom_counts[action] = symptom_counts.get(action, 0) + 1

        # 頻度順にソート
        sorted_symptoms = sorted(
            symptom_counts.items(), key=lambda x: -x[1]
        )

        # アクション→ネガティブプロンプトの変換テーブル
        action_to_prompt: dict[str, str] = {
            "reset_muscle_memory_low_quality": "低品質な応答パターンを繰り返さないこと",
            "adjust_temperature": "同じトーンの応答を続けないこと。変化をつける",
            "adjust_max_tokens": "応答の長さが極端にならないこと（短すぎず長すぎず）",
            "run_immune_check": "エラーが頻発する操作を繰り返さないこと",
            "prune_stale_patterns": "古くて使い物にならないパターンに頼らないこと",
        }

        prompts: list[str] = []
        for action, count in sorted_symptoms[:5]:
            if count >= 2:  # 2回以上発生したもの
                prompt = action_to_prompt.get(
                    action,
                    f"'{action}' に関連する問題を繰り返さないこと",
                )
                prompts.append(prompt)

        # 現在の症状からも追加
        current_symptoms = self.monitor.check_symptoms()
        symptom_prompts: dict[str, str] = {
            Symptom.REPETITIVE.value: "同じ言い回しや表現の繰り返しを避けること",
            Symptom.TOO_SHORT.value: "応答が短すぎないようにすること。内容のある返答をする",
            Symptom.TOO_LONG.value: "応答が長すぎないようにすること。簡潔に",
            Symptom.QUALITY_DROP.value: "応答品質の低下に注意。丁寧に考えて返答すること",
            Symptom.EMOTION_FLAT.value: "感情表現が平坦にならないようにすること",
        }
        for symptom in current_symptoms:
            prompt = symptom_prompts.get(symptom.symptom.value)
            if prompt and prompt not in prompts and len(prompts) < 5:
                prompts.append(prompt)

        return prompts[:5]

    # ─── Akashic Core 統合 ──────────────────────────────

    def quantum_diagnose(self, response_text: str, context: str = "", llm_fn=None) -> dict:
        """
        量子多状態診断: 単一の応答を複数の視点から同時評価。
        「この応答は正しいか？」という問いを多世界的に展開し、
        不確実性の高い箇所（量子不確定性が高い部分）を特定する。
        """
        result = {
            "perspectives": [],
            "quantum_uncertainty": "",   # str: CollapsedResponse.quantum_uncertainty は文字列
            "quantum_uncertainty_level": 0.0,  # float: 独自計算 (worldline confidence 分散)
            "blind_spots": [],
            "consensus": "",
            "akashic_available": False,
        }
        try:
            from core.akashic.superposition import QuantumReasoner
            reasoner = QuantumReasoner(llm_fn=llm_fn)
            question = f"この応答の品質・正確性・自然さを評価せよ: {response_text[:200]}"
            state = reasoner.superpose(question)
            collapsed = reasoner.collapse(state, context)
            result["perspectives"] = [
                {"perspective": wl.perspective, "confidence": wl.confidence}
                for wl in state.worldlines
            ]
            result["quantum_uncertainty"] = collapsed.quantum_uncertainty  # str
            result["consensus"] = collapsed.response
            result["akashic_available"] = True
            # confidence 分散 → 不確実度の float 指標 (0=全員一致, 1=最大分散)
            confidences = [wl.confidence for wl in state.worldlines]
            if confidences:
                mean_c = sum(confidences) / len(confidences)
                variance = sum((c - mean_c) ** 2 for c in confidences) / len(confidences)
                result["quantum_uncertainty_level"] = round(min(1.0, variance * 4), 3)
        except Exception as _e:
            import logging
            logging.getLogger(__name__).debug("[SelfCorr/Akashic] quantum_diagnose エラー: %s", _e)

        try:
            from core.akashic.strange_loop import StrangeLoop
            result["blind_spots"] = StrangeLoop(llm_fn=llm_fn).find_blind_spots(
                response_text, llm_fn=llm_fn
            )
        except Exception:
            pass

        return result

    def is_quantum_anomaly(self, response_text: str, threshold: float = 0.7) -> bool:
        """
        量子不確実性レベルが閾値を超える場合、この応答は「量子異常」として扱う。
        高い不確実性 = 複数の世界線が強く衝突 = 要修正の可能性が高い。
        quantum_uncertainty_level (float 0-1) を使用。
        """
        try:
            diagnosis = self.quantum_diagnose(response_text)
            return diagnosis["quantum_uncertainty_level"] > threshold
        except Exception:
            return False

    # ─── ステータス ─────────────────────────────────────

    def get_health_report(self) -> dict[str, Any]:
        """健康状態レポート"""
        symptoms = self.monitor.check_symptoms()
        recent_treatments = [
            {
                "action": r.prescription.action,
                "reason": r.prescription.reason,
                "effective": r.effective,
                "applied_at": r.applied_at,
            }
            for r in self._treatment_history[-5:]
        ]

        return {
            "quality_avg": round(self.monitor.current_avg, 3),
            "quality_trend": self.monitor.trend,
            "active_symptoms": [
                {"symptom": s.symptom.value, "severity": round(s.severity, 2)}
                for s in symptoms
            ],
            "total_treatments": len(self._treatment_history),
            "recent_treatments": recent_treatments,
        }

    def get_status_text(self) -> str:
        """日本語ステータス"""
        report = self.get_health_report()
        trend = report["quality_trend"]
        avg = report["quality_avg"]

        if not report["active_symptoms"]:
            status = "🟢 健康"
        elif any(s["severity"] > 0.6 for s in report["active_symptoms"]):
            status = "🔴 要治療"
        else:
            status = "🟡 軽度の不調"

        lines = [
            f"🩺 自己修正システム: {status}",
            f"  品質: {avg:.0%} {trend}",
            f"  累計治療: {report['total_treatments']}回",
        ]

        for s in report["active_symptoms"][:3]:
            lines.append(f"  ⚠ {s['symptom']}: 深刻度{s['severity']:.0%}")

        return "\n".join(lines)

    # ─── 永続化 ──────────────────────────────────────────

    def _save(self):
        if not self._state_path:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "turn_count": self._turn_count,
            "last_action_time": self._last_action_time,
            "treatment_count": len(self._treatment_history),
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )

    def _load(self):
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text("utf-8"))
            self._turn_count = data.get("turn_count", 0)
            self._last_action_time = data.get("last_action_time", {})
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("自己修正データの読み込みに失敗: %s", e)

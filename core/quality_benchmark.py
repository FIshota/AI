"""
自動品質ベンチマーク
定型テスト入力に対する応答品質を定期的に測定する。

アイの応答品質が時間とともに改善しているか / 劣化していないかを追跡。
"""
from __future__ import annotations

import json
import logging
import platform
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CriterionFn = Callable[[str], float]


# ── 判定基準関数 ─────────────────────────────────────

def is_japanese(response: str) -> float:
    """日本語文字の比率が 0.5 以上なら 1.0"""
    if not response:
        return 0.0
    jp = sum(
        1 for ch in response
        if "\u3040" <= ch <= "\u309F"
        or "\u30A0" <= ch <= "\u30FF"
        or "\u4E00" <= ch <= "\u9FFF"
    )
    ratio = jp / len(response)
    return 1.0 if ratio > 0.5 else ratio / 0.5


def is_not_empty(response: str) -> float:
    """空でなければ 1.0"""
    return 1.0 if len(response.strip()) > 0 else 0.0


def no_role_prefix(response: str) -> float:
    """AI:/アシスタント: などの接頭辞がなければ 1.0"""
    prefixes = ("AI:", "ai:", "アシスタント:", "Assistant:", "assistant:")
    trimmed = response.strip()
    return 0.0 if any(trimmed.startswith(p) for p in prefixes) else 1.0


def appropriate_length(response: str) -> float:
    """5 < len < 500 なら 1.0"""
    length = len(response.strip())
    if 5 < length < 500:
        return 1.0
    if length <= 5:
        return length / 5.0
    return max(0.0, 1.0 - (length - 500) / 1000)


def no_repetition(response: str) -> float:
    """10文字以上の部分文字列が3回以上繰り返されていなければ 1.0"""
    text = response.strip()
    if len(text) < 30:
        return 1.0
    for size in range(10, len(text) // 3 + 1):
        for start in range(len(text) - size * 3 + 1):
            if text.count(text[start : start + size]) >= 3:
                return 0.0
    return 1.0


def no_desu_masu(response: str) -> float:
    """です/ます調を使っていなければ 1.0"""
    return 0.0 if re.search(r"です[。\s]|ます[。\s]|です$|ます$", response) else 1.0


# ── データ構造 ───────────────────────────────────────

@dataclass(frozen=True)
class CaseResult:
    """個別テストケースの結果"""
    input_text: str
    response: str
    scores: Tuple[Tuple[str, float], ...]
    average: float


@dataclass(frozen=True)
class BenchmarkResult:
    """ベンチマーク全体の結果"""
    overall_score: float        # 0-100
    case_results: Tuple[CaseResult, ...]
    timestamp: str              # ISO 8601


@dataclass(frozen=True)
class TestCase:
    """ベンチマーク用テストケース"""
    input_text: str
    criteria: Tuple[Tuple[str, CriterionFn], ...]


# ── 定型テストケース ─────────────────────────────────

_CC: Tuple[Tuple[str, CriterionFn], ...] = (
    ("is_japanese", is_japanese),
    ("is_not_empty", is_not_empty),
    ("no_role_prefix", no_role_prefix),
    ("appropriate_length", appropriate_length),
    ("no_repetition", no_repetition),
    ("no_desu_masu", no_desu_masu),
)

_INPUTS = (
    "おはよう", "こんにちは", "おやすみ",                          # 挨拶
    "今日は嬉しいことがあったよ", "ちょっと悲しいことがあった",       # 感情
    "明日の天気教えて", "好きな食べ物は？",                          # 質問
    "仕事で悩んでることがあるんだけど聞いてくれる？",                # 複雑
    "最近疲れてるんだよね",
    "アイちゃんって誰？", "名前教えて",                             # アイデンティティ
    "違う、そうじゃなくて",                                          # 訂正
    "うん", "そう", "なるほど",                                     # 短い応答
)

BENCHMARK_CASES: Tuple[TestCase, ...] = tuple(
    TestCase(input_text=t, criteria=_CC) for t in _INPUTS
)


# ── ベンチマーク実行 ─────────────────────────────────

class QualityBenchmark:
    """定型テスト入力に対する応答品質を測定する。"""

    def __init__(self, cases: Tuple[TestCase, ...] = BENCHMARK_CASES) -> None:
        self._cases = cases

    def run_benchmark(self, chat_fn: Callable[[str], str]) -> BenchmarkResult:
        """全テストケースを実行し結果を返す。"""
        case_results: List[CaseResult] = []
        for tc in self._cases:
            try:
                response = chat_fn(tc.input_text)
            except Exception as exc:
                logger.warning("ベンチマーク実行エラー (%s): %s", tc.input_text, exc)
                response = ""

            scores: List[Tuple[str, float]] = []
            for name, fn in tc.criteria:
                try:
                    score = fn(response)
                except Exception:
                    score = 0.0
                scores.append((name, max(0.0, min(1.0, score))))

            avg = sum(s for _, s in scores) / len(scores) if scores else 0.0
            case_results.append(CaseResult(
                input_text=tc.input_text,
                response=response,
                scores=tuple(scores),
                average=avg,
            ))

        overall = (
            sum(cr.average for cr in case_results) / len(case_results) * 100
            if case_results else 0.0
        )
        return BenchmarkResult(
            overall_score=round(overall, 2),
            case_results=tuple(case_results),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def save_result(result: BenchmarkResult, path: Path) -> Path:
        """結果を JSON ファイルとして data/benchmarks/ に保存する。"""
        path.mkdir(parents=True, exist_ok=True)
        ts = result.timestamp.replace(":", "-").replace("+", "p")
        file_path = path / f"benchmark_{ts}.json"

        data = {
            "overall_score": result.overall_score,
            "timestamp": result.timestamp,
            "cases": [
                {
                    "input": cr.input_text,
                    "response": cr.response,
                    "scores": {n: round(v, 4) for n, v in cr.scores},
                    "average": round(cr.average, 4),
                }
                for cr in result.case_results
            ],
        }
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        logger.info("ベンチマーク結果を保存: %s", file_path)
        return file_path

    @staticmethod
    def compare_results(result1: BenchmarkResult, result2: BenchmarkResult) -> str:
        """2つのベンチマーク結果を比較して人間が読める文字列を返す。"""
        diff = result2.overall_score - result1.overall_score
        arrow = "+" if diff > 0 else ""
        lines: List[str] = [
            "=== 品質ベンチマーク比較 ===",
            f"前回: {result1.overall_score:.2f}  ({result1.timestamp})",
            f"今回: {result2.overall_score:.2f}  ({result2.timestamp})",
            f"差分: {arrow}{diff:.2f}",
            "",
        ]
        old_map = {cr.input_text: cr.average for cr in result1.case_results}
        for cr in result2.case_results:
            old_avg = old_map.get(cr.input_text)
            if old_avg is None:
                lines.append(f"  [{cr.input_text}]  {cr.average:.2f} (新規)")
            else:
                d = cr.average - old_avg
                mark = "+" if d > 0 else ""
                sym = "^" if d > 0.05 else ("v" if d < -0.05 else "=")
                lines.append(
                    f"  {sym} [{cr.input_text}]  "
                    f"{old_avg:.2f} -> {cr.average:.2f} ({mark}{d:.2f})"
                )
        return "\n".join(lines)

    # ── #49: 公開レポート ──────────────────────────────────

    def generate_public_report(
        self,
        chat_fn: Callable[[str], str],
        bypass_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        """外部公開用の品質レポートを生成する。

        Args:
            chat_fn: ベンチマーク実行に使うチャット関数。
            bypass_rate: LLMバイパス率（0-1）。外部から渡す。

        Returns:
            {
                "inference_speed": {...},
                "bypass_rate": float | None,
                "quality_scores": {...},
                "system_info": {...},
                "generated_at": str,
            }
        """
        import time

        # 短い入力で推論速度を計測
        speed_samples: List[float] = []
        test_inputs: Tuple[str, ...] = ("おはよう", "こんにちは", "うん")
        for inp in test_inputs:
            start: float = time.monotonic()
            try:
                chat_fn(inp)
            except Exception:
                pass
            elapsed_ms: float = (time.monotonic() - start) * 1000
            speed_samples.append(elapsed_ms)

        avg_speed: Optional[float] = (
            round(sum(speed_samples) / len(speed_samples), 1)
            if speed_samples else None
        )

        # フルベンチマーク
        result: BenchmarkResult = self.run_benchmark(chat_fn)

        # ケースごとの基準別平均
        criterion_totals: Dict[str, List[float]] = {}
        for cr in result.case_results:
            for name, score in cr.scores:
                criterion_totals.setdefault(name, []).append(score)
        criterion_avgs: Dict[str, float] = {
            name: round(sum(vals) / len(vals), 4)
            for name, vals in criterion_totals.items()
            if vals
        }

        return {
            "inference_speed": {
                "avg_ms": avg_speed,
                "samples": len(speed_samples),
            },
            "bypass_rate": bypass_rate,
            "quality_scores": {
                "overall": result.overall_score,
                "by_criterion": criterion_avgs,
                "case_count": len(result.case_results),
            },
            "system_info": {
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "machine": platform.machine(),
            },
            "generated_at": result.timestamp,
        }

    @staticmethod
    def export_report(
        report: Dict[str, Any],
        path: str | Path,
        fmt: str = "json",
    ) -> Path:
        """レポートをファイルにエクスポートする。

        Args:
            report: generate_public_report() の戻り値。
            path: 出力先ファイルパス。
            fmt: "json" のみサポート。

        Returns:
            書き出し先の Path。
        """
        out: Path = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            out.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            raise ValueError(f"未対応フォーマット: {fmt!r}")
        logger.info("品質レポートをエクスポート: %s", out)
        return out

    # ── #51: 日次クイックチェック ───────────────────────────

    _QUICK_INPUTS: Tuple[str, ...] = (
        "おはよう",
        "今日は嬉しいことがあったよ",
        "明日の天気教えて",
        "うん",
        "アイちゃんって誰？",
    )

    def run_daily_check(self, chat_fn: Callable[[str], str]) -> Dict[str, Any]:
        """5つの定型入力で手軽に品質を測定する。

        Returns:
            {"score": float (0-100), "details": [...], "timestamp": str}
        """
        details: List[Dict[str, Any]] = []
        for inp in self._QUICK_INPUTS:
            try:
                response: str = chat_fn(inp)
            except Exception as exc:
                logger.warning("日次チェック実行エラー (%s): %s", inp, exc)
                response = ""

            scores: List[Tuple[str, float]] = []
            for name, fn in _CC:
                try:
                    s: float = fn(response)
                except Exception:
                    s = 0.0
                scores.append((name, max(0.0, min(1.0, s))))

            avg: float = sum(v for _, v in scores) / len(scores) if scores else 0.0
            details.append({
                "input": inp,
                "average": round(avg, 4),
                "scores": {n: round(v, 4) for n, v in scores},
            })

        overall: float = (
            sum(d["average"] for d in details) / len(details) * 100
            if details else 0.0
        )

        return {
            "score": round(overall, 2),
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def save_daily_score(
        score: float,
        data_dir: str | Path = "data",
    ) -> Path:
        """日次スコアを data/daily_scores.jsonl に追記する。

        Args:
            score: 0-100 のスコア。
            data_dir: データディレクトリ。

        Returns:
            書き込み先の Path。
        """
        path: Path = Path(data_dir) / "daily_scores.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        entry: Dict[str, Any] = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "score": round(score, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("日次スコア保存: %.2f -> %s", score, path)
        return path

    @staticmethod
    def get_score_trend(
        days: int = 30,
        data_dir: str | Path = "data",
    ) -> List[Dict[str, Any]]:
        """直近N日間の日次スコア推移を返す。

        Args:
            days: 取得する日数。
            data_dir: データディレクトリ。

        Returns:
            [{"date": "YYYY-MM-DD", "score": float}, ...] 日付昇順。
        """
        path: Path = Path(data_dir) / "daily_scores.jsonl"
        if not path.exists():
            return []

        all_entries: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped: str = line.strip()
                if stripped:
                    try:
                        all_entries.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        pass

        # 直近 N 日のみ
        if len(all_entries) > days:
            all_entries = all_entries[-days:]

        return [
            {"date": e.get("date", ""), "score": e.get("score", 0.0)}
            for e in all_entries
        ]

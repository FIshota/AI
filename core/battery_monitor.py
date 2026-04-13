"""
バッテリー監視エンジン（機能⑥）
pmset コマンドでバッテリー残量を取得します。追加インストール不要・完全ローカル。
"""
from __future__ import annotations
import subprocess
import re
import platform
import threading
import time

IS_MAC = platform.system() == "Darwin"


def get_battery_info() -> dict:
    """
    現在のバッテリー情報を返す。
    戻り値: {"percent": int, "charging": bool, "found": bool}
    """
    if not IS_MAC:
        return {"percent": 100, "charging": True, "found": False}
    try:
        res = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True, text=True, timeout=5
        )
        output = res.stdout
        # パーセント抽出: "	 63%; discharging; ..."
        m = re.search(r'(\d+)%', output)
        percent = int(m.group(1)) if m else -1
        charging = "charging" in output.lower() or "AC Power" in output
        return {"percent": percent, "charging": charging, "found": percent >= 0}
    except Exception:
        return {"percent": -1, "charging": False, "found": False}


def get_battery_hint() -> str | None:
    """
    会話に自然に組み込むためのバッテリーヒント文字列を返す。
    問題ない場合は None。
    """
    info = get_battery_info()
    if not info["found"]:
        return None
    pct = info["percent"]
    if info["charging"]:
        return None   # 充電中は通知不要
    if pct <= 10:
        return f"バッテリーが{pct}%だよ！今すぐ充電して！"
    if pct <= 20:
        return f"バッテリーが{pct}%になってるよ。そろそろ充電したほうがいいかも。"
    return None


class BatteryMonitor(threading.Thread):
    """
    バックグラウンドでバッテリーを監視し、
    閾値を下回ったときにコールバックを呼ぶスレッド。
    """

    def __init__(
        self,
        callback,
        warn_thresholds: list[int] | None = None,
        check_interval: int = 120,   # 2分おきにチェック
    ):
        super().__init__(daemon=True)
        self._callback        = callback
        self._thresholds      = sorted(warn_thresholds or [20, 10], reverse=True)
        self._interval        = check_interval
        self._notified: set[int] = set()
        self._stop_event      = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            info = get_battery_info()
            if info["found"] and not info["charging"]:
                pct = info["percent"]
                for thr in self._thresholds:
                    if pct <= thr and thr not in self._notified:
                        self._notified.add(thr)
                        try:
                            self._callback(pct)
                        except Exception:
                            pass
                # 充電したら通知済みリセット
            elif info.get("charging"):
                self._notified.clear()

            self._stop_event.wait(self._interval)

    def stop(self):
        self._stop_event.set()

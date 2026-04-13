"""
テキスト読み上げエンジン（機能①）
macOS 組み込みの say コマンドを使います。追加インストール不要・完全ローカル。
"""
from __future__ import annotations
import subprocess
import threading
import platform

IS_MAC = platform.system() == "Darwin"

# macOS に標準搭載されている日本語音声
VOICES_JA_DEFAULT = ["Kyoko", "Otoya"]


class TTSEngine:
    """
    macOS say コマンドラッパー。
    enabled=False の場合は speak() が何もしない（安全なno-op）。
    """

    def __init__(self, enabled: bool = False, voice: str = "Kyoko", rate: int = 175):
        self.enabled = enabled
        self.voice   = voice
        self.rate    = rate        # 読み上げ速度 (words per minute)
        self._proc: subprocess.Popen | None = None
        self._lock   = threading.Lock()

    # ─── 公開 API ────────────────────────────────────────────────

    def speak(self, text: str, blocking: bool = False):
        """テキストを読み上げる。enabled=False の場合は何もしない。"""
        if not self.enabled or not IS_MAC:
            return
        clean = _clean_for_tts(text)
        if not clean:
            return

        if blocking:
            self._run(clean)
        else:
            threading.Thread(target=self._run, args=(clean,), daemon=True).start()

    def stop(self):
        """現在の読み上げを停止する。"""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc = None

    def is_speaking(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ─── 内部 ────────────────────────────────────────────────────

    def _run(self, text: str):
        with self._lock:
            # 前の発話を強制停止
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            try:
                self._proc = subprocess.Popen(
                    ["say", "-v", self.voice, "-r", str(self.rate), text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._proc.wait()
            except FileNotFoundError:
                pass  # say コマンドがない環境（非 macOS）
            except Exception as e:
                print(f"[TTS] エラー: {e}", flush=True)

    # ─── ユーティリティ ──────────────────────────────────────────

    @staticmethod
    def available_japanese_voices() -> list[str]:
        """インストール済みの日本語音声一覧を返す"""
        if not IS_MAC:
            return []
        try:
            res = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True, text=True, timeout=5
            )
            voices = []
            for line in res.stdout.splitlines():
                if "ja_JP" in line or "ja-JP" in line:
                    name = line.split()[0]
                    voices.append(name)
            return voices or VOICES_JA_DEFAULT
        except Exception:
            return VOICES_JA_DEFAULT


def _clean_for_tts(text: str) -> str:
    """読み上げに不向きな文字を除去する"""
    import re
    # 絵文字・記号除去
    text = re.sub(r'[^\u3000-\u9FFF\u30A0-\u30FF\u3040-\u309F\uFF00-\uFFEF'
                  r'a-zA-Z0-9\s、。！？「」『』…・ー〜]', '', text)
    text = text.replace("💗", "").replace("✨", "").replace("💕", "")
    return text.strip()

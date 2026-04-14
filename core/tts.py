"""
テキスト読み上げエンジン（機能①）
macOS 組み込みの say コマンドを使います。追加インストール不要・完全ローカル。

Phase B: 文単位逐次読み上げ対応
  - speak_sentence_by_sentence(): フル応答を句点で分割して逐次再生
  - speak_with_callback(): 読み上げ完了後にコールバックを呼ぶ
"""
from __future__ import annotations
import re
import subprocess
import threading
import platform
from typing import Callable, Optional

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

    def speak_sentence_by_sentence(self, text: str, blocking: bool = False):
        """
        文単位で逐次読み上げ。フル応答の say 一括読みより自然な体験。
        blocking=True の場合は全文読み終わるまでブロック。
        blocking=False の場合はバックグラウンドスレッドで実行。
        """
        if not self.enabled or not IS_MAC:
            return
        if not text or not text.strip():
            return

        if blocking:
            self._speak_sentences(text)
        else:
            threading.Thread(
                target=self._speak_sentences, args=(text,), daemon=True
            ).start()

    def speak_with_callback(
        self, text: str, on_done: Optional[Callable] = None, sentence_mode: bool = True
    ):
        """
        テキストを読み上げ、完了後に on_done を呼ぶ。
        sentence_mode=True の場合は文単位逐次読み上げを使う。
        常にバックグラウンドスレッドで実行。
        """
        if not self.enabled or not IS_MAC:
            if on_done:
                on_done()
            return

        def _worker():
            if sentence_mode:
                self._speak_sentences(text)
            else:
                clean = _clean_for_tts(text)
                if clean:
                    self._run(clean)
            if on_done:
                on_done()

        threading.Thread(target=_worker, daemon=True).start()

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

    def _speak_sentences(self, text: str):
        """テキストを文に分割して順番に読み上げる（ブロッキング）"""
        sentences = _split_sentences(text)
        for sentence in sentences:
            clean = _clean_for_tts(sentence)
            if clean:
                self._run(clean)  # 1文ずつブロッキング再生

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


def _split_sentences(text: str) -> list:
    """テキストを日本語の文末記号で分割する"""
    # 句点・感嘆符・疑問符・改行で分割（区切り文字を前の文に含める）
    parts = re.split(r'(?<=[。！？\n])', text)
    return [s.strip() for s in parts if s.strip()]


def _clean_for_tts(text: str) -> str:
    """読み上げに不向きな文字を除去する"""
    # 絵文字・記号除去
    text = re.sub(r'[^\u3000-\u9FFF\u30A0-\u30FF\u3040-\u309F\uFF00-\uFFEF'
                  r'a-zA-Z0-9\s、。！？「」『』…・ー〜]', '', text)
    text = text.replace("💗", "").replace("✨", "").replace("💕", "")
    return text.strip()

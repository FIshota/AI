"""Real-time Chinese -> Japanese translator with minutes logging.

Improvements vs v1:
- faster-whisper large-v3 (or medium) for better ZH accuracy
- VAD-based segmentation (natural speech boundaries) with overlap window
- beam_size=5, initial_prompt for domain context
- translation uses previous 2 lines as context, repeat_penalty to kill loops
- longer rolling buffer so sentences aren't cut mid-word

Usage:
    python3 tools/live_translator.py --device N [--model large-v3] [--domain "..."]
"""
from __future__ import annotations

import argparse
import datetime as dt
import queue
import signal
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "sarashina2-7b.Q4_K_M.gguf"

SAMPLE_RATE = 16000
WINDOW_SECONDS = 10.0
STEP_SECONDS = 10.0
MAX_QUEUE_BACKLOG = 1  # drop older chunks if processing falls behind
SILENCE_THRESHOLD = 0.002
MIN_SEGMENT_CHARS = 2
TARGET_RMS = 0.15

DOMAIN_VOCAB_ZH = "这是一段普通话商业会议的对话。"

FEWSHOT_PAIRS: list[tuple[str, str]] = [
    ("主播和粉丝之间的互动很重要。", "配信者とファンの間のインタラクションはとても重要です。"),
    ("用户通过打赏送礼物给主播。", "ユーザーは投げ銭で配信者にギフトを送ります。"),
    ("我们通过节目脚本让粉丝付费。", "私たちは番組台本を通じてファンに課金を促します。"),
    ("虚拟偶像的商业模式和传统偶像不一样。", "バーチャルアイドルのビジネスモデルは従来のアイドルとは異なります。"),
    ("这个功能在国内已经很成熟了。", "この機能は中国国内ではすでに成熟しています。"),
]


def list_devices() -> None:
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"  [{i}] {d['name']}  (in:{d['max_input_channels']})")


def pick_device(preferred: int | None) -> int:
    if preferred is not None:
        return preferred
    print("Available input devices:")
    list_devices()
    return int(input("Select device index: ").strip())


class RollingRecorder:
    """Rolling audio buffer; emits overlapping windows every STEP seconds."""

    def __init__(self, device: int, channels: int = 1,
                 window_s: float = WINDOW_SECONDS, step_s: float = STEP_SECONDS):
        self.device = device
        self.channels = channels
        self.window = int(SAMPLE_RATE * window_s)
        self.step = int(SAMPLE_RATE * step_s)
        self.buffer = np.zeros(0, dtype=np.float32)
        self.last_emit = 0
        self.q: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        mono = (indata[:, 0] if indata.ndim == 2 else indata).astype(np.float32)
        with self._lock:
            self.buffer = np.concatenate([self.buffer, mono.copy()])
            if len(self.buffer) > self.window * 3:
                self.buffer = self.buffer[-self.window * 3:]
                self.last_emit = max(0, self.last_emit - (len(self.buffer) - self.window * 3))
            while len(self.buffer) - self.last_emit >= self.step and len(self.buffer) >= self.window:
                start = max(0, len(self.buffer) - self.window)
                self.q.put(self.buffer[start:].copy())
                self.last_emit = len(self.buffer)

    def start(self) -> None:
        self._stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=SAMPLE_RATE,
            callback=self._callback,
            blocksize=0,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()


def load_whisper(model_size: str) -> WhisperModel:
    print(f"[whisper] loading '{model_size}' (first run downloads it, large-v3 ~3GB)...")
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def load_translator():
    if not MODEL_PATH.exists():
        print(f"[warn] {MODEL_PATH} not found — translation disabled.")
        return None
    from llama_cpp import Llama
    print(f"[llama] loading {MODEL_PATH.name}...")
    return Llama(
        model_path=str(MODEL_PATH),
        n_ctx=4096,
        n_threads=4,
        n_gpu_layers=0,
        verbose=False,
    )


def translate_zh_to_ja(llm, text: str, context: list[tuple[str, str]], domain: str) -> str:
    if llm is None or not text.strip():
        return ""
    system = (
        "あなたは中国語から日本語へのプロの同時通訳者です。"
        "次のルールを厳守してください:\n"
        "1. 自然で簡潔な日本語に訳す。直訳調にしない。\n"
        "2. 専門用語は業界慣用訳に揃える（例: 直播=ライブ配信、打赏=投げ銭、饭圈=ファンダム）。\n"
        "3. 固有名詞は原表記を尊重（TikTok, B站, VTuber 等）。\n"
        "4. 原文が不完全でも、最も自然な日本語訳一行のみを出力する。\n"
        "5. 説明・言い換え・繰り返し・英語の付記は禁止。\n"
    )
    if domain:
        system += f"\n会話の背景: {domain}\n"
    # Few-shot examples (fixed) + recent conversation context.
    fewshot_block = "".join(f"中文: {zh}\n日本語: {ja}\n\n" for zh, ja in FEWSHOT_PAIRS)
    ctx_block = "".join(f"中文: {zh}\n日本語: {ja}\n\n" for zh, ja in context[-3:])
    prompt = (
        f"{system}\n### 例\n\n{fewshot_block}"
        f"### 直近の会話\n\n{ctx_block}"
        f"### 翻訳\n中文: {text}\n日本語:"
    )
    out = llm(
        prompt,
        max_tokens=180,
        temperature=0.15,
        top_p=0.85,
        top_k=30,
        repeat_penalty=1.3,
        frequency_penalty=0.4,
        presence_penalty=0.25,
        stop=["\n", "中文:", "中国語:", "日本語:", "###"],
    )
    result = out["choices"][0]["text"].strip()
    result = _dedupe_repeats(result)
    # Clean trailing punctuation glitches.
    result = result.lstrip("：:").strip()
    return result


def _dedupe_repeats(s: str) -> str:
    """Collapse runs of a phrase repeated 4+ times into 1 copy."""
    if not s:
        return s
    for n in (2, 3, 4, 5, 6, 8, 10):
        for i in range(len(s) - n * 4):
            phrase = s[i:i + n]
            if not phrase.strip():
                continue
            repeats = 1
            j = i + n
            while j + n <= len(s) and s[j:j + n] == phrase:
                repeats += 1
                j += n
            if repeats >= 4:
                s = s[:i + n] + s[j:]
                return _dedupe_repeats(s)
    return s


def is_silent(audio: np.ndarray) -> bool:
    return float(np.abs(audio).mean()) < SILENCE_THRESHOLD


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """RMS-normalize loud-enough audio; leave quiet audio alone."""
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 0.003:  # truly silent — leave alone
        return audio
    gain = min(TARGET_RMS / rms, 15.0)
    out = audio * gain
    return np.clip(out, -0.99, 0.99).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--model", default="large-v3",
                    help="whisper size: tiny/base/small/medium/large-v3 (default large-v3)")
    ap.add_argument("--domain", default="TikTok・ライブ配信・バーチャルアイドル・ファン経済に関するビジネス会議",
                    help="context hint for better translation")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "logs" / f"minutes_{dt.datetime.now():%Y%m%d_%H%M%S}.md")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-translate", action="store_true")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return 0

    device = pick_device(args.device)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    whisper = load_whisper(args.model)
    llm = None if args.no_translate else load_translator()

    header = (
        f"# 議事録 / 翻訳ログ\n\n"
        f"- 開始: {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"- デバイス: [{device}] {sd.query_devices(device)['name']}\n"
        f"- STT: faster-whisper {args.model} (VAD, beam=5)\n"
        f"- 翻訳: {'sarashina2-7b + context' if llm else '(無効)'}\n"
        f"- ドメイン: {args.domain}\n\n"
        f"| 時刻 | 中国語(原文) | 日本語(訳) |\n"
        f"|------|------------|------------|\n"
    )
    args.out.write_text(header, encoding="utf-8")
    print(f"[log] writing to {args.out}")

    recorder = RollingRecorder(device=device)

    stop_flag = threading.Event()

    def handle_sigint(*_):
        print("\n[main] stopping...")
        stop_flag.set()

    signal.signal(signal.SIGINT, handle_sigint)

    recorder.start()
    print(f"[main] listening... (Ctrl+C to stop)  window={WINDOW_SECONDS}s step={STEP_SECONDS}s")

    seen_texts: deque[str] = deque(maxlen=8)
    context_pairs: list[tuple[str, str]] = []
    whisper_prompt = DOMAIN_VOCAB_ZH

    try:
        while not stop_flag.is_set():
            try:
                audio = recorder.q.get(timeout=0.5)
            except queue.Empty:
                continue

            # Drop stale chunks if we've fallen behind — realtime > completeness.
            dropped = 0
            while recorder.q.qsize() > MAX_QUEUE_BACKLOG:
                try:
                    audio = recorder.q.get_nowait()
                    dropped += 1
                except queue.Empty:
                    break
            if dropped:
                print(f"[main] dropped {dropped} stale chunks to catch up", flush=True)

            if is_silent(audio):
                continue

            audio = normalize_audio(audio)

            t0 = time.time()
            segments, info = whisper.transcribe(
                audio,
                language="zh",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300, "threshold": 0.2},
                beam_size=5,
                best_of=5,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.4,
                condition_on_previous_text=False,
                initial_prompt=whisper_prompt,
            )
            zh_text = " ".join(seg.text.strip() for seg in segments).strip()
            zh_text = _dedupe_repeats(zh_text)
            if len(zh_text) < MIN_SEGMENT_CHARS:
                continue

            # Skip if we just emitted this text (overlap windows duplicate).
            if any(zh_text == prev or (len(zh_text) >= 6 and zh_text in prev)
                   or (len(prev) >= 6 and prev in zh_text) for prev in seen_texts):
                continue
            seen_texts.append(zh_text)

            ja_text = translate_zh_to_ja(llm, zh_text, context_pairs, args.domain) if llm else ""
            if ja_text:
                context_pairs.append((zh_text, ja_text))
                context_pairs[:] = context_pairs[-6:]

            elapsed = time.time() - t0
            ts = dt.datetime.now().strftime("%H:%M:%S")
            print(f"\n[{ts}] ({elapsed:.1f}s)")
            print(f"  ZH: {zh_text}")
            if ja_text:
                print(f"  JA: {ja_text}")

            zh_cell = zh_text.replace("|", "｜").replace("\n", " ")
            ja_cell = ja_text.replace("|", "｜").replace("\n", " ")
            with args.out.open("a", encoding="utf-8") as f:
                f.write(f"| {ts} | {zh_cell} | {ja_cell} |\n")
    finally:
        recorder.stop()
        with args.out.open("a", encoding="utf-8") as f:
            f.write(f"\n- 終了: {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        print(f"[main] saved: {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

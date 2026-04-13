"""
YouTube 学習エンジン
yt-dlp で字幕を取得し、Phi-3 で要約して学習データとして保存します。

オフラインファースト設計:
- ネットワークは字幕取得時のみ使用
- 取得済みの字幕はローカルにキャッシュ → 次回以降はオフラインで参照可
- yt-dlp 未インストールでも動作（機能制限メッセージを返すのみ）
"""
from __future__ import annotations
import subprocess
import json
import re
import tempfile
import os
from pathlib import Path
from datetime import datetime


# YouTube URL にマッチする正規表現
_YT_URL_RE = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s]*v=|youtu\.be/)[\w\-]+'
)

# yt-dlp の実行パスを解決（pip install 後に PATH 外にある場合を考慮）
def _find_ytdlp() -> str:
    """yt-dlp の実行可能パスを返す。見つからなければ 'yt-dlp' をそのまま返す"""
    candidates = [
        "/Users/fujihiranoborudai/Library/Python/3.9/bin/yt-dlp",
        os.path.expanduser("~/Library/Python/3.9/bin/yt-dlp"),
        os.path.expanduser("~/.local/bin/yt-dlp"),
        "/usr/local/bin/yt-dlp",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "yt-dlp"

_YTDLP = _find_ytdlp()


def extract_youtube_url(text: str) -> str | None:
    """テキストから最初の YouTube URL を抽出して返す"""
    m = _YT_URL_RE.search(text)
    return m.group(0) if m else None


def _clean_vtt(vtt: str) -> str:
    """VTT/SRT 形式の字幕をプレーンテキストに変換"""
    lines = vtt.splitlines()
    result = []
    seen: set[str] = set()
    for line in lines:
        line = line.strip()
        if (not line
                or line.startswith("WEBVTT")
                or "-->" in line
                or line.isdigit()
                or re.match(r'^\d+:\d+', line)):
            continue
        # HTML タグ除去
        line = re.sub(r'<[^>]+>', '', line).strip()
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return " ".join(result)


class YouTubeLearner:
    """
    YouTube 字幕学習エンジン
    - fetch_transcript(): yt-dlp で字幕取得（ネットワーク必要、結果をキャッシュ）
    - summarize(): Phi-3 で要約（完全ローカル）
    - store(): learning/ に JSONL として保存（完全ローカル）
    """

    def __init__(self, data_dir: Path, learning_dir: Path):
        self.data_dir    = Path(data_dir)
        self.learning_dir = Path(learning_dir)
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self.data_dir / "youtube_cache.json"
        self._cache: dict[str, dict] = self._load_cache()

    # ─── キャッシュ ─────────────────────────────────────────────

    def _load_cache(self) -> dict:
        if self._cache_path.exists():
            try:
                return json.loads(self._cache_path.read_text("utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2), "utf-8"
        )

    def is_cached(self, url: str) -> bool:
        return url in self._cache

    # ─── 字幕取得 ────────────────────────────────────────────────

    def fetch_transcript(self, url: str) -> dict:
        """
        字幕を取得します（ネットワーク必要）。
        キャッシュがあればネットワーク不要でキャッシュを返します。

        戻り値:
          成功: {"url", "title", "transcript", "lang", "fetched_at"}
          失敗: {"error": "..."}
        """
        # キャッシュヒット
        if url in self._cache:
            return self._cache[url]

        # yt-dlp の存在確認
        try:
            subprocess.run(
                [_YTDLP, "--version"],
                capture_output=True, timeout=5
            )
        except FileNotFoundError:
            return {
                "error": (
                    "yt-dlp が見つかりません。\n"
                    "`pip install yt-dlp` でインストールしてね。"
                )
            }
        except Exception:
            pass

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)

                # 動画メタ情報取得
                info_res = subprocess.run(
                    [_YTDLP, "--dump-json", "--no-playlist", url],
                    capture_output=True, text=True, timeout=30
                )
                if info_res.returncode != 0:
                    return {"error": "動画情報の取得に失敗したよ。URLが正しいか確認してね。"}

                info = json.loads(info_res.stdout)
                title = info.get("title", "不明な動画")

                # 字幕ダウンロード（日本語優先 → 英語）
                subprocess.run(
                    [
                        _YTDLP,
                        "--write-auto-sub", "--write-sub",
                        "--sub-lang", "ja,ja-JP,en",
                        "--sub-format", "vtt",
                        "--skip-download",
                        "--no-playlist",
                        "-o", str(tmp / "caption"),
                        url,
                    ],
                    capture_output=True, text=True, timeout=60
                )

                # VTT ファイルを探す
                vtt_files = list(tmp.glob("*.vtt"))
                if not vtt_files:
                    # 字幕なし → description を代用
                    desc = (info.get("description") or "")[:800]
                    if not desc:
                        return {"error": "この動画には字幕がないよ。"}
                    result = {
                        "url": url,
                        "title": title,
                        "transcript": desc,
                        "lang": "desc",
                        "fetched_at": datetime.now().isoformat()[:16],
                    }
                    self._cache[url] = result
                    self._save_cache()
                    return result

                # 日本語優先
                ja_files = [f for f in vtt_files
                            if ".ja" in f.name or "ja-JP" in f.name]
                target = ja_files[0] if ja_files else vtt_files[0]
                raw = target.read_text("utf-8", errors="ignore")
                transcript = _clean_vtt(raw)

                if not transcript.strip():
                    return {"error": "字幕のテキスト抽出に失敗したよ。"}

                result = {
                    "url": url,
                    "title": title,
                    "transcript": transcript,
                    "lang": "ja" if ja_files else "en",
                    "fetched_at": datetime.now().isoformat()[:16],
                }
                self._cache[url] = result
                self._save_cache()
                return result

        except subprocess.TimeoutExpired:
            return {"error": "タイムアウト。ネットワークが遅いかもしれないよ。"}
        except Exception as e:
            return {"error": f"取得中にエラーが起きたよ: {e}"}

    # ─── 要約・保存 ──────────────────────────────────────────────

    def summarize_with_llm(self, data: dict, llm_engine) -> str:
        """
        Phi-3 を使って字幕を要約します（完全ローカル）。
        llm_engine: LLMEngine インスタンス
        """
        transcript = data.get("transcript", "")
        title      = data.get("title", "動画")

        # コンテキスト長の都合でトリミング（約1200字）
        snippet = transcript[:1200]

        prompt_text = (
            f"この動画のタイトルは「{title}」で、字幕の一部はこれだよ：\n"
            f"{snippet}\n\n"
            "この内容を日本語で2〜3文にまとめて教えて。"
        )

        try:
            from core.llm import LLMEngine
            messages = [
                {"role": "system",
                 "content": "日本語で簡潔に要約してください。"},
                {"role": "user", "content": prompt_text},
            ]
            result = llm_engine.generate_chat(messages)
            return result.strip() if result.strip() else transcript[:200]
        except Exception:
            return transcript[:200]

    def store(self, data: dict, summary: str) -> bool:
        """学習データ（JSONL）として保存。完全ローカル。"""
        target = self.learning_dir / "youtube_learned.jsonl"
        entry = {
            "url":        data["url"],
            "title":      data["title"],
            "user":       f"{data['title']}について教えて",
            "ai":         summary,
            "transcript_snippet": data.get("transcript", "")[:400],
            "lang":       data.get("lang", ""),
            "learned_at": datetime.now().isoformat()[:16],
        }
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True

    # ─── 一覧・統計 ──────────────────────────────────────────────

    def list_learned(self) -> list[dict]:
        """学習済み YouTube 動画一覧"""
        target = self.learning_dir / "youtube_learned.jsonl"
        if not target.exists():
            return []
        results = []
        for line in target.read_text("utf-8").splitlines():
            if line.strip():
                try:
                    results.append(json.loads(line))
                except Exception:
                    pass
        return results

    def stats(self) -> dict:
        return {
            "learned_videos": len(self.list_learned()),
            "cached_urls":    len(self._cache),
        }

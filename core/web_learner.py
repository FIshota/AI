"""
Web ページ学習エンジン（機能②）
requests + BeautifulSoup4 でページテキストを取得し、Phi-3 で要約して学習します。
オフラインファースト: 取得後はローカルにキャッシュ。

インストール: pip install requests beautifulsoup4
"""
from __future__ import annotations
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

# テキスト・ファイル以外の URL を除外するパターン
_SKIP_EXTENSIONS = re.compile(
    r'\.(jpg|jpeg|png|gif|pdf|mp4|mp3|zip|exe|dmg)(\?|$)', re.I
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def is_web_url(text: str) -> str | None:
    """テキストから HTTP/HTTPS URL を抽出（YouTube・ファイル系は除く）"""
    m = re.search(r'https?://[^\s　]+', text)
    if not m:
        return None
    url = m.group(0).rstrip("。、）』」,.")
    # YouTube は YouTubeLearner が担当
    if "youtube.com" in url or "youtu.be" in url:
        return None
    if _SKIP_EXTENSIONS.search(url):
        return None
    return url


class WebLearner:
    """
    Web ページ学習エンジン。
    - fetch_text(): ページテキストを取得（ネットワーク必要、結果をキャッシュ）
    - store(): learning/ に JSONL として保存（完全ローカル）
    """

    def __init__(self, data_dir: Path, learning_dir: Path):
        self.data_dir     = Path(data_dir)
        self.learning_dir = Path(learning_dir)
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path  = self.data_dir / "web_cache.json"
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

    def _cache_key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def is_cached(self, url: str) -> bool:
        return self._cache_key(url) in self._cache

    # ─── テキスト取得 ────────────────────────────────────────────

    def fetch_text(self, url: str) -> dict:
        """
        ページテキストを取得する（ネットワーク必要）。
        キャッシュがあれば即座に返す。
        戻り値:
          成功: {"url", "title", "text", "fetched_at"}
          失敗: {"error": "..."}
        """
        if not WEB_AVAILABLE:
            return {
                "error": (
                    "requests と beautifulsoup4 が必要です。\n"
                    "pip install requests beautifulsoup4 でインストールしてね。"
                )
            }

        key = self._cache_key(url)
        if key in self._cache:
            return self._cache[key]

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"

            soup = BeautifulSoup(resp.text, "html.parser")

            # タイトル
            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()[:120]

            # 不要タグを除去してテキスト抽出
            for tag in soup(["script", "style", "nav", "footer",
                              "header", "aside", "iframe", "noscript"]):
                tag.decompose()

            raw_text = soup.get_text(separator="\n")
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
            clean_text = "\n".join(lines[:300])  # 先頭 300 行

            result = {
                "url":        url,
                "title":      title or url,
                "text":       clean_text,
                "fetched_at": datetime.now().isoformat()[:16],
            }
            self._cache[key] = result
            self._save_cache()
            return result

        except Exception as e:
            err_map = {
                "ConnectionError":   "接続できなかったよ。ネットワークを確認してね。",
                "Timeout":           "タイムアウトしたよ。もう一度試してね。",
                "HTTPError":         f"HTTP エラー: {e}",
            }
            for k, msg in err_map.items():
                if k in type(e).__name__:
                    return {"error": msg}
            return {"error": f"取得エラー: {e}"}

    # ─── 要約・保存 ──────────────────────────────────────────────

    def summarize_with_llm(self, data: dict, llm_engine) -> str:
        """Phi-3 を使ってページ内容を要約する（完全ローカル）"""
        title   = data.get("title", "ページ")
        snippet = data.get("text", "")[:1200]

        prompt_text = (
            f"このWebページのタイトルは「{title}」です。\n"
            f"内容の抜粋：\n{snippet}\n\n"
            "この内容を日本語で2〜3文にまとめて。"
        )
        try:
            messages = [
                {"role": "system", "content": "日本語で簡潔に要約してください。"},
                {"role": "user",   "content": prompt_text},
            ]
            result = llm_engine.generate_chat(messages)
            return result.strip() if result.strip() else snippet[:200]
        except Exception:
            return snippet[:200]

    def store(self, data: dict, summary: str) -> bool:
        """学習データとして JSONL に保存（完全ローカル）"""
        target = self.learning_dir / "web_learned.jsonl"
        entry = {
            "url":             data["url"],
            "title":           data["title"],
            "user":            f"{data['title']}の内容を教えて",
            "ai":              summary,
            "text_snippet":    data.get("text", "")[:400],
            "learned_at":      datetime.now().isoformat()[:16],
        }
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True

    def list_learned(self) -> list[dict]:
        target = self.learning_dir / "web_learned.jsonl"
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
            "learned_pages":  len(self.list_learned()),
            "cached_urls":    len(self._cache),
        }

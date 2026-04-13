"""
L. 天気・ニュース取得モジュール
settings.json の autonomous.allow_network: true の場合のみ動作します。
外部通信を一切行いたい場合は allow_network: false にしてください。
"""
from __future__ import annotations
import json
import time
from typing import List, Optional

_CACHE: dict = {}
CACHE_TTL = 3600  # 1時間キャッシュ


def _cached(key: str, fn):
    """キャッシュ付き関数呼び出し"""
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    try:
        result = fn()
        _CACHE[key] = {"ts": time.time(), "data": result}
        return result
    except Exception as e:
        print(f"[WebFetcher] {key} 取得失敗: {e}")
        return None


def get_weather(city: str = "Tokyo") -> Optional[str]:
    """wttr.in から天気情報を取得して日本語で返す"""

    def _fetch():
        import urllib.request
        url = f"https://wttr.in/{city}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "AiChan/0.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current  = data["current_condition"][0]
        temp_c   = current["temp_C"]
        desc_code = int(current["weatherCode"])
        weather_jp = _weather_code_to_jp(desc_code)
        return f"{weather_jp}、気温{temp_c}℃"

    return _cached(f"weather_{city}", _fetch)


def get_news_headlines(n: int = 3) -> Optional[List[str]]:
    """NHK RSS から最新ニュースの見出しを取得"""

    def _fetch():
        import urllib.request
        import xml.etree.ElementTree as ET
        url = "https://www3.nhk.or.jp/rss/news/cat0.xml"
        req = urllib.request.Request(url, headers={"User-Agent": "AiChan/0.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            tree = ET.parse(resp)

        headlines = []
        for item in tree.findall(".//item")[:n]:
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                headlines.append(title_el.text.strip())
        return headlines

    return _cached("nhk_news", _fetch)


def build_weather_hint(city: str = "Tokyo") -> str:
    """天気情報をコンテキストヒント文字列として返す"""
    w = get_weather(city)
    if w:
        return f"今日の天気: {w}"
    return ""


def build_news_hint() -> str:
    """ニュース見出しをコンテキストヒント文字列として返す"""
    headlines = get_news_headlines(n=2)
    if headlines:
        return "最近のニュース: " + " / ".join(headlines[:2])
    return ""


def web_search(query: str, max_results: int = 5) -> Optional[List[dict]]:
    """
    DuckDuckGo Lite を使ったWeb検索。
    外部ライブラリ不要（urllib + HTMLパース）。

    Returns:
        [{"title": str, "url": str, "snippet": str}, ...]
    """

    def _fetch():
        import urllib.request
        import urllib.parse
        import re as _re

        encoded = urllib.parse.urlencode({"q": query})
        url = f"https://lite.duckduckgo.com/lite/?{encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # DuckDuckGo Lite の結果を簡易パース
        results: List[dict] = []

        # リンク抽出: class='result-link' or class="result-link"
        link_pattern = _re.compile(
            r"<a[^>]*class=['\"]result-link['\"][^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>"
            r"|<a[^>]*href=['\"]([^'\"]+)['\"][^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>",
            _re.DOTALL,
        )
        # スニペット抽出: <td class='result-snippet'>text</td>
        snippet_pattern = _re.compile(
            r"<td[^>]*class=['\"]result-snippet['\"][^>]*>(.*?)</td>",
            _re.DOTALL,
        )

        raw_links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        # 2つの alternation グループを統合
        links: list = []
        for groups in raw_links:
            href = groups[0] or groups[2]
            title_html = groups[1] or groups[3]
            if href and title_html:
                links.append((href, title_html))

        for i, (href, title_html) in enumerate(links[:max_results]):
            # HTMLタグ除去
            clean_title = _re.sub(r"<[^>]+>", "", title_html).strip()
            # URL デコード（&amp; → &）
            clean_href = href.replace("&amp;", "&")
            clean_snippet = ""
            if i < len(snippets):
                clean_snippet = _re.sub(r"<[^>]+>", "", snippets[i]).strip()
            if clean_title and clean_href:
                results.append({
                    "title": clean_title,
                    "url": clean_href,
                    "snippet": clean_snippet,
                })

        return results if results else None

    cache_key = f"search_{query[:50]}"
    return _cached(cache_key, _fetch)


def web_fetch_text(url: str, max_chars: int = 3000) -> Optional[str]:
    """
    URLからテキストコンテンツを取得する。
    HTMLタグを除去して本文のみ返す。
    """

    def _fetch():
        import urllib.request
        import re as _re

        req = urllib.request.Request(url, headers={
            "User-Agent": "AiChan/0.1",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # script/style 除去
        html = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=_re.DOTALL)
        # タグ除去
        text = _re.sub(r"<[^>]+>", " ", html)
        # 連続空白を正規化
        text = _re.sub(r"\s+", " ", text).strip()
        return text[:max_chars] if text else None

    cache_key = f"fetch_{url[:80]}"
    return _cached(cache_key, _fetch)


def _weather_code_to_jp(code: int) -> str:
    sunny  = {113}
    cloudy = {116, 119, 122}
    fog    = {143, 248, 260}
    rain   = {176, 263, 266, 293, 296, 299, 302, 305, 308,
              311, 314, 317, 353, 356, 359}
    snow   = {179, 182, 185, 281, 284, 323, 326, 329, 332,
              335, 338, 350, 362, 365, 368, 371, 374, 377, 392, 395}
    thunder = {200, 386, 389}

    if code in sunny:   return "晴れ"
    if code in cloudy:  return "曇り"
    if code in fog:     return "霧"
    if code in rain:    return "雨"
    if code in snow:    return "雪"
    if code in thunder: return "雷雨"
    return "くもり"

"""
議事録 構造化抽出エンジン
議事録テキストから アクションアイテム・決定事項・日程 を構造化して取り出す。
LLM による高精度抽出 + 正規表現フォールバック の2段構え。
"""
from __future__ import annotations
import re
from datetime import datetime, date, timedelta
from pathlib import Path

# dateparser は省略可能 (インストール済みなら使う)
try:
    import dateparser
    DATEPARSER_OK = True
except ImportError:
    DATEPARSER_OK = False


# ─── 精度向上プロンプト ──────────────────────────────────────────
# 段階的な思考 (CoT) を促してLLM精度を上げる
EXTRACT_PROMPT = """以下の議事録から構造化情報を抽出してください。

【議事録テキスト】
{minutes_text}

【抽出ルール】
1. アクションアイテム: 「○○さんが〜する」「〜を確認する」など、具体的な行動を含む文
2. 期日: 「〇月〇日までに」「来週中に」「今週末」などの日付・期間の表現
3. 担当者: 人名・役職・「チーム」「全員」など
4. 次回会議: 「次回は〇月〇日」「来週月曜」などの次回日程

【出力形式 — 必ずJSONで出力してください】
{{
  "action_items": [
    {{
      "task": "タスクの内容",
      "owner": "担当者名（不明なら空文字）",
      "due_date": "YYYY-MM-DD形式（不明なら空文字）",
      "due_label": "元の表現（例: 来週金曜）",
      "priority": "high/medium/low"
    }}
  ],
  "decisions": [
    "決定事項1",
    "決定事項2"
  ],
  "next_meeting": {{
    "date": "YYYY-MM-DD形式（不明なら空文字）",
    "label": "元の表現",
    "location": "場所・URL（不明なら空文字）"
  }},
  "keywords": ["キーワード1", "キーワード2"]
}}

JSONのみ出力してください。説明文は不要です。"""


# ─── 改良議事録プロンプト ─────────────────────────────────────────
# 元の MINUTES_FORMAT_PROMPT より精度高い版
IMPROVED_FORMAT_PROMPT = """あなたは経験豊富な議事録作成の専門家です。
以下の音声文字起こしを、正確で読みやすい議事録に変換してください。

【文字起こし】
{transcript}

【参加者情報】
{attendees}

【作成ルール】
- 話し言葉を書き言葉に変換する（「〜なんですけど」→「〜である」）
- 重複・フィラー語（えー、あの、まあ）を除去する
- 発言の意図を正確に保ちながら簡潔にまとめる
- アクションアイテムは必ず「誰が・何を・いつまでに」の形式にする
- 日付は具体的な年月日で表記する（「来週」→推定日付を付記）

【出力形式】
## 議題・目的
（1〜2文で会議の目的）

## 主な議論内容
（重要な議論ポイントを箇条書き・簡潔に）

## 決定事項
（この会議で決まったことのみ・箇条書き）

## アクションアイテム
（形式: ・[担当者] [タスク内容] → 期限: [日付または「要確認」]）

## 次回会議
（日時・場所・議題予定）

## 補足・備考
（特記事項があれば）

日本語で出力してください。"""


class MinutesExtractor:
    """議事録テキストから構造化データを抽出する"""

    def __init__(self):
        self._today = date.today()

    def extract_structured(self, minutes_text: str, llm_engine=None) -> dict:
        """
        議事録テキストから構造化データを抽出。
        LLMがあればJSON抽出、なければ正規表現フォールバック。
        """
        result = {
            "action_items":  [],
            "decisions":     [],
            "next_meeting":  {"date": "", "label": "", "location": ""},
            "keywords":      [],
            "extracted_at":  datetime.now().isoformat()[:16],
        }

        # ── LLM による高精度抽出 ──
        if llm_engine and llm_engine.is_loaded():
            llm_result = self._extract_with_llm(minutes_text, llm_engine)
            if llm_result:
                result.update(llm_result)
                # 日付の正規化
                self._normalize_dates(result)
                return result

        # ── 正規表現フォールバック ──
        result["action_items"] = self._regex_action_items(minutes_text)
        result["decisions"]    = self._regex_decisions(minutes_text)
        result["next_meeting"] = self._regex_next_meeting(minutes_text)
        result["keywords"]     = self._extract_keywords(minutes_text)
        self._normalize_dates(result)
        return result

    # ─── LLM 抽出 ────────────────────────────────────────────────

    def _extract_with_llm(self, text: str, llm_engine) -> dict | None:
        import json
        prompt = EXTRACT_PROMPT.format(minutes_text=text[:2500])
        try:
            messages = [
                {"role": "system",
                 "content": "あなたはJSONを正確に出力する情報抽出AIです。必ずJSON形式で出力してください。"},
                {"role": "user", "content": prompt},
            ]
            raw = llm_engine.generate_chat(messages)
            # JSON部分だけを抽出
            json_match = re.search(r'\{[\s\S]+\}', raw)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"[Extractor] LLM抽出失敗 (フォールバックへ): {e}", flush=True)
        return None

    # ─── 正規表現フォールバック ──────────────────────────────────

    def _regex_action_items(self, text: str) -> list[dict]:
        items = []
        # アクションアイテムセクションを探す
        section = self._get_section(text, ["アクションアイテム", "TODO", "To Do", "タスク"])
        if not section:
            section = text

        # 「・[担当者] [タスク] → 期限:」形式
        pat1 = re.compile(
            r'[・\-\*]\s*(?:\[?([^\]]+?)\]?)?\s*(.{4,60}?)\s*[→→]\s*期限[：:]\s*(.+?)(?:\n|$)'
        )
        for m in pat1.finditer(section):
            items.append({
                "task":      m.group(2).strip(),
                "owner":     m.group(1).strip() if m.group(1) else "",
                "due_label": m.group(3).strip(),
                "due_date":  self._parse_date_str(m.group(3)),
                "priority":  "medium",
            })

        # 「〜する必要がある」「〜を確認」「〜を実施」等を含む行
        if not items:
            action_verbs = r'(する|確認|実施|提出|共有|連絡|対応|検討|作成|準備|報告|修正|送る|送付|整理)'
            due_pat      = r'(?:までに|期限[：:]?\s*)([０-９0-9月日週間]+[まで]?)'
            for line in section.splitlines():
                line = line.strip().lstrip('・-*•')
                if not line or len(line) < 5:
                    continue
                if re.search(action_verbs, line):
                    due_match = re.search(due_pat, line)
                    items.append({
                        "task":      line[:80],
                        "owner":     self._guess_owner(line),
                        "due_label": due_match.group(1) if due_match else "",
                        "due_date":  self._parse_date_str(due_match.group(1)) if due_match else "",
                        "priority":  "medium",
                    })
            # 重複除去
            seen, unique = set(), []
            for item in items:
                key = item["task"][:30]
                if key not in seen:
                    seen.add(key)
                    unique.append(item)
            items = unique[:10]

        return items

    def _regex_decisions(self, text: str) -> list[str]:
        section = self._get_section(text, ["決定事項", "決定", "合意事項"])
        if not section:
            return []
        lines = []
        for line in section.splitlines():
            line = line.strip().lstrip('・-*•')
            if line and len(line) > 4:
                lines.append(line)
        return lines[:8]

    def _regex_next_meeting(self, text: str) -> dict:
        patterns = [
            r'次回(?:は|の)?(?:会議|ミーティング)?[：:\s]*([０-９0-9年月日\s（）()〜〜週]+?)(?:に|で|開催|予定)',
            r'(\d{1,2}月\d{1,2}日)(?:[（(][月火水木金土日][）)])?.*?(?:次回|会議)',
            r'来週(?:の)?([月火水木金土日]曜)?',
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                label = m.group(1) if m.lastindex else m.group(0)
                return {
                    "date":     self._parse_date_str(label),
                    "label":    label.strip(),
                    "location": "",
                }
        return {"date": "", "label": "", "location": ""}

    def _extract_keywords(self, text: str) -> list[str]:
        """頻出名詞をキーワードとして抽出"""
        # カタカナ語・漢字2文字以上の語を頻度順
        candidates = re.findall(r'[ァ-ヶー]{3,}|[一-龠]{2,}', text)
        freq: dict[str, int] = {}
        stopwords = {'会議', 'ミーティング', '議事録', 'について', 'ために', 'として'}
        for w in candidates:
            if w not in stopwords:
                freq[w] = freq.get(w, 0) + 1
        return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])][:8]

    # ─── 日付解析 ─────────────────────────────────────────────────

    def _parse_date_str(self, label: str | None) -> str:
        """自然言語の日付表現を YYYY-MM-DD に変換"""
        if not label:
            return ""
        label = label.strip()
        if not label:
            return ""

        # すでに YYYY-MM-DD 形式
        if re.match(r'^\d{4}-\d{2}-\d{2}$', label):
            return label

        # dateparser ライブラリを使う
        if DATEPARSER_OK:
            try:
                dt = dateparser.parse(
                    label,
                    languages=["ja"],
                    settings={"PREFER_DATES_FROM": "future",
                               "RELATIVE_BASE": datetime.now()},
                )
                if dt:
                    return dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        # 手動パース（dateparser なし）
        today = date.today()
        if '来週' in label:
            days = {'月': 0, '火': 1, '水': 2, '木': 3, '金': 4, '土': 5, '日': 6}
            m = re.search(r'([月火水木金土日])曜', label)
            if m:
                target_wd = days[m.group(1)]
                cur_wd    = today.weekday()
                delta     = (target_wd - cur_wd + 7) % 7 or 7
                return (today + timedelta(days=delta + 7)).strftime("%Y-%m-%d")
            return (today + timedelta(weeks=1)).strftime("%Y-%m-%d")

        if '今週' in label:
            days = {'月': 0, '火': 1, '水': 2, '木': 3, '金': 4, '土': 5, '日': 6}
            m = re.search(r'([月火水木金土日])曜', label)
            if m:
                target_wd = days[m.group(1)]
                cur_wd    = today.weekday()
                delta     = (target_wd - cur_wd) % 7
                return (today + timedelta(days=delta)).strftime("%Y-%m-%d")

        m = re.search(r'(\d{1,2})月(\d{1,2})日', label)
        if m:
            mo, dy = int(m.group(1)), int(m.group(2))
            yr = today.year
            try:
                d = date(yr, mo, dy)
                if d < today:
                    d = date(yr + 1, mo, dy)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                pass

        return ""

    def _normalize_dates(self, result: dict):
        """全アクションアイテムの due_date を正規化"""
        for item in result.get("action_items", []):
            if item.get("due_label") and not item.get("due_date"):
                item["due_date"] = self._parse_date_str(item["due_label"])

        nm = result.get("next_meeting", {})
        if nm.get("label") and not nm.get("date"):
            nm["date"] = self._parse_date_str(nm["label"])

    # ─── ヘルパー ────────────────────────────────────────────────

    def _get_section(self, text: str, headers: list[str]) -> str:
        """## ヘッダー以降の本文を取得"""
        for header in headers:
            pat = re.compile(rf'#+\s*{header}.*?\n([\s\S]+?)(?=\n##|\Z)', re.M)
            m = pat.search(text)
            if m:
                return m.group(1)
        return ""

    def _guess_owner(self, line: str) -> str:
        """行から担当者名を推定（姓2文字＋さん/氏 パターン）"""
        m = re.search(r'([一-龠]{2,4}(?:さん|氏|君|さま)?)', line)
        return m.group(1) if m else ""

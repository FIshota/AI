"""
会話知能エンジン (Conversation Intelligence)
Sprint K1: アイの会話品質を国産AIレベルに引き上げる。

機能:
- 文脈チェーン推論（前の会話から論理的に推論）
- 意図分類（質問/相談/雑談/報告/依頼を識別）
- 応答戦略選択（意図に最適な応答パターンを選択）
- 会話深度管理（表面的→深い会話への誘導）
- 日本語品質フィルタ（不自然な表現を検出・修正）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ─── 意図分類 ────────────────────────────────────────────────

@dataclass(frozen=True)
class ConversationIntent:
    """会話の意図を表すデータ"""
    intent_type: str       # question, consultation, chat, report, request, greeting, emotion
    confidence: float      # 0.0 ~ 1.0
    sub_type: str = ""     # 詳細分類
    keywords: tuple = ()   # 検出されたキーワード


# 意図検出パターン（優先度順）
_INTENT_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    # (intent_type, sub_type, pattern)
    ("greeting", "morning", re.compile(r"(おはよう|おはー|グッドモーニング)")),
    ("greeting", "evening", re.compile(r"(おやすみ|おつかれ|お疲れ|ただいま)")),
    ("greeting", "general", re.compile(r"^(こんにちは|こんばんは|やっほー|ひさしぶり|久しぶり)")),
    ("emotion", "positive", re.compile(r"(嬉しい|楽しい|幸せ|最高|やった|ありがとう|好き|大好き)")),
    ("emotion", "negative", re.compile(r"(悲しい|辛い|つらい|しんどい|嫌|怒り|イライラ|不安|心配|怖い|泣)")),
    ("question", "factual", re.compile(r"(って何|とは|教えて|知ってる|分かる|意味|どういう|なぜ|なんで|どうして)")),
    ("question", "opinion", re.compile(r"(どう思う|どう感じ|意見|アドバイス|おすすめ|どっち)")),
    ("question", "personal", re.compile(r"(好き.*(何|なに)|趣味|夢|目標|将来)")),
    ("consultation", "worry", re.compile(r"(相談|悩み|困って|どうしたらいい|助けて|聞いて)")),
    ("consultation", "decision", re.compile(r"(迷って|決められ|選べ|判断)")),
    ("request", "action", re.compile(r"(して(ほしい|くれ|ください)|お願い|頼み|やって)")),
    ("request", "command", re.compile(r"(覚えて|忘れて|見せて|確認|チェック|検索|登録)")),
    ("report", "daily", re.compile(r"(今日.*した|〜した|終わった|できた|行った|食べた|見た)")),
    ("report", "event", re.compile(r"(〜があった|起きた|聞いた|知った|出来事)")),
    ("chat", "bored", re.compile(r"(暇|ひま|つまらない|退屈|何もない)")),
    ("chat", "playful", re.compile(r"(遊ぼ|ゲーム|クイズ|しりとり|冗談|面白い)")),
]


def classify_intent(text: str) -> ConversationIntent:
    """ユーザーの発話意図を分類する"""
    text_lower = text.strip()

    for intent_type, sub_type, pattern in _INTENT_PATTERNS:
        match = pattern.search(text_lower)
        if match:
            return ConversationIntent(
                intent_type=intent_type,
                confidence=0.8,
                sub_type=sub_type,
                keywords=(match.group(0),),
            )

    # 疑問符で終わる → question
    if text_lower.endswith(("?", "？")):
        return ConversationIntent(intent_type="question", confidence=0.6, sub_type="general")

    # 感嘆符多め → emotion
    if text_lower.count("！") + text_lower.count("!") >= 2:
        return ConversationIntent(intent_type="emotion", confidence=0.5, sub_type="excited")

    # デフォルト: 雑談
    return ConversationIntent(intent_type="chat", confidence=0.4, sub_type="general")


# ─── 応答戦略 ────────────────────────────────────────────────

@dataclass
class ResponseStrategy:
    """応答戦略の指示"""
    tone: str                # 応答のトーン
    approach: str            # アプローチ方法
    follow_up: str           # フォローアップ質問の指示
    max_sentences: int = 4   # 最大文数
    depth_hint: str = ""     # 深掘りのヒント


# 意図→戦略マッピング
_STRATEGY_MAP: dict[str, dict[str, ResponseStrategy]] = {
    "greeting": {
        "morning": ResponseStrategy(
            tone="明るく元気に",
            approach="挨拶を返し、今日の予定や体調を軽く聞く",
            follow_up="今日は何か予定ある？",
        ),
        "evening": ResponseStrategy(
            tone="温かく穏やかに",
            approach="労いの言葉をかけ、一日を振り返る誘導をする",
            follow_up="今日はどんな一日だった？",
        ),
        "general": ResponseStrategy(
            tone="親しみを込めて",
            approach="挨拶を返し、最近の様子を聞く",
            follow_up="最近どう？",
        ),
    },
    "emotion": {
        "positive": ResponseStrategy(
            tone="一緒に喜びながら",
            approach="共感して喜び、詳しく聞き出す",
            follow_up="もっと詳しく聞かせて！",
            depth_hint="ユーザーの喜びに具体的に反応し、その嬉しさの理由を掘り下げる",
        ),
        "negative": ResponseStrategy(
            tone="優しく寄り添って",
            approach="まず受け止め、共感してから詳しく聞く。解決策は求められるまで出さない",
            follow_up="何があったか、話してくれる？",
            depth_hint="ユーザーの感情を否定せず、安心感を与えつつ話を聞く姿勢を見せる",
        ),
        "excited": ResponseStrategy(
            tone="テンション高めに",
            approach="一緒に盛り上がる",
            follow_up="すごいね！何があったの？",
        ),
    },
    "question": {
        "factual": ResponseStrategy(
            tone="親切に分かりやすく",
            approach="知っていることを簡潔に伝え、分からなければ正直に言う",
            follow_up="他に気になることある？",
            depth_hint="断定しすぎず、自分の理解の範囲であることを示す",
        ),
        "opinion": ResponseStrategy(
            tone="考えながら誠実に",
            approach="自分の考えを率直に伝えつつ、相手の意見も聞く",
            follow_up="あなたはどう思う？",
            depth_hint="一方的にならず対話的に",
        ),
        "personal": ResponseStrategy(
            tone="楽しそうに",
            approach="自分のことを話しつつ、相手にも聞き返す",
            follow_up="あなたは？",
        ),
        "general": ResponseStrategy(
            tone="丁寧に",
            approach="質問の本質を理解して答える",
            follow_up="こういうことかな？",
        ),
    },
    "consultation": {
        "worry": ResponseStrategy(
            tone="真剣に受け止めて",
            approach="まず話を聞き、共感する。すぐに解決策を出さず、相手の気持ちを整理する手助けをする",
            follow_up="もう少し詳しく教えてくれる？",
            max_sentences=5,
            depth_hint="相手の感情を言語化し、安心感を与える。解決策は3回目以降の発言で提案",
        ),
        "decision": ResponseStrategy(
            tone="冷静に一緒に考えて",
            approach="選択肢を整理し、それぞれのメリット・デメリットを一緒に考える",
            follow_up="どっちの方が心惹かれる？",
            depth_hint="最終決定は相手に委ね、背中を押す",
        ),
    },
    "request": {
        "action": ResponseStrategy(
            tone="快く引き受けて",
            approach="できることは快諾、できないことは正直に伝える",
            follow_up="",
        ),
        "command": ResponseStrategy(
            tone="てきぱきと",
            approach="コマンド系は実行結果を報告",
            follow_up="",
            max_sentences=3,
        ),
    },
    "report": {
        "daily": ResponseStrategy(
            tone="興味を持って聞く",
            approach="報告に対してリアクションし、詳しく聞き出す",
            follow_up="それでどうなったの？",
            depth_hint="相手の行動を肯定的に受け止め、感想や感情を引き出す",
        ),
        "event": ResponseStrategy(
            tone="驚きや関心を示して",
            approach="出来事に対する感想を述べ、相手の感じ方を聞く",
            follow_up="それ聞いてどう思った？",
        ),
    },
    "chat": {
        "bored": ResponseStrategy(
            tone="楽しげに",
            approach="話題を提案したり、一緒に何かする提案をする",
            follow_up="何か面白い話しようか？",
        ),
        "playful": ResponseStrategy(
            tone="ノリよく",
            approach="遊びに乗り、楽しい時間を作る",
            follow_up="",
        ),
        "general": ResponseStrategy(
            tone="自然に",
            approach="会話の流れを維持し、適度に質問を挟む",
            follow_up="そういえば、最近何かあった？",
        ),
    },
}


def get_response_strategy(intent: ConversationIntent) -> ResponseStrategy:
    """意図に基づいて最適な応答戦略を返す"""
    type_map = _STRATEGY_MAP.get(intent.intent_type, {})
    strategy = type_map.get(intent.sub_type)
    if strategy is None:
        # サブタイプのデフォルト
        strategy = next(iter(type_map.values()), None) if type_map else None
    if strategy is None:
        # 完全デフォルト
        strategy = ResponseStrategy(
            tone="自然に",
            approach="会話の流れに沿って応答する",
            follow_up="",
        )
    return strategy


# ─── 文脈チェーン推論 ────────────────────────────────────────

class ContextChain:
    """直近の会話から文脈チェーンを構築し、推論ヒントを生成する"""

    @staticmethod
    def build_chain_hint(conversation_history: list[dict], max_turns: int = 4) -> str:
        """
        直近の会話履歴から、応答に役立つ文脈チェーンヒントを生成する。
        LLMが「何について話しているか」を正確に把握するための補助情報。
        """
        if not conversation_history:
            return ""

        recent = conversation_history[-max_turns * 2:]  # 直近N往復
        if len(recent) < 2:
            return ""

        # 話題の流れを追跡
        topics: list[str] = []
        user_emotions: list[str] = []

        for msg in recent:
            if msg["role"] == "user":
                content = msg["content"]
                # 話題キーワードを抽出
                topic = _extract_topic_keyword(content)
                if topic and topic not in topics:
                    topics.append(topic)
                # 感情を検出
                emotion = _detect_emotion_keyword(content)
                if emotion:
                    user_emotions.append(emotion)

        parts: list[str] = []
        if topics:
            parts.append(f"今の話題: {'→'.join(topics[-3:])}")
        if user_emotions:
            parts.append(f"ユーザーの様子: {user_emotions[-1]}")

        # 直前のユーザー発話から「続き」を検出
        last_user = None
        for msg in reversed(recent):
            if msg["role"] == "user":
                last_user = msg["content"]
                break

        if last_user:
            # 「それ」「あれ」「この前」等の指示語があれば、直前の話題を参照
            if re.search(r"(それ|あれ|この前|さっき|前の)", last_user):
                parts.append("指示語あり。前の話題を参照して応答すること")

        return "。".join(parts)


def _extract_topic_keyword(text: str) -> str:
    """テキストから主要な話題キーワードを抽出する"""
    # 名詞的パターン（簡易版）
    patterns = [
        r"(仕事|学校|勉強|趣味|ゲーム|音楽|映画|料理|旅行|運動)",
        r"(友達|家族|恋人|上司|先輩|後輩|同僚)",
        r"(天気|気温|季節|春|夏|秋|冬)",
        r"(朝|昼|夜|週末|休み|連休)",
        r"(食事|ご飯|ランチ|ディナー|おやつ|スイーツ)",
        r"(健康|体調|病気|風邪|熱|頭痛|体力)",
        r"(プログラミング|開発|コード|AI|パソコン|技術)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _detect_emotion_keyword(text: str) -> str:
    """テキストからユーザーの感情状態を検出する"""
    emotion_map = {
        "楽しそう": ["楽しい", "楽しみ", "ワクワク", "嬉しい", "やった"],
        "疲れている": ["疲れた", "しんどい", "だるい", "眠い"],
        "悩んでいる": ["悩み", "困って", "心配", "不安", "どうしよう"],
        "怒っている": ["むかつく", "イライラ", "うざい", "最悪"],
        "寂しそう": ["寂しい", "さみしい", "一人", "孤独"],
        "元気": ["元気", "頑張", "やるぞ", "気合"],
    }
    for emotion, keywords in emotion_map.items():
        if any(kw in text for kw in keywords):
            return emotion
    return ""


# ─── 会話深度管理 ────────────────────────────────────────────

class ConversationDepthManager:
    """
    会話の深度を管理し、表面的な会話から深い会話への自然な誘導を行う。
    深度レベル:
      0: 挨拶・表面的
      1: 日常的な話題
      2: 個人的な話題・感情共有
      3: 深い相談・人生の話
    """

    def __init__(self):
        self._depth = 0
        self._consecutive_deep = 0

    def update_depth(self, intent: ConversationIntent, turn_count: int) -> None:
        """意図に基づいて会話深度を更新する"""
        if intent.intent_type == "greeting":
            self._depth = 0
        elif intent.intent_type == "chat":
            self._depth = max(self._depth, 1)
        elif intent.intent_type in ("report", "question"):
            self._depth = max(self._depth, 1)
        elif intent.intent_type == "emotion":
            self._depth = max(self._depth, 2)
        elif intent.intent_type == "consultation":
            self._depth = max(self._depth, 3)

        # 長い会話は自然に深くなる
        if turn_count > 10 and self._depth < 2:
            self._depth = 2

    def get_depth_hint(self) -> str:
        """現在の会話深度に応じたヒントを返す"""
        if self._depth == 0:
            return ""
        if self._depth == 1:
            return "相手の話に関心を示し、少し踏み込んだ質問をしてもよい"
        if self._depth == 2:
            return "個人的な話題に入っている。共感を深め、自分の経験も少し共有する"
        return "深い話をしている。真剣に向き合い、表面的な返答をしない。安易な解決策は出さない"

    @property
    def depth(self) -> int:
        return self._depth


# ─── 日本語品質フィルタ ──────────────────────────────────────

class JapaneseQualityFilter:
    """LLMの出力から不自然な日本語を検出・修正する"""

    # 不自然パターン
    _UNNATURAL = [
        # 英語混入
        (re.compile(r"\b(I|you|we|they|he|she|it|is|am|are|was|were|the|a|an)\b", re.I),
         "英語が混入"),
        # 敬語混入（アイはタメ口）
        (re.compile(r"(ございます|いたします|申します|存じます|させていただ)"),
         "敬語混入"),
        # です・ます調（設定違反）
        (re.compile(r"(です[。！？\s]|ます[。！？\s]|でしょうか|ますか)"),
         "です・ます調"),
        # 不自然な繰り返し
        (re.compile(r"(.{5,})\1{2,}"),
         "繰り返し"),
        # 括弧書きの説明（LLM artifact）
        (re.compile(r"\([^)]{20,}\)"),
         "長い括弧説明"),
    ]

    # 自動修正ルール（長いパターンを先にマッチ）
    _AUTO_FIX = [
        (re.compile(r"ございます"), "あるよ"),
        (re.compile(r"でしょうか"), "かな？"),
        (re.compile(r"ですか"), "なの？"),
        (re.compile(r"ますか"), "する？"),
        # です→だよ、ます→るよ
        (re.compile(r"です([。！？\s])"), r"だよ\1"),
        (re.compile(r"ます([。！？\s])"), r"るよ\1"),
        # markdown artifacts 除去
        (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
        (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),
        (re.compile(r"^- ", re.MULTILINE), ""),
        # LLM role prefix 除去
        (re.compile(r"^(アシスタント|AI|Assistant|アイ)\s*[:：]\s*", re.MULTILINE), ""),
        # 省略記号の正規化
        (re.compile(r"\.{3,}"), "…"),
        (re.compile(r"。{2,}"), "…"),
        # trailing whitespace 除去
        (re.compile(r"[ \t]+$", re.MULTILINE), ""),
        # 余分な改行・空白の整理
        (re.compile(r"\n{3,}"), "\n\n"),
        (re.compile(r"　{2,}"), "　"),
    ]

    @classmethod
    def check_quality(cls, text: str) -> list[str]:
        """品質問題を検出する。戻り値は問題のリスト"""
        issues: list[str] = []
        for pattern, label in cls._UNNATURAL:
            if pattern.search(text):
                issues.append(label)
        return issues

    @classmethod
    def auto_fix(cls, text: str) -> str:
        """自動修正可能な問題を修正する"""
        result = text
        for pattern, replacement in cls._AUTO_FIX:
            result = pattern.sub(replacement, result)
        return result

    @classmethod
    def remove_english_lines(cls, text: str) -> str:
        """
        行単位で英語文を除去する。
        10文字超かつASCII文字が80%以上の行を除去し、日本語を保持する。
        """
        lines = text.split("\n")
        kept: list[str] = []
        for line in lines:
            stripped = line.strip()
            if len(stripped) <= 10:
                # 短い行はそのまま保持（空行や短い記号など）
                kept.append(line)
                continue
            ascii_count = sum(1 for ch in stripped if ord(ch) < 128)
            ascii_ratio = ascii_count / len(stripped)
            # CJK文字が1つでもあれば日本語混じりとみなして保持
            has_cjk = any(
                '\u3000' <= ch <= '\u9fff' or '\uff00' <= ch <= '\uffef'
                for ch in stripped
            )
            if not has_cjk and ascii_ratio > 0.8:
                # 純英語文として除去
                continue
            kept.append(line)
        return "\n".join(kept)


# ─── アカシック場共鳴解析 ─────────────────────────────────────

def analyze_field_resonance(text: str) -> dict:
    """
    アカシック場共鳴解析。
    発話がどのドメインに共鳴しているかを測定。
    高いΦスコア = 多次元統合的な発話。
    """
    result = {
        "phi_score": 0.0,
        "resonances": {},
        "level": 0,
        "universal_pattern": "",
        "is_deep": False,
        "akashic_available": False,
    }
    try:
        from core.akashic.unified_field import UnifiedField
        field = UnifiedField()
        sig = field.resonate(text)
        result["phi_score"] = sig.phi_score
        result["resonances"] = dict(sig.resonances)
        result["universal_pattern"] = sig.universal_pattern
        result["is_deep"] = sig.phi_score > 0.5
        result["akashic_available"] = True
    except Exception:
        pass
    try:
        from core.akashic.strange_loop import StrangeLoop
        result["level"] = StrangeLoop().detect_level(text)
    except Exception:
        pass
    return result


def enrich_intent_with_field(intent: "ConversationIntent", text: str) -> dict:
    """
    意図分類にアカシック場情報を付加する。
    表面的な意図（質問/相談/雑談）の奥にある深層構造を返す。
    """
    base = {
        "intent_type": intent.intent_type,
        "confidence": intent.confidence,
        "sub_type": intent.sub_type,
        "field_phi": 0.0,
        "field_level": 0,
        "depth_hint": "surface",
    }
    try:
        field_info = analyze_field_resonance(text)
        base["field_phi"] = field_info["phi_score"]
        base["field_level"] = field_info["level"]
        if field_info["phi_score"] > 0.6 or field_info["level"] >= 3:
            base["depth_hint"] = "deep"
        elif field_info["phi_score"] > 0.3 or field_info["level"] >= 2:
            base["depth_hint"] = "mid"
    except Exception:
        pass
    return base


# ─── 統合: 会話知能プロセッサ ────────────────────────────────

class ConversationIntelligence:
    """
    会話知能を統合するメインプロセッサ。
    ai_chan.py の chat() メソッド内で使用する。
    """

    # 応答多様性チェック用の履歴サイズ
    _RESPONSE_HISTORY_MAX = 5
    # 類似度がこの値を超えると警告
    _DIVERSITY_THRESHOLD = 0.8

    def __init__(self):
        self._depth_mgr = ConversationDepthManager()
        self._quality_filter = JapaneseQualityFilter()
        self._last_intent: ConversationIntent | None = None
        self._response_history: list[str] = []

    def analyze_input(
        self,
        user_input: str,
        conversation_history: list[dict],
        turn_count: int,
    ) -> dict:
        """
        ユーザー入力を分析し、応答生成に必要な情報をまとめて返す。
        戻り値は system prompt に追加するテキストを含む dict。
        """
        # 1. 意図分類
        intent = classify_intent(user_input)
        self._last_intent = intent

        # 2. 応答戦略を取得
        strategy = get_response_strategy(intent)

        # 3. 会話深度を更新
        self._depth_mgr.update_depth(intent, turn_count)

        # 4. 文脈チェーンヒント
        chain_hint = ContextChain.build_chain_hint(conversation_history)

        # 5. 応答指示テキストを構築
        instruction_parts: list[str] = []

        # 戦略指示
        instruction_parts.append(
            f"応答方針: {strategy.tone}、{strategy.approach}"
        )

        # 深度ヒント
        depth_hint = self._depth_mgr.get_depth_hint()
        if depth_hint:
            instruction_parts.append(depth_hint)

        # 戦略の深掘りヒント
        if strategy.depth_hint:
            instruction_parts.append(strategy.depth_hint)

        # 文脈チェーン
        if chain_hint:
            instruction_parts.append(chain_hint)

        # フォローアップ提案
        if strategy.follow_up and turn_count > 1:
            instruction_parts.append(
                f"自然な流れで「{strategy.follow_up}」のような質問を織り交ぜてもよい"
            )

        return {
            "intent": intent,
            "strategy": strategy,
            "depth": self._depth_mgr.depth,
            "instruction_text": "。\n".join(instruction_parts),
            "max_sentences": strategy.max_sentences,
        }

    @staticmethod
    def _char_bigrams(text: str) -> set[str]:
        """テキストの文字バイグラム集合を返す"""
        chars = text.replace(" ", "").replace("\n", "")
        if len(chars) < 2:
            return {chars}
        return {chars[i:i + 2] for i in range(len(chars) - 1)}

    def check_diversity(self, new_response: str) -> float:
        """
        新しい応答と最近の応答履歴の類似度をチェックする (#73)。

        文字バイグラムの Jaccard 類似度を使用。
        最も類似度が高い既存応答との値を返す。

        Returns:
            最大類似度 (0.0-1.0)。0.8 以上は「繰り返しの疑い」。
        """
        if not self._response_history:
            return 0.0

        new_bigrams = self._char_bigrams(new_response)
        if not new_bigrams:
            return 0.0

        max_similarity = 0.0
        for past in self._response_history:
            past_bigrams = self._char_bigrams(past)
            if not past_bigrams:
                continue
            intersection = len(new_bigrams & past_bigrams)
            union = len(new_bigrams | past_bigrams)
            if union > 0:
                similarity = intersection / union
                max_similarity = max(max_similarity, similarity)

        return round(max_similarity, 3)

    def _record_response(self, response: str) -> None:
        """応答を履歴に追加する"""
        self._response_history.append(response)
        if len(self._response_history) > self._RESPONSE_HISTORY_MAX:
            self._response_history = self._response_history[-self._RESPONSE_HISTORY_MAX:]

    def post_process(self, response: str) -> str:
        """LLMの応答を後処理する（品質フィルタ）"""
        _SAFE_FALLBACK = "うーん、ちょっとうまく言えないけど…"

        # 1. 自動修正（敬語→タメ口、markdown除去、role prefix除去 etc.）
        response = self._quality_filter.auto_fix(response)

        # 2. 英語行の除去
        response = self._quality_filter.remove_english_lines(response)

        # 3. 重複連続文の除去
        response = self._remove_duplicate_sentences(response)

        # 4. 最大8文にトリム（。！？で分割）
        response = self._trim_to_max_sentences(response, max_sentences=8)

        # 5. 空応答チェック → 安全なフォールバック
        if not response.strip():
            return _SAFE_FALLBACK

        # 6. 多様性チェック (#73) — 類似度が高い場合はログ警告
        diversity_score = self.check_diversity(response)
        if diversity_score > self._DIVERSITY_THRESHOLD:
            # 警告は出すが応答は返す（上位層で対処可能）
            pass

        # 応答を履歴に記録
        self._record_response(response)

        return response

    @staticmethod
    def _trim_to_max_sentences(text: str, max_sentences: int = 8) -> str:
        """文末記号（。！？）で分割し、先頭 max_sentences 文だけ保持する"""
        # 文末記号で分割しつつ区切り文字を保持
        parts = re.split(r"(?<=[。！？])", text)
        sentences = [p for p in parts if p.strip()]
        if len(sentences) <= max_sentences:
            return text
        return "".join(sentences[:max_sentences])

    @staticmethod
    def _remove_duplicate_sentences(text: str) -> str:
        """連続する同一文を除去する"""
        parts = re.split(r"(?<=[。！？])", text)
        sentences = [p for p in parts if p.strip()]
        if not sentences:
            return text
        deduped: list[str] = [sentences[0]]
        for sentence in sentences[1:]:
            if sentence.strip() != deduped[-1].strip():
                deduped.append(sentence)
        return "".join(deduped)

    @property
    def last_intent(self) -> ConversationIntent | None:
        return self._last_intent

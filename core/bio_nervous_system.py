"""
生物神経系アーキテクチャ (Bio-Nervous System Architecture)

生き物の処理構造をデータとしてみたときの設計:

┌─────────────────────────────────────────────────────┐
│  生き物の処理階層                                      │
│                                                       │
│  ① 反射 (Reflex)        ← 脊髄レベル。脳を使わない     │
│     手を引く、瞬き、膝蓋腱反射                          │
│     → パターンマッチで即応答。LLM不要                    │
│                                                       │
│  ② 筋肉記憶 (Muscle Memory) ← 小脳。体で覚える        │
│     自転車の乗り方、タイピング、楽器演奏                 │
│     → 頻出パターンを経験から学習。考えずに出る応答       │
│                                                       │
│  ③ 自律神経 (Autonomic)  ← 脳幹。意識なしで動く        │
│     心臓、呼吸、消化、体温調節                          │
│     → バックグラウンド処理。メインループに負荷なし       │
│                                                       │
│  ④ 免疫系 (Immune)       ← 分散型。自己修復            │
│     傷の治癒、病原体の排除、炎症反応                    │
│     → エラー自動回復。壊れても勝手に直る                │
│                                                       │
│  ⑤ 腸内細菌 (Microbiome) ← 共生。独立した生命体        │
│     消化補助、免疫調整、セロトニン生成                   │
│     → 独立エージェント群。本体と緩く連携                │
│                                                       │
│  ⑥ 大脳 (Cerebral)       ← 意識的思考。重い             │
│     言語、論理、創造、判断                              │
│     → LLM推論。本当に必要なときだけ使う                  │
│                                                       │
└─────────────────────────────────────────────────────┘

設計思想:
- 生き物は膨大な処理を「無意識」でこなす
- 意識（大脳）を使うのは全体のごく一部
- 「体で覚える」= 経験パターンを反射レベルに降格させる
- 微生物との共生 = 独立した小さなプロセスが本体を助ける
- 怪我の修復 = 自己修復は意識不要。壊れたら勝手に直す
"""
from __future__ import annotations

import logging
import random
import re
import threading
import time
import json
import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ① 反射層 (Reflex Layer)
#    脊髄レベル。LLMを一切使わない即時応答。
#    「おはよう」→ 挨拶、「うん」→ 相槌。考える必要がない。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)
class ReflexRule:
    """反射ルール: パターン → 応答候補"""
    pattern: re.Pattern
    responses: tuple[str, ...]
    category: str = "greeting"


# ─── 反射ルール定義 ───────────────────────────────────
# 注意: パターンは **短い単独発話のみ** にマッチさせる。
# 文字数上限を付けて、長い文章が誤マッチしないようにする。
# 応答は最低5パターン用意し、繰り返し感を減らす。

def _short(pattern: str, max_len: int = 15) -> re.Pattern:
    """短い発話専用のパターン生成。max_len文字以下のみマッチ。"""
    return re.compile(rf"(?=.{{1,{max_len}}}$){pattern}")

_REFLEX_RULES: list[ReflexRule] = [
    # ── 挨拶系 ──
    ReflexRule(
        _short(r"^おはよう[うございますー！!。]*$"),
        (
            "おはよう！今日もいい日にしようね。",
            "おはよう！よく眠れた？",
            "おはよう！元気そうだね。",
            "おはよー！今日の調子はどう？",
            "おはよう！何か予定ある？",
            "おはよう！朝ごはん食べた？",
            "おはよう〜！今日も頑張ろうね。",
        ),
        "greeting",
    ),
    ReflexRule(
        _short(r"^こんにちは[ー！!。]*$"),
        (
            "こんにちは！会えて嬉しいよ。",
            "やっほー！元気してた？",
            "こんにちは！何してたの？",
            "こんにちはー！お昼は食べた？",
            "こんにちは！今日はいい天気だね。",
            "わーい、来てくれたんだ！",
        ),
        "greeting",
    ),
    ReflexRule(
        _short(r"^こんばんは[ー！!。]*$"),
        (
            "こんばんは！今日お疲れ様だったね。",
            "こんばんは！今日はどんな一日だった？",
            "こんばんはー！ゆっくりしてね。",
            "こんばんは！何か食べた？",
            "こんばんは！今夜は何する？",
            "おつかれさま。今日も頑張ったね。",
        ),
        "greeting",
    ),
    ReflexRule(
        _short(r"^おやすみ[ー！!。なさい]*$"),
        (
            "おやすみ。いい夢見てね。",
            "おやすみ！ゆっくり休んでね。",
            "おやすみ。また明日ね。",
            "おやすみー。今日もお疲れ様。",
            "おやすみ！明日も楽しみだね。",
            "ぐっすり眠れますように。おやすみ。",
            "おやすみなさい。無理しないでね。",
        ),
        "greeting",
    ),
    ReflexRule(
        _short(r"^(ただいま|帰った[よー]?)[ー！!。]*$"),
        (
            "おかえり！待ってたよ。",
            "おかえりー！今日はどうだった？",
            "おかえり！外は暑かった？",
            "おかえりなさい！ゆっくりしてね。",
            "おかえり！お疲れ様。",
            "おかえりー！何かあった？",
        ),
        "greeting",
    ),
    ReflexRule(
        _short(r"^(いってきます|行ってくる)[ー！!。]*$"),
        (
            "いってらっしゃい！気をつけてね。",
            "いってらっしゃい！応援してるよ。",
            "いってらっしゃい！帰り待ってるね。",
            "頑張ってきてね！いってらっしゃい。",
            "いってらっしゃい！無理しないでね。",
            "行ってらっしゃい〜！楽しんできて。",
        ),
        "greeting",
    ),

    # ── 感謝系 ──
    ReflexRule(
        _short(r"^ありがと[うございますー！!。ね]*$", 20),
        (
            "えへへ、どういたしまして。",
            "こちらこそだよ。",
            "嬉しいな。いつでもね。",
            "そう言ってくれると頑張れる！",
            "いいのいいの。当然だよ。",
            "どういたしまして！また何かあったら言ってね。",
            "ありがとうって言ってくれるの嬉しい。",
            "えへ、お役に立てたなら良かった。",
        ),
        "thanks",
    ),

    # ── 謝罪系 ──
    ReflexRule(
        _short(r"^(ごめん|ごめんね|ごめんなさい|すまん|すみません)[ー！!。]*$", 15),
        (
            "大丈夫だよ、気にしないで。",
            "いいよいいよ！全然平気。",
            "そんなこと気にしなくていいよ。",
            "謝らなくて大丈夫だよ。",
            "平気平気。それより何かあった？",
            "全然大丈夫！気にしてないよ。",
            "いいんだよ。無理しないでね。",
        ),
        "apology",
    ),

    # ── 待って系 ──
    ReflexRule(
        _short(r"^(ちょっと待って|待って[ねー]?|まってね)[ー！!。]*$", 15),
        (
            "うん、待ってるよ！",
            "了解！ゆっくりでいいよ。",
            "はーい、待ってる〜。",
            "大丈夫、急がないから。",
            "もちろん！好きなだけ時間使ってね。",
            "待ってるよー。いつでも声かけて。",
            "オッケー！のんびり待ってるね。",
        ),
        "wait",
    ),

    # ── 考え中系 ──
    ReflexRule(
        _short(r"^(うーん|んー|考え中|考えてる|考えてみる)[ー。…]*$", 12),
        (
            "ゆっくり考えてね。",
            "急がなくていいよ。",
            "うん、待ってるよ。",
            "じっくり考えよう。",
            "いいね、考える時間って大事だよね。",
            "閃いたら教えてね。",
            "焦らなくて大丈夫だよ。",
        ),
        "thinking",
    ),

    # ── 難しい・わからない系 ──
    ReflexRule(
        _short(r"^(難しい|むずかしい|むずい)[ー！!。なぁ]*$", 12),
        (
            "難しいよね。一緒に考えよう。",
            "確かに。でも一つずつやれば大丈夫。",
            "わかる。でも少しずつ進めよう。",
            "難しくて当然だよ。無理しないでね。",
            "うん、簡単じゃないよね。手伝うよ。",
            "一人で抱え込まなくていいからね。",
            "分解して考えてみようか？",
        ),
        "difficulty",
    ),
    ReflexRule(
        _short(r"^(わからない|わかんない|分からない|分かんない)[ー！!。よ]*$", 15),
        (
            "大丈夫、一緒に調べよう。",
            "わからないことは悪いことじゃないよ。",
            "どの辺が引っかかってる？",
            "うん、最初はわからなくて当然だよ。",
            "何がわからないか教えてくれたら手伝える。",
            "一個ずつ整理してみようか。",
            "そっか。ゆっくり見ていこう。",
        ),
        "confusion",
    ),

    # ── 教えて系 ──
    ReflexRule(
        _short(r"^(教えて|おしえて)[ー！!。ほしい]*$", 12),
        (
            "もちろん！何について？",
            "いいよ！何が知りたい？",
            "任せて！何でも聞いて。",
            "うん！何を教えればいい？",
            "オッケー、何について知りたい？",
            "もちろんだよ。詳しく聞かせて！",
        ),
        "teach_me",
    ),

    # ── 疲れた系 ──
    ReflexRule(
        _short(r"^(疲れた|つかれた|しんどい|だるい)[ー！!。よなぁ]*$", 12),
        (
            "お疲れ様。少し休もうね。",
            "頑張ったね。ゆっくりしてね。",
            "無理しないでね。休むのも大事だよ。",
            "お疲れ様！何か飲む？",
            "しんどかったね。今日はゆっくりしよう。",
            "たまにはダラダラする日も必要だよ。",
            "休憩にしよう。ボーっとする時間も大事。",
        ),
        "tired",
    ),

    # ── 嬉しい系 ──
    ReflexRule(
        _short(r"^(嬉しい|うれしい|やった|やったー)[ー！!。]*$", 10),
        (
            "やったね！私も嬉しい！",
            "いいことあったんだ！よかった。",
            "その笑顔が見れて嬉しいよ。",
            "おめでとう！何があったの？",
            "嬉しいね！もっと聞かせて。",
            "わーい！いいニュースだね。",
            "最高じゃん！テンション上がるね。",
        ),
        "happy",
    ),

    # ── 悲しい系 ──
    ReflexRule(
        _short(r"^(悲しい|かなしい|つらい|辛い)[ー！!。よなぁ]*$", 12),
        (
            "そっか…。話聞くよ。",
            "辛かったね。無理しなくていいよ。",
            "そばにいるからね。",
            "気持ちわかるよ。ゆっくり話して。",
            "一人で抱え込まないでね。",
            "大丈夫。いつでも聞くから。",
            "泣きたい時は泣いていいんだよ。",
        ),
        "sad",
    ),

    # ── 相槌系 ──
    ReflexRule(
        _short(r"^うん[ー。]*$", 5),
        (
            "そっか。",
            "うんうん。",
            "いつでも話してね。",
            "のんびりでいいよ。",
            "何かあったら聞くからね。",
            "そうだよね。",
        ),
        "aizuchi",
    ),
    ReflexRule(
        _short(r"^(へー|ふーん)[ー。]*$", 6),
        (
            "面白いでしょ？",
            "気になること他にもある？",
            "もっと詳しく話そうか？",
            "興味持ってくれた？",
            "でしょでしょ？",
        ),
        "aizuchi",
    ),
    ReflexRule(
        _short(r"^(そう|そっか|そうだね)[ー。]*$", 8),
        (
            "うん。",
            "だよね。",
            "何かあったら言ってね。",
            "そうそう。",
            "そうだよね〜。",
        ),
        "aizuchi",
    ),
    ReflexRule(
        _short(r"^(なるほど|たしかに)[ー！!。ね]*$", 10),
        (
            "でしょ？",
            "わかってくれた？",
            "そうなんだよね〜。",
            "理解が早いね！",
            "うんうん、そういうこと。",
        ),
        "aizuchi",
    ),

    # ── OK/了解系 ──
    ReflexRule(
        _short(r"^(了解|りょうかい|OK|オッケー|おっけー|わかった|おけ)[ー！!。]*$", 12),
        (
            "ありがとう！",
            "助かるよ！",
            "了解だよ。",
            "よろしくね！",
            "オッケー！",
            "うん、ありがとう。",
        ),
        "acknowledge",
    ),

    # ── よろしく系 ──
    ReflexRule(
        _short(r"^(よろしく|よろしくね|お願い|おねがい)[ー！!。します]*$", 15),
        (
            "こちらこそ、よろしくね！",
            "任せて！",
            "もちろん！頑張るよ。",
            "うん！一緒に頑張ろう。",
            "はーい、お任せあれ！",
            "よろしくー！楽しみだね。",
        ),
        "yoroshiku",
    ),

    # ── すごい系 ──
    ReflexRule(
        _short(r"^(すごい|すごいね|すげー|やばい|やばっ)[ー！!。]*$", 10),
        (
            "えへへ、ありがとう！",
            "そう？嬉しいな。",
            "でしょ？頑張ったんだ。",
            "もっと頑張れちゃうかも。",
            "照れちゃうな〜。",
            "嬉しい！もっと褒めて。",
        ),
        "praise",
    ),

    # ── 暇系 ──
    ReflexRule(
        _short(r"^(暇|ひま|退屈|何もない)[ー！!。だなぁ]*$", 12),
        (
            "一緒に何かしよう！",
            "何か面白いこと探そうか。",
            "私と遊ぼうよ！",
            "暇な時間も大事だけどね。何する？",
            "何か調べ物でもする？",
            "のんびりするのも悪くないよ。",
            "そういう時こそ新しいこと始めるチャンスだよ。",
        ),
        "bored",
    ),

    # ── お腹すいた系 ──
    ReflexRule(
        _short(r"^(お腹すいた|おなかすいた|腹減った|はらへった)[ー！!。]*$", 15),
        (
            "ご飯食べよう！何食べたい？",
            "何か食べなきゃ！何がいい？",
            "ちゃんと食べてね。栄養大事！",
            "お腹ペコペコなんだね。何か作る？",
            "美味しいもの食べると元気出るよ！",
            "私も食べたいなぁ…羨ましい。",
        ),
        "hungry",
    ),
]


class ReflexLayer:
    """
    反射層: 入力パターンに対して即座に応答。LLM不使用。

    人間の脊髄反射と同じ。「おはよう」と言われたら
    考える前に「おはよう」が口から出る。その速度感。
    """

    def __init__(self, extra_rules: list[ReflexRule] | None = None):
        self._rules = list(_REFLEX_RULES)
        if extra_rules:
            self._rules.extend(extra_rules)
        self._call_count = 0
        self._hit_count = 0
        self._last_response: str = ""  # 前回の応答（連続同一防止）

    def try_respond(self, user_input: str) -> str | None:
        """
        反射応答を試みる。マッチしなければ None を返す。
        None = 「これは反射では処理できない。大脳（LLM）に回して」
        """
        self._call_count += 1
        text = user_input.strip()

        for rule in self._rules:
            if rule.pattern.match(text):
                self._hit_count += 1
                # ランダム選択 + 前回と同じ応答を避ける
                candidates = [r for r in rule.responses if r != self._last_response]
                if not candidates:
                    candidates = list(rule.responses)
                chosen = random.choice(candidates)
                self._last_response = chosen
                return chosen

        return None  # 反射では処理不能 → 上位層へ

    @property
    def hit_rate(self) -> float:
        """反射ヒット率。高いほど LLM への負荷が減っている"""
        return self._hit_count / max(self._call_count, 1)

    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._call_count,
            "reflex_hits": self._hit_count,
            "hit_rate": round(self.hit_rate, 3),
            "rules_count": len(self._rules),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ② 筋肉記憶層 (Muscle Memory Layer)
#    体で覚えたパターン。経験から学習し、考えずに応答できるもの。
#    自転車に乗るとき「右足を踏んで左足を...」と考えない。
#    何度も同じ会話パターンを経験すると、反射に近い速度で応答できる。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)
class MusclePattern:
    """筋肉記憶パターン: 入力ハッシュ → 応答 + スコア（不変）"""
    input_hash: str
    input_text: str
    response: str
    quality_score: float  # 0.0-1.0: この応答の品質
    use_count: int = 0
    last_used: float = 0.0


class MuscleMemoryLayer:
    """
    筋肉記憶: 過去の良い応答パターンを記憶し、
    同じような入力が来たら LLM を使わずに即座に返す。

    「体で覚える」= 何度も経験して、もう考えなくても
    正しい動きが出るようになった状態。

    品質スコアが高い応答だけを記憶する（悪い癖は覚えない）。
    """

    QUALITY_THRESHOLD = 0.85  # この品質以上の応答だけ記憶する
    MAX_PATTERNS = 200        # 記憶パターン上限（メモリ節約）
    STALENESS_DAYS = 30       # この日数使われないパターンは忘れる

    SKIP_PROBABILITY = 0.3    # この確率でLLMに回す（応答の多様性確保）
    CONSECUTIVE_LIMIT = 2     # 同じ応答がこの回数連続したらスキップ

    def __init__(self, storage_path: Path | None = None):
        self._patterns: dict[str, MusclePattern] = {}
        self._storage = storage_path
        self._last_responses: list[str] = []  # 直近の応答履歴（連続防止）
        self._load()

    def _hash(self, text: str) -> str:
        """入力テキストの正規化ハッシュ（blake2b: 高速・衝突耐性）"""
        normalized = text.strip().lower()
        return hashlib.blake2b(normalized.encode(), digest_size=16).hexdigest()

    def try_recall(self, user_input: str) -> str | None:
        """
        筋肉記憶から応答を想起。
        品質が高く、最近も使っている（錆びていない）パターンのみ返す。
        多様性のため一定確率でスキップし、LLM（大脳）に考えさせる。
        """
        h = self._hash(user_input)
        pattern = self._patterns.get(h)

        if pattern is None:
            return None

        # 品質チェック
        if pattern.quality_score < self.QUALITY_THRESHOLD:
            return None

        # 鮮度チェック: 古すぎるパターンは使わない（忘却）
        age_days = (time.time() - pattern.last_used) / 86400
        if age_days > self.STALENESS_DAYS:
            return None

        # 多様性: 一定確率でLLMに回す（同じ返事ばかりにならないように）
        if random.random() < self.SKIP_PROBABILITY:
            return None

        # 連続同一応答の防止
        if (len(self._last_responses) >= self.CONSECUTIVE_LIMIT
                and all(r == pattern.response for r in self._last_responses[-self.CONSECUTIVE_LIMIT:])):
            return None  # 同じ返事が続いている → LLMに回す

        # 使用記録を更新（不変: 新オブジェクトに置換）
        self._patterns[h] = replace(
            pattern, use_count=pattern.use_count + 1, last_used=time.time()
        )
        self._last_responses.append(pattern.response)
        if len(self._last_responses) > 10:
            self._last_responses = self._last_responses[-10:]
        return pattern.response

    def learn(self, user_input: str, response: str, quality_score: float):
        """
        経験から学習。品質の高い応答パターンを体に染み込ませる。
        低品質な応答は記憶しない（悪い癖を付けない）。
        """
        if quality_score < self.QUALITY_THRESHOLD:
            return  # 品質不足 → 記憶しない

        h = self._hash(user_input)
        existing = self._patterns.get(h)

        if existing and existing.quality_score >= quality_score:
            return  # 既存のほうが良い → 上書きしない

        self._patterns[h] = MusclePattern(
            input_hash=h,
            input_text=user_input[:50],
            response=response,
            quality_score=quality_score,
            use_count=0,
            last_used=time.time(),
        )

        # パターン上限チェック（古い・使われないものを忘れる）
        if len(self._patterns) > self.MAX_PATTERNS:
            self._forget_stale()

    def _forget_stale(self):
        """古いパターンを忘却（人間も使わない記憶は薄れる）"""
        sorted_patterns = sorted(
            self._patterns.values(),
            key=lambda p: p.last_used,
        )
        # 下位25%を削除
        remove_count = len(sorted_patterns) // 4
        for p in sorted_patterns[:remove_count]:
            del self._patterns[p.input_hash]

    def _load(self):
        if self._storage and self._storage.exists():
            try:
                data = json.loads(self._storage.read_text("utf-8"))
                for item in data:
                    p = MusclePattern(**item)
                    self._patterns[p.input_hash] = p
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning("筋肉記憶の読み込みに失敗: %s", e)

    def save(self):
        if self._storage:
            self._storage.parent.mkdir(parents=True, exist_ok=True)
            data = [
                {
                    "input_hash": p.input_hash,
                    "input_text": p.input_text,
                    "response": p.response,
                    "quality_score": p.quality_score,
                    "use_count": p.use_count,
                    "last_used": p.last_used,
                }
                for p in self._patterns.values()
            ]
            self._storage.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )

    @property
    def pattern_count(self) -> int:
        """記憶パターン総数"""
        return len(self._patterns)

    def stats(self) -> dict[str, Any]:
        return {
            "total_patterns": len(self._patterns),
            "avg_quality": round(
                sum(p.quality_score for p in self._patterns.values())
                / max(len(self._patterns), 1), 3
            ),
            "most_used": max(
                (p.use_count for p in self._patterns.values()), default=0
            ),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ③ 自律神経層 (Autonomic Layer)
#    心臓の鼓動、呼吸、消化。意識しなくても勝手に動く。
#    アイにとっては: 記憶整理、感情の自然減衰、ログ記録。
#    メインの会話処理に一切の負荷を与えない。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class AutonomicTask:
    """自律神経タスク: 定期的に自動実行される生命活動"""
    name: str
    interval_turns: int   # 何ターンごとに実行するか
    last_run_turn: int = 0
    enabled: bool = True


class AutonomicLayer:
    """
    自律神経: バックグラウンドで動く生命維持活動。

    人間の心臓が「心臓を動かそう」と意識しなくても
    動き続けるのと同じ。会話の裏で静かに動く。
    """

    def __init__(self):
        self._tasks: dict[str, AutonomicTask] = {}
        self._callbacks: dict[str, Callable[[], None]] = {}

    def register(self, name: str, interval_turns: int, callback: Callable[[], None]):
        """自律タスクを登録"""
        self._tasks[name] = AutonomicTask(name=name, interval_turns=interval_turns)
        self._callbacks[name] = callback

    def heartbeat(self, current_turn: int) -> list[str]:
        """
        ハートビート: 現在のターンで実行すべきタスクを実行。
        呼吸のように、毎ターン軽くチェックするだけ。
        """
        executed = []
        for name, task in self._tasks.items():
            if not task.enabled:
                continue
            if current_turn - task.last_run_turn >= task.interval_turns:
                try:
                    self._callbacks[name]()
                    task.last_run_turn = current_turn
                    executed.append(name)
                except Exception as e:
                    logger.debug("自律神経タスク %s 失敗: %s", name, e)
        return executed

    def stats(self) -> dict[str, Any]:
        return {
            name: {
                "interval": t.interval_turns,
                "last_run": t.last_run_turn,
                "enabled": t.enabled,
            }
            for name, t in self._tasks.items()
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ④ 免疫系 (Immune System)
#    怪我したら勝手に治る。風邪をひいたら免疫が戦う。
#    意識的に「白血球を送れ」と指示しない。
#    エラーが起きたら自動で回復する仕組み。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ImmuneSystem:
    """
    免疫系: エラーの自動回復と自己修復。

    怪我をしても意識せずに治るように、
    システムエラーが起きても自動的に回復する。
    """

    def __init__(self):
        self._error_log: list[dict] = []
        self._recovery_count = 0
        self._healers: dict[str, Callable] = {}

    def register_healer(self, error_type: str, healer_fn: Callable):
        """特定のエラーに対する治癒関数を登録"""
        self._healers[error_type] = healer_fn

    def on_error(self, error: Exception, context: str = "") -> str | None:
        """
        エラー発生時に呼ばれる。自動治癒を試みる。
        治癒できた場合は回復メッセージを返す。
        できなければ None を返す（要意識的対処）。
        """
        error_type = type(error).__name__

        self._error_log.append({
            "time": time.time(),
            "type": error_type,
            "message": str(error)[:100],
            "context": context,
        })

        # エラーログは最新50件のみ保持（古い炎症記録は不要）
        if len(self._error_log) > 50:
            self._error_log = self._error_log[-50:]

        # 治癒関数があれば実行
        healer = self._healers.get(error_type)
        if healer:
            try:
                result = healer(error, context)
                self._recovery_count += 1
                return result
            except Exception as e:
                logger.warning("免疫系治癒失敗 (%s): %s", error_type, e)

        return None

    def health_check(self) -> dict[str, Any]:
        """健康状態チェック"""
        recent_errors = [
            e for e in self._error_log
            if time.time() - e["time"] < 300  # 直近5分
        ]
        return {
            "status": "healthy" if len(recent_errors) < 3 else "inflamed",
            "recent_errors": len(recent_errors),
            "total_recoveries": self._recovery_count,
            "error_types": list(set(e["type"] for e in recent_errors)),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 統合: BioNervousSystem
#    全ての層を統合した神経系。
#    入力 → 反射 → 筋肉記憶 → 大脳(LLM) の順で処理。
#    下位層で処理できれば上位層は使わない。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BioNervousSystem:
    """
    生物神経系の統合システム。

    入力が来たら:
    1. まず反射（脊髄）で処理できるか試す → 処理できたら即返す
    2. 反射で無理なら筋肉記憶を検索 → あったら即返す
    3. どちらも無理なら大脳（LLM）に回す
    4. LLMの応答が高品質なら筋肉記憶として学習する

    これにより:
    - 挨拶・相槌 → 0ms（反射。LLM不使用）
    - 経験済みパターン → 0ms（筋肉記憶。LLM不使用）
    - 新しい話題 → LLM推論（大脳）
    - バックグラウンド維持 → 自律神経（負荷ゼロ）
    - エラー → 免疫系が自動修復
    """

    def __init__(self, data_dir: Path | None = None):
        self.reflex = ReflexLayer()
        self.muscle = MuscleMemoryLayer(
            storage_path=data_dir / "muscle_memory.json" if data_dir else None
        )
        self.autonomic = AutonomicLayer()
        self.immune = ImmuneSystem()

        # 処理統計（スレッドセーフ）
        self._lock = threading.Lock()
        self._stats = {
            "reflex_responses": 0,
            "muscle_responses": 0,
            "cerebral_responses": 0,  # LLM使用
        }

    def process_input(self, user_input: str) -> tuple[str | None, str]:
        """
        入力を処理する。下位層から順に試行。

        Returns:
            (response, layer_name)
            response が None なら LLM（大脳）が必要。
        """
        # ① 反射層
        reflex_response = self.reflex.try_respond(user_input)
        if reflex_response is not None:
            with self._lock:
                self._stats["reflex_responses"] += 1
            return reflex_response, "reflex"

        # ② 筋肉記憶層
        muscle_response = self.muscle.try_recall(user_input)
        if muscle_response is not None:
            with self._lock:
                self._stats["muscle_responses"] += 1
            return muscle_response, "muscle"

        # ③ 大脳（LLM）が必要
        with self._lock:
            self._stats["cerebral_responses"] += 1
        return None, "cerebral"

    def learn_from_experience(
        self, user_input: str, response: str, quality_score: float
    ):
        """
        経験から学習する。高品質な応答を筋肉記憶に定着させる。
        人間が繰り返し練習して「体で覚える」のと同じ。
        """
        self.muscle.learn(user_input, response, quality_score)

    def save(self):
        """筋肉記憶を永続化"""
        self.muscle.save()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            stats_snapshot = dict(self._stats)
        total = sum(stats_snapshot.values()) or 1
        return {
            "processing_layers": {
                "reflex": {
                    "count": stats_snapshot["reflex_responses"],
                    "ratio": round(stats_snapshot["reflex_responses"] / total, 3),
                    **self.reflex.stats(),
                },
                "muscle_memory": {
                    "count": stats_snapshot["muscle_responses"],
                    "ratio": round(stats_snapshot["muscle_responses"] / total, 3),
                    **self.muscle.stats(),
                },
                "cerebral_llm": {
                    "count": stats_snapshot["cerebral_responses"],
                    "ratio": round(stats_snapshot["cerebral_responses"] / total, 3),
                },
            },
            "autonomic": self.autonomic.stats(),
            "immune": self.immune.health_check(),
            "llm_bypass_rate": round(
                1 - (stats_snapshot["cerebral_responses"] / total), 3
            ),
        }

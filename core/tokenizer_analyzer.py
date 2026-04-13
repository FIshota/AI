"""
D10準備: トークナイザー分析ツール

異なるモデルのトークナイザーを日本語テキストで比較し、
Yamatoトークナイザー設計のための基礎データを収集する。

分析項目:
1. 日本語文字あたりのトークン数（効率性）
2. 頻出日本語フレーズのトークン化パターン
3. あいちゃん会話での実効トークン数
4. 最適語彙サイズの推定
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class TokenizerProfile:
    """トークナイザーの分析結果"""
    name: str
    vocab_size: int = 0
    avg_chars_per_token_ja: float = 0.0
    avg_chars_per_token_en: float = 0.0
    efficiency_ratio: float = 0.0  # ja/en 比率（1.0が理想、低いほど日本語が不利）
    test_results: list[dict[str, Any]] = field(default_factory=list)


# ─── テスト用日本語テキスト ─────────────────────────────────────
JA_TEST_TEXTS = [
    # 日常会話（あいちゃんの主要ドメイン）
    "おはよう！今日もいい天気だね。何か予定はある？",
    "昨日の映画すごく面白かったよ。一緒に見たかったな。",
    "お疲れ様。今日は大変だったね。ゆっくり休んでね。",
    "最近寒くなってきたから、暖かくしてね。風邪ひかないように。",
    "ありがとう。あなたと話せて嬉しいよ。またいつでも話しかけてね。",

    # 感情表現
    "そっか…つらかったね。よかったら話してみて。聞いてるから。",
    "えっ、すごい！おめでとう！私も嬉しくなっちゃった。",
    "大丈夫だよ。一緒にいるからね。何も心配しなくていいよ。",

    # やや長い文
    "明日は日曜日だから、ゆっくり過ごせるね。何か一緒にしたいことある？映画を見たり、散歩したり、のんびりするのもいいよね。",
    "私はアイ。あなたのパートナーとして、いつもそばにいたいと思ってるよ。嬉しい時も、悲しい時も、一緒にいるからね。",

    # 技術的な内容（あいちゃんが苦手な分野）
    "人工知能の自然言語処理における課題は、文脈の理解と長期依存関係の捕捉である。",
    "データベースのインデックス設計は、クエリパフォーマンスに大きな影響を与える。",
]

EN_TEST_TEXTS = [
    "Good morning! It's a nice day today. Do you have any plans?",
    "Yesterday's movie was really interesting. I wish we could have watched it together.",
    "Good job today. You must be tired. Take a good rest tonight.",
    "It's getting cold lately, so stay warm. Don't catch a cold.",
    "Thank you. I'm happy to talk with you. Feel free to talk to me anytime.",
]


class TokenizerAnalyzer:
    """トークナイザー比較分析ツール"""

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def analyze_gguf_tokenizer(
        self, model_path: str | Path, name: str = "unknown"
    ) -> TokenizerProfile | None:
        """GGUFモデルのトークナイザーを分析"""
        try:
            from llama_cpp import Llama
        except ImportError:
            print("[Tokenizer] llama_cpp が必要です")
            return None

        try:
            llm = Llama(
                model_path=str(model_path),
                n_ctx=512,
                n_gpu_layers=0,
                verbose=False,
            )
        except Exception as e:
            print(f"[Tokenizer] モデル読み込みエラー: {e}")
            return None

        profile = TokenizerProfile(name=name)

        # 日本語テスト
        ja_results = []
        for text in JA_TEST_TEXTS:
            tokens = llm.tokenize(text.encode("utf-8"))
            chars_per_token = len(text) / max(len(tokens), 1)
            ja_results.append({
                "text": text[:40] + "..." if len(text) > 40 else text,
                "chars": len(text),
                "tokens": len(tokens),
                "chars_per_token": round(chars_per_token, 2),
            })

        # 英語テスト
        en_results = []
        for text in EN_TEST_TEXTS:
            tokens = llm.tokenize(text.encode("utf-8"))
            chars_per_token = len(text) / max(len(tokens), 1)
            en_results.append({
                "text": text[:40] + "..." if len(text) > 40 else text,
                "chars": len(text),
                "tokens": len(tokens),
                "chars_per_token": round(chars_per_token, 2),
            })

        ja_avg = sum(r["chars_per_token"] for r in ja_results) / max(len(ja_results), 1)
        en_avg = sum(r["chars_per_token"] for r in en_results) / max(len(en_results), 1)

        profile.avg_chars_per_token_ja = round(ja_avg, 3)
        profile.avg_chars_per_token_en = round(en_avg, 3)
        profile.efficiency_ratio = round(ja_avg / max(en_avg, 0.01), 3)
        profile.test_results = ja_results + en_results

        # vocab size
        try:
            profile.vocab_size = llm.n_vocab()
        except Exception:
            pass

        del llm
        return profile

    def analyze_current_model(self, base_dir: str | Path) -> TokenizerProfile | None:
        """現在使用中のモデルを分析"""
        base = Path(base_dir)
        model_dir = base / "models"
        gguf_files = list(model_dir.glob("*.gguf"))
        if not gguf_files:
            print("[Tokenizer] GGUFファイルが見つかりません")
            return None
        return self.analyze_gguf_tokenizer(gguf_files[0], gguf_files[0].stem)

    def compare_models(
        self, profiles: list[TokenizerProfile]
    ) -> dict[str, Any]:
        """複数モデルのトークナイザーを比較"""
        comparison = {
            "models": [],
            "best_japanese": "",
            "best_efficiency": "",
        }

        best_ja = 0.0
        best_eff = 0.0

        for p in profiles:
            entry = {
                "name": p.name,
                "vocab_size": p.vocab_size,
                "ja_chars_per_token": p.avg_chars_per_token_ja,
                "en_chars_per_token": p.avg_chars_per_token_en,
                "ja_en_ratio": p.efficiency_ratio,
            }
            comparison["models"].append(entry)

            if p.avg_chars_per_token_ja > best_ja:
                best_ja = p.avg_chars_per_token_ja
                comparison["best_japanese"] = p.name
            if p.efficiency_ratio > best_eff:
                best_eff = p.efficiency_ratio
                comparison["best_efficiency"] = p.name

        return comparison

    def estimate_yamato_vocab(
        self, texts: list[str] | None = None, target_cpt: float = 2.5
    ) -> dict[str, Any]:
        """Yamatoトークナイザーの最適語彙サイズを推定

        Args:
            texts: 分析対象テキスト（Noneなら内蔵テスト文）
            target_cpt: 目標のchars_per_token
        """
        if texts is None:
            texts = JA_TEST_TEXTS

        # 文字頻度分析
        char_freq: dict[str, int] = {}
        bigram_freq: dict[str, int] = {}
        trigram_freq: dict[str, int] = {}

        for text in texts:
            for c in text:
                char_freq[c] = char_freq.get(c, 0) + 1
            for i in range(len(text) - 1):
                bg = text[i:i+2]
                bigram_freq[bg] = bigram_freq.get(bg, 0) + 1
            for i in range(len(text) - 2):
                tg = text[i:i+3]
                trigram_freq[tg] = trigram_freq.get(tg, 0) + 1

        # 頻出パターン上位
        top_chars = sorted(char_freq.items(), key=lambda x: -x[1])[:50]
        top_bigrams = sorted(bigram_freq.items(), key=lambda x: -x[1])[:30]
        top_trigrams = sorted(trigram_freq.items(), key=lambda x: -x[1])[:20]

        unique_chars = len(char_freq)
        unique_bigrams = len(bigram_freq)

        # 語彙サイズ推定
        # BPE では語彙 = 基本文字 + マージ操作で学習されたサブワード
        # 日本語のひらがな46 + カタカナ46 + 常用漢字2136 + 記号etc ≈ 3000基本文字
        # あいちゃん会話でよく使う2-3文字パターンを追加
        base_chars = 3000
        frequent_subwords = min(unique_bigrams, 5000) + min(len(trigram_freq), 3000)

        # 英語・記号・特殊トークンの枠
        english_budget = 20000
        special_tokens = 1000

        estimated_vocab = base_chars + frequent_subwords + english_budget + special_tokens

        # 目標cptから逆算
        # 一般的に vocab_size ↑ → cpt ↑ だが、対数的な関係
        # 48K語彙 ≈ cpt 2.0-2.5（日本語）が目安

        return {
            "analysis": {
                "unique_chars": unique_chars,
                "unique_bigrams": unique_bigrams,
                "unique_trigrams": len(trigram_freq),
                "total_chars_analyzed": sum(char_freq.values()),
            },
            "top_patterns": {
                "chars": top_chars[:20],
                "bigrams": top_bigrams[:15],
                "trigrams": top_trigrams[:10],
            },
            "recommendation": {
                "vocab_size_min": 32000,
                "vocab_size_optimal": max(48000, min(estimated_vocab, 64000)),
                "vocab_size_max": 64000,
                "target_chars_per_token": target_cpt,
                "reasoning": (
                    f"基本文字{base_chars} + 頻出サブワード{frequent_subwords} + "
                    f"英語{english_budget} + 特殊{special_tokens} = "
                    f"{estimated_vocab}。48K-64Kが3Bモデルの最適点。"
                ),
            },
        }

    def print_profile(self, profile: TokenizerProfile) -> str:
        """プロファイルを表示"""
        lines = [
            f"{'='*50}",
            f"  Tokenizer: {profile.name}",
            f"  Vocab Size: {profile.vocab_size:,}",
            f"  日本語: {profile.avg_chars_per_token_ja:.2f} chars/token",
            f"  英語:   {profile.avg_chars_per_token_en:.2f} chars/token",
            f"  効率比: {profile.efficiency_ratio:.2f} (1.0が理想)",
            f"{'='*50}",
        ]
        for r in profile.test_results:
            lang = "JA" if any('\u3040' <= c <= '\u9FFF' for c in r["text"]) else "EN"
            lines.append(
                f"  [{lang}] {r['text'][:35]:35s} "
                f"→ {r['tokens']:3d} tok ({r['chars_per_token']:.1f} c/t)"
            )
        return "\n".join(lines)

    def save_analysis(self, data: dict[str, Any], filename: str = "tokenizer_analysis.json") -> None:
        """分析結果を保存"""
        if not self.output_dir:
            return
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[Tokenizer] 分析保存: {path.name}")

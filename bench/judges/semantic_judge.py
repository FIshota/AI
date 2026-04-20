"""Semantic judge: sentence-transformers による意味類似度 (Phase 1).

無料・ローカル動作。OpenAI Embeddings の代替。
初回実行時に多言語モデル (約 470MB) を HuggingFace からダウンロード。

推奨モデル:
  - paraphrase-multilingual-MiniLM-L12-v2 (多言語対応, 480MB)
  - intfloat/multilingual-e5-small        (高品質, 470MB)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .base import JudgeScore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


@dataclass
class SemanticJudge:
    """埋め込みコサイン類似度で採点.

    H-2: aggregation に "max" (既定) / "mean" / "median" を指定可能。
    reference list が多様化したとき max は saturate しやすいため mean が有効。
    """
    name: str = "semantic"
    model_name: str = DEFAULT_MODEL
    aggregation: str = "max"  # "max" | "mean" | "median"
    _model: Optional[object] = field(default=None, init=False, repr=False)

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    "sentence-transformers が未インストールです。"
                    " pip install sentence-transformers"
                ) from e
            logger.info("[semantic_judge] loading model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def score(
        self,
        prediction: str,
        reference: str | list[str],
        **kwargs,
    ) -> JudgeScore:
        if not prediction or not prediction.strip():
            return JudgeScore(score=0.0, judge_name=self.name,
                              raw={"reason": "empty_prediction"})

        refs = reference if isinstance(reference, list) else [reference]
        refs = [r for r in refs if r and r.strip()]
        if not refs:
            return JudgeScore(score=0.0, judge_name=self.name,
                              raw={"reason": "empty_reference"})

        model = self._ensure_model()
        # 一回で encode してベクトル化
        vecs = model.encode([prediction] + refs, normalize_embeddings=True,
                            show_progress_bar=False)
        pred_vec = vecs[0]
        ref_vecs = vecs[1:]

        # コサイン類似度 (normalize 済みなので内積 = cos)
        import numpy as np
        sims = [float(np.dot(pred_vec, rv)) for rv in ref_vecs]
        if not sims:
            return JudgeScore(score=0.0, judge_name=self.name,
                              raw={"reason": "no_sims"})
        if self.aggregation == "mean":
            agg = sum(sims) / len(sims)
        elif self.aggregation == "median":
            agg = float(sorted(sims)[len(sims) // 2])
        else:  # "max" (既定)
            agg = max(sims)

        # -1..1 → 0..1 に正規化
        normalized = (agg + 1.0) / 2.0
        normalized = max(0.0, min(1.0, normalized))

        return JudgeScore(
            score=normalized,
            raw={
                "cosine_agg": agg,
                "aggregation": self.aggregation,
                "cosine_all": sims,
                "model": self.model_name,
            },
            judge_name=self.name,
        )

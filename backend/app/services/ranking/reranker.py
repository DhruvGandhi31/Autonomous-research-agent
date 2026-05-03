"""
Cross-encoder reranker using ms-marco-MiniLM-L-6-v2 (~22 MB, CPU-friendly).
Runs 100% locally via sentence-transformers.

Cross-encoders see query + document together — far more accurate than
bi-encoder cosine similarity for ranking, but too slow for initial retrieval.
Use this as a second-stage reranker on top of hybrid retrieval.
"""
import asyncio
from typing import Optional

from loguru import logger


class CrossEncoderReranker:
    MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self):
        self._model = None
        self._available: Optional[bool] = None

    def _load(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(
                self.MODEL_NAME,
                device="cpu",    # Swap to "cuda" if GPU is available
                max_length=512,
            )
            self._available = True
            logger.info(f"CrossEncoderReranker loaded: {self.MODEL_NAME}")
        except Exception as e:
            logger.warning(f"CrossEncoderReranker unavailable (reranking disabled): {e}")
            self._available = False
        return self._available

    async def rerank(self, query: str, docs: list, top_n: int = 12) -> list:
        """
        Score (query, doc) pairs and return top_n by score.
        Falls back to original order if the model isn't available.
        """
        if not self._load() or not docs:
            return docs[:top_n]

        pairs = [(query, (doc.content if hasattr(doc, "content") else "")[:400]) for doc in docs]

        def _sync_predict():
            return self._model.predict(pairs, batch_size=32, show_progress_bar=False)

        try:
            scores = await asyncio.to_thread(_sync_predict)
            for doc, score in zip(docs, scores):
                doc.metadata["rerank_score"] = float(score)
            docs.sort(key=lambda d: d.metadata.get("rerank_score", 0.0), reverse=True)
            return docs[:top_n]
        except Exception as e:
            logger.warning(f"Reranking failed, using original order: {e}")
            return docs[:top_n]

    @property
    def is_available(self) -> bool:
        return self._load()


reranker = CrossEncoderReranker()

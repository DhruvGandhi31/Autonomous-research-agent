"""
Full RAG pipeline — Perplexity-quality local research:

  1. Hybrid retrieval (Qdrant dense + tantivy BM25, HyDE query expansion)
  2. Credibility scoring per chunk
  3. Cross-encoder reranking
  4. MMR diversity selection (avoid redundant chunks)
  5. LLM synthesis with inline citations
  6. Self-critique pass (hallucination guard)
  7. Confidence score

All local — no external APIs.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
from loguru import logger

from services.llm_service import llm_service
from services.ranking.credibility_scorer import credibility_scorer
from services.ranking.reranker import reranker
from services.retrieval.hybrid_retriever import hybrid_retriever, RetrievedDoc
from services.cache_manager import cache_manager

# ── Prompts ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a precise research assistant. You answer questions using ONLY the provided context chunks.

Rules:
- Cite every factual claim using [N] notation, where N is the chunk number
- If the context does not contain enough information, say so explicitly
- Never invent facts not present in the context
- Use technical language appropriate to the topic
- Structure the response with clear paragraphs"""

_SYNTHESIS_PROMPT = """\
Context chunks (use these as your ONLY sources):

{context}

---
Research question: {query}

Provide a comprehensive, well-cited answer. Every factual sentence must include \
at least one citation [N]. End with a brief conclusion paragraph."""

_CRITIQUE_PROMPT = """\
Review this research response for unsupported claims.

Response:
{response}

Context summary (what the sources actually say):
{context_summary}

List every sentence that makes a claim NOT traceable to the context.
If all claims are supported by the context, respond with exactly: VERIFIED
Be specific — quote the problematic sentence."""


# ── Response model ─────────────────────────────────────────────────────────────

@dataclass
class RAGResponse:
    answer: str
    citations: list[dict]
    confidence: float
    sources_used: int
    verified: bool
    critique: Optional[str] = None


# ── Pipeline ───────────────────────────────────────────────────────────────────

class RAGPipeline:
    def __init__(self, top_k: int = 12, use_hyde: bool = True):
        self.top_k = top_k
        self.use_hyde = use_hyde

    async def query(self, question: str, top_k: Optional[int] = None) -> RAGResponse:
        k = top_k or self.top_k
        logger.info(f"RAG query: {question[:80]!r}")

        # ── Cache check ──────────────────────────────────────────────────────
        cached = cache_manager.get_query(question)
        if cached:
            logger.info("RAG: cache hit")
            return RAGResponse(**cached)

        # ── 1. Retrieve candidates ───────────────────────────────────────────
        candidates = await hybrid_retriever.retrieve(question, top_k=k * 3, use_hyde=self.use_hyde)

        if not candidates:
            return RAGResponse(
                answer=(
                    "Insufficient information in the knowledge base for this query. "
                    "Try running a research session first to populate the knowledge base."
                ),
                citations=[],
                confidence=0.0,
                sources_used=0,
                verified=False,
            )

        # ── 2. Credibility scoring ───────────────────────────────────────────
        for doc in candidates:
            doc.metadata["credibility_score"] = credibility_scorer.score(doc)

        # ── 3. Cross-encoder rerank ──────────────────────────────────────────
        reranked = await reranker.rerank(question, candidates, top_n=k * 2)

        # ── 4. MMR diversity selection ───────────────────────────────────────
        selected = _mmr_select(reranked, top_k=k, lambda_param=0.6)

        # ── 5. Build context with numbered citation IDs ──────────────────────
        context_parts: list[str] = []
        citations: list[dict] = []
        for i, doc in enumerate(selected, 1):
            context_parts.append(f"[{i}] {doc.content}")
            citations.append({
                "id": i,
                "url": doc.source_url,
                "title": doc.metadata.get("title", ""),
                "domain": doc.metadata.get("domain", ""),
                "credibility": doc.metadata.get("credibility_score", 0.5),
                "source_type": doc.metadata.get("source", "web"),
            })

        context = "\n\n".join(context_parts)

        # ── 6. Synthesise ────────────────────────────────────────────────────
        prompt = _SYNTHESIS_PROMPT.format(context=context, query=question)
        answer = await llm_service.generate(
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=1200,
        )

        # ── 7. Self-critique (hallucination guard) ───────────────────────────
        context_summary = "\n".join(
            f"[{i+1}] {d.content[:200]}..." for i, d in enumerate(selected)
        )
        critique_prompt = _CRITIQUE_PROMPT.format(
            response=answer, context_summary=context_summary
        )
        critique_raw = await llm_service.generate(critique_prompt, temperature=0.1, max_tokens=300)
        verified = critique_raw.strip().upper().startswith("VERIFIED")
        critique = None if verified else critique_raw.strip()

        # ── 8. Confidence score ──────────────────────────────────────────────
        confidence = _compute_confidence(selected, verified)

        logger.info(
            f"RAG complete: {len(selected)} sources, confidence={confidence:.2f}, verified={verified}"
        )

        response = RAGResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            sources_used=len(selected),
            verified=verified,
            critique=critique,
        )

        # Cache the result (1 hour TTL)
        cache_manager.set_query(question, {
            "answer": response.answer,
            "citations": response.citations,
            "confidence": response.confidence,
            "sources_used": response.sources_used,
            "verified": response.verified,
            "critique": response.critique,
        })

        return response


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mmr_select(
    docs: list[RetrievedDoc], top_k: int, lambda_param: float = 0.6
) -> list[RetrievedDoc]:
    """
    Maximal Marginal Relevance — balance relevance with diversity.
    lambda=1.0 → pure relevance, lambda=0.0 → pure diversity.
    Uses word-overlap as a cheap similarity proxy (no extra embeddings needed).
    """
    if len(docs) <= top_k:
        return docs

    # Prefer the cross-encoder rerank score when available; fall back to RRF.
    scores = np.array(
        [d.metadata.get("rerank_score", d.rrf_score) for d in docs],
        dtype=float,
    )
    max_score = scores.max()
    if max_score > 0:
        scores /= max_score

    def _word_sim(a: str, b: str) -> float:
        sa = set(a.lower().split())
        sb = set(b.lower().split())
        return len(sa & sb) / (len(sa | sb) + 1e-9)

    selected_idx: list[int] = []
    candidates = list(range(len(docs)))

    while len(selected_idx) < top_k and candidates:
        if not selected_idx:
            best = max(candidates, key=lambda i: scores[i])
        else:
            def mmr(i: int) -> float:
                rel = lambda_param * scores[i]
                max_sim = max(_word_sim(docs[i].content, docs[j].content) for j in selected_idx)
                return rel - (1 - lambda_param) * max_sim
            best = max(candidates, key=mmr)

        selected_idx.append(best)
        candidates.remove(best)

    return [docs[i] for i in selected_idx]


def _compute_confidence(docs: list[RetrievedDoc], verified: bool) -> float:
    if not docs:
        return 0.0
    avg_cred = sum(d.metadata.get("credibility_score", 0.5) for d in docs) / len(docs)
    coverage = min(len(docs) / 10.0, 1.0)
    base = avg_cred * 0.7 + coverage * 0.3
    return round(base * (1.0 if verified else 0.8), 2)


rag_pipeline = RAGPipeline()

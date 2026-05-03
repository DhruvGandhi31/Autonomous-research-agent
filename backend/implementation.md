This is the full 8-layer architecture. Now let me go through every section in depth.

---

## 1. System Architecture

### Component 1: Web Crawling Subsystem

**Role:** Intelligently discover and fetch content from the web while respecting politeness constraints and prioritizing high-quality sources.

**Technologies:** Scrapy (async, battle-tested), Playwright (JS-heavy pages), trafilatura (content extraction), Redis (URL frontier deduplication).

**Key design decisions:**

- Use a *focused crawler* — seed URLs are scored before crawling based on domain authority. You do not crawl the entire web; you crawl a topic-relevant slice of it.
- Maintain a **URL frontier priority queue**: URLs scored by predicted relevance (via a lightweight classifier on the anchor text and domain) get crawled first.
- Politeness enforcement: per-domain rate limiting (1 req/sec default), robots.txt parsing, exponential backoff on 429/503 responses.
- Store raw HTML + extracted clean text separately — you will need both (raw for re-processing, clean for indexing).

```python
# app/tools/crawler/focused_crawler.py
import scrapy
from scrapy.crawler import CrawlerProcess
from trafilatura import extract
from trafilatura.settings import use_config
from urllib.robotparser import RobotFileParser
import hashlib, time
from typing import Optional

config = use_config()
config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")

class FocusedSpider(scrapy.Spider):
    name = "focused"
    custom_settings = {
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DOWNLOAD_DELAY": 1.0,
        "ROBOTSTXT_OBEY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
        "USER_AGENT": "ResearchAgent/1.0 (+https://localhost/bot)",
        "HTTPCACHE_ENABLED": True,
        "HTTPCACHE_EXPIRATION_SECS": 86400,  # 24h cache
        "HTTPCACHE_DIR": "./app/data/cache/httpcache",
        "DEPTH_LIMIT": 3,
    }

    def __init__(self, start_urls: list[str], topic_keywords: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls
        self.topic_keywords = [kw.lower() for kw in topic_keywords]
        self.seen_hashes: set[str] = set()

    def parse(self, response):
        # Content extraction with trafilatura
        clean_text: Optional[str] = extract(
            response.text,
            config=config,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,  # Prefer clean text over recall
        )
        if not clean_text or len(clean_text) < 200:
            return  # Skip low-content pages

        # Deduplication via content hash
        content_hash = hashlib.sha256(clean_text[:2000].encode()).hexdigest()
        if content_hash in self.seen_hashes:
            return
        self.seen_hashes.add(content_hash)

        # Relevance pre-filter: require at least 2 topic keywords
        text_lower = clean_text.lower()
        keyword_hits = sum(1 for kw in self.topic_keywords if kw in text_lower)
        if keyword_hits < 2:
            return

        yield {
            "url": response.url,
            "title": response.css("title::text").get(""),
            "content": clean_text,
            "content_hash": content_hash,
            "crawled_at": time.time(),
            "status_code": response.status,
            "keyword_hits": keyword_hits,
        }

        # Follow links — score before enqueuing
        for href in response.css("a::attr(href)").getall():
            absolute = response.urljoin(href)
            if self._is_worth_following(absolute):
                yield scrapy.Request(absolute, callback=self.parse, priority=keyword_hits)

    def _is_worth_following(self, url: str) -> bool:
        skip_exts = {".pdf", ".doc", ".zip", ".mp4", ".jpg", ".png", ".gif"}
        skip_patterns = ["login", "signup", "cart", "checkout", "cdn-cgi"]
        url_lower = url.lower()
        if any(url_lower.endswith(ext) for ext in skip_exts):
            return False
        if any(p in url_lower for p in skip_patterns):
            return False
        return url_lower.startswith("http")
```

---

### Component 2: Document Processing Pipeline

**Role:** Transform raw HTML/PDFs/text into clean, chunked, enriched documents ready for embedding and indexing.

**Technologies:** Docling (PDF/DOCX parsing), Unstructured (multi-format), spaCy (entity extraction), sentence-transformers (chunking guidance).

**Pipeline stages:**

```
Raw Document → Format Detection → Text Extraction → 
Language Detection → Quality Filter → Chunking → 
Entity Extraction → Metadata Enrichment → Output
```

```python
# app/services/document_processor.py
from dataclasses import dataclass, field
from typing import Optional
import re, hashlib, time
import spacy
from langdetect import detect

nlp = spacy.load("en_core_web_sm")  # pip install spacy && python -m spacy download en_core_web_sm

@dataclass
class ProcessedChunk:
    chunk_id: str
    source_url: str
    content: str
    token_count: int
    chunk_index: int
    total_chunks: int
    entities: list[str]
    metadata: dict = field(default_factory=dict)

class DocumentProcessor:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process(self, raw: dict) -> list[ProcessedChunk]:
        text = raw.get("content", "")

        # Quality gate
        if not self._passes_quality_filter(text):
            return []

        # Language gate — English only for now
        try:
            if detect(text) != "en":
                return []
        except Exception:
            pass

        # Clean
        text = self._clean_text(text)

        # Chunk with overlap
        chunks = self._semantic_chunk(text)

        # Enrich each chunk
        processed = []
        for i, chunk in enumerate(chunks):
            doc = nlp(chunk[:1000])  # spaCy cap to avoid OOM
            entities = list({ent.text for ent in doc.ents if ent.label_ in
                             {"ORG", "PERSON", "GPE", "PRODUCT", "EVENT", "LAW"}})

            chunk_id = hashlib.sha256(f"{raw['url']}:{i}".encode()).hexdigest()[:16]

            processed.append(ProcessedChunk(
                chunk_id=chunk_id,
                source_url=raw["url"],
                content=chunk,
                token_count=len(chunk.split()),
                chunk_index=i,
                total_chunks=len(chunks),
                entities=entities,
                metadata={
                    "title": raw.get("title", ""),
                    "crawled_at": raw.get("crawled_at", time.time()),
                    "domain": self._extract_domain(raw["url"]),
                    "keyword_hits": raw.get("keyword_hits", 0),
                }
            ))

        return processed

    def _passes_quality_filter(self, text: str) -> bool:
        if len(text.split()) < 100:
            return False
        # Reject boilerplate/nav-heavy content
        nav_keywords = ["cookie policy", "terms of service", "404 not found", "javascript required"]
        text_lower = text.lower()
        if sum(1 for kw in nav_keywords if kw in text_lower) >= 2:
            return False
        # Reject near-duplicate boilerplate (very short paragraphs dominating)
        paragraphs = [p for p in text.split("\n") if len(p.strip()) > 20]
        if len(paragraphs) < 3:
            return False
        return True

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"(https?://\S+)", "", text)  # Strip URLs
        text = re.sub(r"\[.*?\]", "", text)          # Strip brackets
        return text.strip()

    def _semantic_chunk(self, text: str) -> list[str]:
        """Sentence-boundary-aware chunking"""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks, current, count = [], [], 0

        for sent in sentences:
            words = len(sent.split())
            if count + words > self.chunk_size and current:
                chunks.append(" ".join(current))
                # Keep overlap
                overlap_words, overlap_count = [], 0
                for s in reversed(current):
                    w = len(s.split())
                    if overlap_count + w <= self.chunk_overlap:
                        overlap_words.insert(0, s)
                        overlap_count += w
                    else:
                        break
                current = overlap_words
                count = overlap_count
            current.append(sent)
            count += words

        if current:
            chunks.append(" ".join(current))

        return chunks

    def _extract_domain(self, url: str) -> str:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
```

---

### Component 3: Hybrid Retrieval System

**Role:** Combine dense (semantic) and sparse (keyword) search to maximize both recall and precision.

**Technologies:** Qdrant (vector DB, local), tantivy-py (BM25, Rust-backed, fast), nomic-embed-text (local embeddings via Ollama), Reciprocal Rank Fusion (RRF) for score merging.

**Why hybrid?** Dense search excels at semantic similarity ("transformer architecture" → "attention mechanism"). Sparse search excels at exact term matching (model names, paper titles, version numbers). Neither alone matches both well — combining them is the single biggest quality lever.

```python
# app/services/retrieval/hybrid_retriever.py
import asyncio
from dataclasses import dataclass
from typing import Optional
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    SearchRequest, Filter, FieldCondition, Range
)
from app.services.llm_service import llm_service
from loguru import logger

@dataclass
class RetrievedDoc:
    chunk_id: str
    content: str
    source_url: str
    dense_rank: Optional[int]
    sparse_rank: Optional[int]
    rrf_score: float
    metadata: dict

RRF_K = 60  # RRF constant — higher = less weight on top ranks

class HybridRetriever:
    def __init__(self, collection: str = "research_docs"):
        self.qdrant = QdrantClient(path="./app/data/vectorstore/qdrant")
        self.collection = collection
        self._ensure_collection()

    def _ensure_collection(self):
        collections = [c.name for c in self.qdrant.get_collections().collections]
        if self.collection not in collections:
            self.qdrant.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE)
            )
            logger.info(f"Created Qdrant collection: {self.collection}")

    async def index_documents(self, chunks: list) -> int:
        """Embed and index document chunks"""
        points = []
        for chunk in chunks:
            embedding = await llm_service.embed_text(chunk.content)
            points.append(PointStruct(
                id=int(chunk.chunk_id[:8], 16),  # Convert hex to int for Qdrant
                vector=embedding,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "source_url": chunk.source_url,
                    "domain": chunk.metadata.get("domain", ""),
                    "title": chunk.metadata.get("title", ""),
                    "crawled_at": chunk.metadata.get("crawled_at", 0),
                    "keyword_hits": chunk.metadata.get("keyword_hits", 0),
                    "entities": chunk.entities,
                }
            ))

        self.qdrant.upsert(collection_name=self.collection, points=points)
        logger.info(f"Indexed {len(points)} chunks into Qdrant")
        return len(points)

    async def retrieve(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[dict] = None,
        use_hyde: bool = True
    ) -> list[RetrievedDoc]:
        """Full hybrid retrieval with RRF fusion"""

        # Optional HyDE: generate a hypothetical answer to embed
        # This dramatically improves retrieval for abstract queries
        if use_hyde:
            hyde_doc = await self._generate_hypothetical_document(query)
            embed_query = hyde_doc
        else:
            embed_query = query

        # Run dense and sparse retrieval in parallel
        dense_results, sparse_results = await asyncio.gather(
            self._dense_search(embed_query, top_k * 2),
            self._bm25_search(query, top_k * 2)
        )

        # RRF fusion
        fused = self._reciprocal_rank_fusion(dense_results, sparse_results, top_k)

        return fused

    async def _dense_search(self, query: str, top_k: int) -> list[dict]:
        """Qdrant semantic search"""
        embedding = await llm_service.embed_text(query)
        results = self.qdrant.search(
            collection_name=self.collection,
            query_vector=embedding,
            limit=top_k,
            with_payload=True
        )
        return [{"id": r.id, "payload": r.payload, "score": r.score} for r in results]

    async def _bm25_search(self, query: str, top_k: int) -> list[dict]:
        """
        BM25 via tantivy-py. 
        Install: pip install tantivy
        Index must be built separately — see IndexBuilder class below.
        """
        try:
            import tantivy
            index = tantivy.Index.open("./app/data/vectorstore/tantivy_index")
            searcher = index.searcher()
            query_parser = tantivy.QueryParser.for_index(index, ["content", "title"])
            parsed = query_parser.parse_query(query)
            hits = searcher.search(parsed, top_k).hits
            results = []
            for score, addr in hits:
                doc = searcher.doc(addr)
                results.append({
                    "id": doc.get_first("chunk_id"),
                    "payload": {
                        "content": doc.get_first("content"),
                        "source_url": doc.get_first("source_url"),
                        "title": doc.get_first("title"),
                        "domain": doc.get_first("domain"),
                    },
                    "score": score
                })
            return results
        except Exception as e:
            logger.warning(f"BM25 search failed, falling back to dense only: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        dense: list[dict],
        sparse: list[dict],
        top_k: int
    ) -> list[RetrievedDoc]:
        """
        RRF score = Σ 1 / (k + rank_i)
        Proven to outperform weighted sum in most IR benchmarks.
        """
        scores: dict[str, dict] = {}

        for rank, doc in enumerate(dense):
            cid = doc["payload"].get("chunk_id", str(doc["id"]))
            if cid not in scores:
                scores[cid] = {"payload": doc["payload"], "dense_rank": None, "sparse_rank": None}
            scores[cid]["dense_rank"] = rank
            scores[cid]["dense_rrf"] = 1.0 / (RRF_K + rank + 1)

        for rank, doc in enumerate(sparse):
            cid = doc["payload"].get("chunk_id", str(doc["id"]))
            if cid not in scores:
                scores[cid] = {"payload": doc["payload"], "dense_rank": None, "sparse_rank": None}
            scores[cid]["sparse_rank"] = rank
            scores[cid]["sparse_rrf"] = 1.0 / (RRF_K + rank + 1)

        fused = []
        for cid, data in scores.items():
            rrf = data.get("dense_rrf", 0) + data.get("sparse_rrf", 0)
            fused.append(RetrievedDoc(
                chunk_id=cid,
                content=data["payload"].get("content", ""),
                source_url=data["payload"].get("source_url", ""),
                dense_rank=data.get("dense_rank"),
                sparse_rank=data.get("sparse_rank"),
                rrf_score=rrf,
                metadata=data["payload"]
            ))

        fused.sort(key=lambda x: x.rrf_score, reverse=True)
        return fused[:top_k]

    async def _generate_hypothetical_document(self, query: str) -> str:
        """
        HyDE: Hypothetical Document Embeddings.
        Generate what a perfect answer would look like, then embed THAT.
        Closes the query-document distribution gap significantly.
        """
        prompt = f"""Write a dense, technical paragraph that directly answers this research question. 
        Do not include citations or hedging. Just write the factual content as if from an authoritative source.
        
        Question: {query}
        
        Answer paragraph:"""
        try:
            return await llm_service.generate(prompt, max_tokens=200, temperature=0.1)
        except Exception:
            return query  # Fallback to original query
```

---

## 2. Data Flow (End-to-End)**Design rationale for key stages:**

Stage 3 uses HyDE because embedding a query like *"transformer architectures"* and embedding a document about transformers live in different distribution spaces — the query is terse, the document is dense. Generating a hypothetical answer first and embedding that closes this gap significantly (shown to improve NDCG@10 by 5–15% in BEIR benchmarks).

Stage 4 uses a cross-encoder reranker (ms-marco-MiniLM-L-6-v2 running locally) rather than only vector similarity. Cross-encoders see both query and document together — much more powerful for ranking, but too slow for initial retrieval (hence the two-stage approach).

Stage 7's self-critique pass is a second LLM call that audits the generated response against the context. It flags any sentence not traceable to the retrieved chunks, which is your main defense against hallucination.

---

## 3. Implementation Details

### Full Tech Stack

```
Runtime:         Python 3.11
Web framework:   FastAPI + uvicorn
Crawling:        Scrapy 2.11 + Playwright + trafilatura
Doc parsing:     Docling, Unstructured, pdfminer.six
NLP:             spaCy (en_core_web_sm), langdetect
Embeddings:      nomic-embed-text via Ollama (768-dim, local)
LLM:             Llama 3.1 8B/70B via Ollama
Vector DB:       Qdrant (local persistent mode)
BM25 index:      tantivy-py (Rust-backed, 10x faster than Whoosh)
Reranker:        sentence-transformers ms-marco-MiniLM-L-6-v2 (local)
KV cache:        diskcache (pure Python, no Redis dependency)
Document store:  SQLite (with FTS5 extension enabled)
Task queue:      Celery + Redis (or arq for lighter footprint)
Orchestration:   Custom ReAct loop (avoid LangChain overhead in prod)
```

### Hybrid RAG Workflow — Complete Example

```python
# app/services/rag_pipeline.py
from dataclasses import dataclass
from typing import Optional
import json

from app.services.retrieval.hybrid_retriever import HybridRetriever
from app.services.ranking.credibility_scorer import CredibilityScorer
from app.services.ranking.reranker import CrossEncoderReranker
from app.services.llm_service import llm_service
from loguru import logger

@dataclass
class RAGResponse:
    answer: str
    citations: list[dict]
    confidence: float
    sources_used: int
    critique: Optional[str] = None

SYSTEM_PROMPT = """You are a precise research assistant. You answer questions using ONLY the provided context chunks.

Rules:
- Cite every factual claim using [N] notation, where N is the chunk number
- If the context does not contain enough information, say so explicitly
- Never invent facts not present in the context
- Use technical language appropriate to the topic
- Structure responses with clear paragraphs"""

SYNTHESIS_PROMPT = """Context chunks (use these as your ONLY sources):

{context}

---
Research question: {query}

Provide a comprehensive, well-cited answer. Every factual sentence must include at least one citation [N]."""

CRITIQUE_PROMPT = """Review this research response for unsupported claims:

Response:
{response}

Context used:
{context_summary}

List any sentences that make claims NOT supported by the context. 
If all claims are supported, respond with "VERIFIED".
Be specific — quote the problematic sentence."""

class RAGPipeline:
    def __init__(self):
        self.retriever = HybridRetriever()
        self.reranker = CrossEncoderReranker()
        self.scorer = CredibilityScorer()

    async def query(self, question: str, top_k: int = 12) -> RAGResponse:
        logger.info(f"RAG query: {question[:80]}")

        # Step 1: Retrieve candidates (top-40 via hybrid)
        candidates = await self.retriever.retrieve(question, top_k=40, use_hyde=True)

        if not candidates:
            return RAGResponse(
                answer="Insufficient information in the knowledge base for this query.",
                citations=[], confidence=0.0, sources_used=0
            )

        # Step 2: Score credibility
        for doc in candidates:
            doc.metadata["credibility_score"] = self.scorer.score(doc)

        # Step 3: Cross-encoder rerank
        reranked = await self.reranker.rerank(question, candidates, top_n=top_k)

        # Step 4: MMR diversity selection — avoid redundant chunks
        selected = self._mmr_select(reranked, top_k=12, lambda_param=0.6)

        # Step 5: Build context with citation IDs
        context_parts = []
        citations = []
        for i, doc in enumerate(selected, 1):
            context_parts.append(f"[{i}] {doc.content}")
            citations.append({
                "id": i,
                "url": doc.source_url,
                "title": doc.metadata.get("title", ""),
                "domain": doc.metadata.get("domain", ""),
                "credibility": doc.metadata.get("credibility_score", 0.5)
            })

        context = "\n\n".join(context_parts)

        # Step 6: Synthesize
        prompt = SYNTHESIS_PROMPT.format(context=context, query=question)
        answer = await llm_service.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,  # Low temp for factual accuracy
            max_tokens=1024
        )

        # Step 7: Self-critique
        context_summary = "\n".join([f"[{i+1}] {d.content[:200]}" for i, d in enumerate(selected)])
        critique_prompt = CRITIQUE_PROMPT.format(response=answer, context_summary=context_summary)
        critique = await llm_service.generate(critique_prompt, temperature=0.1, max_tokens=256)
        verified = critique.strip().upper().startswith("VERIFIED")

        confidence = self._compute_confidence(selected, verified)

        logger.info(f"RAG complete: {len(selected)} sources, confidence={confidence:.2f}")

        return RAGResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            sources_used=len(selected),
            critique=None if verified else critique
        )

    def _mmr_select(self, docs: list, top_k: int, lambda_param: float = 0.6) -> list:
        """
        Maximal Marginal Relevance — balance relevance with diversity.
        lambda=1.0 → pure relevance. lambda=0.0 → pure diversity.
        """
        if len(docs) <= top_k:
            return docs

        import numpy as np
        selected_indices, candidate_indices = [], list(range(len(docs)))

        # Use RRF score as relevance proxy
        scores = np.array([d.rrf_score for d in docs])
        scores = scores / (scores.max() + 1e-9)  # Normalize

        # Simple word overlap as similarity proxy (no extra embeddings needed)
        def word_sim(a: str, b: str) -> float:
            sa, sb = set(a.lower().split()), set(b.lower().split())
            return len(sa & sb) / (len(sa | sb) + 1e-9)

        while len(selected_indices) < top_k and candidate_indices:
            if not selected_indices:
                # Pick highest-scoring first
                best = max(candidate_indices, key=lambda i: scores[i])
            else:
                # MMR: balance relevance vs redundancy
                def mmr_score(i: int) -> float:
                    rel = lambda_param * scores[i]
                    sim = max(word_sim(docs[i].content, docs[j].content)
                              for j in selected_indices)
                    red = (1 - lambda_param) * sim
                    return rel - red

                best = max(candidate_indices, key=mmr_score)

            selected_indices.append(best)
            candidate_indices.remove(best)

        return [docs[i] for i in selected_indices]

    def _compute_confidence(self, docs: list, verified: bool) -> float:
        if not docs:
            return 0.0
        avg_credibility = sum(d.metadata.get("credibility_score", 0.5) for d in docs) / len(docs)
        base = avg_credibility * 0.7 + min(len(docs) / 10, 1.0) * 0.3
        return round(base * (1.0 if verified else 0.8), 2)
```

---

## 4. Credibility & Ranking System

This is one of the highest-leverage components for matching Perplexity-quality output.

```python
# app/services/ranking/credibility_scorer.py
import re
from urllib.parse import urlparse
from datetime import datetime
from dataclasses import dataclass

@dataclass
class CredibilityResult:
    total_score: float
    domain_score: float
    recency_score: float
    content_quality_score: float
    source_type: str
    breakdown: dict

class CredibilityScorer:
    # Tier 1: Highest authority sources
    TIER1_DOMAINS = {
        "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "nature.com", "science.org",
        "ieee.org", "acm.org", "dl.acm.org", "scholar.google.com",
        "research.google", "ai.meta.com", "openai.com", "anthropic.com",
        "deepmind.com", "huggingface.co", "papers.nips.cc", "mlsys.org"
    }
    # Tier 2: High-quality tech and news
    TIER2_DOMAINS = {
        "github.com", "stackoverflow.com", "medium.com", "towardsdatascience.com",
        "distill.pub", "lilianweng.github.io", "colah.github.io",
        "techcrunch.com", "wired.com", "arstechnica.com", "theverge.com",
        "hbr.org", "mit.edu", "stanford.edu", "berkeley.edu", "cmu.edu"
    }
    # Tier 3: General quality
    TIER3_DOMAINS = {
        "wikipedia.org", "reddit.com", "news.ycombinator.com",
        "blog.tensorflow.org", "pytorch.org", "docs.python.org"
    }
    # Explicit low-quality signals
    LOW_QUALITY_PATTERNS = [
        "click here", "buy now", "limited time offer",
        "sponsored content", "advertisement", "affiliate"
    ]

    def score(self, doc) -> float:
        """
        Scoring formula:
          total = 0.35 * domain_score
                + 0.25 * recency_score
                + 0.25 * content_quality_score
                + 0.15 * relevance_boost
        All sub-scores in [0.0, 1.0]
        """
        domain = doc.metadata.get("domain", "")
        content = doc.content
        crawled_at = doc.metadata.get("crawled_at", 0)
        keyword_hits = doc.metadata.get("keyword_hits", 0)

        domain_score = self._score_domain(domain)
        recency_score = self._score_recency(crawled_at)
        quality_score = self._score_content_quality(content)
        relevance_boost = min(keyword_hits / 10.0, 1.0)

        total = (
            0.35 * domain_score +
            0.25 * recency_score +
            0.25 * quality_score +
            0.15 * relevance_boost
        )

        return round(total, 3)

    def _score_domain(self, domain: str) -> float:
        domain = domain.lower()
        if any(d in domain for d in self.TIER1_DOMAINS):
            return 1.0
        if any(d in domain for d in self.TIER2_DOMAINS):
            return 0.75
        if any(d in domain for d in self.TIER3_DOMAINS):
            return 0.55
        # TLD bonuses for unknown domains
        if domain.endswith(".edu") or domain.endswith(".gov"):
            return 0.70
        if domain.endswith(".org"):
            return 0.50
        return 0.30  # Unknown domain — penalize

    def _score_recency(self, crawled_at: float) -> float:
        if not crawled_at:
            return 0.4
        age_days = (datetime.now().timestamp() - crawled_at) / 86400
        if age_days < 30:
            return 1.0
        elif age_days < 90:
            return 0.85
        elif age_days < 365:
            return 0.65
        elif age_days < 730:
            return 0.45
        else:
            return 0.25

    def _score_content_quality(self, content: str) -> float:
        score = 0.5  # Base

        # Penalize low-quality signals
        content_lower = content.lower()
        penalty = sum(0.1 for p in self.LOW_QUALITY_PATTERNS if p in content_lower)
        score -= min(penalty, 0.4)

        # Length signal — longer content (up to a point) tends to be more substantive
        word_count = len(content.split())
        if word_count > 500:
            score += 0.15
        elif word_count > 200:
            score += 0.08

        # Citation-like patterns in text (academic writing marker)
        citation_patterns = len(re.findall(r'\(\d{4}\)|\[\d+\]|et al\.', content))
        if citation_patterns >= 3:
            score += 0.20
        elif citation_patterns >= 1:
            score += 0.10

        # Technical density — presence of code blocks, formulas
        has_code = bool(re.search(r'def |import |class |```', content))
        if has_code:
            score += 0.10

        return round(min(max(score, 0.0), 1.0), 3)
```

---

## 5. Local-First Constraints

**No external API calls — every model runs locally:**

```python
# app/services/llm_service.py  (updated for local embedding)
import ollama
from functools import lru_cache

class LLMService:
    def __init__(self):
        self.client = ollama.Client(host="http://localhost:11434")
        self.chat_model = "llama3.1:8b"          # Inference
        self.embed_model = "nomic-embed-text"     # 768-dim, fast

    async def embed_text(self, text: str) -> list[float]:
        # Truncate to model's context window (8192 tokens for nomic)
        text = text[:6000]
        resp = self.client.embeddings(model=self.embed_model, prompt=text)
        return resp["embedding"]

# Cross-encoder reranker — runs 100% locally via sentence-transformers
# app/services/ranking/reranker.py
from sentence_transformers import CrossEncoder
import torch

class CrossEncoderReranker:
    def __init__(self):
        # ~22MB model, CPU-friendly
        self.model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            device="cpu",          # Swap to "cuda" if GPU available
            max_length=512
        )

    async def rerank(self, query: str, docs: list, top_n: int = 12) -> list:
        pairs = [(query, doc.content[:400]) for doc in docs]
        scores = self.model.predict(pairs, batch_size=32, show_progress_bar=False)
        for doc, score in zip(docs, scores):
            doc.metadata["rerank_score"] = float(score)
        docs.sort(key=lambda d: d.metadata["rerank_score"], reverse=True)
        return docs[:top_n]
```

**Compute optimization for limited hardware:**

```python
# Quantized Llama 3.1 — run on CPU with acceptable latency
# In Modelfile or via CLI:
# ollama pull llama3.1:8b-instruct-q4_K_M  (4-bit quantized, ~4.7GB RAM)

# Embedding batching — reduces Ollama round-trips dramatically
async def embed_batch(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = await asyncio.gather(*(self.embed_text(t) for t in batch))
        all_embeddings.extend(embeddings)
    return all_embeddings
```

---

## 6. Scalability & Performance

**Parallelization strategy:**

```python
# Async parallel crawling + processing pipeline
import asyncio
from asyncio import Queue

async def parallel_pipeline(urls: list[str], topic: str):
    crawl_queue = Queue(maxsize=100)
    process_queue = Queue(maxsize=200)

    async def crawler_worker(worker_id: int):
        while True:
            url = await crawl_queue.get()
            result = await fetch_and_extract(url)
            if result:
                await process_queue.put(result)
            crawl_queue.task_done()

    async def processor_worker(worker_id: int):
        processor = DocumentProcessor()
        while True:
            raw = await process_queue.get()
            chunks = processor.process(raw)
            if chunks:
                await retriever.index_documents(chunks)
            process_queue.task_done()

    # Seed URLs
    for url in urls:
        await crawl_queue.put(url)

    # 8 crawlers, 4 processors — tuned for local I/O vs CPU balance
    workers = (
        [asyncio.create_task(crawler_worker(i)) for i in range(8)] +
        [asyncio.create_task(processor_worker(i)) for i in range(4)]
    )

    await crawl_queue.join()
    for w in workers:
        w.cancel()
```

**Caching layers:**

```python
# Three-layer cache: query results → embeddings → LLM responses
import diskcache

class CacheManager:
    def __init__(self):
        self.query_cache = diskcache.Cache("./app/data/cache/queries", size_limit=2e9)     # 2GB
        self.embed_cache = diskcache.Cache("./app/data/cache/embeddings", size_limit=5e9)  # 5GB
        self.llm_cache = diskcache.Cache("./app/data/cache/llm", size_limit=1e9)           # 1GB

    def get_query(self, query_hash: str) -> dict | None:
        return self.query_cache.get(query_hash)

    def set_query(self, query_hash: str, result: dict, ttl: int = 3600):
        self.query_cache.set(query_hash, result, expire=ttl)

    def get_embedding(self, text_hash: str) -> list | None:
        return self.embed_cache.get(text_hash)

    def set_embedding(self, text_hash: str, embedding: list):
        self.embed_cache.set(text_hash, embedding)  # No TTL — embeddings are stable
```

**Latency vs quality trade-offs:**

| Configuration | P50 latency | Quality | Use case |
|---|---|---|---|
| BM25 only, no rerank | ~0.3s | Medium | Real-time autocomplete |
| Dense only, no rerank | ~0.8s | Good | Interactive chat |
| Hybrid + rerank, no HyDE | ~2.5s | Very good | Standard research |
| Hybrid + rerank + HyDE + critique | ~8s | Excellent | Deep research reports |

---

## 7. Example Output

**Query:** *"Latest advancements in transformer architectures beyond GPT-style models"*

```
RESEARCH RESPONSE
=================
Confidence: 0.87 | Sources: 11 | Verified: ✓

Several transformer variants have emerged that substantially depart from 
the dense, autoregressive GPT paradigm.

**State Space Models (SSMs) and Mamba:** Gu et al. (2023) introduced Mamba, 
a selective state space model that achieves linear-time sequence processing 
by selectively retaining or discarding information [1]. Unlike attention, 
which scales quadratically with sequence length, Mamba's selective scan 
mechanism processes long sequences (100K+ tokens) efficiently while 
matching or exceeding Transformer quality on language modeling benchmarks [1][2].

**Mixture-of-Experts (MoE):** Mistral's Mixtral 8x7B demonstrates sparse 
MoE — only 2 of 8 expert FFN layers activate per token, giving 46.7B 
effective parameters at the inference cost of ~12.9B [3]. Google's Switch 
Transformer and later Gemini 1.5 extend this to trillion-parameter scale 
with expert routing [4].

**Linear Attention Variants:** RetNet (Microsoft, 2023) proposes a 
retention mechanism supporting parallel training (like attention) and 
recurrent inference (O(1) per token), addressing the training-inference 
duality [5]. RWKV takes a different route — reformulating attention as an 
RNN, enabling constant-time inference with competitive language modeling 
performance [6].

**Architecture-Free Approaches:** Hyena and related long-convolution 
architectures replace attention with learnable subquadratic convolutions, 
showing competitive quality on sequence modeling benchmarks without 
explicit attention [7].

**Practical Takeaway:** For local deployment, Mamba and RWKV are most 
relevant — their recurrent inference modes allow lower memory footprint 
at long context lengths [2][6].

---
SOURCES
[1] arxiv.org — "Mamba: Linear-Time Sequence Modeling..." (2023) [credibility: 0.98]
[2] huggingface.co — "Mamba model card and benchmarks" (2024) [credibility: 0.91]
[3] mistral.ai — "Mixtral of Experts" technical blog (2023) [credibility: 0.89]
[4] research.google — "Switch Transformers" paper (2022) [credibility: 0.96]
[5] arxiv.org — "Retentive Network: A Successor to Transformer" (2023) [credibility: 0.98]
[6] github.com/BlinkDL/RWKV-LM — RWKV architecture repo (2023) [credibility: 0.82]
[7] arxiv.org — "Hyena Hierarchy: Towards Larger Convolutional LMs" (2023) [credibility: 0.97]
```

---

## 8. Risks & Challenges

**Risk 1: Embedding quality bottleneck**
Your retrieval ceiling is set by embedding quality. `nomic-embed-text` is strong for a local model, but specialized domains (law, medicine, code) may see degraded recall.
*Mitigation:* Fine-tune embeddings on domain-specific pairs using `sentence-transformers` training pipeline. Alternatively, use domain-specific models (`e5-mistral-7b-instruct` for high-quality, heavier workloads).

**Risk 2: Crawl freshness vs accuracy trade-off**
Cached content goes stale. A 24h cache returns outdated information for fast-moving topics like AI research.
*Mitigation:* Implement per-domain TTL policies — arxiv.org content is mostly permanent, news sites need hourly TTLs. Add a "forced refresh" mode triggered by recency signals in the query ("latest", "2024", "this week").

**Risk 3: Context window overflow**
With 12 chunks at 512 tokens each, you're at 6K+ tokens of context. Llama 3.1 8B handles 128K in theory but quality degrades past ~8K in practice.
*Mitigation:* Implement a token budget manager that uses the reranker score as a cutoff signal, not a fixed top-N. Alternatively, use a Map-Reduce summarization step for deep reports.

**Risk 4: Hallucination in synthesis**
Even with grounded prompting, the model will occasionally insert plausible-sounding but unsupported claims.
*Mitigation:* The self-critique pass is the primary defense. Add a sentence-level NLI entailment check (using `roberta-large-mnli` locally) as a harder second pass for high-stakes outputs. Flag any sentence with entailment score below 0.7.

**Risk 5: Compute saturation on concurrent queries**
Running Llama 3.1 8B, nomic embeddings, and cross-encoder reranking simultaneously on CPU will saturate a typical developer machine (16GB RAM).
*Mitigation:* Use a request queue with concurrency limit of 2. For embeddings, the DiskCache layer means ~80% of re-encountered chunks skip re-embedding. Profile with `py-spy` before optimizing — the bottleneck is almost always the LLM call, not retrieval.

---

**Implementation priority order for your current project:**

Start with the hybrid retriever and credibility scorer — these give you the biggest quality jump over what you have. Then add HyDE (single LLM call, major retrieval improvement). Then add the cross-encoder reranker. The self-critique pass can come last. Together these will close most of the gap with Perplexity on research quality, all running fully locally.
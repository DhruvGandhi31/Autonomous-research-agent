"""
Hybrid retrieval: dense (Qdrant) + sparse (tantivy BM25) fused via RRF.

Why hybrid:
  Dense search excels at semantic similarity ("transformer architecture" →
  "attention mechanism"). Sparse search excels at exact term matching
  (model names, version numbers, paper titles). Neither alone matches both.
  RRF fusion gives the best of both worlds.

HyDE (Hypothetical Document Embeddings):
  Embeds a generated hypothetical answer instead of the raw query, closing
  the query-document distribution gap. Typically improves NDCG@10 by 5-15%.

All heavy deps (qdrant-client, tantivy) are optional — the retriever
degrades gracefully to whichever backend is available.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from services.llm_service import llm_service

RRF_K = 60        # Higher = less weight on top-ranked docs
EMBEDDING_DIM = 768   # nomic-embed-text default

_HYDE_PROMPT = """\
Write a dense, technical paragraph that directly answers this research question.
Do not include citations or hedging. Write as if from an authoritative source.

Question: {query}

Answer paragraph:"""


@dataclass
class RetrievedDoc:
    chunk_id: str
    content: str
    source_url: str
    dense_rank: Optional[int]
    sparse_rank: Optional[int]
    rrf_score: float
    metadata: dict = field(default_factory=dict)


class HybridRetriever:
    def __init__(self, collection: str = "research_docs"):
        self.collection = collection
        self._qdrant = None
        self._qdrant_ok: Optional[bool] = None
        self._tantivy_index = None
        self._tantivy_ok: Optional[bool] = None

    # ── Lazy initialisation ────────────────────────────────────────────

    def _init_qdrant(self) -> bool:
        if self._qdrant_ok is not None:
            return self._qdrant_ok
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            self._qdrant = QdrantClient(path="./app/data/vectorstore/qdrant")
            names = [c.name for c in self._qdrant.get_collections().collections]
            if self.collection not in names:
                self._qdrant.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
                logger.info(f"Created Qdrant collection: {self.collection}")
            self._qdrant_ok = True
            logger.info("Qdrant initialised (local persistent mode)")
        except Exception as e:
            logger.warning(f"Qdrant unavailable: {e}")
            self._qdrant_ok = False
        return self._qdrant_ok

    def _init_tantivy(self) -> bool:
        if self._tantivy_ok is not None:
            return self._tantivy_ok
        try:
            import tantivy
            import os
            index_path = "./app/data/vectorstore/tantivy_index"
            os.makedirs(index_path, exist_ok=True)

            builder = tantivy.SchemaBuilder()
            builder.add_text_field("content", stored=True, tokenizer_name="en_stem")
            builder.add_text_field("title", stored=True)
            builder.add_text_field("source_url", stored=True)
            builder.add_text_field("domain", stored=True)
            builder.add_text_field("chunk_id", stored=True)
            schema = builder.build()

            try:
                self._tantivy_index = tantivy.Index.open(index_path)
            except Exception:
                self._tantivy_index = tantivy.Index(schema, path=index_path)

            self._tantivy_ok = True
            logger.info("tantivy BM25 index initialised")
        except Exception as e:
            logger.warning(f"tantivy unavailable (BM25 disabled): {e}")
            self._tantivy_ok = False
        return self._tantivy_ok

    # ── Indexing ───────────────────────────────────────────────────────

    async def index_documents(self, chunks: list) -> int:
        """
        Embed and index ProcessedChunk objects into Qdrant and tantivy.
        Returns number of chunks indexed.
        """
        if not chunks:
            return 0

        indexed = 0

        # Dense index (Qdrant)
        if self._init_qdrant():
            from qdrant_client.models import PointStruct
            texts = [c.content for c in chunks]
            try:
                embeddings = await llm_service.embed_batch(texts, batch_size=16)
                points = []
                for chunk, embedding in zip(chunks, embeddings):
                    # Qdrant requires integer IDs — derive from hex chunk_id
                    point_id = int(chunk.chunk_id[:15], 16) % (2**63)
                    points.append(PointStruct(
                        id=point_id,
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
                        },
                    ))
                def _upsert():
                    self._qdrant.upsert(collection_name=self.collection, points=points)
                await asyncio.to_thread(_upsert)
                indexed = len(points)
                logger.info(f"Indexed {indexed} chunks into Qdrant")
            except Exception as e:
                logger.warning(f"Qdrant indexing error: {e}")

        # Sparse index (tantivy)
        if self._init_tantivy():
            try:
                import tantivy
                writer = self._tantivy_index.writer()
                for chunk in chunks:
                    writer.add_document(tantivy.Document(
                        content=[chunk.content],
                        title=[chunk.metadata.get("title", "")],
                        source_url=[chunk.source_url],
                        domain=[chunk.metadata.get("domain", "")],
                        chunk_id=[chunk.chunk_id],
                    ))
                def _commit():
                    writer.commit()
                await asyncio.to_thread(_commit)
                logger.info(f"Indexed {len(chunks)} chunks into tantivy")
            except Exception as e:
                logger.warning(f"tantivy indexing error: {e}")

        return indexed

    # ── Retrieval ──────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int = 20,
        use_hyde: bool = True,
    ) -> list[RetrievedDoc]:
        """
        Full hybrid retrieval with RRF fusion.
        Falls back gracefully if one backend is unavailable.
        """
        embed_query = query
        if use_hyde:
            embed_query = await self._generate_hypothetical_document(query)

        dense_task = self._dense_search(embed_query, top_k * 2)
        sparse_task = self._bm25_search(query, top_k * 2)
        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)

        if not dense_results and not sparse_results:
            return []

        return self._rrf_fuse(dense_results, sparse_results, top_k)

    async def _dense_search(self, query: str, top_k: int) -> list[dict]:
        if not self._init_qdrant():
            return []
        try:
            embedding = await llm_service.embed_text(query)
            def _search():
                return self._qdrant.search(
                    collection_name=self.collection,
                    query_vector=embedding,
                    limit=top_k,
                    with_payload=True,
                )
            results = await asyncio.to_thread(_search)
            return [{"id": r.id, "payload": r.payload, "score": r.score} for r in results]
        except Exception as e:
            logger.warning(f"Dense search error: {e}")
            return []

    async def _bm25_search(self, query: str, top_k: int) -> list[dict]:
        if not self._init_tantivy():
            return []
        try:
            def _search():
                searcher = self._tantivy_index.searcher()
                qp = self._tantivy_index.parse_query(query, ["content", "title"])
                hits = searcher.search(qp, top_k).hits
                results = []
                for score, addr in hits:
                    doc = searcher.doc(addr)
                    results.append({
                        "id": doc.get_first("chunk_id"),
                        "payload": {
                            "chunk_id": doc.get_first("chunk_id"),
                            "content": doc.get_first("content"),
                            "source_url": doc.get_first("source_url"),
                            "title": doc.get_first("title"),
                            "domain": doc.get_first("domain"),
                        },
                        "score": score,
                    })
                return results
            return await asyncio.to_thread(_search)
        except Exception as e:
            logger.warning(f"BM25 search error: {e}")
            return []

    def _rrf_fuse(
        self, dense: list[dict], sparse: list[dict], top_k: int
    ) -> list[RetrievedDoc]:
        """
        Reciprocal Rank Fusion:  score = Σ 1/(k + rank_i)
        Outperforms weighted score sum across most IR benchmarks.
        """
        scores: dict[str, dict] = {}

        for rank, doc in enumerate(dense):
            cid = doc["payload"].get("chunk_id", str(doc["id"]))
            if cid not in scores:
                scores[cid] = {"payload": doc["payload"], "dense_rank": None,
                               "sparse_rank": None, "dense_rrf": 0, "sparse_rrf": 0}
            scores[cid]["dense_rank"] = rank
            scores[cid]["dense_rrf"] = 1.0 / (RRF_K + rank + 1)

        for rank, doc in enumerate(sparse):
            cid = doc["payload"].get("chunk_id", str(doc["id"]))
            if cid not in scores:
                scores[cid] = {"payload": doc["payload"], "dense_rank": None,
                               "sparse_rank": None, "dense_rrf": 0, "sparse_rrf": 0}
            scores[cid]["sparse_rank"] = rank
            scores[cid]["sparse_rrf"] = 1.0 / (RRF_K + rank + 1)

        fused = []
        for cid, data in scores.items():
            rrf = data["dense_rrf"] + data["sparse_rrf"]
            fused.append(RetrievedDoc(
                chunk_id=cid,
                content=data["payload"].get("content", ""),
                source_url=data["payload"].get("source_url", ""),
                dense_rank=data["dense_rank"],
                sparse_rank=data["sparse_rank"],
                rrf_score=rrf,
                metadata=data["payload"],
            ))

        fused.sort(key=lambda d: d.rrf_score, reverse=True)
        return fused[:top_k]

    async def _generate_hypothetical_document(self, query: str) -> str:
        """
        HyDE: generate what a perfect answer looks like, then embed THAT.
        Closes the query-document distribution gap significantly.
        """
        try:
            return await llm_service.generate(
                _HYDE_PROMPT.format(query=query),
                temperature=0.1,
                max_tokens=200,
            )
        except Exception:
            return query  # Graceful fallback

    @property
    def is_qdrant_available(self) -> bool:
        return self._init_qdrant()

    @property
    def is_tantivy_available(self) -> bool:
        return self._init_tantivy()


hybrid_retriever = HybridRetriever()

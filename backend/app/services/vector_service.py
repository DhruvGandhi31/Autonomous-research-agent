from typing import Any, Dict, List, Optional

from loguru import logger

from config.settings import settings
from services.llm_service import llm_service


class VectorService:
    """
    ChromaDB-backed semantic store for research content.
    Failures are isolated — the rest of the pipeline continues without it.
    """

    def __init__(self):
        self._client = None
        self._collection = None
        self._available: Optional[bool] = None

    def _init(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._client = chromadb.PersistentClient(
                path=settings.chroma_persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=settings.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info("ChromaDB initialised")
        except Exception as e:
            logger.warning(f"ChromaDB not available (vector search disabled): {e}")
            self._available = False
        return self._available

    async def store_document(
        self, doc_id: str, content: str, metadata: Dict[str, Any] | None = None
    ) -> bool:
        if not self._init():
            return False
        try:
            embedding = await llm_service.embed(content[:2000])
            self._collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content[:5000]],
                metadatas=[metadata or {}],
            )
            return True
        except Exception as e:
            logger.warning(f"Vector store write failed for {doc_id}: {e}")
            return False

    async def search_similar(
        self,
        query: str,
        n_results: int = 5,
        where: Dict | None = None,
    ) -> List[Dict[str, Any]]:
        if not self._init():
            return []
        try:
            embedding = await llm_service.embed(query)
            kwargs: dict = {"query_embeddings": [embedding], "n_results": n_results}
            if where:
                kwargs["where"] = where

            results = self._collection.query(**kwargs)
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            return [
                {"content": doc, "metadata": metas[i], "distance": distances[i]}
                for i, doc in enumerate(docs)
            ]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []


vector_service = VectorService()

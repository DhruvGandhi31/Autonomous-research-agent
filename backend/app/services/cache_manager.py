"""
Three-layer diskcache:
  query_cache    — full RAG query results (TTL: 1h by default)
  embed_cache    — embedding vectors (no TTL — stable)
  llm_cache      — LLM response strings (TTL: 6h by default)

All caches fail silently so the pipeline degrades to uncached operation.
"""
import hashlib
import json
from typing import Any, Optional

from loguru import logger


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class CacheManager:
    _QUERY_DIR = "./app/data/cache/queries"
    _EMBED_DIR = "./app/data/cache/embeddings"
    _LLM_DIR = "./app/data/cache/llm"
    _QUERY_SIZE = 2_000_000_000   # 2 GB
    _EMBED_SIZE = 5_000_000_000   # 5 GB
    _LLM_SIZE = 1_000_000_000     # 1 GB

    def __init__(self):
        self._q = None
        self._e = None
        self._l = None
        self._available = False
        self._init()

    def _init(self):
        try:
            import diskcache
            self._q = diskcache.Cache(self._QUERY_DIR, size_limit=self._QUERY_SIZE)
            self._e = diskcache.Cache(self._EMBED_DIR, size_limit=self._EMBED_SIZE)
            self._l = diskcache.Cache(self._LLM_DIR, size_limit=self._LLM_SIZE)
            self._available = True
            logger.info("CacheManager initialised (diskcache)")
        except Exception as ex:
            logger.warning(f"CacheManager unavailable (caching disabled): {ex}")

    # ── Query results ──────────────────────────────────────────────────

    def get_query(self, query: str) -> Optional[dict]:
        if not self._available:
            return None
        try:
            return self._q.get(_hash(query))
        except Exception:
            return None

    def set_query(self, query: str, result: dict, ttl: int = 3600):
        if not self._available:
            return
        try:
            self._q.set(_hash(query), result, expire=ttl)
        except Exception:
            pass

    # ── Embedding vectors ──────────────────────────────────────────────

    def get_embedding(self, text: str) -> Optional[list]:
        if not self._available:
            return None
        try:
            return self._e.get(_hash(text))
        except Exception:
            return None

    def set_embedding(self, text: str, embedding: list):
        if not self._available:
            return
        try:
            self._e.set(_hash(text), embedding)  # no TTL — stable
        except Exception:
            pass

    # ── LLM responses ─────────────────────────────────────────────────

    def get_llm(self, prompt: str) -> Optional[str]:
        if not self._available:
            return None
        try:
            return self._l.get(_hash(prompt))
        except Exception:
            return None

    def set_llm(self, prompt: str, response: str, ttl: int = 21600):
        if not self._available:
            return
        try:
            self._l.set(_hash(prompt), response, expire=ttl)
        except Exception:
            pass

    @property
    def is_available(self) -> bool:
        return self._available


cache_manager = CacheManager()

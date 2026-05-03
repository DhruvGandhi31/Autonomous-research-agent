import asyncio

import ollama
from loguru import logger

from config.settings import settings


class LLMService:
    def __init__(self):
        self.model = settings.default_model
        self.embedding_model = settings.embedding_model
        self._client: ollama.Client | None = None

    def _get_client(self) -> ollama.Client:
        if not self._client:
            self._client = ollama.Client(host=settings.ollama_base_url)
        return self._client

    def is_available(self) -> bool:
        try:
            self._get_client().list()
            return True
        except Exception as e:
            logger.error(f"Ollama not available: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        options: dict = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens

        client = self._get_client()

        def _sync_call() -> str:
            response = client.chat(model=self.model, messages=messages, options=options)
            return response.message.content

        return await asyncio.to_thread(_sync_call)

    async def embed(self, text: str) -> list[float]:
        """Embed text. Truncates to 6000 chars to stay within nomic-embed-text context."""
        # Check cache first
        from services.cache_manager import cache_manager
        cached = cache_manager.get_embedding(text)
        if cached is not None:
            return cached

        client = self._get_client()
        truncated = text[:6000]

        def _sync_call() -> list[float]:
            response = client.embeddings(model=self.embedding_model, prompt=truncated)
            return response["embedding"]

        result = await asyncio.to_thread(_sync_call)
        cache_manager.set_embedding(text, result)
        return result

    # Alias used by hybrid_retriever and rag_pipeline
    async def embed_text(self, text: str) -> list[float]:
        return await self.embed(text)

    async def embed_batch(
        self, texts: list[str], batch_size: int = 16
    ) -> list[list[float]]:
        """Embed multiple texts concurrently in batches."""
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = await asyncio.gather(*(self.embed(t) for t in batch))
            all_embeddings.extend(embeddings)
        return all_embeddings


llm_service = LLMService()

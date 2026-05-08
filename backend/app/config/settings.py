from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Ollama / LLM
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "llama3.1:8b"
    embedding_model: str = "nomic-embed-text"
    max_tokens: int = 4096
    temperature: float = 0.7

    # Vector Database
    chroma_persist_directory: str = "./app/data/vectorstore"
    collection_name: str = "research_documents"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    # Crawling
    max_crawl_depth: int = 3
    crawl_delay: float = 1.0
    user_agent: str = "ResearchAgent/1.0"
    max_requests_per_minute: int = 60

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # External APIs
    serpapi_key: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

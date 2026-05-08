# Backend Reference

The backend is a **FastAPI** application (`backend/app/`). Start it with:

```bash
cd backend/app
python main.py          # http://localhost:8000
```

> **Import path quirk**: `main.py` appends its own directory to `sys.path`, so all imports are relative to `backend/app/` (e.g. `from config.settings import settings`). The server **must** be started from within `backend/app/`.

---

## Table of Contents

1. [Configuration](#1-configuration)
2. [Application Entry Point](#2-application-entry-point)
3. [Core — Agent](#3-core--agent)
4. [Core — Planner](#4-core--planner)
5. [Core — Memory Manager](#5-core--memory-manager)
6. [Services — LLM Service](#6-services--llm-service)
7. [Services — RAG Pipeline](#7-services--rag-pipeline)
8. [Services — Hybrid Retriever](#8-services--hybrid-retriever)
9. [Services — Document Processor](#9-services--document-processor)
10. [Services — Cache Manager](#10-services--cache-manager)
11. [Services — Credibility Scorer](#11-services--credibility-scorer)
12. [Services — CrossEncoder Reranker](#12-services--crossencoder-reranker)
13. [Services — Chat Service](#13-services--chat-service)
14. [Services — Image Analyzer](#14-services--image-analyzer)
15. [Services — Document Extractor](#15-services--document-extractor)
16. [Tools — Base Tool](#16-tools--base-tool)
17. [Tools — Web Search](#17-tools--web-search)
18. [Tools — Academic Search](#18-tools--academic-search)
19. [Tools — Summarizer](#19-tools--summarizer)
20. [Tools — Focused Crawler](#20-tools--focused-crawler)
21. [API Routes — Research](#21-api-routes--research)
22. [API Routes — Chat](#22-api-routes--chat)
23. [API Routes — Upload](#23-api-routes--upload)

---

## 1. Configuration

**File**: `config/settings.py`

All settings are read from `backend/.env` via Pydantic `BaseSettings`. Every setting has a default so the `.env` file is optional.

```python
class Settings(BaseSettings):
    # Ollama / LLM
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "llama3.1:8b"
    embedding_model: str = "nomic-embed-text"
    max_tokens: int = 4096
    temperature: float = 0.7

    # Vector Database (legacy ChromaDB path, Qdrant is primary)
    chroma_persist_directory: str = "./app/data/vectorstore"
    collection_name: str = "research_documents"

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    # Web crawler
    max_crawl_depth: int = 3
    crawl_delay: float = 1.0
    user_agent: str = "ResearchAgent/1.0"
    max_requests_per_minute: int = 60
```

**`.env` example** (`backend/.env`):
```env
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=llama3.1:8b
API_PORT=8000
DEBUG=True
```

---

## 2. Application Entry Point

**File**: `main.py`

### Lifespan (startup / shutdown)

On **startup**:
1. Creates data directories: `app/data/{vectorstore,documents,reports,cache,memory,chat}`
2. Verifies Ollama is reachable (raises `RuntimeError` if not)
3. Registers three tools with `ResearchAgent`: `web_search`, `summarizer`, `academic_search`

On **shutdown**:
- Closes aiohttp sessions for all tools

### CORS

Allows all methods from `http://localhost:3000` and `http://127.0.0.1:3000` (Next.js dev server).

### Registered Routes

| Prefix | Module | Tags |
|---|---|---|
| `/api/research` | `api/routes/research.py` | research |
| `/api/chat` | `api/routes/chat.py` | chat |
| `/api/upload` | `api/routes/upload.py` | upload |

### Built-in Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | API info JSON |
| `GET` | `/health` | Ollama status, agent state, active session count |

---

## 3. Core — Agent

**File**: `core/agent.py`  
**Singleton**: `research_agent`

The `ResearchAgent` orchestrates the full 6-step research pipeline.

### State Machine

```
IDLE → PLANNING → RESEARCHING → SYNTHESIZING → COMPLETE
                                             → ERROR
```

Each research job (`research_id`) has its own independent state tracked in `_research_states: Dict[str, AgentState]`.

### Key Methods

#### `conduct_research(topic, requirements, research_id)`

Main async entry point. Runs the complete pipeline:

1. **Store context** — saves topic, status `"planning"`, timestamps to `MemoryManager`
2. **Create plan** — calls `TaskPlanner.create_research_plan()` → JSON task list
3. **Execute tasks** — `_execute_tasks()` runs batches of ≤3 concurrent tasks, respecting dependency order
4. **Process & index** — `_process_and_index()` extracts raw content → `DocumentProcessor` → `HybridRetriever.index_documents()`
5. **RAG synthesis** — `_rag_synthesize()` → `RAGPipeline.query()` (or fallback direct synthesis)
6. **Mark complete** — stores final report insight, updates status to `"complete"`

#### `_execute_tasks(research_id, tasks, topic)`

```python
while remaining tasks:
    ready = tasks with all dependencies satisfied
    batch = ready[:3]
    await asyncio.gather(*[execute each task in batch])
```

If a task's tool name is unknown, it silently falls back to `web_search`.

#### `_fallback_synthesize(research_id, topic)`

Used when RAG pipeline has no indexed data (e.g., all tools failed). Builds a direct LLM prompt from raw task result summaries.

#### `get_research_status(research_id) → dict`

Returns:
```json
{
  "research_id": "...",
  "topic": "...",
  "status": "researching",
  "agent_state": "researching",
  "started_at": "ISO datetime",
  "completed_at": null,
  "error": null,
  "progress": {
    "completed_tasks": 4,
    "total_tasks": 7,
    "percentage": 57
  }
}
```

#### `get_research_results(research_id) → dict`

Returns the full report, citations, confidence score, verified flag, and a deduplicated list of all sources from all task results.

---

## 4. Core — Planner

**File**: `core/planner.py`  
**Singleton**: `task_planner`

### `create_research_plan(topic, requirements) → dict`

Sends a structured prompt to `llm_service.generate()` (temperature 0.3) asking the LLM to produce a JSON research plan. The JSON is then parsed and each task is assigned a UUID.

**Prompt instructs the LLM to use only three tool names**: `web_search`, `academic_search`, `summarizer`.

### Plan Schema

```json
{
  "research_id": "...",
  "topic": "...",
  "research_strategy": "...",
  "key_questions": ["..."],
  "tasks": [
    {
      "id": "task_abc12345",
      "name": "Search recent papers",
      "description": "...",
      "tool": "academic_search",
      "parameters": { "query": "...", "max_results": 5 },
      "priority": 8,
      "dependencies": [],
      "estimated_time": 5,
      "status": "pending"
    }
  ],
  "expected_outcomes": ["..."],
  "success_criteria": ["..."],
  "created_at": "ISO datetime"
}
```

### Fallback Plan

If the LLM returns invalid JSON, `_create_fallback_plan()` creates a single `web_search` task for the topic.

---

## 5. Core — Memory Manager

**File**: `core/memory.py`  
**Singleton**: `memory_manager`

Provides key-value storage for research session data with in-memory cache + JSON-on-disk persistence.

### Storage Layout

All files are stored under `app/data/memory/` with naming convention `{research_id}_{type}.json`:

| File pattern | Content |
|---|---|
| `{id}_context.json` | Topic, status, timestamps, requirements |
| `{id}_plan.json` | Full task plan from planner |
| `{id}_{task_id}_result.json` | Tool execution result for one task |
| `{id}_insight_{timestamp}.json` | Final report, citations, confidence |

### Key Methods

| Method | Description |
|---|---|
| `store_context(research_id, context)` | Save/update the research context dict |
| `store_plan(research_id, plan)` | Save the task plan |
| `store_task_result(research_id, task_id, result)` | Save one task's output |
| `store_insight(research_id, insight)` | Save final report data |
| `get_research_context(research_id)` | Read context (cache → disk) |
| `get_research_plan(research_id)` | Read task plan |
| `get_task_results(research_id)` | Read all task results for a session |
| `clear_research_session(research_id)` | Delete all memory + disk files |

---

## 6. Services — LLM Service

**File**: `services/llm_service.py`  
**Singleton**: `llm_service`

Thin async wrapper around the `ollama` Python SDK.

### Methods

#### `generate(prompt, system_prompt, temperature, max_tokens) → str`

Constructs a `messages` array (optional system + user) and calls `ollama.Client.chat()` in `asyncio.to_thread`. Returns the response string.

#### `embed(text) → list[float]`

Calls `ollama.Client.embeddings()` with `nomic-embed-text`. Checks embedding cache first (`CacheManager`); writes result on miss. Truncates input to 6000 chars.

#### `embed_batch(texts, batch_size=16) → list[list[float]]`

Embeds multiple texts concurrently using `asyncio.gather()` in batches.

#### `is_available() → bool`

Calls `client.list()` to verify Ollama is reachable.

---

## 7. Services — RAG Pipeline

**File**: `services/rag_pipeline.py`  
**Singleton**: `rag_pipeline`

Full Perplexity-quality local retrieval-augmented generation pipeline. All steps are local.

### `query(question, top_k=12) → RAGResponse`

**Step-by-step:**

1. **Cache check** — returns cached `RAGResponse` if available (1h TTL)
2. **Retrieve candidates** — `HybridRetriever.retrieve(question, top_k=k*3, use_hyde=True)`
3. **Credibility scoring** — `CredibilityScorer.score(doc)` per chunk
4. **Cross-encoder rerank** — `CrossEncoderReranker.rerank(question, candidates, top_n=k*2)`
5. **MMR diversity selection** — `_mmr_select(reranked, top_k=k, lambda=0.6)`  
   MMR formula: `score = λ * relevance - (1-λ) * max_similarity_to_selected`
6. **Build context** — numbered `[N] content` blocks + citations array
7. **LLM synthesis** — temperature 0.2, `max_tokens=1200`, inline `[N]` citations
8. **Self-critique** — checks if any claim in the answer is unsupported by context; sets `verified=True` only if the critique returns exactly `VERIFIED`
9. **Confidence score** — `0.7 * avg_credibility + 0.3 * (sources_used/10)`, multiplied by 0.8 if unverified

### `RAGResponse` fields

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | Full LLM-generated report with `[N]` citations |
| `citations` | `list[dict]` | `{id, url, title, domain, credibility, source_type}` per source |
| `confidence` | `float` | 0.0–1.0 quality score |
| `sources_used` | `int` | Number of chunks used in synthesis |
| `verified` | `bool` | Passed self-critique check |
| `critique` | `str \| None` | Hallucination notes if not verified |

---

## 8. Services — Hybrid Retriever

**File**: `services/retrieval/hybrid_retriever.py`  
**Singleton**: `hybrid_retriever`

Combines dense (Qdrant) and sparse (tantivy BM25) retrieval with Reciprocal Rank Fusion.

### Storage

- **Qdrant** — persisted at `./app/data/vectorstore/qdrant`, collection `research_docs`, 768-dimensional cosine similarity (nomic-embed-text)
- **tantivy** — persisted at `./app/data/vectorstore/tantivy_index`, BM25 over `content` + `title` + `url` fields

Both are lazily initialised on first use.

### `index_documents(chunks) → int`

Accepts a list of chunk dicts with `{chunk_id, content, source_url, metadata}`. Upserts into both Qdrant and tantivy. Returns number of successfully indexed chunks.

### `retrieve(query, top_k, use_hyde) → list[RetrievedDoc]`

1. **HyDE** (if `use_hyde=True`) — calls `llm_service.generate()` to produce a hypothetical answer paragraph, then embeds it instead of the raw query
2. **Dense search** — Qdrant vector search returning ranked list with scores
3. **Sparse search** — tantivy BM25 keyword search
4. **RRF fusion** — `score = Σ 1/(RRF_K + rank)` for each doc appearing in either list (RRF_K=60)

### `RetrievedDoc` fields

| Field | Type | Description |
|---|---|---|
| `chunk_id` | `str` | Unique chunk identifier |
| `content` | `str` | Text content of the chunk |
| `source_url` | `str` | Origin URL |
| `dense_rank` | `int \| None` | Rank in Qdrant results |
| `sparse_rank` | `int \| None` | Rank in tantivy results |
| `rrf_score` | `float` | Fused RRF score |
| `metadata` | `dict` | title, domain, crawled_at, keyword_hits, etc. |

---

## 9. Services — Document Processor

**File**: `services/document_processor.py`  
**Singleton**: `document_processor`

Transforms raw crawled/fetched content into indexable chunks.

### `process(raw_doc) → list[dict]`

**Pipeline:**
1. **Language detection** — `langdetect`; skips non-English content
2. **Quality filter** — minimum 100 words; deduplication by content hash
3. **Text cleaning** — strip excess whitespace, normalize Unicode
4. **Semantic chunking** — splits on sentence boundaries into 512-token chunks with 64-token overlap
5. **NER tagging** — spaCy `en_core_web_sm`; entities stored in chunk metadata
6. **Returns** list of chunk dicts with `chunk_id`, `content`, `source_url`, `metadata`

---

## 10. Services — Cache Manager

**File**: `services/cache_manager.py`  
**Singleton**: `cache_manager`

Three independent `diskcache.Cache` instances, all under `app/data/cache/`:

| Cache | Directory | Size Limit | TTL | Key |
|---|---|---|---|---|
| Query results | `cache/queries/` | 2 GB | 1 hour | SHA-256 of query string |
| Embeddings | `cache/embeddings/` | 5 GB | No expiry | SHA-256 of text |
| LLM responses | `cache/llm/` | 1 GB | 6 hours | SHA-256 of prompt |

All operations fail silently — if `diskcache` is unavailable, the pipeline continues uncached.

---

## 11. Services — Credibility Scorer

**File**: `services/ranking/credibility_scorer.py`  
**Singleton**: `credibility_scorer`

Scores a `RetrievedDoc` on a 0.0–1.0 scale using four weighted factors:

```
total = 0.35 × domain_score
      + 0.25 × recency_score
      + 0.25 × content_quality_score
      + 0.15 × relevance_boost
```

### Domain Tiers

| Tier | Score | Examples |
|---|---|---|
| Tier 1 (academic) | 1.00 | arxiv.org, nature.com, openai.com, anthropic.com |
| Tier 2 (quality) | 0.75 | github.com, .edu, .gov, springer.com, mit.edu |
| Tier 3 (general) | 0.55 | wikipedia.org, reddit.com, pytorch.org |
| Unknown | 0.30 | Everything else |

### Recency Score

| Age | Score |
|---|---|
| < 30 days | 1.00 |
| 30–90 days | 0.85 |
| 90–365 days | 0.65 |
| 1–2 years | 0.45 |
| > 2 years | 0.25 |

### Content Quality Signals

- **Bonuses**: >500 words (+0.15), >200 words (+0.08), ≥3 academic citations (+0.20), code blocks (+0.10)
- **Penalties**: Low-quality phrases like "buy now", "sponsored content" (-0.10 each, max -0.40)

---

## 12. Services — CrossEncoder Reranker

**File**: `services/ranking/reranker.py`  
**Singleton**: `reranker`

Second-stage reranker using `cross-encoder/ms-marco-MiniLM-L-6-v2` (sentence-transformers).

### `rerank(query, docs, top_n) → list[RetrievedDoc]`

Creates `(query, doc_content)` pairs, runs them through the CrossEncoder, replaces `rrf_score` with the CrossEncoder logit, and returns the top-N by score. Falls back to the original RRF order if the model is unavailable.

---

## 13. Services — Chat Service

**File**: `services/chat_service.py`  
**Singleton**: `chat_service`

Manages persistent conversation sessions for the chat UI.

### Data Models

#### `ChatMessage`
```python
@dataclass
class ChatMessage:
    id: str                        # UUID
    role: str                      # "user" | "assistant"
    content: str
    timestamp: str                 # ISO 8601
    attachments: list              # list of FileAttachment dicts
    research_id: Optional[str]     # set if this message triggered research
    sources: list                  # citation list (assistant messages)
```

#### `ChatSession`
```python
@dataclass
class ChatSession:
    id: str                        # UUID
    title: str                     # Auto-generated from first user message
    created_at: str
    updated_at: str
    mode: str                      # "chat" | "research"
    messages: list                 # list of ChatMessage
```

### Storage

Sessions are persisted as `{uuid}.json` files under `app/data/chat/`. Loaded into memory on startup, written on every change.

### Key Methods

| Method | Description |
|---|---|
| `create_session(title, mode)` | Create and persist a new session |
| `get_session(session_id)` | Return session by ID |
| `list_sessions()` | All sessions sorted by `updated_at` descending |
| `delete_session(session_id)` | Remove session from memory and disk |
| `add_message(session_id, message)` | Append message; auto-titles session from first user message |
| `get_conversation_history(session_id, limit=20)` | Return last N messages as `[{role, content}]` dicts; prepends attached file text to user messages |
| `rename_session(session_id, title)` | Update session title |

### File Attachment Handling

When building conversation history for the LLM, `get_conversation_history()` prepends each attachment's `extracted_text` to the user message content:

```
[Attached: report.pdf]
<extracted PDF text>

<original user message>
```

---

## 14. Services — Image Analyzer

**File**: `services/image_service.py`  
**Singleton**: `image_analyzer`

Analyzes uploaded images via two methods, tried in order:

### 1. llava (Ollama vision model)

Calls `ollama.Client.chat()` with `model="llava"` and the image as a base64 string. Produces a rich description including visible text, charts, diagrams, and key information.

Availability is checked once at first use by calling `client.list()` and searching for `"llava"` in model names.

### 2. pytesseract OCR (fallback)

Opens the image with `PIL.Image`, runs `pytesseract.image_to_string()`. Returns extracted text. Requires system Tesseract installation.

### `analyze(image_bytes, user_query) → dict`

```python
{
    "description": str,      # llava output (empty if not available)
    "ocr_text": str,         # pytesseract output (empty if not available)
    "combined": str,         # "Image Analysis:\n{desc}\n\nExtracted Text:\n{ocr}"
    "llava_used": bool,
    "ocr_used": bool,
}
```

---

## 15. Services — Document Extractor

**File**: `services/document_extractor.py`  
**Singleton**: `document_extractor`

### `extract(content: bytes, filename: str) → dict`

Dispatches by file extension:

| Extension | Library | Notes |
|---|---|---|
| `.pdf` | `PyPDF2.PdfReader` | Extracts text from all pages |
| `.docx` / `.doc` | `python-docx` | Extracts paragraphs + table cell text |
| `.txt` | built-in | UTF-8 decode with error replacement |

Returns:
```python
{
    "text": str,       # full extracted text (capped at 50k chars in route)
    "pages": int,      # page count (PDF) or paragraph count (DOCX)
    "method": str,     # "pypdf2" | "python-docx" | "plain_text"
    "error": str,      # only present on failure
}
```

---

## 16. Tools — Base Tool

**File**: `tools/base_tool.py`

Abstract base class all tools must implement.

```python
@dataclass
class ToolResult:
    success: bool
    data: dict | None = None
    error: str | None = None
    sources: list = field(default_factory=list)
    summaries: list = field(default_factory=list)

class BaseTool(ABC):
    def __init__(self, name: str, description: str): ...
    
    @abstractmethod
    async def execute(self, parameters: dict) -> ToolResult: ...
    
    @abstractmethod
    def _get_parameters_schema(self) -> dict: ...
    
    async def close(self): ...  # override to clean up aiohttp sessions
```

---

## 17. Tools — Web Search

**File**: `tools/web_search.py`  
**Singleton**: `web_search_tool`

### `execute({query, max_results}) → ToolResult`

1. Scrapes DuckDuckGo HTML search (`https://html.duckduckgo.com/html/`) via aiohttp
2. Parses result links and snippets with BeautifulSoup
3. Fetches full page content for the top 5 results using `AsyncFocusedCrawler`
4. Returns structured data:

```python
ToolResult.data = {
    "query": str,
    "total_results": int,
    "results": [{"url", "title", "snippet"}, ...],
    "detailed_content": [{"url", "title", "content"}, ...]
}
ToolResult.sources = [{"url", "title", "snippet"}, ...]
ToolResult.summaries = [first 500 chars of each detailed result]
```

---

## 18. Tools — Academic Search

**File**: `tools/academic_search.py`  
**Singleton**: `academic_search_tool`

Queries three academic sources concurrently using `asyncio.gather()`:

| Source | API | Notes |
|---|---|---|
| arXiv | `export.arxiv.org/api/query` (XML) | Returns title, authors, summary, published date |
| Semantic Scholar | `api.semanticscholar.org/graph/v1/paper/search` | Returns title, authors, year, abstract, citationCount |
| Wikipedia | `en.wikipedia.org/api/rest_v1/page/summary/{topic}` | Returns title, extract, URL |

Academic sources are assigned a `credibility_boost` of 5 `keyword_hits` in the indexing stage, giving them higher credibility scores.

---

## 19. Tools — Summarizer

**File**: `tools/summarizer.py`  
**Singleton**: `summarizer_tool`

### `execute({content, topic}) → ToolResult`

Calls `llm_service.generate()` with a structured summarization prompt. The LLM is asked to return JSON with:

```json
{
    "executive_summary": "...",
    "key_points": ["..."],
    "insights": ["..."],
    "credibility": "high|medium|low",
    "relevance": "high|medium|low"
}
```

Falls back to raw text if the JSON parse fails.

---

## 20. Tools — Focused Crawler

**File**: `tools/crawler/focused_crawler.py`

`AsyncFocusedCrawler` — depth-limited, keyword-filtered web crawler used internally by `WebSearchTool`.

Key behaviours:
- Respects `robots.txt` via `urllib.robotparser`
- Rate limiting: configurable delay between requests
- Keyword relevance filtering: only follows links containing topic keywords
- Content extraction: `trafilatura.extract()` for clean article text (better than plain BeautifulSoup)
- Priority URL frontier: BFS with keyword-hit scoring
- Returns `list[CrawledPage]` with `url`, `title`, `content`, `crawled_at`, `keyword_hits`

---

## 21. API Routes — Research

**File**: `api/routes/research.py`  
**Prefix**: `/api/research`

See the full [API Reference](./api-reference.md#research-endpoints) for request/response schemas.

| Method | Path | Description |
|---|---|---|
| `POST` | `/start` | Queue a new research job (returns immediately with `research_id`) |
| `GET` | `/status/{research_id}` | Poll pipeline progress |
| `GET` | `/results/{research_id}` | Fetch completed report (202 if still running) |
| `DELETE` | `/session/{research_id}` | Delete session from memory and disk |
| `GET` | `/sessions` | List all active sessions |
| `GET` | `/test/llm` | Verify Ollama is responding |
| `POST` | `/test/search` | Test DuckDuckGo search |
| `POST` | `/test/academic` | Test academic search |
| `POST` | `/test/summarize` | Test LLM summarization |
| `POST` | `/query` | Direct RAG query against the knowledge base |
| `POST` | `/crawl` | Focused crawl of provided seed URLs |

---

## 22. API Routes — Chat

**File**: `api/routes/chat.py`  
**Prefix**: `/api/chat`

| Method | Path | Description |
|---|---|---|
| `POST` | `/sessions` | Create a new chat session |
| `GET` | `/sessions` | List all sessions (sorted by `updated_at`) |
| `GET` | `/sessions/{session_id}` | Get full session with all messages |
| `DELETE` | `/sessions/{session_id}` | Delete session |
| `PATCH` | `/sessions/{session_id}/rename` | Rename session |
| `POST` | `/sessions/{session_id}/messages` | **Send message** — streaming SSE response |

### Send Message — SSE Stream

**Request body:**
```json
{
    "content": "Your message",
    "attachments": [
        {
            "name": "report.pdf",
            "file_type": "document",
            "extracted_text": "...",
            "description": "Document 'report.pdf' — 12 pages",
            "size": 204800
        }
    ],
    "trigger_research": false
}
```

**Response**: `Content-Type: text/event-stream`

Chat mode SSE events:
```
data: {"type":"chunk","content":"Hello"}
data: {"type":"chunk","content":" world"}
data: {"type":"done","message":{"id":"...","role":"assistant","content":"Hello world",...}}
```

Research mode SSE events:
```
data: {"type":"research_started","research_id":"research_abc123","topic":"quantum computing"}
data: {"type":"done","message":{"id":"...","role":"assistant","content":"Starting research...","research_id":"research_abc123"}}
```

Error SSE event:
```
data: {"type":"error","error":"Connection to Ollama failed"}
```

### System Prompt (chat mode)

```
You are a highly capable research assistant. You help users understand complex topics, 
analyze documents and images, and conduct in-depth research. When users share document 
or image content, analyze it carefully and provide detailed insights.

Use markdown formatting for clarity (headers, bullet points, code blocks). 
Be concise yet thorough.
```

---

## 23. API Routes — Upload

**File**: `api/routes/upload.py`  
**Prefix**: `/api/upload`

| Method | Path | Description |
|---|---|---|
| `POST` | `/image` | Upload image → OCR + vision analysis |
| `POST` | `/document` | Upload PDF / DOCX / TXT → text extraction |

### Limits

- Maximum file size: 20 MB
- Accepted image types: JPEG, PNG, GIF, WEBP, BMP
- Accepted document types: PDF, DOCX, DOC, TXT

### `POST /image`

Form fields: `file` (required), `query` (optional — passed to llava for context-aware analysis)

**Response:**
```json
{
    "filename": "screenshot.png",
    "content_type": "image/png",
    "size": 102400,
    "extracted_text": "Image Analysis:\n...\n\nExtracted Text (OCR):\n...",
    "description": "llava description",
    "ocr_text": "raw OCR output",
    "llava_used": true,
    "ocr_used": false,
    "file_type": "image"
}
```

### `POST /document`

Form field: `file` (required)

**Response:**
```json
{
    "filename": "report.pdf",
    "content_type": "application/pdf",
    "size": 1048576,
    "extracted_text": "... (capped at 50,000 chars) ...",
    "description": "Document 'report.pdf' — 24 pages/paragraphs extracted",
    "preview": "First 500 characters...",
    "char_count": 48320,
    "method": "pypdf2",
    "file_type": "document"
}
```

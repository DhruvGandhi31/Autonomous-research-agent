# Research Agent

An autonomous AI research assistant with a Perplexity-style chat interface. Runs entirely locally — no external AI APIs required.

**Stack:** FastAPI · Next.js 14 · Ollama (llama3.1:8b) · Qdrant · tantivy BM25 · sentence-transformers

---

## Features

- **Autonomous research pipeline** — plan → multi-source search → RAG synthesis → hallucination-guarded report
- **Per-message tool selector** — choose Chat, Web Search, Academic, or Full Research per message via chips in the input area
- **Session mode toggle** — switch any session between Chat and Research mode from the header
- **Streaming chat** — token-by-token responses via Ollama
- **Image analysis** — llava vision model + pytesseract OCR fallback
- **Document upload** — PDF, DOCX, TXT extraction with full LLM context
- **Persistent sessions** — chat history saved to disk
- **Academic search** — arXiv (with 429 retry), Semantic Scholar, Wikipedia, Google Scholar (SerpApi, optional)
- **Source citations** — inline `[N]` references with credibility scoring
- **Dark-mode UI** — Next.js 14 + Tailwind CSS

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend |
| Node.js | 18+ | Frontend |
| [Ollama](https://ollama.ai) | latest | Local LLM server |
| Tesseract | 5+ | Optional — image OCR ([install guide](https://github.com/UB-Mannheim/tesseract/wiki)) |

---

## Quick Start

### 1 — Start Ollama

```bash
ollama serve

# Required models
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# Optional — image analysis
ollama pull llava
```

### 2 — Backend

```bash
# From project root (research-agent/)
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Create data directories
mkdir -p backend/app/app/data/vectorstore
mkdir -p backend/app/app/data/documents
mkdir -p backend/app/app/data/reports
mkdir -p backend/app/app/data/cache
mkdir -p backend/app/app/data/memory
mkdir -p backend/app/app/data/chat
mkdir -p backend/logs

# Start the server
cd backend/app
python main.py
```

Server runs at **http://localhost:8000** · Interactive docs at **http://localhost:8000/docs**

### 3 — Frontend

```bash
# From project root, in a new terminal
cd frontend
npm install
npm run dev
```

UI runs at **http://localhost:3000**

### 4 — Verify

```bash
# Health check
curl http://localhost:8000/health

# LLM connectivity
curl http://localhost:8000/api/research/test/llm
```

---

## Environment Variables

Copy `.env.example` to `backend/.env` (or `backend/app/.env`) and edit as needed.

```env
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=llama3.1:8b
CHROMA_PERSIST_DIRECTORY=./app/data/vectorstore
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True

# Optional — override allowed CORS origins (comma-separated or JSON list)
# CORS_ORIGINS=["http://localhost:3000","https://your-domain.com"]

# Optional — Google Scholar via SerpApi (https://serpapi.com)
SERPAPI_KEY=your_key_here
```

---

## Project Layout

```
research-agent/
├── backend/
│   ├── .env                          ← environment variables
│   └── app/
│       ├── main.py                   ← FastAPI entry point
│       ├── config/settings.py        ← Pydantic settings
│       ├── core/
│       │   ├── agent.py              ← Research orchestrator
│       │   ├── planner.py            ← LLM task planner
│       │   └── memory.py             ← JSON persistence
│       ├── services/
│       │   ├── rag_pipeline.py       ← HyDE → rerank → MMR → synthesise → critique
│       │   ├── llm_service.py        ← Ollama async wrapper
│       │   ├── chat_service.py       ← Session management
│       │   ├── image_service.py      ← llava + pytesseract
│       │   ├── document_extractor.py ← PDF / DOCX / TXT
│       │   ├── document_processor.py ← chunking + NER
│       │   ├── cache_manager.py      ← 3-layer diskcache
│       │   ├── retrieval/
│       │   │   └── hybrid_retriever.py  ← Qdrant + tantivy + RRF
│       │   └── ranking/
│       │       ├── credibility_scorer.py
│       │       └── reranker.py       ← CrossEncoder ms-marco
│       ├── tools/
│       │   ├── base_tool.py
│       │   ├── web_search.py         ← DuckDuckGo
│       │   ├── academic_search.py    ← arXiv · Semantic Scholar · Wikipedia · Google Scholar
│       │   ├── summarizer.py
│       │   └── crawler/
│       │       └── focused_crawler.py
│       └── api/routes/
│           ├── research.py
│           ├── chat.py
│           └── upload.py
├── frontend/
│   └── src/
│       ├── app/                      ← Next.js App Router
│       ├── components/
│       │   ├── layout/Sidebar.tsx
│       │   ├── chat/
│       │   │   ├── ChatArea.tsx
│       │   │   ├── MessageBubble.tsx
│       │   │   ├── InputArea.tsx
│       │   │   └── WelcomeScreen.tsx
│       │   └── research/
│       │       ├── ResearchProgress.tsx
│       │       └── ResearchReport.tsx
│       ├── contexts/ChatContext.tsx
│       ├── hooks/useResearch.ts
│       └── lib/
│           ├── api.ts
│           ├── types.ts
│           └── utils.ts
├── docs/
│   ├── architecture.md
│   ├── backend.md
│   ├── frontend.md
│   └── api-reference.md
├── tests/
│   ├── sanity_backend.py             ← backend smoke tests
│   └── sanity_frontend.py           ← frontend smoke tests
├── requirements.txt
└── README.md
```

---

## API Quick Reference

### System
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Ollama status + active sessions |
| `GET` | `/docs` | Swagger UI |

### Chat
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat/sessions` | Create session |
| `GET` | `/api/chat/sessions` | List sessions |
| `GET` | `/api/chat/sessions/{id}` | Get session with messages |
| `DELETE` | `/api/chat/sessions/{id}` | Delete session |
| `PATCH` | `/api/chat/sessions/{id}/rename` | Rename session |
| `POST` | `/api/chat/sessions/{id}/messages` | **Send message (SSE stream)** |

### Research
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/research/start` | Start autonomous research job |
| `GET` | `/api/research/status/{id}` | Poll progress |
| `GET` | `/api/research/results/{id}` | Fetch completed report |
| `DELETE` | `/api/research/session/{id}` | Delete session |
| `GET` | `/api/research/sessions` | List all sessions |
| `POST` | `/api/research/query` | Direct RAG query |

### Upload
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/upload/image` | OCR + vision analysis (JPEG/PNG/GIF/WEBP) |
| `POST` | `/api/upload/document` | Text extraction (PDF/DOCX/TXT) |

---

## Smoke Tests

```bash
# Backend (server must be running)
python tests/sanity_backend.py

# Frontend (both servers must be running)
python tests/sanity_frontend.py
```

---

## Architecture Overview

```
Browser (localhost:3000)
  └─ Next.js frontend (rewrites /api/* → localhost:8000)
       └─ FastAPI backend (localhost:8000)
            ├─ Ollama (localhost:11434)  llama3.1:8b · nomic-embed-text · llava
            ├─ Qdrant (local files)      dense vector store
            ├─ tantivy (local files)     BM25 sparse index
            └─ diskcache (local files)   query · embedding · LLM caches
```

**Research pipeline (triggered by any non-Chat tool mode):**
```
User selects tool chip (Web / Academic / Full Research) → sends message
  │
POST /api/chat/sessions/{id}/messages
  │  trigger_research: true, tool_preference: "web_search" | "academic_search" | ""
  │
  1. TaskPlanner (LLM)   → JSON task list  [tool_preference hint appended to prompt]
  2. Concurrent tasks    → web_search · academic_search · summarizer
  3. DocumentProcessor   → language filter → chunking → spaCy NER
  4. HybridRetriever     → Qdrant dense + tantivy BM25 → RRF fusion
  5. RAGPipeline         → HyDE → CrossEncoder rerank → MMR → LLM → self-critique
  6. MemoryManager       → persist report + citations + confidence
```

**Frontend tool mode → backend mapping:**

| Chip | `trigger_research` | `tool_preference` |
|---|---|---|
| 💬 Chat | `false` | `""` |
| 🌐 Web Search | `true` | `"web_search"` |
| 📚 Academic | `true` | `"academic_search"` |
| 🔬 Full Research | `true` | `""` |

---

## Troubleshooting

**Ollama unavailable**
```bash
ollama serve          # start in a separate terminal
ollama list           # verify models are pulled
```

**`ModuleNotFoundError`**
```bash
# Ensure venv is active and server is started from correct directory
cd backend/app && python main.py
```

**Port already in use**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# macOS/Linux
lsof -ti:8000 | xargs kill
```

**Frontend can't reach backend**
- Confirm the backend is running on port 8000
- Check `frontend/next.config.mjs` — the proxy rewrites `/api/*` to `http://localhost:8000`

**No search results**
- Check internet connectivity
- DuckDuckGo occasionally rate-limits automated requests; wait a few seconds and retry

---

## Detailed Documentation

See the [`docs/`](./docs/) directory:

- [`docs/architecture.md`](./docs/architecture.md) — full system design and data flows
- [`docs/backend.md`](./docs/backend.md) — every Python service, tool, and route
- [`docs/frontend.md`](./docs/frontend.md) — every component, hook, and context
- [`docs/api-reference.md`](./docs/api-reference.md) — complete HTTP API reference
- [`docs/bug-fix.md`](./docs/bug-fix.md) — all 13 bug fixes with before/after code

# Research Agent — Project Documentation

> An autonomous AI research assistant powered by local LLMs (Ollama / llama3.1:8b) with a Perplexity-style web interface.

---

## Table of Contents

| Document | Description |
|---|---|
| [Architecture](./architecture.md) | End-to-end system design, data flows, component diagrams |
| [Backend Reference](./backend.md) | All Python services, tools, routes, and configuration |
| [Frontend Reference](./frontend.md) | Next.js components, context, hooks, and UI design |
| [API Reference](./api-reference.md) | Every HTTP endpoint with request/response schemas |

---

## Quick Overview

```
research-agent/
├── backend/app/          ← FastAPI application (Python 3.11+)
│   ├── main.py           ← Entry point, lifespan, CORS, route registration
│   ├── config/           ← Pydantic settings (reads .env)
│   ├── core/             ← agent · planner · memory
│   ├── services/         ← LLM · RAG pipeline · hybrid retriever · chat · image · cache
│   ├── tools/            ← web_search · academic_search · summarizer · crawler
│   └── api/routes/       ← research · chat · upload
├── frontend/             ← Next.js 14 (TypeScript + Tailwind CSS)
│   └── src/
│       ├── app/          ← Root layout and page
│       ├── components/   ← Sidebar · ChatArea · MessageBubble · InputArea · Research*
│       ├── contexts/     ← ChatContext (global state)
│       ├── hooks/        ← useResearch (polling)
│       └── lib/          ← API client · TypeScript types · utilities
├── docs/                 ← This documentation
└── requirements.txt      ← Python dependencies
```

---

## Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend runtime |
| Ollama | latest | Local LLM server |
| llama3.1:8b | — | Main LLM (`ollama pull llama3.1:8b`) |
| nomic-embed-text | — | Embeddings (`ollama pull nomic-embed-text`) |
| llava | — | **Optional** — image analysis (`ollama pull llava`) |
| Tesseract | 5+ | **Optional** — OCR fallback (system install) |

---

## Quick Start

### 1. Start Ollama

```bash
ollama serve
ollama pull llama3.1:8b
ollama pull nomic-embed-text
# Optional (image analysis):
ollama pull llava
```

### 2. Backend

```bash
# From project root
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Create required data directories
mkdir -p backend/app/app/data/{vectorstore,documents,reports,cache,memory,chat}

cd backend/app
python main.py                 # Server starts at http://localhost:8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                    # UI at http://localhost:3000
```

### 4. Verify

- Open `http://localhost:3000` — the chat interface should load.
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

---

## Environment Variables (`backend/.env`)

```env
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=llama3.1:8b
CHROMA_PERSIST_DIRECTORY=./app/data/vectorstore
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True
```

All settings have sensible defaults — `.env` is optional.

---

## Feature Matrix

| Feature | Status | Notes |
|---|---|---|
| Chat with streaming | ✅ | SSE streaming via Ollama |
| Chat memory (session history) | ✅ | JSON persistence under `app/data/chat/` |
| Autonomous research pipeline | ✅ | Plan → Search → Index → RAG → Report |
| Image analysis (vision) | ✅ | llava (preferred) + Tesseract OCR (fallback) |
| PDF upload | ✅ | PyPDF2 text extraction |
| DOCX upload | ✅ | python-docx text extraction |
| Source citations | ✅ | Inline `[N]` + sources panel |
| Hallucination guard | ✅ | Self-critique pass in RAG pipeline |
| Confidence scoring | ✅ | Based on credibility + coverage |
| Dark-mode UI | ✅ | Tailwind CSS custom theme |

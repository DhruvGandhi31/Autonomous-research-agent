# Architecture

---

## System Overview

The Research Agent is a fully local, privacy-first AI research assistant. Every computation — LLM inference, embeddings, vector search — runs on your machine via Ollama. No external AI APIs are used.

```
Browser (localhost:3000)
       │  HTTP / SSE
       ▼
Next.js 14 Frontend
  │  Rewrites /api/* → http://localhost:8000/api/*
  ▼
FastAPI Backend (localhost:8000)
  ├── /api/chat/*      ← conversation management + streaming LLM
  ├── /api/research/*  ← autonomous research pipeline
  └── /api/upload/*    ← image OCR / document extraction
       │
       ├── Ollama (localhost:11434)
       │     ├── llama3.1:8b        ← text generation
       │     ├── nomic-embed-text   ← embeddings
       │     └── llava              ← image analysis (optional)
       │
       ├── Qdrant (local file)      ← dense vector store
       ├── tantivy (local file)     ← BM25 sparse index
       └── diskcache (local files)  ← 3-layer response cache
```

---

## Request Flows

### A. Chat Message (streaming)

```
POST /api/chat/sessions/{id}/messages
  │
  ├── Save user message to ChatService (JSON)
  ├── Build conversation history (last 20 messages)
  ├── Detect mode: chat vs. research
  │
  ├── [chat mode]
  │     └── Stream ollama.chat(llama3.1:8b, messages, stream=True)
  │           → SSE: data: {"type":"chunk","content":"..."}  (token by token)
  │           → SSE: data: {"type":"done","message":{...}}   (final, saved to JSON)
  │
  └── [research mode]
        ├── Create research_id
        ├── Store initial context in MemoryManager
        ├── Kick off ResearchAgent.conduct_research() as BackgroundTask
        └── SSE: data: {"type":"research_started","research_id":"..."}
              → SSE: data: {"type":"done","message":{...research_id set}}
```

### B. Autonomous Research Pipeline

```
POST /api/research/start  (or triggered from chat)
  │
  ├── 1. PLANNING
  │     TaskPlanner.create_research_plan(topic)
  │     └── LLM generates JSON task list with tool assignments + dependencies
  │
  ├── 2. EXECUTION (concurrent batches of ≤3 tasks, dependency-aware)
  │     ├── web_search    → DuckDuckGo HTML scrape → content extraction
  │     ├── academic_search → arXiv API + Semantic Scholar API + Wikipedia
  │     └── summarizer    → LLM summarisation of collected snippets
  │
  ├── 3. DOCUMENT PROCESSING
  │     DocumentProcessor.process(raw_doc)
  │     ├── Language filter (langdetect — English only)
  │     ├── Quality filter (min 100 words, dedup)
  │     ├── Semantic chunking (512 tokens, 64 overlap)
  │     └── spaCy NER (entity extraction to metadata)
  │
  ├── 4. INDEXING
  │     HybridRetriever.index_documents(chunks)
  │     ├── Qdrant (dense) — nomic-embed-text embeddings, cosine similarity
  │     └── tantivy (sparse) — BM25 term index
  │
  ├── 5. RAG SYNTHESIS
  │     RAGPipeline.query(topic)
  │     ├── HyDE: embed hypothetical answer instead of raw query
  │     ├── Hybrid retrieve: Qdrant + tantivy → RRF fusion
  │     ├── CredibilityScorer: domain tier + recency + content quality
  │     ├── CrossEncoder rerank: ms-marco-MiniLM-L-6-v2
  │     ├── MMR selection: diversity-aware top-K (λ=0.6)
  │     ├── LLM synthesise: structured report with [N] inline citations
  │     └── Self-critique: hallucination guard → sets verified flag
  │
  └── 6. COMPLETE
        Store report + citations + confidence in MemoryManager
        Update status → "complete"
```

### C. File Upload → Chat

```
POST /api/upload/image
  ├── Try llava (Ollama vision) → rich image description
  └── Fallback: pytesseract OCR → extracted text

POST /api/upload/document
  ├── .pdf → PyPDF2.PdfReader → full text
  └── .docx → python-docx → paragraphs + tables

Result: { extracted_text, description, ... }
  └── Frontend attaches as FileAttachment to next chat message
        └── extracted_text prepended to conversation history
              └── LLM sees document/image content as context
```

---

## Data Persistence

All data is stored locally under `backend/app/app/data/`:

```
app/data/
├── memory/          ← Research sessions (JSON files, named by research_id)
│   ├── {id}_context.json       ← topic, status, timestamps
│   ├── {id}_plan.json          ← LLM-generated task list
│   ├── {id}_{task}_result.json ← per-task raw output
│   └── {id}_insight_*.json     ← final report + citations
├── chat/            ← Chat sessions (one JSON file per session UUID)
│   └── {uuid}.json             ← title, mode, messages[]
├── vectorstore/     ← Qdrant database (persistent local mode)
│   └── qdrant/
├── cache/           ← diskcache directories
│   ├── queries/     ← RAG query results (1h TTL)
│   ├── embeddings/  ← embedding vectors (no TTL)
│   └── llm/         ← LLM responses (6h TTL)
└── documents/       ← (future use)
```

---

## Component Dependency Graph

```
main.py
  ├── ResearchAgent (core/agent.py)
  │     ├── TaskPlanner (core/planner.py)
  │     ├── MemoryManager (core/memory.py)
  │     ├── WebSearchTool (tools/web_search.py)
  │     │     └── AsyncFocusedCrawler (tools/crawler/focused_crawler.py)
  │     ├── AcademicSearchTool (tools/academic_search.py)
  │     ├── SummarizerTool (tools/summarizer.py)
  │     ├── DocumentProcessor (services/document_processor.py)
  │     ├── HybridRetriever (services/retrieval/hybrid_retriever.py)
  │     │     ├── Qdrant (qdrant-client)
  │     │     └── tantivy
  │     └── RAGPipeline (services/rag_pipeline.py)
  │           ├── CredibilityScorer (services/ranking/credibility_scorer.py)
  │           ├── CrossEncoderReranker (services/ranking/reranker.py)
  │           └── LLMService (services/llm_service.py)
  │
  ├── ChatService (services/chat_service.py)
  ├── ImageAnalyzer (services/image_service.py)
  │     ├── Ollama llava (optional)
  │     └── pytesseract (optional)
  └── DocumentExtractor (services/document_extractor.py)
        ├── PyPDF2
        └── python-docx
```

---

## Graceful Degradation

The system is designed to function even when optional components are unavailable:

| Component | Absent behaviour |
|---|---|
| Qdrant | Falls back to in-memory dict retrieval |
| tantivy | Falls back to dense-only Qdrant retrieval |
| CrossEncoder reranker | Skips reranking, uses RRF scores directly |
| llava (Ollama vision) | Falls back to pytesseract OCR |
| pytesseract | Returns a helpful error message, no crash |
| diskcache | Caching disabled; pipeline still works uncached |
| nomic-embed-text | HyDE disabled; uses raw query embedding |

---

## Threading Model

The backend uses FastAPI's async model throughout:

- **LLM calls** — sync Ollama SDK wrapped in `asyncio.to_thread()`
- **Streaming** — sync Ollama generator run in a daemon thread, results fed into `asyncio.Queue`, consumed by async generator
- **Research pipeline** — runs as FastAPI `BackgroundTask` (non-blocking)
- **Concurrent task batches** — `asyncio.gather()` with batch size ≤ 3
- **Frontend polling** — `setInterval(3000)` in `useResearch` hook

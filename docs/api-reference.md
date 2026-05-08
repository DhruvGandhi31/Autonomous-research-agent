# API Reference

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs` (Swagger UI)

All request/response bodies use `application/json` unless noted otherwise.  
All timestamps are ISO 8601 strings.

---

## Table of Contents

- [System Endpoints](#system-endpoints)
- [Research Endpoints](#research-endpoints)
- [Chat Endpoints](#chat-endpoints)
- [Upload Endpoints](#upload-endpoints)

---

## System Endpoints

### `GET /`

Returns basic API information.

**Response 200**
```json
{
    "message": "🔬 Research Agent API",
    "status": "running",
    "version": "1.0.0",
    "description": "Autonomous research agent for comprehensive topic analysis",
    "docs": "/docs",
    "health_check": "/health"
}
```

---

### `GET /health`

Health check for monitoring and startup verification.

**Response 200 (healthy)**
```json
{
    "status": "healthy",
    "timestamp": "2025-05-08T10:30:00.000Z",
    "services": {
        "ollama": "available",
        "agent": "idle",
        "model": "llama3.1:8b"
    },
    "active_sessions": 2
}
```

**Response 200 (degraded — Ollama unreachable)**
```json
{
    "status": "degraded",
    "services": { "ollama": "unavailable" }
}
```

---

## Research Endpoints

Prefix: `/api/research`

---

### `POST /api/research/start`

Enqueue a new autonomous research job. Returns immediately with a `research_id`. Poll `/status/{research_id}` to track progress.

**Request body**
```json
{
    "topic": "Advances in quantum error correction 2024",
    "max_sources": 10,
    "include_academic": true,
    "include_analysis": true
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `topic` | `string` | ✅ | — | Research topic (3–500 chars) |
| `max_sources` | `integer` | ❌ | `10` | Max sources to collect (1–50) |
| `include_academic` | `boolean` | ❌ | `true` | Include arXiv / Semantic Scholar / Wikipedia |
| `include_analysis` | `boolean` | ❌ | `true` | Enable RAG synthesis |

**Response 200**
```json
{
    "research_id": "research_a3b7c291d4e5",
    "topic": "Advances in quantum error correction 2024",
    "status": "queued",
    "message": "Research started. Poll /status/research_a3b7c291d4e5 for progress."
}
```

---

### `GET /api/research/status/{research_id}`

Poll the status of a running or completed research job.

**Path params**: `research_id` — the ID returned by `/start`

**Response 200**
```json
{
    "research_id": "research_a3b7c291d4e5",
    "topic": "Advances in quantum error correction 2024",
    "status": "researching",
    "agent_state": "researching",
    "started_at": "2025-05-08T10:30:00.000Z",
    "completed_at": null,
    "error": null,
    "progress": {
        "completed_tasks": 4,
        "total_tasks": 7,
        "percentage": 57
    }
}
```

**`status` values**

| Value | Description |
|---|---|
| `queued` | Job received, not yet started |
| `planning` | LLM generating task list |
| `researching` | Executing search/academic/summarizer tasks |
| `indexing` | Processing and indexing documents |
| `synthesizing` | RAG pipeline generating report |
| `complete` | Done — results available |
| `error` | Pipeline failed — see `error` field |

**Response 404**
```json
{ "detail": "Research session not found" }
```

---

### `GET /api/research/results/{research_id}`

Fetch the completed research report.

**Response 200 (complete)**
```json
{
    "research_id": "research_a3b7c291d4e5",
    "topic": "Advances in quantum error correction 2024",
    "status": "complete",
    "report": "## Executive Summary\n\nQuantum error correction...",
    "citations": [
        {
            "id": 1,
            "url": "https://arxiv.org/abs/2401.12345",
            "title": "Surface code thresholds...",
            "domain": "arxiv.org",
            "credibility": 0.91,
            "source_type": "tier1_academic"
        }
    ],
    "confidence": 0.84,
    "verified": true,
    "critique": null,
    "sources": [
        { "url": "...", "title": "...", "snippet": "...", "credibility_score": 0.91 }
    ],
    "total_sources": 23,
    "task_count": 7,
    "started_at": "2025-05-08T10:30:00.000Z",
    "completed_at": "2025-05-08T10:34:12.000Z"
}
```

**Response 202 (still running)**
```json
{ "detail": "Research is still 'synthesizing'. Try again later." }
```

**Response 404**
```json
{ "detail": "Research session not found" }
```

---

### `DELETE /api/research/session/{research_id}`

Delete all data for a research session (memory + disk files).

**Response 200**
```json
{ "message": "Session research_a3b7c291d4e5 deleted successfully" }
```

---

### `GET /api/research/sessions`

List all active research sessions.

**Response 200**
```json
{
    "sessions": [
        {
            "research_id": "research_a3b7c291d4e5",
            "topic": "Quantum error correction",
            "status": "complete",
            "started_at": "2025-05-08T10:30:00.000Z"
        }
    ],
    "total": 1
}
```

---

### `GET /api/research/test/llm`

Verify the LLM connection.

**Response 200**
```json
{
    "success": true,
    "response": "LLM connection successful",
    "model": "llama3.1:8b"
}
```

**Response 500** — Ollama unreachable or model error.

---

### `POST /api/research/test/search`

Test DuckDuckGo web search.

**Query params**: `query` (required), `max_results` (default: 5, max: 20)

**Response 200**
```json
{
    "query": "quantum computing",
    "total_results": 5,
    "results": [
        { "url": "https://...", "title": "...", "snippet": "..." }
    ],
    "detailed_content": [
        { "url": "...", "title": "...", "content": "Full page text..." }
    ]
}
```

---

### `POST /api/research/test/academic`

Test academic search (arXiv + Semantic Scholar + Wikipedia).

**Query params**: `query` (required), `max_results` (default: 3, max: 10)

**Response 200**
```json
{
    "results": [
        {
            "title": "...",
            "url": "https://arxiv.org/...",
            "authors": ["Author 1", "Author 2"],
            "published": "2024-03-15",
            "abstract": "...",
            "source": "arxiv"
        }
    ]
}
```

---

### `POST /api/research/test/summarize`

Test LLM summarization.

**Query params**: `content` (required), `topic` (default: `"general"`)

**Response 200**
```json
{
    "executive_summary": "...",
    "key_points": ["...", "..."],
    "insights": ["..."],
    "credibility": "high",
    "relevance": "high"
}
```

---

### `POST /api/research/query`

Direct RAG query against the currently indexed knowledge base. Run `/start` first to populate the knowledge base.

**Query params**: `question` (required), `top_k` (default: 12, range: 3–30)

**Response 200**
```json
{
    "question": "What are the main error correction codes?",
    "answer": "Surface codes are the most prominent... [1] [2]",
    "citations": [
        {
            "id": 1,
            "url": "https://arxiv.org/...",
            "title": "...",
            "credibility": 0.91
        }
    ],
    "confidence": 0.82,
    "sources_used": 8,
    "verified": true,
    "critique": null
}
```

---

### `POST /api/research/crawl`

Start a focused crawl on seed URLs. Results are indexed into the knowledge base for later `/query` calls.

**Query params**: `urls[]` (required), `topic` (required), `max_pages` (default: 20, max: 100)

**Response 200** (starts immediately, runs in background)
```json
{
    "crawl_id": "crawl_a1b2c3d4",
    "status": "started",
    "seed_urls": ["https://example.com/article"],
    "topic": "quantum error correction",
    "message": "Crawling up to 20 pages. Use /query to search after completion."
}
```

---

## Chat Endpoints

Prefix: `/api/chat`

---

### `POST /api/chat/sessions`

Create a new chat session.

**Request body**
```json
{
    "title": "My Research Session",
    "mode": "chat"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `title` | `string` | `"New Chat"` | Display name |
| `mode` | `"chat" \| "research"` | `"chat"` | Chat = direct LLM, Research = research pipeline |

**Response 200**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "My Research Session",
    "mode": "chat",
    "created_at": "2025-05-08T10:30:00.000Z",
    "updated_at": "2025-05-08T10:30:00.000Z",
    "messages": []
}
```

---

### `GET /api/chat/sessions`

List all sessions sorted by most recently updated.

**Response 200**
```json
{
    "sessions": [
        {
            "id": "550e8400-...",
            "title": "What is RLHF?",
            "mode": "chat",
            "created_at": "2025-05-08T10:00:00.000Z",
            "updated_at": "2025-05-08T10:05:00.000Z",
            "message_count": 4,
            "last_message": "RLHF stands for Reinforcement Learning from Human Feedback..."
        }
    ],
    "total": 1
}
```

---

### `GET /api/chat/sessions/{session_id}`

Get a full session including all messages.

**Response 200**
```json
{
    "id": "550e8400-...",
    "title": "What is RLHF?",
    "mode": "chat",
    "created_at": "...",
    "updated_at": "...",
    "messages": [
        {
            "id": "msg-uuid",
            "role": "user",
            "content": "What is RLHF?",
            "timestamp": "...",
            "attachments": [],
            "research_id": null,
            "sources": []
        },
        {
            "id": "msg-uuid-2",
            "role": "assistant",
            "content": "RLHF stands for...",
            "timestamp": "...",
            "attachments": [],
            "research_id": null,
            "sources": []
        }
    ]
}
```

**Response 404**
```json
{ "detail": "Session not found" }
```

---

### `DELETE /api/chat/sessions/{session_id}`

Delete a session and all its messages.

**Response 200**
```json
{ "message": "Session deleted" }
```

---

### `PATCH /api/chat/sessions/{session_id}/rename`

Rename a session (max 100 chars).

**Request body**
```json
{ "title": "RLHF Explained" }
```

**Response 200**
```json
{ "message": "Session renamed" }
```

---

### `POST /api/chat/sessions/{session_id}/messages`

**The main chat endpoint.** Saves the user message, generates an LLM response, and streams it back as Server-Sent Events.

**Content-Type**: `application/json`  
**Response Content-Type**: `text/event-stream`

**Request body**
```json
{
    "content": "Summarize the attached document",
    "attachments": [
        {
            "name": "report.pdf",
            "file_type": "document",
            "extracted_text": "Full text of the PDF...",
            "description": "Document 'report.pdf' — 12 pages",
            "size": 204800
        }
    ],
    "trigger_research": false,
    "tool_preference": ""
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | `string` | ✅ | User message text (1–32,000 chars) |
| `attachments` | `array` | ❌ | Pre-uploaded file data |
| `trigger_research` | `boolean` | ❌ | Force research pipeline for this message |
| `tool_preference` | `string` | ❌ | Hint to TaskPlanner: `"web_search"`, `"academic_search"`, or `""` (planner decides freely) |

**SSE events — Chat mode** (`trigger_research: false` and session `mode: "chat"`)

```
data: {"type":"chunk","content":"RLHF "}
data: {"type":"chunk","content":"stands "}
data: {"type":"chunk","content":"for..."}
data: {"type":"done","message":{"id":"...","role":"assistant","content":"RLHF stands for...","timestamp":"...","attachments":[],"research_id":null,"sources":[]}}
```

**SSE events — Research mode** (`trigger_research: true` or session `mode: "research"`)

```
data: {"type":"research_started","research_id":"research_abc123","topic":"What is RLHF?"}
data: {"type":"done","message":{"id":"...","role":"assistant","content":"Starting research on **What is RLHF?**...","timestamp":"...","research_id":"research_abc123"}}
```

**SSE events — Error**

```
data: {"type":"error","error":"Error communicating with LLM"}
```

**Notes**:
- The stream ends after the `done` event.
- In chat mode, the full `message.content` equals the concatenation of all `chunk` events.
- In research mode, the message has `research_id` set; poll `/api/research/status/{research_id}` to track it.
- `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers are set to prevent proxy buffering.

---

## Upload Endpoints

Prefix: `/api/upload`  
**Content-Type**: `multipart/form-data`  
**Max file size**: 20 MB

---

### `POST /api/upload/image`

Upload an image for OCR and/or vision analysis.

**Form fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `File` | ✅ | Image (JPEG, PNG, GIF, WEBP, BMP) |
| `query` | `string` | ❌ | Optional context passed to llava |

**Response 200**
```json
{
    "filename": "screenshot.png",
    "content_type": "image/png",
    "size": 102400,
    "extracted_text": "Image Analysis:\nThe image shows a bar chart...\n\nExtracted Text (OCR):\nQ1 Revenue: $2.4M",
    "description": "The image shows a bar chart comparing Q1–Q4 revenue figures...",
    "ocr_text": "Q1 Revenue: $2.4M\nQ2 Revenue: $3.1M",
    "llava_used": true,
    "ocr_used": true,
    "file_type": "image"
}
```

| Field | Description |
|---|---|
| `extracted_text` | Combined text for use as chat context (`description` + `ocr_text`) |
| `description` | Rich description from llava (empty string if unavailable) |
| `ocr_text` | Raw OCR output from pytesseract (empty string if unavailable) |
| `llava_used` | Whether the llava model was used |
| `ocr_used` | Whether pytesseract OCR was used |

**Response 400** — unsupported file type  
**Response 413** — file exceeds 20 MB

---

### `POST /api/upload/document`

Upload a PDF, DOCX, or TXT file for text extraction.

**Form fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `File` | ✅ | PDF, DOCX, DOC, or TXT file |

**Response 200**
```json
{
    "filename": "research_paper.pdf",
    "content_type": "application/pdf",
    "size": 1048576,
    "extracted_text": "Abstract\n\nThis paper presents...",
    "description": "Document 'research_paper.pdf' — 24 pages/paragraphs extracted",
    "preview": "Abstract\n\nThis paper presents a novel approach...",
    "char_count": 48320,
    "method": "pypdf2",
    "file_type": "document"
}
```

| Field | Description |
|---|---|
| `extracted_text` | Full extracted text, capped at 50,000 characters |
| `description` | Human-readable summary with page/paragraph count |
| `preview` | First 500 characters of the extracted text |
| `char_count` | Total character count before the 50k cap |
| `method` | Extraction method used: `"pypdf2"`, `"python-docx"`, or `"plain_text"` |

**Response 400** — unsupported file type  
**Response 413** — file exceeds 20 MB  
**Response 500** — extraction failed (corrupt file, password-protected PDF, etc.)

---

## Common Error Format

All error responses follow FastAPI's default format:

```json
{
    "detail": "Human-readable error message"
}
```

HTTP status codes:

| Code | Meaning |
|---|---|
| `400` | Bad request (invalid parameters, unsupported type) |
| `404` | Resource not found |
| `413` | Payload too large |
| `202` | Research not yet complete (retry later) |
| `500` | Internal server error |

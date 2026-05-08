# Bug Report

Audited: 2026-05-08  
Scope: all Python backend files + all TypeScript frontend files

Severity scale: **Critical** → app broken / data lost · **High** → feature broken · **Medium** → silent wrong behaviour · **Low** → quality / UX degradation

---

## Summary

| ID | Severity | File | One-line description |
|---|---|---|---|
| [BUG-001](#bug-001) | 🔴 Critical | `api/routes/chat.py:63` | All chat streaming crashes — dict subscript on a typed ollama response object |
| [BUG-002](#bug-002) | 🔴 Critical | `core/planner.py:70` | Research plan always falls back — LLM wraps JSON in markdown fences |
| [BUG-003](#bug-003) | 🟠 High | `core/planner.py:95-107` | `task_id_map` is built but never used — task dependencies silently ignored |
| [BUG-004](#bug-004) | 🟠 High | `services/rag_pipeline.py:116` | MMR diversity selection uses stale pre-rerank scores |
| [BUG-005](#bug-005) | 🟠 High | `core/memory.py:138-175` | `async` functions call blocking file I/O directly on the event loop |
| [BUG-006](#bug-006) | 🟡 Medium | `api/routes/research.py:92` | 404 detection uses fragile string equality on error message text |
| [BUG-007](#bug-007) | 🟡 Medium | `main.py:101-107` | CORS origins hardcoded to `localhost:3000` — breaks every non-local setup |
| [BUG-008](#bug-008) | 🟡 Medium | `core/agent.py:395` | Synchronous `glob()` call inside an `async` method blocks the event loop |
| [BUG-009](#bug-009) | 🔵 Low | `services/document_processor.py:159` | Regex strips `[N]` citation markers from academic chunks before indexing |
| [BUG-010](#bug-010) | 🔵 Low | `tools/academic_search.py:41` | `google_scholar` included in default sources even when no SerpApi key exists |
| [BUG-011](#bug-011) | 🔵 Low | `requirements.txt:8` | `ollama` unpinned — version skew is the root cause of BUG-001 |
| [BUG-012](#bug-012) | 🔵 Low | `frontend/…/InputArea.tsx:77` | Multiple file uploads happen sequentially instead of in parallel |
| [BUG-013](#bug-013) | 🔵 Low | `frontend/lib/types.ts` | `research_id` typed as `string \| undefined` but API returns `null` |

---

## BUG-001

**🔴 Critical — All chat streaming is broken on ollama SDK ≥ 0.2.0**

**File**: `backend/app/api/routes/chat.py`, line 63  
**Root cause**: The ollama Python SDK switched from plain-dict responses to typed Pydantic objects in v0.2.0 (March 2024). The streaming helper was never updated. Since `requirements.txt` pins no version, any fresh install gets a current SDK (≥ 0.3.x) and all streaming immediately crashes with:

```
TypeError: 'ChatResponse' object is not subscriptable
```

Notice that `llm_service.py` uses the correct attribute style (`response.message.content`) while `chat.py` still uses the old dict style — they reference the same SDK with different access patterns.

**Buggy code** (`chat.py`, lines 60–66):
```python
def run_sync():
    try:
        client = ollama.Client(host=settings.ollama_base_url)
        for chunk in client.chat(
            model=settings.default_model, messages=messages, stream=True
        ):
            content = chunk["message"]["content"]   # ← TypeError on SDK ≥ 0.2.0
```

**Fix**:
```python
def run_sync():
    try:
        client = ollama.Client(host=settings.ollama_base_url)
        for chunk in client.chat(
            model=settings.default_model, messages=messages, stream=True
        ):
            content = chunk.message.content         # ← attribute access (consistent with llm_service.py)
```

---

## BUG-002

**🔴 Critical — Research plan always uses the single-task fallback**

**File**: `backend/app/core/planner.py`, lines 70–74  
**Root cause**: Modern LLMs (including llama3.1:8b) almost always wrap structured JSON output in markdown code fences:

````
```json
{
  "research_strategy": "...",
  "tasks": [...]
}
```
````

`json.loads(plan_response)` does not strip fences, so it raises `JSONDecodeError` on every call. The except-branch silently swaps in `_create_fallback_plan()`, which creates exactly one `web_search` task regardless of topic complexity. The entire multi-step planning system is unreachable.

**Buggy code** (`planner.py`, lines 70–76):
```python
try:
    plan_data = json.loads(plan_response)
except json.JSONDecodeError:
    logger.warning("LLM response was not valid JSON, creating fallback plan")
    plan_data = self._create_fallback_plan(topic, requirements)
```

**Fix** — strip fences before parsing, then fall back only on truly invalid JSON:
```python
import re

# Strip ```json ... ``` or ``` ... ``` fences LLMs add around structured output
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)

def _extract_json(text: str) -> str:
    m = _JSON_FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()
```

```python
try:
    plan_data = json.loads(_extract_json(plan_response))
except json.JSONDecodeError:
    logger.warning("LLM response was not valid JSON, creating fallback plan")
    plan_data = self._create_fallback_plan(topic, requirements)
```

---

## BUG-003

**🟠 High — Task dependency ordering is silently ignored**

**File**: `backend/app/core/planner.py`, lines 88–120 (`_structure_plan`)  
**Root cause**: Task UUIDs are generated *after* the LLM writes the plan, so the LLM cannot emit real UUIDs in `"dependencies"`. It emits either integer indices (`[0, 1]`) or made-up names (`["task_1"]`). The code builds `task_id_map` to remap these indices to real UUIDs, but never applies the mapping — `task_id_map` is populated and then discarded.

In `_execute_tasks`, when `completed` never contains the LLM's fake dependency values, `ready` is always empty for dependent tasks, so the fallback `ready = [remaining[0]]` fires — effectively running tasks in their original order with all dependency constraints stripped.

**Buggy code** (`planner.py`, lines 94–107):
```python
task_id_map = {}

for i, task_info in enumerate(plan_data.get("tasks", [])):
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    task_id_map[i] = task_id          # built but NEVER USED below

    task = ResearchTask(
        id=task_id,
        ...
        dependencies=task_info.get("dependencies", []),  # raw LLM output — int indices
        ...
    )
    tasks.append(task)
# task_id_map is thrown away here
```

**Fix** — remap dependencies immediately after all tasks are built:
```python
task_id_map = {}
raw_tasks = plan_data.get("tasks", [])

# First pass: assign IDs
for i, task_info in enumerate(raw_tasks):
    task_id_map[i] = f"task_{uuid.uuid4().hex[:8]}"
    # Also index by the LLM-generated name if present
    if task_info.get("name"):
        task_id_map[task_info["name"]] = task_id_map[i]

tasks = []
for i, task_info in enumerate(raw_tasks):
    raw_deps = task_info.get("dependencies") or []
    # Remap integer indices or string names to real UUIDs
    remapped_deps = [
        task_id_map[dep]
        for dep in raw_deps
        if dep in task_id_map
    ]
    task = ResearchTask(
        id=task_id_map[i],
        ...
        dependencies=remapped_deps,
        ...
    )
    tasks.append(task)
```

---

## BUG-004

**🟠 High — MMR diversity selection uses stale relevance scores**

**File**: `backend/app/services/rag_pipeline.py`, line 116; `_mmr_select()` lines 184–221  
**Root cause**: After `reranker.rerank()` runs, each document's cross-encoder score is stored in `doc.metadata["rerank_score"]` and documents are sorted by that score. However, `_mmr_select` reads `d.rrf_score` — the original pre-reranking RRF fusion score — to decide relevance in the MMR formula. The whole purpose of reranking is undermined because MMR ignores the reranked relevance entirely.

**Buggy code** (`rag_pipeline.py`, `_mmr_select` helper, line 195):
```python
scores = np.array([d.rrf_score for d in docs], dtype=float)   # stale — pre-rerank
```

**Fix** — prefer the rerank score when available:
```python
scores = np.array(
    [d.metadata.get("rerank_score", d.rrf_score) for d in docs],
    dtype=float,
)
```

---

## BUG-005

**🟠 High — Blocking file I/O on the async event loop**

**File**: `backend/app/core/memory.py`, lines 138–154 (`_save_memory_item`) and 156–175 (`_load_memory_item`)  
**Root cause**: Both methods are declared `async` but use synchronous `open()` / `json.dump()` / `json.load()` directly, without wrapping in `asyncio.to_thread`. Every research step — storing context, plan, task results, insights — blocks the event loop while writing to disk. Under load or on a slow disk, this freezes all concurrent requests.

**Buggy code** (`memory.py`, lines 144–152):
```python
async def _save_memory_item(self, item: MemoryItem):
    ...
    with open(file_path, 'w') as f:         # ← blocks event loop
        json.dump(item_dict, f, indent=2)
```

```python
async def _load_memory_item(self, item_id: str) -> Optional[MemoryItem]:
    ...
    with open(file_path, 'r') as f:         # ← blocks event loop
        item_dict = json.load(f)
```

**Fix** — wrap I/O in `asyncio.to_thread`:
```python
async def _save_memory_item(self, item: MemoryItem):
    ...
    item_dict = asdict(item)
    item_dict['timestamp'] = item.timestamp.isoformat()

    def _write():
        with open(file_path, 'w') as f:
            json.dump(item_dict, f, indent=2)

    await asyncio.to_thread(_write)
```

```python
async def _load_memory_item(self, item_id: str) -> Optional[MemoryItem]:
    ...
    def _read():
        with open(file_path, 'r') as f:
            return json.load(f)

    item_dict = await asyncio.to_thread(_read)
    item_dict['timestamp'] = datetime.fromisoformat(item_dict['timestamp'])
    ...
```

---

## BUG-006

**🟡 Medium — 404 detection is brittle string comparison**

**File**: `backend/app/api/routes/research.py`, lines 92–93  
**Root cause**: The route inspects the return value of `get_research_status()` and raises 404 only if `status["error"]` exactly equals the string `"Research session not found"`. If that error message ever changes (e.g., a typo fix), valid "not found" requests will silently return HTTP 200 with `{"error": "..."}` instead of 404.

**Buggy code** (`research.py`, lines 92–93):
```python
status = await research_agent.get_research_status(research_id)
if "error" in status and status["error"] == "Research session not found":
    raise HTTPException(status_code=404, detail="Research session not found")
return status
```

**Fix** — use a sentinel key instead of string equality:
```python
# In agent.py get_research_status(), replace:
return {"error": "Research session not found"}
# with:
return {"not_found": True}
```

```python
# In research.py:
status = await research_agent.get_research_status(research_id)
if status.get("not_found"):
    raise HTTPException(status_code=404, detail="Research session not found")
return status
```

---

## BUG-007

**🟡 Medium — CORS origins hardcoded to `localhost:3000`**

**File**: `backend/app/main.py`, lines 101–107  
**Root cause**: `allow_origins` is a hard-coded list in source code. Any deployment outside `localhost` — including Docker Compose where the frontend container has a different hostname, or any future hosted instance — will have all browser requests blocked by CORS policy.

**Buggy code** (`main.py`, lines 101–107):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    ...
)
```

**Fix** — move to `settings.py` and read from the environment:
```python
# settings.py — add:
cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
```

```python
# main.py:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`.env` for custom deployments:
```env
CORS_ORIGINS=["https://yourdomain.com"]
```

---

## BUG-008

**🟡 Medium — Synchronous `glob()` inside an `async` method**

**File**: `backend/app/core/agent.py`, line 395 (`get_research_results`)  
**Root cause**: `Path.glob()` is a synchronous, potentially blocking filesystem call. Calling it directly inside an `async def` without `asyncio.to_thread` blocks the event loop until the directory scan completes. For large `memory/` directories this can cause perceptible request latency on other concurrent operations.

**Buggy code** (`agent.py`, line 395):
```python
for f in self.memory.memory_dir.glob(f"{research_id}_insight_*.json"):
```

**Fix**:
```python
def _find_insight_files(directory: Path, research_id: str) -> list[Path]:
    return list(directory.glob(f"{research_id}_insight_*.json"))

insight_files = await asyncio.to_thread(
    _find_insight_files, self.memory.memory_dir, research_id
)
for f in insight_files:
    ...
```

---

## BUG-009

**🔵 Low — Citation markers stripped from academic content before indexing**

**File**: `backend/app/services/document_processor.py`, line 159  
**Root cause**: The cleaning step removes all `[...]` patterns to strip wiki-style footnote markers. But it also erases `[1]`, `[2]` inline citation references from academic papers and arXiv abstracts — the very content that carries provenance signals for the RAG pipeline. This degrades chunk quality for academic sources.

**Buggy code** (`document_processor.py`, line 159):
```python
text = re.sub(r"\[.*?\]", "", text)  # also strips [1], [2], [Figure 3] …
```

**Fix** — only strip numeric citation markers, not all brackets:
```python
text = re.sub(r"\[\d+\]", "", text)          # strip [1], [23], etc.
text = re.sub(r"\[edit\]", "", text)          # strip Wikipedia [edit] links
# Keep [Figure N], [Table N], [Equation N] — they carry useful context
```

---

## BUG-010

**🔵 Low — `google_scholar` included in default sources without an API key**

**File**: `backend/app/tools/academic_search.py`, line 41  
**Root cause**: The default `sources` parameter includes `"google_scholar"`, but `_search_google_scholar()` is guarded by `settings.serpapi_key`. With no key (the default), the Google Scholar task is silently skipped. This is harmless but creates misleading log entries and wastes the JSON parsing of the parameter. The LLM planner prompt does not mention Google Scholar as a tool option, making this unreachable in normal operation anyway.

**Buggy code** (`academic_search.py`, line 41):
```python
sources = parameters.get("sources", ["arxiv", "semantic_scholar", "wikipedia", "google_scholar"])
```

**Fix** — omit `google_scholar` from the default; add it only when a key is present:
```python
default_sources = ["arxiv", "semantic_scholar", "wikipedia"]
if settings.serpapi_key:
    default_sources.append("google_scholar")
sources = parameters.get("sources", default_sources)
```

---

## BUG-011

**🔵 Low — `ollama` package unpinned (root cause of BUG-001)**

**File**: `requirements.txt`, line 8  
**Root cause**: `ollama` without a version specifier installs the latest version. The SDK changed its response type from `dict` to typed objects in v0.2.0. Any user who installs a fresh environment will get the current version (≥ 0.3.x) and immediately hit BUG-001.

**Buggy code** (`requirements.txt`, line 8):
```
ollama
```

**Fix** — once BUG-001 is fixed (attribute access is correct for ≥ 0.2.0), pin a minimum version:
```
ollama>=0.2.0
```

---

## BUG-012

**🔵 Low — Multiple file uploads happen sequentially**

**File**: `frontend/src/components/chat/InputArea.tsx`, lines 77–130 (`handleFileSelect`)  
**Root cause**: The `for...of` loop with `await` inside processes each file one at a time. Uploading 3 files takes 3× as long as necessary; the send button stays disabled for the entire duration.

**Buggy code** (`InputArea.tsx`, lines 81–130):
```typescript
for (const file of files) {
    const id = crypto.randomUUID();
    setPendingFiles(prev => [...prev, { id, file, status: "uploading" }]);
    try {
        let uploaded;
        if (isImageFile(file.name)) uploaded = await uploadImage(file);   // sequential
        else if (isDocumentFile(file.name)) uploaded = await uploadDocument(file);
        ...
    }
}
```

**Fix** — launch all uploads in parallel:
```typescript
const uploadFile = async (file: File) => {
    const id = crypto.randomUUID();
    setPendingFiles(prev => [...prev, { id, file, status: "uploading" }]);
    try {
        const uploaded = isImageFile(file.name)
            ? await uploadImage(file)
            : await uploadDocument(file);
        const attachment: FileAttachment = {
            name: uploaded.filename,
            file_type: uploaded.file_type as "image" | "document",
            extracted_text: uploaded.extracted_text,
            description: uploaded.description,
            size: uploaded.size,
        };
        setPendingFiles(prev =>
            prev.map(f => f.id === id ? { ...f, status: "ready", attachment } : f)
        );
    } catch (err) {
        setPendingFiles(prev =>
            prev.map(f => f.id === id
                ? { ...f, status: "error", error: err instanceof Error ? err.message : "Upload failed" }
                : f
            )
        );
    }
};

// Launch all uploads in parallel
await Promise.all(files.map(uploadFile));
```

---

## BUG-013

**🔵 Low — `research_id` typed as `string | undefined` but API sends `null`**

**File**: `frontend/src/lib/types.ts`  
**Root cause**: Python's `dataclasses.asdict()` serializes `Optional[str] = None` fields as JSON `null`. TypeScript's optional property (`research_id?: string`) represents `string | undefined`, not `string | null`. Strict-mode TypeScript (`strictNullChecks`) will treat `null` and `undefined` as different types. While runtime behaviour is identical (both are falsy), this discrepancy causes type errors if you ever enable strict null checks or use null-aware operators (`?.`, `??`) expecting `undefined`.

**Buggy type** (`types.ts`):
```typescript
interface ChatMessage {
    ...
    research_id?: string;   // means string | undefined
    ...
}
```

**Fix** — explicitly allow `null`:
```typescript
interface ChatMessage {
    ...
    research_id?: string | null;
    sources?: Citation[] | null;
    ...
}
```

---

## Fix Priority Order

For a stable GitHub release, apply fixes in this order:

1. **BUG-001** — Without this, no chat message can be sent. Fix first.
2. **BUG-002** — Without this, every research job creates a single-task fallback plan.
3. **BUG-011** — Pin `ollama>=0.2.0` so fresh installs don't regress on BUG-001.
4. **BUG-003** — Research tasks run in correct order once planning works.
5. **BUG-007** — Required before Docker packaging; CORS breaks everything in containers.
6. **BUG-004** — RAG quality improvement; fix once core pipeline works.
7. **BUG-005** — Correctness improvement; low practical impact on single-user local app.
8. **BUG-006** through **BUG-013** — Polish; fix before public release but not blocking.

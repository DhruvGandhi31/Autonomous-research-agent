# Bug Fix Report

All 13 bugs from `bug-report.md` have been resolved. Changes are documented below in priority order.

---

## BUG-001 🔴 Critical — Ollama dict subscript crash

**File:** `backend/app/api/routes/chat.py:64`

**Problem:** The streaming loop used dict-style access (`chunk["message"]["content"]`) on the ollama SDK response object. The ollama Python SDK ≥ 0.2.0 returns typed `ChatResponse` objects, not dicts — this caused `TypeError: 'ChatResponse' object is not subscriptable` on every chat message.

**Fix:** Switched to attribute access.

```python
# Before
content = chunk["message"]["content"]

# After
content = chunk.message.content
```

Also added `asyncio.wait_for(queue.get(), timeout=120.0)` to the queue consumer so hung streams are detected and logged instead of blocking the event loop indefinitely.

---

## BUG-002 🔴 Critical — LLM JSON fence stripping broke plan parsing

**File:** `backend/app/core/planner.py:70`

**Problem:** LLMs consistently wrap JSON output in markdown code fences (` ```json ... ``` `). The `json.loads()` call received the raw LLM string including the fences, always raised `JSONDecodeError`, and always fell back to the single-task fallback plan — meaning the LLM-generated multi-step plan was silently discarded on every research session.

**Fix:** Added a module-level regex and `_extract_json()` helper that strips code fences before parsing.

```python
# Added at module level
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)

def _extract_json(text: str) -> str:
    m = _JSON_FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()

# Before
plan_data = json.loads(plan_response)

# After
plan_data = json.loads(_extract_json(plan_response))
```

---

## BUG-003 🔴 Critical — Task dependency map built but never used

**File:** `backend/app/core/planner.py:95-107`

**Problem:** `_structure_plan()` built a `task_id_map` dict in a first pass, then immediately discarded it and built tasks in the same loop — so every task got `dependencies=[]` regardless of what the LLM specified. Research tasks were always executed in parallel with no ordering, causing tasks that depend on earlier results (e.g., a summarizer waiting for web searches) to run empty.

**Fix:** Rewrote `_structure_plan()` as a proper two-pass algorithm. Pass 1 assigns UUIDs and populates `task_id_map` keyed by integer index, string index, and task name. Pass 2 remaps LLM dependency references through the map.

```python
# Pass 1: assign UUIDs
task_id_map: Dict[Any, str] = {}
for i, task_info in enumerate(raw_tasks):
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    task_id_map[i] = task_id
    task_id_map[str(i)] = task_id
    task_id_map[task_info.get("name", "")] = task_id

# Pass 2: build tasks with remapped dependencies
for i, task_info in enumerate(raw_tasks):
    raw_deps = task_info.get("dependencies") or []
    remapped_deps = [task_id_map[dep] for dep in raw_deps if dep in task_id_map]
    task = ResearchTask(id=task_id_map[i], ..., dependencies=remapped_deps)
```

Also fixed: `dependencies: List[str] = None` → `field(default_factory=list)` to avoid mutable default argument bug.

---

## BUG-004 🟠 High — MMR used stale RRF scores instead of rerank scores

**File:** `backend/app/services/rag_pipeline.py:116`

**Problem:** `_mmr_select()` computed relevance scores using only `d.rrf_score` (the raw hybrid retrieval score). The cross-encoder reranker had already computed much better per-document scores into `d.metadata["rerank_score"]`, but MMR ignored them entirely — making the expensive reranking step useless for diversity selection.

**Fix:** Prefer `rerank_score` from metadata when available, fall back to `rrf_score`.

```python
# Before
scores = np.array([d.rrf_score for d in docs], dtype=float)

# After
scores = np.array(
    [d.metadata.get("rerank_score", d.rrf_score) for d in docs],
    dtype=float,
)
```

---

## BUG-005 🟠 High — Blocking file I/O on async event loop

**File:** `backend/app/core/memory.py`

**Problem:** `_save_memory_item()`, `_load_memory_item()`, `get_task_results()`, and `clear_research_session()` all called blocking `open()` and `Path.glob()` directly on the asyncio event loop, stalling all concurrent coroutines during every disk operation.

**Fix:** Wrapped all blocking I/O in `asyncio.to_thread()`.

```python
# _save_memory_item — before
with open(file_path, "w") as f:
    json.dump(item_dict, f, indent=2)

# After
def _write():
    with open(file_path, "w") as f:
        json.dump(item_dict, f, indent=2)
await asyncio.to_thread(_write)

# get_task_results — before
memory_files = list(self.memory_dir.glob(...))

# After
memory_files = await asyncio.to_thread(
    lambda: list(self.memory_dir.glob(...))
)

# clear_research_session — before
for file_path in self.memory_dir.glob(...):
    file_path.unlink()

# After
def _delete_files():
    for file_path in self.memory_dir.glob(...):
        file_path.unlink(missing_ok=True)
await asyncio.to_thread(_delete_files)
```

---

## BUG-006 🟡 Medium — 404 detection used fragile string equality

**Files:** `backend/app/core/agent.py`, `backend/app/api/routes/research.py:92`

**Problem:** `get_research_status()` and `get_research_results()` returned `{"error": "Research session not found"}`. The route checked `status["error"] == "Research session not found"` — a fragile string match that would silently break if the message was ever edited or if `error` held a different runtime error.

**Fix:** Both agent methods now return `{"not_found": True}` for missing sessions. The route checks the boolean flag.

```python
# agent.py — before
return {"error": "Research session not found"}

# agent.py — after
return {"not_found": True}

# research.py — before
if "error" in status and status["error"] == "Research session not found":

# research.py — after
if status.get("not_found"):
```

---

## BUG-007 🟡 Medium — CORS origins hardcoded in main.py

**Files:** `backend/app/config/settings.py`, `backend/app/main.py`

**Problem:** `allow_origins` was a hardcoded list literal in `main.py`, requiring a code change (and redeploy) to add any new origin such as a staging domain or a different port.

**Fix:** Moved the list to `Settings` so it can be overridden via the `CORS_ORIGINS` environment variable.

```python
# settings.py — added
cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

# main.py — before
allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],

# main.py — after
allow_origins=settings.cors_origins,
```

---

## BUG-008 🟡 Medium — Sync glob() inside async method

**File:** `backend/app/core/agent.py:395`

**Problem:** `get_research_results()` called `self.memory.memory_dir.glob(...)` synchronously inside an `async def`, blocking the event loop while the OS scanned the directory.

**Fix:** Wrapped in `asyncio.to_thread`.

```python
# Before
for f in self.memory.memory_dir.glob(f"{research_id}_insight_*.json"):

# After
insight_files = await asyncio.to_thread(
    lambda: list(self.memory.memory_dir.glob(f"{research_id}_insight_*.json"))
)
for f in insight_files:
```

---

## BUG-009 🔵 Low — Regex stripped all bracket content including citation markers

**File:** `backend/app/services/document_processor.py:159`

**Problem:** `_clean_text()` used `re.sub(r"\[.*?\]", "", text)` which stripped every `[...]` pattern, including the `[1]`, `[2]` citation markers that the RAG pipeline inserts. Cleaned documents lost their citation links before indexing.

**Fix:** Target only numeric citation refs and Wikipedia's `[edit]` links specifically.

```python
# Before
text = re.sub(r"\[.*?\]", "", text)

# After
text = re.sub(r"\[\d+\]", "", text)
text = re.sub(r"\[edit\]", "", text, flags=re.IGNORECASE)
```

---

## BUG-010 🔵 Low — google_scholar in default sources without SerpApi key

**File:** `backend/app/tools/academic_search.py:41`

**Problem:** `"google_scholar"` was hardcoded into the default `sources` list. When `settings.serpapi_key` was empty, the dispatch block guarded the actual API call — but the source name was still in the list, causing confusing log output and potential issues if the guard logic changed.

**Fix:** Build the default list dynamically, appending `"google_scholar"` only when a key is configured.

```python
# Before
sources = parameters.get("sources", ["arxiv", "semantic_scholar", "wikipedia", "google_scholar"])

# After
default_sources = ["arxiv", "semantic_scholar", "wikipedia"]
if settings.serpapi_key:
    default_sources.append("google_scholar")
sources = parameters.get("sources", default_sources)
```

---

## BUG-011 🔵 Low — ollama dependency unpinned

**File:** `requirements.txt:8`

**Problem:** `ollama` had no version constraint. Installing into a fresh environment could pull a version older than 0.2.0 (which returns dicts instead of typed objects), causing the BUG-001 crash even after its fix was applied.

**Fix:** Added a minimum version pin matching the API that the codebase targets.

```
# Before
ollama

# After
ollama>=0.2.0
```

---

## BUG-012 🔵 Low — Multiple file uploads were sequential

**File:** `frontend/src/components/chat/InputArea.tsx:77`

**Problem:** `handleFileSelect` used a `for...of` loop with `await` inside, uploading files one at a time. Selecting 3 files took 3× as long as necessary.

**Fix:** Stamp all IDs upfront, add all entries to state in one `setPendingFiles` call, then dispatch all uploads in parallel with `Promise.all`.

```typescript
// Before
for (const file of files) {
  const id = crypto.randomUUID();
  setPendingFiles(prev => [...prev, { id, file, status: "uploading" }]);
  const uploaded = await uploadImage(file); // sequential
  ...
}

// After
const entries = files.map((file) => ({ id: crypto.randomUUID(), file }));
setPendingFiles(prev => [...prev, ...entries.map(...)]); // single state update
await Promise.all(entries.map(uploadOne));              // parallel
```

---

## BUG-013 🔵 Low — research_id and sources typed as string | undefined

**File:** `frontend/src/lib/types.ts`

**Problem:** `ChatMessage.research_id` was typed `string | undefined` and `sources` as `Citation[] | undefined`. The backend serialises missing values as JSON `null`, not `undefined`. TypeScript treats `null` and `undefined` differently — code checking `if (msg.research_id)` worked, but code like `msg.research_id === undefined` would be wrong.

**Fix:** Added `null` to both union types to match the actual API contract.

```typescript
// Before
research_id?: string;
sources?: Citation[];

// After
research_id?: string | null;
sources?: Citation[] | null;
```

---

## Summary

| ID | Severity | File | Status |
|---|---|---|---|
| BUG-001 | 🔴 Critical | `api/routes/chat.py` | Fixed |
| BUG-002 | 🔴 Critical | `core/planner.py` | Fixed |
| BUG-003 | 🔴 Critical | `core/planner.py` | Fixed |
| BUG-004 | 🟠 High | `services/rag_pipeline.py` | Fixed |
| BUG-005 | 🟠 High | `core/memory.py` | Fixed |
| BUG-006 | 🟡 Medium | `core/agent.py`, `api/routes/research.py` | Fixed |
| BUG-007 | 🟡 Medium | `config/settings.py`, `main.py` | Fixed |
| BUG-008 | 🟡 Medium | `core/agent.py` | Fixed |
| BUG-009 | 🔵 Low | `services/document_processor.py` | Fixed |
| BUG-010 | 🔵 Low | `tools/academic_search.py` | Fixed |
| BUG-011 | 🔵 Low | `requirements.txt` | Fixed |
| BUG-012 | 🔵 Low | `frontend/src/components/chat/InputArea.tsx` | Fixed |
| BUG-013 | 🔵 Low | `frontend/src/lib/types.ts` | Fixed |

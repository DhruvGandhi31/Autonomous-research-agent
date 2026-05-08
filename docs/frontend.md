# Frontend Reference

The frontend is a **Next.js 14** application using the App Router, TypeScript, and Tailwind CSS.

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run build        # production build
```

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Configuration](#2-configuration)
3. [Design System](#3-design-system)
4. [Types (`lib/types.ts`)](#4-types)
5. [API Client (`lib/api.ts`)](#5-api-client)
6. [Utilities (`lib/utils.ts`)](#6-utilities)
7. [Context — ChatContext](#7-context--chatcontext)
8. [Hook — useResearch](#8-hook--useresearch)
9. [Page — Root (`app/page.tsx`)](#9-page--root)
10. [Component — Sidebar](#10-component--sidebar)
11. [Component — ChatArea](#11-component--chatarea)
12. [Component — MessageBubble](#12-component--messagebubble)
13. [Component — InputArea](#13-component--inputarea)
14. [Component — WelcomeScreen](#14-component--welcomescreen)
15. [Component — ResearchProgress](#15-component--researchprogress)
16. [Component — ResearchReport](#16-component--researchreport)
17. [Data Flow — Sending a Chat Message](#17-data-flow--sending-a-chat-message)
18. [Data Flow — File Upload](#18-data-flow--file-upload)
19. [Data Flow — Research Mode](#19-data-flow--research-mode)

---

## 1. Project Structure

```
frontend/
├── next.config.mjs          ← API proxy rewrites (→ localhost:8000)
├── tailwind.config.ts       ← Custom dark color tokens + animations
├── tsconfig.json
├── package.json
└── src/
    ├── app/
    │   ├── globals.css      ← Custom scrollbar, prose styles, animations
    │   ├── layout.tsx       ← Root HTML shell, metadata
    │   └── page.tsx         ← Root page: ChatProvider + Sidebar + ChatArea
    ├── components/
    │   ├── layout/
    │   │   └── Sidebar.tsx  ← Session list, new-chat buttons
    │   ├── chat/
    │   │   ├── ChatArea.tsx     ← Header, messages list, streaming placeholder
    │   │   ├── MessageBubble.tsx ← Per-message renderer (markdown, code, citations)
    │   │   ├── InputArea.tsx    ← Textarea + file upload + send button
    │   │   └── WelcomeScreen.tsx ← Empty state with capability cards + starters
    │   └── research/
    │       ├── ResearchProgress.tsx ← Live progress bar during research
    │       └── ResearchReport.tsx   ← Full rendered report with citations
    ├── contexts/
    │   └── ChatContext.tsx   ← Global state: sessions, active session, streaming
    ├── hooks/
    │   └── useResearch.ts   ← Polling hook for research pipeline status
    └── lib/
        ├── types.ts         ← All TypeScript interfaces
        ├── api.ts           ← Typed fetch wrappers + SSE stream consumer
        └── utils.ts         ← cn(), formatRelativeTime(), formatBytes()
```

---

## 2. Configuration

### `next.config.mjs`

Proxies all `/api/*` and `/health` requests to the backend at `http://localhost:8000` (or `NEXT_PUBLIC_BACKEND_URL`):

```js
async rewrites() {
    return [
        { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
        { source: "/health",     destination: `${BACKEND_URL}/health` },
    ];
}
```

This means all frontend API calls use relative paths (`/api/...`), and CORS is never an issue during development.

### Environment Variables

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000   # default if not set
```

---

## 3. Design System

### Color Tokens (Tailwind custom config)

| Token | Hex | Usage |
|---|---|---|
| `bg-primary` | `#0a0a10` | Page background |
| `bg-secondary` | `#13131f` | Sidebar, header, input area |
| `bg-tertiary` | `#1a1a2e` | Hover states, input fields |
| `bg-card` | `#16162a` | Message bubbles, cards |
| `bg-hover` | `#1e1e35` | Hover state for buttons/items |
| `border` | `#2a2a45` | Default borders |
| `border-light` | `#3a3a5c` | Lighter borders on hover |
| `accent` | `#6366f1` | Primary action color (indigo) |
| `accent-hover` | `#4f46e5` | Hover state for accent |
| `accent-light` | `#818cf8` | Lighter indigo for icons/links |
| `accent-dim` | `#312e81` | User message bubble background |
| `text-primary` | `#e2e8f0` | Main text |
| `text-secondary` | `#94a3b8` | Secondary/muted text |
| `text-muted` | `#64748b` | Very muted (timestamps, hints) |

### Typography

- **Body**: Inter (Google Fonts)
- **Code**: JetBrains Mono

### Animations

| Class | Duration | Effect |
|---|---|---|
| `animate-fade-in` | 200ms | Opacity 0→1 |
| `animate-slide-up` | 300ms | Y+8px + opacity → 0 |
| `animate-blink` | 1s step | Cursor blink |
| `animate-spin-slow` | 2s | Full rotation |
| `.streaming-cursor::after` | — | Blinking block cursor appended to streaming text |

### Prose Styles (`globals.css`)

The `.prose` class is customized for dark mode: white headings, indigo links, purple inline code on dark background, indigo-accented blockquotes, dark table rows.

---

## 4. Types

**File**: `src/lib/types.ts`

### Tool mode

```typescript
type ToolMode = "chat" | "web_search" | "academic" | "research";
```

| Value | Behavior |
|---|---|
| `"chat"` | Direct LLM response — no tools invoked |
| `"web_search"` | Research pipeline, TaskPlanner biased toward `web_search` |
| `"academic"` | Research pipeline, TaskPlanner biased toward `academic_search` |
| `"research"` | Full autonomous pipeline — planner picks tools freely |

### Core interfaces

```typescript
interface FileAttachment {
    name: string;
    file_type: "image" | "document";
    extracted_text: string;   // content passed to LLM as context
    description: string;
    size: number;
}

interface ChatMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    timestamp: string;          // ISO 8601
    attachments: FileAttachment[];
    research_id?: string | null;  // set when this message triggered research
    sources?: Citation[] | null;
}

interface ChatSession {
    id: string;
    title: string;
    mode: "chat" | "research";
    created_at: string;
    updated_at: string;
    messages: ChatMessage[];
}

interface SessionListItem {
    id: string;
    title: string;
    mode: "chat" | "research";
    created_at: string;
    updated_at: string;
    message_count: number;
    last_message: string | null;
}

interface Citation {
    title: string;
    url: string;
    snippet?: string;
    source?: string;
    credibility_score?: number;
}
```

### Research types

```typescript
interface ResearchStatus {
    research_id: string;
    status: "queued" | "planning" | "researching" | "synthesizing" | "complete" | "error";
    topic?: string;
    message?: string;
    error?: string;
    progress?: {
        completed_tasks: number;
        total_tasks: number;
        percentage: number;     // 0–100
    };
}

interface ResearchResult {
    research_id: string;
    topic: string;
    status: string;
    report?: string;            // Markdown report text
    citations?: Citation[];
    confidence?: number;        // 0.0–1.0
    verified?: boolean;
    completed_at?: string;
    error?: string;
}
```

### Upload types

```typescript
interface UploadedFile {
    filename: string;
    content_type: string;
    size: number;
    extracted_text: string;
    description: string;
    preview?: string;
    file_type: "image" | "document";
}

interface StreamEvent {
    type: "chunk" | "done" | "error" | "research_started";
    content?: string;          // for "chunk"
    message?: ChatMessage;     // for "done"
    error?: string;            // for "error"
    research_id?: string;      // for "research_started"
    topic?: string;
}
```

---

## 5. API Client

**File**: `src/lib/api.ts`

All backend communication goes through typed async functions.

### Session Management

```typescript
createSession(title, mode)           → Promise<ChatSession>
listSessions()                       → Promise<SessionListItem[]>
getSession(sessionId)                → Promise<ChatSession>
deleteSession(sessionId)             → Promise<void>
renameSession(sessionId, title)      → Promise<void>
```

### Streaming Chat

```typescript
async function* sendMessage(
    sessionId: string,
    content: string,
    attachments: FileAttachment[],
    triggerResearch: boolean,
    toolPreference: string        // "web_search" | "academic_search" | ""
): AsyncGenerator<StreamEvent>
```

Uses the Fetch API with `response.body.getReader()` for incremental SSE parsing. Handles incomplete lines by keeping a `buffer` across read calls.

`toolPreference` is forwarded as `tool_preference` in the request body and hints to the backend TaskPlanner which tool to prioritise. An empty string lets the planner decide freely.

**SSE parsing loop:**
```typescript
buffer += decoder.decode(value, { stream: true });
const lines = buffer.split("\n");
buffer = lines.pop() ?? "";   // keep incomplete line

for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const event = JSON.parse(line.slice(6));
    yield event;
}
```

### Research Pipeline

```typescript
getResearchStatus(researchId)   → Promise<ResearchStatus>
getResearchResults(researchId)  → Promise<ResearchResult>
listResearchSessions()          → Promise<unknown[]>
```

`getResearchResults` throws if the API returns HTTP 202 (still in progress).

### File Uploads

```typescript
uploadImage(file: File, query?: string)  → Promise<UploadedFile>
uploadDocument(file: File)               → Promise<UploadedFile>
```

Both use `FormData` with `multipart/form-data`. Errors parse the backend's JSON error response.

---

## 6. Utilities

**File**: `src/lib/utils.ts`

```typescript
cn(...inputs)                 // clsx + tailwind-merge
formatRelativeTime(iso)       // "just now" | "5m ago" | "2h ago" | "3d ago"
formatBytes(bytes)            // "1.2 MB" | "456 KB" | "128 B"
isImageFile(filename)         // /\.(jpe?g|png|gif|webp|bmp)$/i
isDocumentFile(filename)      // /\.(pdf|docx?|txt)$/i
```

---

## 7. Context — ChatContext

**File**: `src/contexts/ChatContext.tsx`

The single source of truth for all UI state. Wraps the entire app via `ChatProvider`.

### State

| State variable | Type | Description |
|---|---|---|
| `sessions` | `SessionListItem[]` | All sessions for the sidebar list |
| `activeSession` | `ChatSession \| null` | Currently open session with full message history |
| `streaming` | `{sessionId, content} \| null` | Active SSE stream content |
| `pendingResearchId` | `string \| null` | Set when a research job starts; disables input |

### Actions (exposed via context)

| Action | Description |
|---|---|
| `loadSessions()` | Fetch session list from backend, update sidebar |
| `openSession(id)` | Fetch full session and set as active |
| `newChat(mode?)` | Create a new session (default mode: `"chat"`) |
| `removeSession(id)` | Delete session; clears active if it was active |
| `send(content, attachments?, toolMode?)` | Full send flow (see below) |
| `switchSessionMode(mode)` | Toggle active session between `"chat"` and `"research"` locally |

### Tool mode mapping (`TOOL_CONFIG`)

Defined at module scope and used inside `send()`:

```typescript
const TOOL_CONFIG: Record<ToolMode, { triggerResearch: boolean; toolPreference: string }> = {
    chat:       { triggerResearch: false, toolPreference: "" },
    web_search: { triggerResearch: true,  toolPreference: "web_search" },
    academic:   { triggerResearch: true,  toolPreference: "academic_search" },
    research:   { triggerResearch: true,  toolPreference: "" },
};
```

`switchSessionMode` updates `activeSession.mode` in local React state only — it does not persist to the backend. The change resets when the user navigates to another session.

### `send()` Flow

1. Resolves `toolMode` — uses the passed argument; falls back to `"research"` if session is research mode, else `"chat"`
2. Looks up `{ triggerResearch, toolPreference }` from `TOOL_CONFIG`
3. Optimistically adds the user message to `activeSession.messages`
4. Sets `streaming` state with empty content
5. Iterates `sendMessage(sessionId, content, attachments, triggerResearch, toolPreference)`:
   - `chunk` events: appends to `streamingContentRef.current`, updates `streaming.content`
   - `research_started`: sets `pendingResearchId`
   - `done`: clears `streaming`, appends `event.message` to messages; clears `pendingResearchId` if not a research message
   - `error`: clears `streaming`, adds error message
6. Calls `loadSessions()` to refresh sidebar

### Research Completion Polling

A `useEffect` watches `pendingResearchId`. While set, it polls `/api/research/status` every 3 seconds. When status becomes `"complete"` or `"error"`, it clears `pendingResearchId` (re-enabling the input).

---

## 8. Hook — useResearch

**File**: `src/hooks/useResearch.ts`

Encapsulates the polling loop for a single research job. Used by `MessageWithResearch` in `ChatArea.tsx` — every assistant message that has a `research_id` gets its own polling instance.

```typescript
const { status, result, phase, error } = useResearch(researchId);
```

| Return value | Type | Description |
|---|---|---|
| `status` | `ResearchStatus \| null` | Latest status from API |
| `result` | `ResearchResult \| null` | Set when `phase === "complete"` |
| `phase` | `"idle" \| "polling" \| "complete" \| "error"` | Current lifecycle phase |
| `error` | `string \| null` | Error message if failed |

**Lifecycle:**
- `researchId = null` → `phase = "idle"`, stops any interval
- `researchId` set → immediately calls `fetchStatus`, starts 3-second interval
- First poll with `status === "complete"` → fetches results, transitions to `"complete"`, stops interval
- `status === "error"` → transitions to `"error"`, stops interval

---

## 9. Page — Root

**File**: `src/app/page.tsx`

```tsx
export default function Home() {
    return (
        <ChatProvider>
            <div className="flex h-screen overflow-hidden">
                <Sidebar />
                <main className="flex-1 flex flex-col overflow-hidden">
                    <ChatArea />
                </main>
            </div>
        </ChatProvider>
    );
}
```

This is a client component (`"use client"`). The layout is a simple two-column flex: fixed-width sidebar + flex-1 main area.

---

## 10. Component — Sidebar

**File**: `src/components/layout/Sidebar.tsx`

### Layout

```
┌─────────────────────────────┐
│  [Logo] Research Agent       │
│         AI-powered research  │
├─────────────────────────────┤
│  [+ New Chat]  [Flask icon]  │
├─────────────────────────────┤
│  ▼ CHATS (3)                │
│    ○ Quantum computing       │
│    ○ ML transformers         │
│  ▼ RESEARCH (2)             │
│    ⬡ Climate change 2024    │
├─────────────────────────────┤
│  Powered by llama3.1 via     │
│  Ollama                      │
└─────────────────────────────┘
```

### Behaviour

- **New Chat** button: calls `newChat("chat")` — creates chat session
- **Flask icon** button: calls `newChat("research")` — creates research session
- Sessions grouped into collapsible "CHATS" and "RESEARCH" sections
- Active session highlighted with `bg-accent/15`
- Delete: single click shows red icon (2.5s timeout); second click confirms deletion
- Session titles truncate with ellipsis; timestamps shown as relative time

---

## 11. Component — ChatArea

**File**: `src/components/chat/ChatArea.tsx`

The main content area. Shows one of three states:

1. **No active session** — centered empty state with icon
2. **Empty active session** — `WelcomeScreen` component
3. **Session with messages** — scrollable message list + input

### Header

```
┌──────────────────────────────────────────────┐
│ Session Title                   [💬 Chat ▾]  │  ← mode toggle pill
└──────────────────────────────────────────────┘
```

The mode toggle pill (right side of header) shows the current session mode. Clicking it calls `switchSessionMode()` in `ChatContext` to flip between `"chat"` and `"research"`. The toggle is purely a local UI state change — it updates the default chip selection in `InputArea` without persisting to the backend.

| Mode badge | Appearance |
|---|---|
| Chat | Gray pill — `MessageSquare` icon |
| Research | Indigo pill — `FlaskConical` icon |

### MessageWithResearch (inner component)

Each message is wrapped in `MessageWithResearch`, which calls `useResearch(message.research_id)` and conditionally renders:
- `ResearchProgress` while `phase === "polling"` (live progress bar)
- `ResearchReport` when `phase === "complete"` (full rendered report)

This means historical messages from past sessions automatically replay their research results when loaded.

### StreamingMessage (inner component)

Displayed while `streaming.sessionId === activeSession.id`. Shows:
- A spinning `Loader2` icon as the avatar
- The streaming text content with `.streaming-cursor` animation
- Three bouncing dots when content is empty (thinking state)

### Input Disabled States

The `InputArea` is disabled when:
- `isStreaming` — LLM is generating a response
- `pendingResearchId` is set — research pipeline is running

---

## 12. Component — MessageBubble

**File**: `src/components/chat/MessageBubble.tsx`

Renders a single message. Supports three structural variants:

### User Messages

```
                    [👤]
             ┌────────────────┐
             │ User text here │ ← right-aligned, accent/15 bg
             └────────────────┘
             [file chips if any]
             2m ago
```

### Assistant Messages

```
[🤖]
┌─────────────────────────────────────────────┐
│ Markdown-rendered content                    │
│ with syntax highlighted code blocks          │
│ and clickable links with external icons      │  ← left-aligned, bg-card
└──────────────────────────────────────────────┘
[source chips if any]
5m ago
```

### File Attachment Chips

Shown above the message bubble for user messages:
```
[📄 report.pdf  204 KB ×]   [🖼 screenshot.png  45 KB ×]
```

### Markdown Rendering

Uses `react-markdown` v9 with `remark-gfm` for full GitHub Flavored Markdown support.

**Custom renderers:**

| Element | Renderer |
|---|---|
| Code block with language | `react-syntax-highlighter` (Prism + `vscDarkPlus` theme) with language label + copy button |
| Inline code | Styled `<code>` with purple text on dark bg |
| Links | Open in new tab, with external link icon |
| Tables | Dark-themed with alternating row colors |
| Blockquotes | Left indigo border |

### Copy Button

Every assistant message and every code block has a copy button. Uses `navigator.clipboard.writeText()`. Shows a green checkmark for 2 seconds after copying.

### Sources List

Shows inline citation cards for `message.sources`. Limited to 3 by default with an "expand" button. Each card links to the source URL in a new tab.

---

## 13. Component — InputArea

**File**: `src/components/chat/InputArea.tsx`

```
┌──────────────────────────────────────────────┐
│ [📄 report.pdf 2MB ×]                         │  ← pending file chips (if any)
├──────────────────────────────────────────────┤
│ [💬 Chat] [🌐 Web Search] [📚 Academic] [🔬 Full Research] │  ← tool mode chips
├──────────────────────────────────────────────┤
│ [📎]  [Textarea ...]                   [➤]  │
├──────────────────────────────────────────────┤
│  Web Search · Search the web · results appear below message │  ← status hint
└──────────────────────────────────────────────┘
```

### Tool Mode Chips

Four pill buttons select the tool mode for the **next message**. The active chip is highlighted in accent color.

| Chip | `ToolMode` | Trigger | Planner hint |
|---|---|---|---|
| 💬 Chat | `"chat"` | Direct LLM | None |
| 🌐 Web Search | `"web_search"` | Research pipeline | Prefer `web_search` |
| 📚 Academic | `"academic"` | Research pipeline | Prefer `academic_search` |
| 🔬 Full Research | `"research"` | Research pipeline | Free choice |

**Default chip** is determined by the session mode: `"chat"` sessions default to `Chat`, `"research"` sessions default to `Full Research`. The default resets after each message send.

The default also resets when the session changes (via a `useEffect` that depends on the `mode` prop), so switching sessions or toggling the header mode badge always brings chips back in sync.

### Textarea Behaviour

- Auto-resizes (height calculated from `scrollHeight`)
- Maximum height: 200px (overflows with scroll)
- `Enter` → submit; `Shift+Enter` → newline
- Placeholder text adapts to the selected tool chip:
  - Chat → "Ask anything..."
  - Web Search → "Search the web for..."
  - Academic → "Search academic papers for..."
  - Full Research → "Enter a research topic..."

### Props

```typescript
interface InputAreaProps {
    onSend: (content: string, attachments: FileAttachment[], toolMode: ToolMode) => void;
    disabled?: boolean;
    mode: "chat" | "research";   // sets the default chip
}
```

### File Upload Flow

1. User clicks the paperclip icon → `<input type="file" hidden>` is programmatically clicked
2. Accepted types: images (JPEG/PNG/GIF/WEBP) and documents (PDF/DOCX/DOC/TXT)
3. Multiple files upload in **parallel** via `Promise.all`
4. Each file gets a `PendingFile` entry with `status: "uploading"`
5. `isImageFile()` / `isDocumentFile()` routes to `uploadImage()` or `uploadDocument()`
6. On success: `status: "ready"`, `attachment` field populated
7. On failure: `status: "error"`, error message shown in chip
8. Send is disabled while any file is `status: "uploading"`

### File Chip States

| Status | Color | Icon |
|---|---|---|
| `uploading` | Gray | Spinning loader |
| `ready` | Green | Image or FileText icon |
| `error` | Red | Alert icon + error tooltip |

---

## 14. Component — WelcomeScreen

**File**: `src/components/chat/WelcomeScreen.tsx`

Shown when a session has no messages yet. Content adapts to the session mode.

**Chat mode** — shows four capability cards:
- Chat, Research, Images, Documents

**Research mode** — shows research-focused description.

Both modes show four starter prompt buttons. Clicking one immediately calls `send(text)`.

**Chat starters**: "Explain quantum computing...", "Differences between React and Vue...", etc.  
**Research starters**: "Advances in large language models 2024", "Climate change mitigation...", etc.

---

## 15. Component — ResearchProgress

**File**: `src/components/research/ResearchProgress.tsx`

Displayed inside `MessageWithResearch` when `phase === "polling"`.

```
┌──────────────────────────────────────────┐
│ 🔍 Quantum Computing    [Searching...] 42%│
│ ████████████░░░░░░░░░░░░░░░░░░░░░░░░░  │
│ 3 / 7 tasks completed                    │
└──────────────────────────────────────────┘
```

### Phase Indicators

| Status | Icon | Color |
|---|---|---|
| `queued` | `Loader2` (spinning) | text-muted |
| `planning` | `Brain` (spinning) | purple |
| `researching` | `Search` (spinning) | blue |
| `synthesizing` | `BookOpen` (spinning) | accent-light |
| `complete` | `CheckCircle2` | green |
| `error` | `XCircle` | red |

The progress bar fills based on `status.progress.percentage` (0–100). Error state turns the bar red and shows the error message below.

---

## 16. Component — ResearchReport

**File**: `src/components/research/ResearchReport.tsx`

Displayed inside `MessageWithResearch` when `phase === "complete"`.

```
┌──────────────────────────────────────────────┐
│ 📖 Quantum Computing         [✓ Verified] [Copy]│
│    ✅ Verified  ████ 87% confidence  12 sources │
├──────────────────────────────────────────────┤
│ ## Executive Summary                          │
│ [Markdown-rendered report with [1][2] cites]  │
│                                               │
│ ## Key Findings                               │
│ ...                                           │
├──────────────────────────────────────────────┤
│ REFERENCES                                    │
│ [1] Paper title — https://arxiv.org/...       │
│ [2] Blog post — https://...                   │
└──────────────────────────────────────────────┘
```

### Header Metadata

| Indicator | Condition | Color |
|---|---|---|
| `✅ Verified` | `result.verified === true` | Green |
| `⚠ Unverified` | `result.verified === false` | Amber |
| `XX% confidence` | Always shown | Green ≥70%, Amber 40–70%, Red <40% |
| Source count | When `citations.length > 0` | Muted |

The report body renders as full markdown (same `react-markdown` + `vscDarkPlus` setup as `MessageBubble`).

The references section renders each citation with: `[N]` index, title (linked), URL, and truncated snippet.

---

## 17. Data Flow — Sending a Chat Message

```
User selects "💬 Chat" chip, types "What is RLHF?", presses Enter
        │
InputArea.submit()
  ├── Calls ChatContext.send("What is RLHF?", [], "chat")
  └── Clears textarea; resets chip to session default

ChatContext.send(content, [], "chat")
  ├── 1. Resolve toolMode → TOOL_CONFIG["chat"] = { triggerResearch: false, toolPreference: "" }
  ├── 2. Optimistically add user ChatMessage to activeSession.messages
  ├── 3. Set streaming = { sessionId, content: "" }
  ├── 4. for await (event of sendMessage(sessionId, content, [], false, ""))
  │     ├── chunk events → append to streaming.content (triggers re-render)
  │     └── done event  → clear streaming, add assistant ChatMessage to messages
  └── 5. loadSessions() to refresh sidebar title

ChatArea renders:
  ├── All historical messages via MessageBubble
  └── StreamingMessage with live content while streaming
        (disappears when streaming is cleared and done message added)
```

---

## 18. Data Flow — File Upload

```
User clicks paperclip → selects "report.pdf"
        │
InputArea.handleFileSelect()
  ├── 1. Add PendingFile { id, file, status: "uploading" }
  ├── 2. isDocumentFile("report.pdf") → true
  ├── 3. await uploadDocument(file) → POST /api/upload/document (multipart)
  │     Backend: PyPDF2 extracts text → returns { extracted_text, description, ... }
  ├── 4. Update PendingFile → { status: "ready", attachment: FileAttachment }
  └── 5. File chip turns green

User types "Summarize this" and submits
        │
ChatContext.send("Summarize this", [{ name: "report.pdf", extracted_text: "...", ... }])
  │
Backend chat route:
  ├── Save user message with attachments to ChatSession
  ├── get_conversation_history()
  │     → prepends "[Attached: report.pdf]\n{extracted_text}" to user message
  └── Stream LLM response with full document as context
```

---

## 19. Data Flow — Research Mode

Tool modes other than `"chat"` all trigger the research pipeline. The difference is what hint is sent to the TaskPlanner.

```
User selects "📚 Academic" chip, types "Transformer architecture 2024"
        │
InputArea.submit()
  └── ChatContext.send("Transformer architecture 2024", [], "academic")

ChatContext.send(content, [], "academic")
  ├── TOOL_CONFIG["academic"] = { triggerResearch: true, toolPreference: "academic_search" }
  └── sendMessage(sessionId, content, [], true, "academic_search")
        │
Backend POST /api/chat/sessions/{id}/messages
  ├── trigger_research: true  →  _handle_research_stream()
  │     requirements = { max_sources: 10, tool_preference: "academic_search" }
  ├── Creates research_id = "research_abc123"
  ├── Stores context in MemoryManager
  ├── BackgroundTask: research_agent.conduct_research(topic, requirements, research_id)
  │     └── TaskPlanner receives tool_preference → LLM prompt appends:
  │           "Prioritize tasks that use 'academic_search'"
  └── SSE stream:
        data: {"type":"research_started","research_id":"research_abc123","topic":"..."}
        data: {"type":"done","message":{...,"research_id":"research_abc123"}}

ChatContext receives:
  ├── research_started → setPendingResearchId("research_abc123") → input disabled
  └── done → add assistant message (with research_id) to session

ChatArea renders MessageWithResearch for the assistant message:
  └── useResearch("research_abc123")
        ├── Polls GET /api/research/status/research_abc123 every 3s
        ├── Shows <ResearchProgress> with live % and phase
        └── When status → "complete":
              fetchResults() → GET /api/research/results/research_abc123
              Shows <ResearchReport> with full markdown + citations

ChatContext pendingResearchId polling:
  └── Also polls every 3s → when "complete", setPendingResearchId(null) → input re-enabled
```

The same flow applies to `"web_search"` (hint: `"web_search"`) and `"research"` (no hint — planner decides freely).

### Header Mode Toggle

Clicking the mode badge in the chat header calls `switchSessionMode("research")` or `switchSessionMode("chat")`. This updates `activeSession.mode` locally, which causes `InputArea`'s `useEffect` to reset the default chip. It does **not** make a backend request — the session's server-side mode is unchanged.

import type {
  ChatSession,
  SessionListItem,
  ResearchStatus,
  ResearchResult,
  UploadedFile,
  StreamEvent,
  FileAttachment,
} from "./types";

const API_BASE = "/api";

// ─────────────────────────────────────────────────────────────────
// Session management
// ─────────────────────────────────────────────────────────────────

export async function createSession(
  title: string,
  mode: "chat" | "research"
): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, mode }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listSessions(): Promise<SessionListItem[]> {
  const res = await fetch(`${API_BASE}/chat/sessions`);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.sessions;
}

export async function getSession(sessionId: string): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function renameSession(
  sessionId: string,
  title: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/rename`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(await res.text());
}

// ─────────────────────────────────────────────────────────────────
// Streaming chat messages
// ─────────────────────────────────────────────────────────────────

export async function* sendMessage(
  sessionId: string,
  content: string,
  attachments: FileAttachment[] = [],
  triggerResearch = false
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      attachments,
      trigger_research: triggerResearch,
    }),
  });

  if (!res.ok) {
    const errText = await res.text();
    yield { type: "error", error: errText };
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event: StreamEvent = JSON.parse(line.slice(6));
        yield event;
      } catch {
        // malformed SSE line — skip
      }
    }
  }

  // Finalize the decoder to flush any buffered multi-byte UTF-8 sequences,
  // then process any remaining complete SSE line that lacked a trailing newline.
  buffer += decoder.decode();
  if (buffer.startsWith("data: ")) {
    try {
      const event: StreamEvent = JSON.parse(buffer.slice(6));
      yield event;
    } catch {
      // malformed final line
    }
  }
}

// ─────────────────────────────────────────────────────────────────
// Research pipeline
// ─────────────────────────────────────────────────────────────────

export async function getResearchStatus(
  researchId: string
): Promise<ResearchStatus> {
  const res = await fetch(`${API_BASE}/research/status/${researchId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getResearchResults(
  researchId: string
): Promise<ResearchResult> {
  const res = await fetch(`${API_BASE}/research/results/${researchId}`);
  if (res.status === 202) {
    const data = await res.json();
    throw new Error(data.detail ?? "Research still in progress");
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listResearchSessions(): Promise<unknown[]> {
  const res = await fetch(`${API_BASE}/research/sessions`);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.sessions;
}

// ─────────────────────────────────────────────────────────────────
// File uploads
// ─────────────────────────────────────────────────────────────────

export async function uploadImage(
  file: File,
  query = ""
): Promise<UploadedFile> {
  const form = new FormData();
  form.append("file", file);
  if (query) form.append("query", query);

  const res = await fetch(`${API_BASE}/upload/image`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function uploadDocument(file: File): Promise<UploadedFile> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/upload/document`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────
// Health
// ─────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{
  status: string;
  services: Record<string, string>;
}> {
  const res = await fetch("/health");
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

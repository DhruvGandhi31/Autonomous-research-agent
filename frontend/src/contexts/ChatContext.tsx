"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import type {
  ChatSession,
  ChatMessage,
  SessionListItem,
  FileAttachment,
  ToolMode,
} from "@/lib/types";
import {
  createSession,
  listSessions,
  getSession,
  deleteSession,
  sendMessage,
  getResearchStatus,
} from "@/lib/api";

interface StreamingState {
  sessionId: string;
  content: string;
}

interface ChatContextValue {
  sessions: SessionListItem[];
  activeSession: ChatSession | null;
  streaming: StreamingState | null;
  /** Set while a research job is running, used only to disable the input. */
  pendingResearchId: string | null;

  loadSessions: () => Promise<void>;
  openSession: (id: string) => Promise<void>;
  newChat: (mode?: "chat" | "research") => Promise<void>;
  removeSession: (id: string) => Promise<void>;
  setActiveSession: (session: ChatSession | null) => void;
  send: (content: string, attachments?: FileAttachment[], toolMode?: ToolMode) => Promise<void>;
  switchSessionMode: (mode: "chat" | "research") => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

const TOOL_CONFIG: Record<ToolMode, { triggerResearch: boolean; toolPreference: string }> = {
  chat:       { triggerResearch: false, toolPreference: "" },
  web_search: { triggerResearch: true,  toolPreference: "web_search" },
  academic:   { triggerResearch: true,  toolPreference: "academic_search" },
  research:   { triggerResearch: true,  toolPreference: "" },
};

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const [pendingResearchId, setPendingResearchId] = useState<string | null>(null);
  const streamingContentRef = useRef("");

  // Clear pendingResearchId once the research job finishes
  useEffect(() => {
    if (!pendingResearchId) return;
    const id = pendingResearchId;
    const interval = setInterval(async () => {
      try {
        const s = await getResearchStatus(id);
        if (s.status === "complete" || s.status === "error") {
          setPendingResearchId(null);
          clearInterval(interval);
        }
      } catch {
        setPendingResearchId(null);
        clearInterval(interval);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [pendingResearchId]);

  const loadSessions = useCallback(async () => {
    try {
      const list = await listSessions();
      setSessions(list);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const openSession = useCallback(async (id: string) => {
    try {
      const session = await getSession(id);
      setActiveSession(session);
      setPendingResearchId(null);
    } catch (err) {
      console.error("Failed to load session:", err);
    }
  }, []);

  const newChat = useCallback(
    async (mode: "chat" | "research" = "chat") => {
      try {
        const session = await createSession("New Chat", mode);
        await loadSessions();
        setActiveSession({ ...session, messages: [] });
        setPendingResearchId(null);
      } catch (err) {
        console.error("Failed to create session:", err);
      }
    },
    [loadSessions]
  );

  const removeSession = useCallback(
    async (id: string) => {
      try {
        await deleteSession(id);
        if (activeSession?.id === id) setActiveSession(null);
        await loadSessions();
      } catch (err) {
        console.error("Failed to delete session:", err);
      }
    },
    [activeSession, loadSessions]
  );

  const switchSessionMode = useCallback((mode: "chat" | "research") => {
    setActiveSession((prev) => (prev ? { ...prev, mode } : prev));
  }, []);

  const send = useCallback(
    async (content: string, attachments: FileAttachment[] = [], toolMode?: ToolMode) => {
      if (!activeSession) return;

      const sessionId = activeSession.id;
      const resolvedMode: ToolMode = toolMode ?? (activeSession.mode === "research" ? "research" : "chat");
      const { triggerResearch, toolPreference } = TOOL_CONFIG[resolvedMode];

      // Optimistically add user message
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: new Date().toISOString(),
        attachments,
        sources: [],
      };
      setActiveSession((prev) =>
        prev ? { ...prev, messages: [...prev.messages, userMsg] } : prev
      );

      // Start streaming placeholder
      streamingContentRef.current = "";
      setStreaming({ sessionId, content: "" });

      try {
        for await (const event of sendMessage(sessionId, content, attachments, triggerResearch, toolPreference)) {
          if (event.type === "chunk" && event.content) {
            streamingContentRef.current += event.content;
            setStreaming({ sessionId, content: streamingContentRef.current });
          } else if (event.type === "research_started" && event.research_id) {
            // Research kicked off — disable input until the message's useResearch resolves it
            setPendingResearchId(event.research_id);
          } else if (event.type === "done" && event.message) {
            setStreaming(null);
            streamingContentRef.current = "";
            setActiveSession((prev) =>
              prev
                ? { ...prev, messages: [...prev.messages, event.message!] }
                : prev
            );
            // If this was a research message, pendingResearchId stays set
            // until useResearch in MessageWithResearch gets "complete" status.
            // For regular chat, clear it (it was never set).
            if (!event.message.research_id) {
              setPendingResearchId(null);
            }
          } else if (event.type === "error") {
            setStreaming(null);
            streamingContentRef.current = "";
            setPendingResearchId(null);
            const errMsg: ChatMessage = {
              id: crypto.randomUUID(),
              role: "assistant",
              content: `Error: ${event.error}`,
              timestamp: new Date().toISOString(),
              attachments: [],
              sources: [],
            };
            setActiveSession((prev) =>
              prev ? { ...prev, messages: [...prev.messages, errMsg] } : prev
            );
          }
        }
      } catch (err) {
        setStreaming(null);
        streamingContentRef.current = "";
        setPendingResearchId(null);
        console.error("Send failed:", err);
      }

      await loadSessions();
    },
    [activeSession, loadSessions]
  );

  return (
    <ChatContext.Provider
      value={{
        sessions,
        activeSession,
        streaming,
        pendingResearchId,
        loadSessions,
        openSession,
        newChat,
        removeSession,
        setActiveSession,
        send,
        switchSessionMode,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatContext must be used within ChatProvider");
  return ctx;
}

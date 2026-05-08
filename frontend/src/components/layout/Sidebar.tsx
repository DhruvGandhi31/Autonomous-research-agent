"use client";

import { useState } from "react";
import {
  Plus,
  MessageSquare,
  Search,
  Trash2,
  FlaskConical,
  ChevronDown,
  ChevronRight,
  Bot,
} from "lucide-react";
import { useChatContext } from "@/contexts/ChatContext";
import { formatRelativeTime, cn } from "@/lib/utils";
import type { SessionListItem } from "@/lib/types";

export default function Sidebar() {
  const { sessions, activeSession, newChat, openSession, removeSession } =
    useChatContext();
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [showResearchSessions, setShowResearchSessions] = useState(true);
  const [showChatSessions, setShowChatSessions] = useState(true);

  const chatSessions = sessions.filter((s) => s.mode === "chat");
  const researchSessions = sessions.filter((s) => s.mode === "research");

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirmDelete === id) {
      await removeSession(id);
      setConfirmDelete(null);
    } else {
      setConfirmDelete(id);
      setTimeout(() => setConfirmDelete(null), 2500);
    }
  };

  return (
    <aside className="flex flex-col w-64 h-full bg-bg-secondary border-r border-border shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-border">
        <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/30 flex items-center justify-center">
          <Bot className="w-4 h-4 text-accent-light" />
        </div>
        <div>
          <p className="text-sm font-semibold text-text-primary">Research Agent</p>
          <p className="text-xs text-text-muted">AI-powered research</p>
        </div>
      </div>

      {/* New chat buttons */}
      <div className="flex gap-2 p-3">
        <button
          onClick={() => newChat("chat")}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          New Chat
        </button>
        <button
          onClick={() => newChat("research")}
          title="New Research"
          className="flex items-center justify-center px-3 py-2 rounded-lg bg-bg-tertiary hover:bg-bg-hover border border-border text-text-secondary hover:text-text-primary text-xs transition-colors"
        >
          <FlaskConical className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-1">
        {/* Chat sessions */}
        {chatSessions.length > 0 && (
          <div>
            <button
              onClick={() => setShowChatSessions((v) => !v)}
              className="flex items-center gap-1 w-full px-2 py-1.5 text-xs font-medium text-text-muted uppercase tracking-wider hover:text-text-secondary transition-colors"
            >
              {showChatSessions ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
              Chats
              <span className="ml-auto text-xs text-text-muted">
                {chatSessions.length}
              </span>
            </button>
            {showChatSessions &&
              chatSessions.map((s) => (
                <SessionItem
                  key={s.id}
                  session={s}
                  isActive={activeSession?.id === s.id}
                  confirmingDelete={confirmDelete === s.id}
                  onOpen={() => openSession(s.id)}
                  onDelete={(e) => handleDelete(s.id, e)}
                />
              ))}
          </div>
        )}

        {/* Research sessions */}
        {researchSessions.length > 0 && (
          <div>
            <button
              onClick={() => setShowResearchSessions((v) => !v)}
              className="flex items-center gap-1 w-full px-2 py-1.5 text-xs font-medium text-text-muted uppercase tracking-wider hover:text-text-secondary transition-colors"
            >
              {showResearchSessions ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
              Research
              <span className="ml-auto text-xs text-text-muted">
                {researchSessions.length}
              </span>
            </button>
            {showResearchSessions &&
              researchSessions.map((s) => (
                <SessionItem
                  key={s.id}
                  session={s}
                  isActive={activeSession?.id === s.id}
                  confirmingDelete={confirmDelete === s.id}
                  onOpen={() => openSession(s.id)}
                  onDelete={(e) => handleDelete(s.id, e)}
                />
              ))}
          </div>
        )}

        {sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <MessageSquare className="w-8 h-8 text-text-muted mb-3 opacity-50" />
            <p className="text-xs text-text-muted">No conversations yet</p>
            <p className="text-xs text-text-muted mt-1">Start a new chat above</p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border">
        <p className="text-xs text-text-muted text-center">
          Powered by{" "}
          <span className="text-accent-light font-medium">llama3.1</span> via Ollama
        </p>
      </div>
    </aside>
  );
}

function SessionItem({
  session,
  isActive,
  confirmingDelete,
  onOpen,
  onDelete,
}: {
  session: SessionListItem;
  isActive: boolean;
  confirmingDelete: boolean;
  onOpen: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      onClick={onOpen}
      className={cn(
        "group w-full flex items-start gap-2 px-2.5 py-2 rounded-lg text-left transition-colors",
        isActive
          ? "bg-accent/15 text-text-primary"
          : "hover:bg-bg-hover text-text-secondary hover:text-text-primary"
      )}
    >
      <div className="mt-0.5 shrink-0">
        {session.mode === "research" ? (
          <FlaskConical className="w-3.5 h-3.5 text-accent-light" />
        ) : (
          <MessageSquare className="w-3.5 h-3.5 text-text-muted" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium truncate leading-tight">
          {session.title}
        </p>
        <p className="text-xs text-text-muted mt-0.5">
          {formatRelativeTime(session.updated_at)}
        </p>
      </div>
      <button
        onClick={onDelete}
        title={confirmingDelete ? "Click again to confirm" : "Delete"}
        className={cn(
          "shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity",
          confirmingDelete
            ? "text-red-400 opacity-100"
            : "text-text-muted hover:text-red-400"
        )}
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </button>
  );
}

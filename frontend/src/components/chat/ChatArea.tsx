"use client";

import { useEffect, useRef } from "react";
import { Bot, Loader2 } from "lucide-react";
import { useChatContext } from "@/contexts/ChatContext";
import { useResearch } from "@/hooks/useResearch";
import MessageBubble from "./MessageBubble";
import WelcomeScreen from "./WelcomeScreen";
import InputArea from "./InputArea";
import ResearchProgress from "@/components/research/ResearchProgress";
import ResearchReport from "@/components/research/ResearchReport";
import type { ChatMessage } from "@/lib/types";

export default function ChatArea() {
  const { activeSession, streaming, pendingResearchId, send } = useChatContext();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession?.messages, streaming]);

  if (!activeSession) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-primary">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-bg-secondary border border-border flex items-center justify-center mx-auto mb-4">
            <Bot className="w-8 h-8 text-text-muted" />
          </div>
          <p className="text-text-secondary">
            Select a conversation or start a new one
          </p>
        </div>
      </div>
    );
  }

  const isStreaming = streaming?.sessionId === activeSession.id;
  const inputDisabled = isStreaming || Boolean(pendingResearchId);

  return (
    <div className="flex-1 flex flex-col bg-bg-primary overflow-hidden">
      {/* Header */}
      <div className="shrink-0 flex items-center gap-3 px-5 py-3.5 border-b border-border bg-bg-secondary">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-text-primary truncate">
            {activeSession.title}
          </h2>
          <p className="text-xs text-text-muted capitalize">
            {activeSession.mode} mode
          </p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {activeSession.messages.length === 0 && !isStreaming ? (
          <WelcomeScreen />
        ) : (
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
            {activeSession.messages.map((msg) => (
              <MessageWithResearch key={msg.id} message={msg} />
            ))}

            {isStreaming && <StreamingMessage content={streaming!.content} />}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <InputArea onSend={send} disabled={inputDisabled} mode={activeSession.mode} />
    </div>
  );
}

function MessageWithResearch({ message }: { message: ChatMessage }) {
  const { status, result, phase } = useResearch(message.research_id ?? null);

  return (
    <>
      <MessageBubble message={message} />
      {message.research_id && phase === "polling" && status && (
        <div className="pl-11">
          <ResearchProgress status={status} />
        </div>
      )}
      {message.research_id && phase === "complete" && result && (
        <div className="pl-11 animate-fade-in">
          <ResearchReport result={result} />
        </div>
      )}
    </>
  );
}

function StreamingMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="shrink-0 w-8 h-8 rounded-full bg-bg-card border border-border flex items-center justify-center">
        <Loader2 className="w-4 h-4 text-accent-light animate-spin" />
      </div>
      <div className="flex-1">
        <div className="bg-bg-card border border-border rounded-2xl px-4 py-3 max-w-[85%]">
          {content ? (
            <div className="prose text-sm streaming-cursor">{content}</div>
          ) : (
            <span className="inline-flex gap-1 items-center py-0.5">
              {[0, 150, 300].map((d) => (
                <span
                  key={d}
                  className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce"
                  style={{ animationDelay: `${d}ms` }}
                />
              ))}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

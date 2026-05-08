"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check, User, Bot, FileText, Image, ExternalLink, FlaskConical } from "lucide-react";
import { useState } from "react";
import { cn, formatRelativeTime, formatBytes } from "@/lib/utils";
import type { ChatMessage, Citation } from "@/lib/types";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex gap-3 animate-slide-up",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
          isUser
            ? "bg-accent/20 border border-accent/30"
            : "bg-bg-card border border-border"
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-accent-light" />
        ) : message.research_id ? (
          <FlaskConical className="w-4 h-4 text-accent-light" />
        ) : (
          <Bot className="w-4 h-4 text-text-secondary" />
        )}
      </div>

      <div className={cn("flex flex-col gap-2 max-w-[85%]", isUser && "items-end")}>
        {/* File attachments */}
        {message.attachments?.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {message.attachments.map((att) => (
              <AttachmentChip key={att.name} attachment={att} />
            ))}
          </div>
        )}

        {/* Message bubble */}
        <div
          className={cn(
            "relative group rounded-2xl px-4 py-3",
            isUser
              ? "bg-accent/15 border border-accent/20 text-text-primary"
              : "bg-bg-card border border-border text-text-primary"
          )}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {message.content}
            </p>
          ) : (
            <div className="text-sm">
              <MarkdownContent
                content={message.content}
                isStreaming={isStreaming}
              />
            </div>
          )}

          {/* Copy button */}
          {!isUser && message.content && (
            <CopyButton text={message.content} />
          )}
        </div>

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <SourcesList sources={message.sources} />
        )}

        {/* Timestamp */}
        <p className="text-xs text-text-muted px-1">
          {formatRelativeTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
}

function MarkdownContent({
  content,
  isStreaming,
}: {
  content: string;
  isStreaming?: boolean;
}) {
  return (
    <div className={cn("prose", isStreaming && "streaming-cursor")}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const isBlock = (children?.toString() ?? "").includes("\n");
            if (match && isBlock) {
              return (
                <div className="relative my-3">
                  <div className="flex items-center justify-between bg-bg-primary px-3 py-1.5 rounded-t-lg border border-border border-b-0">
                    <span className="text-xs text-text-muted font-mono">
                      {match[1]}
                    </span>
                    <CopyButton text={String(children).replace(/\n$/, "")} />
                  </div>
                  <SyntaxHighlighter
                    style={vscDarkPlus as Record<string, React.CSSProperties>}
                    language={match[1]}
                    PreTag="div"
                    customStyle={{
                      margin: 0,
                      borderRadius: "0 0 8px 8px",
                      border: "1px solid #2a2a45",
                      borderTop: "none",
                      fontSize: "0.8rem",
                    }}
                  >
                    {String(children).replace(/\n$/, "")}
                  </SyntaxHighlighter>
                </div>
              );
            }
            return (
              <code className={cn(className, "text-xs")} {...props}>
                {children}
              </code>
            );
          },
          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent-light hover:text-accent inline-flex items-center gap-0.5"
              >
                {children}
                <ExternalLink className="w-3 h-3 inline" />
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={copy}
      className="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-secondary transition-colors"
      title="Copy"
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-green-400" />
      ) : (
        <Copy className="w-3.5 h-3.5" />
      )}
    </button>
  );
}

function AttachmentChip({
  attachment,
}: {
  attachment: { name: string; file_type: string; size?: number };
}) {
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border text-xs text-text-secondary">
      {attachment.file_type === "image" ? (
        <Image className="w-3.5 h-3.5 text-blue-400" />
      ) : (
        <FileText className="w-3.5 h-3.5 text-amber-400" />
      )}
      <span className="truncate max-w-[160px]">{attachment.name}</span>
      {attachment.size && (
        <span className="text-text-muted">{formatBytes(attachment.size)}</span>
      )}
    </div>
  );
}

function SourcesList({ sources }: { sources: Citation[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? sources : sources.slice(0, 3);

  return (
    <div className="w-full">
      <p className="text-xs text-text-muted mb-1.5 px-1">Sources</p>
      <div className="flex flex-wrap gap-2">
        {visible.map((src, i) => (
          <a
            key={src.url || i}
            href={src.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border hover:border-accent/50 text-xs text-text-secondary hover:text-accent-light transition-colors max-w-[220px]"
          >
            <ExternalLink className="w-3 h-3 shrink-0" />
            <span className="truncate">{src.title || src.url}</span>
          </a>
        ))}
        {sources.length > 3 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            {expanded ? "Show less" : `+${sources.length - 3} more`}
          </button>
        )}
      </div>
    </div>
  );
}

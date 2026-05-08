"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  BarChart3,
  BookOpen,
  Copy,
  Check,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ResearchResult } from "@/lib/types";

export default function ResearchReport({ result }: { result: ResearchResult }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!result.report) return;
    await navigator.clipboard.writeText(result.report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const confidence = result.confidence ?? 0;
  const confidenceColor =
    confidence >= 0.7
      ? "text-green-400"
      : confidence >= 0.4
        ? "text-amber-400"
        : "text-red-400";

  return (
    <div className="rounded-xl border border-border bg-bg-card overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-bg-secondary">
        <BookOpen className="w-4 h-4 text-accent-light shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-text-primary truncate">
            {result.topic}
          </p>
          <div className="flex items-center gap-3 mt-0.5">
            {result.verified !== undefined && (
              <span
                className={cn(
                  "flex items-center gap-1 text-xs",
                  result.verified ? "text-green-400" : "text-amber-400"
                )}
              >
                {result.verified ? (
                  <CheckCircle2 className="w-3 h-3" />
                ) : (
                  <AlertCircle className="w-3 h-3" />
                )}
                {result.verified ? "Verified" : "Unverified"}
              </span>
            )}
            {result.confidence !== undefined && (
              <span className={cn("flex items-center gap-1 text-xs", confidenceColor)}>
                <BarChart3 className="w-3 h-3" />
                {Math.round(confidence * 100)}% confidence
              </span>
            )}
            {result.citations && (
              <span className="text-xs text-text-muted">
                {result.citations.length} source{result.citations.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-bg-tertiary border border-border hover:border-border-light text-xs text-text-secondary hover:text-text-primary transition-colors"
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-green-400" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {/* Report content */}
      <div className="px-5 py-4">
        {result.report ? (
          <div className="prose text-sm">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  if (match && (children?.toString() ?? "").includes("\n")) {
                    return (
                      <SyntaxHighlighter
                        style={vscDarkPlus as Record<string, React.CSSProperties>}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{
                          borderRadius: "8px",
                          border: "1px solid #2a2a45",
                          fontSize: "0.8rem",
                        }}
                      >
                        {String(children).replace(/\n$/, "")}
                      </SyntaxHighlighter>
                    );
                  }
                  return (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {result.report}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-text-muted italic">No report content available.</p>
        )}
      </div>

      {/* Citations */}
      {result.citations && result.citations.length > 0 && (
        <div className="px-5 py-4 border-t border-border">
          <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            References
          </p>
          <div className="space-y-2">
            {result.citations.map((cite, i) => (
              <a
                key={cite.url || i}
                href={cite.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-2.5 group"
              >
                <span className="text-xs text-text-muted font-mono mt-0.5 shrink-0 w-5 text-right">
                  [{i + 1}]
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-accent-light group-hover:text-accent truncate font-medium">
                    {cite.title || cite.url}
                  </p>
                  {cite.url && (
                    <p className="text-xs text-text-muted truncate">{cite.url}</p>
                  )}
                  {cite.snippet && (
                    <p className="text-xs text-text-muted line-clamp-2 mt-0.5">
                      {cite.snippet}
                    </p>
                  )}
                </div>
                <ExternalLink className="w-3 h-3 text-text-muted shrink-0 mt-0.5 group-hover:text-accent-light" />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

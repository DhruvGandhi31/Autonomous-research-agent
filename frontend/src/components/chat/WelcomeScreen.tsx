"use client";

import { Bot, FlaskConical, FileText, Image, MessageSquare, Search } from "lucide-react";
import { useChatContext } from "@/contexts/ChatContext";

const CHAT_STARTERS = [
  "Explain quantum computing in simple terms",
  "What are the key differences between React and Vue?",
  "Help me understand the implications of AI on the job market",
  "Write a Python function to parse JSON and handle errors",
];

const RESEARCH_STARTERS = [
  "Advances in large language models 2024",
  "Climate change mitigation strategies",
  "CRISPR gene editing applications",
  "Future of renewable energy storage",
];

export default function WelcomeScreen() {
  const { activeSession, send } = useChatContext();
  const isResearch = activeSession?.mode === "research";

  const starters = isResearch ? RESEARCH_STARTERS : CHAT_STARTERS;

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-12 max-w-2xl mx-auto">
      {/* Icon */}
      <div className="w-16 h-16 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center mb-6">
        {isResearch ? (
          <FlaskConical className="w-8 h-8 text-accent-light" />
        ) : (
          <Bot className="w-8 h-8 text-accent-light" />
        )}
      </div>

      <h1 className="text-2xl font-semibold text-text-primary mb-2 text-center">
        {isResearch ? "Research Mode" : "Research Agent"}
      </h1>
      <p className="text-text-secondary text-center mb-8 leading-relaxed max-w-md">
        {isResearch
          ? "Enter any topic and I'll conduct comprehensive research using web sources, academic papers, and AI synthesis."
          : "Ask me anything. I can answer questions, analyze documents, process images, and conduct in-depth research."}
      </p>

      {/* Capabilities */}
      {!isResearch && (
        <div className="grid grid-cols-2 gap-3 w-full mb-8">
          {[
            {
              icon: MessageSquare,
              title: "Chat",
              desc: "Ask questions & get intelligent answers",
            },
            {
              icon: Search,
              title: "Research",
              desc: "Deep research with citations",
            },
            {
              icon: Image,
              title: "Images",
              desc: "Upload & analyze images with OCR",
            },
            {
              icon: FileText,
              title: "Documents",
              desc: "Process PDF & DOCX files",
            },
          ].map(({ icon: Icon, title, desc }) => (
            <div
              key={title}
              className="flex items-start gap-3 p-3.5 rounded-xl bg-bg-card border border-border"
            >
              <Icon className="w-4 h-4 text-accent-light mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-text-primary">{title}</p>
                <p className="text-xs text-text-muted mt-0.5">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Starter suggestions */}
      <div className="w-full">
        <p className="text-xs text-text-muted uppercase tracking-wider mb-3 text-center">
          {isResearch ? "Try researching" : "Try asking"}
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {starters.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="text-left px-4 py-3 rounded-xl bg-bg-card border border-border hover:border-accent/40 hover:bg-bg-hover text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

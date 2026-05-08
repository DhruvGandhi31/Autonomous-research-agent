"use client";

import {
  useRef,
  useState,
  useCallback,
  useEffect,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import {
  SendHorizontal,
  Paperclip,
  X,
  Loader2,
  Image,
  FileText,
  AlertCircle,
  MessageSquare,
  Globe,
  BookOpen,
  FlaskConical,
} from "lucide-react";
import { cn, formatBytes, isImageFile, isDocumentFile } from "@/lib/utils";
import { uploadImage, uploadDocument } from "@/lib/api";
import type { FileAttachment, ToolMode } from "@/lib/types";

interface InputAreaProps {
  onSend: (content: string, attachments: FileAttachment[], toolMode: ToolMode) => void;
  disabled?: boolean;
  mode: "chat" | "research";
}

interface PendingFile {
  id: string;
  file: File;
  status: "uploading" | "ready" | "error";
  attachment?: FileAttachment;
  error?: string;
}

const TOOL_MODES: { mode: ToolMode; label: string; icon: React.ElementType; description: string }[] = [
  { mode: "chat",       label: "Chat",          icon: MessageSquare, description: "Direct LLM response" },
  { mode: "web_search", label: "Web Search",    icon: Globe,         description: "Search the web" },
  { mode: "academic",   label: "Academic",      icon: BookOpen,      description: "arXiv · Semantic Scholar · Wikipedia" },
  { mode: "research",   label: "Full Research", icon: FlaskConical,  description: "All tools + RAG synthesis" },
];

export default function InputArea({ onSend, disabled, mode }: InputAreaProps) {
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const defaultTool: ToolMode = mode === "research" ? "research" : "chat";
  const [selectedTool, setSelectedTool] = useState<ToolMode>(defaultTool);

  // Sync default chip when session mode changes (e.g. header toggle or session switch)
  useEffect(() => {
    setSelectedTool(mode === "research" ? "research" : "chat");
  }, [mode]);

  const isUploading = pendingFiles.some((f) => f.status === "uploading");
  const canSend = text.trim().length > 0 && !disabled && !isUploading;

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, []);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    adjustHeight();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) submit();
    }
  };

  const submit = () => {
    const content = text.trim();
    if (!content) return;
    const attachments = pendingFiles
      .filter((f) => f.status === "ready" && f.attachment)
      .map((f) => f.attachment!);
    onSend(content, attachments, selectedTool);
    setText("");
    setPendingFiles([]);
    setSelectedTool(defaultTool);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleFileSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";

    const entries = files.map((file) => ({ id: crypto.randomUUID(), file }));
    setPendingFiles((prev) => [
      ...prev,
      ...entries.map(({ id, file }) => ({ id, file, status: "uploading" as const })),
    ]);

    const uploadOne = async ({ id, file }: { id: string; file: File }) => {
      try {
        let uploaded;
        if (isImageFile(file.name)) {
          uploaded = await uploadImage(file);
        } else if (isDocumentFile(file.name)) {
          uploaded = await uploadDocument(file);
        } else {
          setPendingFiles((prev) =>
            prev.map((f) =>
              f.id === id
                ? { ...f, status: "error" as const, error: "Unsupported file type" }
                : f
            )
          );
          return;
        }

        const attachment: FileAttachment = {
          name: uploaded.filename,
          file_type: uploaded.file_type as "image" | "document",
          extracted_text: uploaded.extracted_text,
          description: uploaded.description,
          size: uploaded.size,
        };
        setPendingFiles((prev) =>
          prev.map((f) =>
            f.id === id ? { ...f, status: "ready" as const, attachment } : f
          )
        );
      } catch (err) {
        setPendingFiles((prev) =>
          prev.map((f) =>
            f.id === id
              ? {
                  ...f,
                  status: "error" as const,
                  error: err instanceof Error ? err.message : "Upload failed",
                }
              : f
          )
        );
      }
    };

    await Promise.all(entries.map(uploadOne));
  };

  const removeFile = (id: string) => {
    setPendingFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const activeToolMeta = TOOL_MODES.find((t) => t.mode === selectedTool)!;

  return (
    <div className="border-t border-border bg-bg-secondary px-4 py-3">
      {/* Pending files */}
      {pendingFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {pendingFiles.map((pf) => (
            <FileChip
              key={pf.id}
              name={pf.file.name}
              size={pf.file.size}
              status={pf.status}
              error={pf.error}
              onRemove={() => removeFile(pf.id)}
            />
          ))}
        </div>
      )}

      {/* Tool mode chips */}
      <div className="flex items-center gap-1.5 mb-2">
        {TOOL_MODES.map(({ mode: tm, label, icon: Icon }) => (
          <button
            key={tm}
            type="button"
            onClick={() => setSelectedTool(tm)}
            disabled={disabled}
            title={TOOL_MODES.find((t) => t.mode === tm)?.description}
            className={cn(
              "flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors border",
              selectedTool === tm
                ? "bg-accent border-accent text-white"
                : "bg-bg-tertiary border-border text-text-muted hover:text-text-secondary hover:border-border-light disabled:opacity-40"
            )}
          >
            <Icon className="w-3 h-3" />
            {label}
          </button>
        ))}
      </div>

      {/* Input row */}
      <div className="flex items-end gap-2">
        {/* File upload button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="shrink-0 p-2.5 rounded-xl bg-bg-tertiary border border-border hover:border-border-light text-text-muted hover:text-text-secondary transition-colors disabled:opacity-40"
          title="Attach image or document"
        >
          <Paperclip className="w-4 h-4" />
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.docx,.doc,.txt"
          multiple
          className="hidden"
          onChange={handleFileSelect}
        />

        {/* Textarea */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={
              selectedTool === "chat"
                ? "Ask anything... (Shift+Enter for newline)"
                : selectedTool === "web_search"
                  ? "Search the web for..."
                  : selectedTool === "academic"
                    ? "Search academic papers for..."
                    : "Enter a research topic..."
            }
            rows={1}
            className={cn(
              "w-full bg-bg-tertiary border border-border rounded-xl px-4 py-3 pr-12",
              "text-sm text-text-primary placeholder:text-text-muted",
              "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30",
              "transition-colors disabled:opacity-50 resize-none",
              "min-h-[46px] max-h-[200px]"
            )}
          />
        </div>

        {/* Send button */}
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          className={cn(
            "shrink-0 p-2.5 rounded-xl transition-colors",
            canSend
              ? "bg-accent hover:bg-accent-hover text-white"
              : "bg-bg-tertiary border border-border text-text-muted opacity-50 cursor-not-allowed"
          )}
        >
          {disabled && !canSend ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <SendHorizontal className="w-4 h-4" />
          )}
        </button>
      </div>

      <p className="text-xs text-text-muted mt-2">
        <span className="font-medium text-accent-light">{activeToolMeta.label}</span>
        {" · "}
        {activeToolMeta.description}
        {selectedTool !== "chat" && " · results appear below message"}
      </p>
    </div>
  );
}

function FileChip({
  name,
  size,
  status,
  error,
  onRemove,
}: {
  name: string;
  size: number;
  status: PendingFile["status"];
  error?: string;
  onRemove: () => void;
}) {
  const isImg = isImageFile(name);

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-colors",
        status === "error"
          ? "border-red-500/50 bg-red-950/20 text-red-400"
          : status === "uploading"
            ? "border-border bg-bg-tertiary text-text-muted"
            : "border-green-500/30 bg-green-950/20 text-green-400"
      )}
      title={error}
    >
      {status === "uploading" ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : status === "error" ? (
        <AlertCircle className="w-3.5 h-3.5" />
      ) : isImg ? (
        <Image className="w-3.5 h-3.5" />
      ) : (
        <FileText className="w-3.5 h-3.5" />
      )}
      <span className="max-w-[140px] truncate">{name}</span>
      <span className="text-current opacity-60">{formatBytes(size)}</span>
      <button
        onClick={onRemove}
        className="hover:opacity-100 opacity-70 transition-opacity"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

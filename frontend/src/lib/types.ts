export type ToolMode = "chat" | "web_search" | "academic" | "research";

export interface FileAttachment {
  name: string;
  file_type: "image" | "document";
  extracted_text: string;
  description: string;
  size: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  attachments: FileAttachment[];
  research_id?: string | null;
  sources?: Citation[] | null;
}

export interface ChatSession {
  id: string;
  title: string;
  mode: "chat" | "research";
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface SessionListItem {
  id: string;
  title: string;
  mode: "chat" | "research";
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message: string | null;
}

export interface Citation {
  title: string;
  url: string;
  snippet?: string;
  source?: string;
  credibility_score?: number;
}

export interface ResearchStatus {
  research_id: string;
  status: "queued" | "planning" | "researching" | "synthesizing" | "complete" | "error";
  topic?: string;
  message?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  progress?: {
    completed_tasks: number;
    total_tasks: number;
    percentage: number;
  };
}

export interface ResearchResult {
  research_id: string;
  topic: string;
  status: string;
  report?: string;
  citations?: Citation[];
  confidence?: number;
  verified?: boolean;
  completed_at?: string;
  error?: string;
}

export interface UploadedFile {
  filename: string;
  content_type: string;
  size: number;
  extracted_text: string;
  description: string;
  preview?: string;
  file_type: "image" | "document";
}

export interface StreamEvent {
  type: "chunk" | "done" | "error" | "research_started";
  content?: string;
  message?: ChatMessage;
  error?: string;
  research_id?: string;
  topic?: string;
}

export type MessageRole = "user" | "assistant" | "system";

export interface ChatSession {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export interface ChatSessionDetail extends ChatSession {
  user_id: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  stage_data?: StageData | null;
  token_count?: number | null;
  created_at: string;
}

export interface StageData {
  stage: string;
  node: string;
  progress: string;
}

export interface ContextUsage {
  used_tokens: number;
  max_tokens: number;
}

export interface SSEEvent {
  event: string;
  data: string;
}

export interface PipelineStageUpdate {
  stage: string;
  node: string;
  progress: string;
}

export interface FinalDecision {
  content: string;
  rating: string;
  ticker: string;
  trade_date: string;
}

export interface AssistantMessage {
  content: string;
  role: "assistant";
}
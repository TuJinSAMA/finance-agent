import type { PipelineStageUpdate, FinalDecision, AssistantMessage, ContextUsage } from "@/types/chat";

export interface SSEHandlers {
  onStageUpdate?: (data: PipelineStageUpdate) => void;
  onFinalDecision?: (data: FinalDecision) => void;
  onAssistantMessage?: (data: AssistantMessage) => void;
  onContextUsage?: (data: ContextUsage) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function streamChatMessage(
  sessionId: string,
  message: string,
  token: string,
  handlers: SSEHandlers
): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ content: message }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    handlers.onError?.(errorText || `HTTP ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    handlers.onError?.("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const rawData = line.slice(6).trim();
        if (!rawData) continue;

        try {
          const parsed = JSON.parse(rawData);

          switch (currentEvent || parsed.event) {
            case "stage_update":
              handlers.onStageUpdate?.(parsed as PipelineStageUpdate);
              break;
            case "final_decision":
              handlers.onFinalDecision?.(parsed as FinalDecision);
              break;
            case "assistant_message":
              handlers.onAssistantMessage?.(parsed as AssistantMessage);
              break;
            case "context_usage":
              handlers.onContextUsage?.(parsed as ContextUsage);
              break;
            case "error":
              handlers.onError?.(parsed.message || "Unknown error");
              break;
            case "done":
              handlers.onDone?.();
              break;
          }
        } catch {
          // Not JSON, ignore
        }
      }
    }
  }

  handlers.onDone?.();
}
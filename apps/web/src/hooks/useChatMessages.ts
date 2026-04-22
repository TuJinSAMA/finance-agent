"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";
import { streamChatMessage } from "@/lib/chat-sse";
import type { ChatMessage, PipelineStageUpdate, ContextUsage } from "@/types/chat";

export function useChatMessages(sessionId: string | null) {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [stages, setStages] = useState<PipelineStageUpdate[]>([]);
  const [contextUsage, setContextUsage] = useState<ContextUsage>({ used_tokens: 0, max_tokens: 128000 });
  const [error, setError] = useState<string | null>(null);

  const fetchMessages = useCallback(async () => {
    if (!sessionId) return;
    try {
      const token = await getToken();
      const data = await apiFetch<ChatMessage[]>(
        `/api/v1/chat/sessions/${sessionId}/messages?limit=200`,
        { token: token || undefined }
      );
      setMessages(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch messages");
    }
  }, [sessionId, getToken]);

  const sendMessage = useCallback(async (content: string) => {
    if (!sessionId || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);
    setStages([]);
    setError(null);

    const token = await getToken();

    const assistantMsg: ChatMessage = {
      id: `temp-assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, assistantMsg]);

    await streamChatMessage(sessionId, content, token || "", {
      onStageUpdate: (data) => {
        setStages((prev) => [...prev, data]);
      },
      onFinalDecision: (data) => {
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: `## Investment Decision: ${data.ticker}\n\n**Rating: ${data.rating}**\n\n${data.content}\n\n*Analysis date: ${data.trade_date}*`,
            };
          }
          return updated;
        });
      },
      onAssistantMessage: (data) => {
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: data.content,
            };
          }
          return updated;
        });
      },
      onContextUsage: (data) => {
        setContextUsage(data);
      },
      onError: (msg) => {
        setError(msg);
      },
      onDone: () => {
        setIsStreaming(false);
        fetchMessages();
      },
    });
  }, [sessionId, isStreaming, getToken, fetchMessages]);

  const stopStreaming = useCallback(() => {
    setIsStreaming(false);
  }, []);

  return {
    messages,
    isStreaming,
    stages,
    contextUsage,
    error,
    fetchMessages,
    sendMessage,
    stopStreaming,
  };
}
"use client";

import { useEffect } from "react";
import { useChatMessages } from "@/hooks/useChatMessages";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { ContextGauge } from "./ContextGauge";
import { RotateCcw } from "lucide-react";
import { useChatSession } from "@/hooks/useChatSession";

interface ChatAreaProps {
  sessionId: string;
}

export function ChatArea({ sessionId }: ChatAreaProps) {
  const { messages, isStreaming, stages, contextUsage, error, fetchMessages, sendMessage, stopStreaming } =
    useChatMessages(sessionId);
  const { clearContext } = useChatSession();

  useEffect(() => {
    fetchMessages();
  }, [sessionId, fetchMessages]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-divider bg-cream">
        <ContextGauge usage={contextUsage} />
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              await clearContext(sessionId);
              await fetchMessages();
            }}
            className="p-1.5 rounded hover:bg-warm-gray/10 text-warm-gray"
            title="Clear context"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </div>
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-700 text-sm">{error}</div>
      )}
      <MessageList messages={messages} stages={stages} isStreaming={isStreaming} />
      <ChatInput onSend={sendMessage} isStreaming={isStreaming} onStop={stopStreaming} />
    </div>
  );
}
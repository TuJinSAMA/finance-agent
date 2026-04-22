"use client";

import type { ChatMessage } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed
          ${isUser
            ? "bg-terracotta text-white rounded-br-sm"
            : "bg-ink/5 text-ink rounded-bl-sm"
          }`}
      >
        <div className="whitespace-pre-wrap prose prose-sm max-w-none">
          {message.content}
        </div>
      </div>
    </div>
  );
}
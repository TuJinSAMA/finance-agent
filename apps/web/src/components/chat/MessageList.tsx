"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { PipelineProgress } from "./PipelineProgress";
import type { PipelineStageUpdate } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
  stages: PipelineStageUpdate[];
  isStreaming: boolean;
}

export function MessageList({ messages, stages, isStreaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevMsgCount = useRef(0);

  useEffect(() => {
    if (messages.length > prevMsgCount.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    prevMsgCount.current = messages.length;
  }, [messages.length]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
      {stages.length > 0 && isStreaming && (
        <PipelineProgress stages={stages} />
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isStreaming && messages.length > 0 && messages[messages.length - 1].role === "user" && (
        <div className="flex justify-start mb-4">
          <div className="bg-ink/5 rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm text-ink/60 animate-pulse">
            Thinking...
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
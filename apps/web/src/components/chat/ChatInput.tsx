"use client";

import { useState } from "react";
import { Send, Square } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  isStreaming: boolean;
  onStop?: () => void;
}

export function ChatInput({ onSend, isStreaming, onStop }: ChatInputProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 p-3 border-t border-divider bg-cream">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Ask about a stock or market analysis..."
        disabled={isStreaming}
        className="flex-1 rounded-lg border border-divider bg-white px-4 py-2.5 text-sm
          focus:outline-none focus:ring-2 focus:ring-terracotta/30
          disabled:opacity-50 disabled:cursor-not-allowed"
      />
      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          className="p-2.5 rounded-lg bg-red-100 text-red-600 hover:bg-red-200 transition-colors"
        >
          <Square className="w-4 h-4" />
        </button>
      ) : (
        <button
          type="submit"
          disabled={!input.trim()}
          className="p-2.5 rounded-lg bg-terracotta text-white hover:bg-terracotta/90 transition-colors
            disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4" />
        </button>
      )}
    </form>
  );
}
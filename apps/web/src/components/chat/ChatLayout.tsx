"use client";

import { useState } from "react";
import { SessionSidebar } from "./SessionSidebar";
import { ChatArea } from "./ChatArea";
import type { ChatSession } from "@/types/chat";

export function ChatLayout() {
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-cream">
      <SessionSidebar
        activeSessionId={activeSession?.id ?? null}
        onSessionSelect={setActiveSession}
      />
      <div className="flex-1">
        {activeSession ? (
          <ChatArea sessionId={activeSession.id} />
        ) : (
          <div className="flex items-center justify-center h-full text-warm-gray">
            <p className="text-lg">Select a session or create a new one to start chatting</p>
          </div>
        )}
      </div>
    </div>
  );
}
"use client";

import { useChatSession } from "@/hooks/useChatSession";
import { SessionItem } from "./SessionItem";
import { NewSessionButton } from "./NewSessionButton";
import type { ChatSession } from "@/types/chat";

interface SessionSidebarProps {
  activeSessionId: string | null;
  onSessionSelect: (session: ChatSession) => void;
}

export function SessionSidebar({ activeSessionId, onSessionSelect }: SessionSidebarProps) {
  const { sessions, loading, createSession, deleteSession, updateSession } = useChatSession();

  const handleNewSession = async () => {
    const session = await createSession();
    if (session) {
      onSessionSelect(session as unknown as ChatSession);
    }
  };

  return (
    <div className="w-64 h-full bg-cream border-r border-divider flex flex-col">
      <div className="p-3">
        <NewSessionButton onClick={handleNewSession} disabled={loading} />
      </div>
      <div className="flex-1 overflow-y-auto px-2">
        {sessions.map((session) => (
          <SessionItem
            key={session.id}
            session={session}
            isActive={session.id === activeSessionId}
            onSelect={(id) => {
              const s = sessions.find((s) => s.id === id);
              if (s) onSessionSelect(s);
            }}
            onDelete={deleteSession}
            onRename={updateSession}
          />
        ))}
      </div>
    </div>
  );
}
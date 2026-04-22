"use client";

import { useState, useCallback, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";
import type { ChatSession, ChatSessionDetail } from "@/types/chat";

export function useChatSession() {
  const { getToken } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const token = await getToken();
      const data = await apiFetch<ChatSession[]>("/api/v1/chat/sessions", {
        token: token || undefined,
      });
      setSessions(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch sessions");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const createSession = useCallback(async (title?: string) => {
    const token = await getToken();
    const session = await apiFetch<ChatSessionDetail>("/api/v1/chat/sessions", {
      token: token || undefined,
      method: "POST",
      body: { title: title || "New Chat" },
    });
    setSessions((prev) => [session, ...prev]);
    return session;
  }, [getToken]);

  const updateSession = useCallback(async (id: string, title: string) => {
    const token = await getToken();
    const updated = await apiFetch<ChatSessionDetail>(`/api/v1/chat/sessions/${id}`, {
      token: token || undefined,
      method: "PATCH",
      body: { title },
    });
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title: updated.title, updated_at: updated.updated_at } : s))
    );
  }, [getToken]);

  const deleteSession = useCallback(async (id: string) => {
    const token = await getToken();
    await apiFetch<void>(`/api/v1/chat/sessions/${id}`, {
      token: token || undefined,
      method: "DELETE",
    });
    setSessions((prev) => prev.filter((s) => s.id !== id));
  }, [getToken]);

  const clearContext = useCallback(async (id: string) => {
    const token = await getToken();
    await apiFetch<void>(`/api/v1/chat/sessions/${id}/clear-context`, {
      token: token || undefined,
      method: "POST",
    });
  }, [getToken]);

  return {
    sessions,
    loading,
    error,
    fetchSessions,
    createSession,
    updateSession,
    deleteSession,
    clearContext,
  };
}
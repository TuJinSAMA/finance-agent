"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { UnreadCountResponse } from "@/types/api";

const POLL_INTERVAL_MS = 60_000;

export function useUnreadCount() {
  const { getToken, isSignedIn } = useAuth();
  const [count, setCount] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetch = useCallback(async () => {
    if (!isSignedIn) return;
    try {
      const token = await getToken();
      const data = await apiFetch<UnreadCountResponse>(
        "/api/v1/notifications/unread-count",
        { token },
      );
      setCount(data.count);
    } catch {
      // silently ignore polling errors
    }
  }, [getToken, isSignedIn]);

  useEffect(() => {
    fetch();
    intervalRef.current = setInterval(fetch, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetch]);

  return { count, refetch: fetch };
}

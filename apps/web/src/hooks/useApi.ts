"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export function useApi<T>(
  path: string | null,
  auth: boolean = false,
) {
  const { getToken } = useAuth();
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: !!path,
    error: null,
  });
  const [fetchCount, setFetchCount] = useState(0);

  useEffect(() => {
    if (!path) return;

    let cancelled = false;

    async function run() {
      if (!cancelled) setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const token = auth ? await getToken() : null;
        const data = await apiFetch<T>(path!, { token });
        if (!cancelled) setState({ data, loading: false, error: null });
      } catch (err) {
        if (!cancelled) {
          setState({
            data: null,
            loading: false,
            error: err instanceof Error ? err.message : "Unknown error",
          });
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [path, auth, getToken, fetchCount]);

  const refetch = useCallback(() => {
    setFetchCount((c) => c + 1);
  }, []);

  return { ...state, refetch };
}

export function useAuthFetch() {
  const { getToken } = useAuth();

  return useCallback(
    async <T>(
      path: string,
      options?: { method?: string; body?: unknown },
    ): Promise<T> => {
      const token = await getToken();
      return apiFetch<T>(path, { ...options, token });
    },
    [getToken],
  );
}

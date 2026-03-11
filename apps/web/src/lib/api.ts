const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface FetchOptions {
  method?: string;
  body?: unknown;
  token?: string | null;
}

export async function apiFetch<T>(
  path: string,
  options?: FetchOptions,
): Promise<T> {
  const headers: Record<string, string> = {};

  if (options?.body) {
    headers["Content-Type"] = "application/json";
  }
  if (options?.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method: options?.method || "GET",
    headers,
    body: options?.body ? JSON.stringify(options.body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || `API error ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

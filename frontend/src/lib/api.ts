import "server-only";

import { BACKEND_API_URL } from "@/lib/config";
import { getAccessToken } from "@/lib/session";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
  }
}

type Options = RequestInit & { searchParams?: Record<string, string | number | boolean | undefined> };

/**
 * Server-side data access. Every page and layout reads through this, so the
 * browser never talks to the API directly and never holds a token.
 */
export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const token = await getAccessToken();
  const url = new URL(`${BACKEND_API_URL}${path.startsWith("/") ? path : `/${path}`}`);
  for (const [key, value] of Object.entries(options.searchParams ?? {})) {
    if (value !== undefined && value !== "" && value !== null) {
      url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let code = "request_failed";
    let message = `${response.status} ${response.statusText}`;
    let details: unknown;
    try {
      const body = await response.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
      details = body?.error?.details;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, code, message, details);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Returns null instead of throwing, for panels that should degrade quietly. */
export async function apiSafe<T>(path: string, options: Options = {}): Promise<T | null> {
  try {
    return await api<T>(path, options);
  } catch {
    return null;
  }
}

"use client";

/**
 * Browser-side data access.
 *
 * All requests go to the Next.js proxy at /api/be/*, which attaches the access
 * token from the httpOnly cookie server-side. The bundle therefore contains no
 * credentials and no backend URL.
 */
export class ClientApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
  }
}

export async function request<T>(
  path: string,
  init: RequestInit & { params?: Record<string, string | number | boolean | undefined> } = {},
): Promise<T> {
  const url = new URL(
    `/api/be${path.startsWith("/") ? path : `/${path}`}`,
    window.location.origin,
  );
  for (const [key, value] of Object.entries(init.params ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let code = "request_failed";
    let message = `Request failed (${response.status})`;
    let details: unknown;
    try {
      const body = await response.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
      details = body?.error?.details;
    } catch {
      /* ignore */
    }
    throw new ClientApiError(response.status, code, message, details);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const apiGet = <T,>(path: string, params?: Record<string, any>) =>
  request<T>(path, { method: "GET", params });

export const apiPost = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const apiPatch = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) });

export const apiPut = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });

export const apiDelete = <T,>(path: string, params?: Record<string, any>) =>
  request<T>(path, { method: "DELETE", params });

/** Page renders and original documents stream through the same proxy. */
export const documentFileUrl = (id: string, disposition: "inline" | "attachment" = "inline") =>
  `/api/be/documents/${id}/file?disposition=${disposition}`;

export const pageRenderUrl = (id: string, page: number, layer = "page") =>
  `/api/be/documents/${id}/pages/${page}/render?layer=${layer}`;

export const reportExportUrl = (id: string) => `/api/be/reports/${id}/export?disposition=inline`;

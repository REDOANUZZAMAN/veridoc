import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { BACKEND_API_URL, REFRESH_COOKIE, SESSION_COOKIE } from "@/lib/config";

/**
 * Authenticated reverse proxy.
 *
 * Client components call `/api/be/<backend path>`; this handler attaches the
 * access token from the httpOnly cookie and streams the response back. Three
 * reasons it exists rather than calling the API from the browser:
 *
 *   1. no token ever reaches the browser bundle;
 *   2. `<img src>` for page renders and forensic overlays works without
 *      query-string credentials;
 *   3. an expired access token is refreshed transparently, once, using the
 *      refresh cookie - the investigator is not logged out mid-review.
 */
const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "transfer-encoding", "upgrade", "host", "content-length",
]);

async function refreshAccessToken(): Promise<string | null> {
  const store = await cookies();
  const refresh = store.get(REFRESH_COOKIE)?.value;
  if (!refresh) return null;
  try {
    const response = await fetch(`${BACKEND_API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    });
    if (!response.ok) return null;
    const body = await response.json();
    return body.access_token as string;
  } catch {
    return null;
  }
}

async function forward(request: Request, path: string[]): Promise<NextResponse> {
  const store = await cookies();
  let token = store.get(SESSION_COOKIE)?.value;

  const incoming = new URL(request.url);
  const target = new URL(`${BACKEND_API_URL}/${path.join("/")}`);
  target.search = incoming.search;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && key.toLowerCase() !== "cookie") {
      headers.set(key, value);
    }
  });

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const send = async (bearer?: string) => {
    const attempt = new Headers(headers);
    if (bearer) attempt.set("Authorization", `Bearer ${bearer}`);
    return fetch(target, {
      method: request.method,
      headers: attempt,
      body: body ? Buffer.from(body) : undefined,
      cache: "no-store",
      redirect: "manual",
    });
  };

  let upstream: Response;
  try {
    upstream = await send(token);
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "backend_unreachable",
          message: "The analysis service is not reachable. Your work has not been lost.",
          retryable: true,
        },
      },
      { status: 503 },
    );
  }

  let rotated: string | null = null;
  if (upstream.status === 401 && token) {
    rotated = await refreshAccessToken();
    if (rotated) {
      try {
        upstream = await send(rotated);
      } catch {
        /* fall through with the 401 */
      }
    }
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && key.toLowerCase() !== "set-cookie") {
      responseHeaders.set(key, value);
    }
  });

  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });

  if (rotated) {
    response.cookies.set(SESSION_COOKIE, rotated, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
    });
  }
  return response;
}

type Params = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, { params }: Params) {
  return forward(request, (await params).path);
}
export async function POST(request: Request, { params }: Params) {
  return forward(request, (await params).path);
}
export async function PATCH(request: Request, { params }: Params) {
  return forward(request, (await params).path);
}
export async function PUT(request: Request, { params }: Params) {
  return forward(request, (await params).path);
}
export async function DELETE(request: Request, { params }: Params) {
  return forward(request, (await params).path);
}

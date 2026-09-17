import { NextResponse } from "next/server";

import { BACKEND_API_URL, REFRESH_COOKIE, SESSION_COOKIE } from "@/lib/config";

/**
 * Credential exchange.
 *
 * The browser never receives a token: the access and refresh tokens are stored
 * in httpOnly, SameSite=Lax cookies, so page code cannot read them and they are
 * not attached to cross-site requests.
 */
export async function POST(request: Request) {
  let payload: { email?: string; password?: string };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json(
      { error: { code: "bad_request", message: "Invalid request body." } },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: payload.email, password: payload.password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "backend_unreachable",
          message: "The analysis service is not reachable. Check that the API is running.",
        },
      },
      { status: 503 },
    );
  }

  const body = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(body, { status: upstream.status });
  }

  const response = NextResponse.json({ user: body.user });
  const secure = process.env.NODE_ENV === "production";
  const expires = new Date(body.expires_at);
  response.cookies.set(SESSION_COOKIE, body.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    expires: Number.isNaN(expires.getTime()) ? undefined : expires,
  });
  response.cookies.set(REFRESH_COOKIE, body.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}

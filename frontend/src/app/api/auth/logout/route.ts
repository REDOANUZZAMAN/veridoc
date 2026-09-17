import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { BACKEND_API_URL, REFRESH_COOKIE, SESSION_COOKIE } from "@/lib/config";

export async function POST() {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;

  // Record the sign-out in the audit trail on a best-effort basis; clearing the
  // local session must succeed regardless of whether the API is reachable.
  if (token) {
    try {
      await fetch(`${BACKEND_API_URL}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      /* ignore */
    }
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}

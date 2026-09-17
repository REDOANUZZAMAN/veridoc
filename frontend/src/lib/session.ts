import "server-only";

import { cookies } from "next/headers";

import { BACKEND_API_URL, REFRESH_COOKIE, SESSION_COOKIE } from "@/lib/config";
import type { SessionUser } from "@/lib/types";

/**
 * The access token lives in an httpOnly cookie and is attached to backend calls
 * on the server. It is never exposed to the browser bundle, so a script injected
 * into the page cannot read or exfiltrate it.
 */
export async function getAccessToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value;
}

export async function getRefreshToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value;
}

export async function getSessionUser(): Promise<SessionUser | null> {
  const token = await getAccessToken();
  if (!token) return null;
  try {
    const response = await fetch(`${BACKEND_API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as SessionUser;
  } catch {
    return null;
  }
}

export function can(user: SessionUser | null, permission: string): boolean {
  return Boolean(user?.permissions?.includes(permission));
}

export function canAny(user: SessionUser | null, ...permissions: string[]): boolean {
  return permissions.some((permission) => can(user, permission));
}

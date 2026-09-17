/** Server-only configuration. Never imported from a client component. */
export const BACKEND_API_URL =
  process.env.BACKEND_API_URL?.replace(/\/$/, "") ?? "http://localhost:8088/api";

export const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "veridoc_session";
export const REFRESH_COOKIE = `${SESSION_COOKIE}_refresh`;

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "VeriDoc";
export const DEMO_MODE = (process.env.NEXT_PUBLIC_DEMO_MODE ?? "true") === "true";

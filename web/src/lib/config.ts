/**
 * Where the hub lives.
 *
 * 1. `VITE_HUB_URL` when set at build time.
 * 2. On the Vite dev server (port 5173): the local hub on port 9000.
 * 3. Otherwise the same origin: the hub serves this app itself.
 */
export function hubBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_HUB_URL as string | undefined;
  if (fromEnv) return fromEnv.replace(/\/+$/, "");
  if (typeof window !== "undefined" && window.location.port === "5173") return "http://127.0.0.1:9000";
  return "";
}

/** An absolute URL for a hub path, for display and for URL parsing. */
export function hubUrl(path: string, base = hubBaseUrl()): URL {
  const origin = typeof window !== "undefined" ? window.location.href : "http://127.0.0.1:9000/";
  return new URL(base + path, origin);
}

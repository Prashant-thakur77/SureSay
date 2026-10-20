/** localStorage that never throws (private windows, blocked storage, tests). */

export function readJson<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: settings last for this visit only */
  }
}

export function remove(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export const KEYS = {
  device: "suresay.device",
  settings: "suresay.settings",
  /** "voice" or "quiet": the first-run choice. */
  start: "suresay.start",
} as const;

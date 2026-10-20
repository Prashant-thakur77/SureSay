import { useCallback, useEffect, useState } from "react";
import { KEYS, readJson, writeJson } from "../lib/storage";

export type ThemeChoice = "auto" | "light" | "dark" | "contrast";
export type TextScale = 1 | 1.25 | 1.5 | 2;
export type ScanSpeed = 1 | 1.5 | 2 | 3;

export interface Settings {
  textScale: TextScale;
  theme: ThemeChoice;
  readAloud: boolean;
  autoVoice: boolean;
  scan: boolean;
  scanSpeed: ScanSpeed;
  bigScreen: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  textScale: 1,
  theme: "auto",
  readAloud: true,
  autoVoice: true,
  scan: false,
  scanSpeed: 2,
  bigScreen: false,
};

const SCALES: TextScale[] = [1, 1.25, 1.5, 2];
const SPEEDS: ScanSpeed[] = [1, 1.5, 2, 3];
const THEMES: ThemeChoice[] = ["auto", "light", "dark", "contrast"];

function load(): Settings {
  const saved = readJson<Partial<Settings>>(KEYS.settings) ?? {};
  const s = { ...DEFAULT_SETTINGS, ...saved };
  return {
    textScale: SCALES.includes(s.textScale) ? s.textScale : 1,
    theme: THEMES.includes(s.theme) ? s.theme : "auto",
    readAloud: s.readAloud !== false,
    autoVoice: s.autoVoice !== false,
    scan: s.scan === true,
    scanSpeed: SPEEDS.includes(s.scanSpeed) ? s.scanSpeed : 2,
    bigScreen: s.bigScreen === true,
  };
}

function media(query: string): boolean {
  try {
    return typeof window.matchMedia === "function" && window.matchMedia(query).matches;
  } catch {
    return false;
  }
}

/** "auto" follows the device: high contrast when asked for, dark when the device is dark. */
export function resolveTheme(choice: ThemeChoice): "light" | "dark" | "contrast" {
  if (choice !== "auto") return choice;
  if (media("(prefers-contrast: more)") || media("(forced-colors: active)")) return "contrast";
  return media("(prefers-color-scheme: dark)") ? "dark" : "light";
}

export function tvFromUrl(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("tv") === "1";
  } catch {
    return false;
  }
}

/** Settings, saved on this device, applied to <html> (text size, theme, big screen). */
export function useSettings() {
  const [settings, setSettings] = useState<Settings>(load);
  const [systemTick, setSystemTick] = useState(0);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      writeJson(KEYS.settings, next);
      return next;
    });
  }, []);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const queries = ["(prefers-color-scheme: dark)", "(prefers-contrast: more)"].map((q) => window.matchMedia(q));
    const onChange = () => setSystemTick((t) => t + 1);
    queries.forEach((q) => q.addEventListener?.("change", onChange));
    return () => queries.forEach((q) => q.removeEventListener?.("change", onChange));
  }, []);

  const bigScreen = settings.bigScreen || tvFromUrl();
  const theme = resolveTheme(settings.theme);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.scale = String(settings.textScale);
    root.dataset.tv = bigScreen ? "1" : "0";
    root.style.fontSize = `${125 * settings.textScale}%`;
  }, [theme, settings.textScale, bigScreen, systemTick]);

  return { settings, update, bigScreen, theme };
}

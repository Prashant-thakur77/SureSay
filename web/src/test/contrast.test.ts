import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/** Reads the theme tokens out of styles.css and checks every pair the UI uses. */

const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

function tokens(theme: string): Record<string, string> {
  const block = new RegExp(`:root\\[data-theme="${theme}"\\]\\s*\\{([^}]*)\\}`).exec(css);
  if (!block) throw new Error(`no ${theme} block`);
  const out: Record<string, string> = {};
  for (const m of block[1].matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[m[1]] = m[2];
  return out;
}

function luminance(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

export function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT_PAIRS: Array<[string, string]> = [
  ["ink", "bg"],
  ["ink", "surface"],
  ["ink", "surface2"],
  ["muted", "bg"],
  ["muted", "surface"],
  ["muted", "surface2"],
  ["on-accent", "accent"],
  ["accent-ink", "bg"],
  ["accent-ink", "surface"],
  ["primary-ink", "primary-bg"],
  ["warn-ink", "warn-bg"],
  ["ok-ink", "ok-bg"],
  ["assist-ink", "assist-bg"],
  ["on-ink", "ink"],
  // receipt ticket and consent trail
  ["ink", "ticket-bg"],
  ["muted", "ticket-bg"],
  ["stamp", "ticket-bg"],
  ["ok-ink", "surface2"],
  ["warn-ink", "surface2"],
  ["accent-ink", "surface2"],
];

const UI_PAIRS: Array<[string, string]> = [
  ["focus", "bg"],
  ["focus", "surface"],
  ["line", "bg"],
  ["line", "surface"],
  ["mic-border", "bg"],
];

describe.each(["light", "dark", "contrast"])("%s theme contrast", (theme) => {
  const t = tokens(theme);
  it.each(TEXT_PAIRS)("text %s on %s is at least 7:1", (fg, bg) => {
    expect(t[fg], `--${fg}`).toBeDefined();
    expect(t[bg], `--${bg}`).toBeDefined();
    expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(7);
  });
  it.each(UI_PAIRS)("%s against %s is at least 3:1", (fg, bg) => {
    expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(3);
  });
});

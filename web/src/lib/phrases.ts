/** Speak-for-me tiles, the Teach choices, and plain words for what a phrase means. */

import type { Phrase } from "./types";

export interface BoardTile {
  key: string;
  /** Big words on the tile. */
  title: string;
  /** The sentence SureSay says out loud. */
  text: string;
  /** From the user's own phrasebook. */
  own: boolean;
}

export const STARTER_BOARD: Array<{ title: string; text: string }> = [
  { title: "Yes", text: "Yes." },
  { title: "No", text: "No." },
  { title: "Thank you", text: "Thank you." },
  { title: "I need help", text: "I need help." },
  { title: "I am in pain", text: "I am in pain." },
  { title: "I am thirsty", text: "I am thirsty." },
  { title: "Please wait", text: "Please wait." },
  { title: "Call my carer", text: "Please call my carer." },
];

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();

function capitalise(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

/** The user's say_for_me phrases first, then starter tiles (skipping ones they already have) until there are at least 8. */
export function boardTiles(phrasebook: Phrase[]): BoardTile[] {
  const own: BoardTile[] = phrasebook
    .filter((p) => p.action === "say_for_me" && typeof p.args?.text === "string" && p.args.text.trim())
    .map((p) => ({ key: p.id, title: capitalise(p.phrase), text: String(p.args.text), own: true }));
  if (own.length >= 8) return own;
  const seen = own.flatMap((t) => [norm(t.title), norm(t.text)]);
  const starters = STARTER_BOARD.filter((s) => {
    const t = norm(s.title);
    return !seen.some((x) => x === t || x.startsWith(`${t} `));
  }).map((s, i) => ({ key: `starter-${i}`, title: s.title, text: s.text, own: false }));
  return [...own, ...starters];
}

export interface TeachChoice {
  id: string;
  label: string;
  action: string;
  args: Record<string, unknown>;
  /** Needs a sentence typed in. */
  sentence?: boolean;
}

export const TEACH_CHOICES: TeachChoice[] = [
  { id: "fan-on", label: "Fan on", action: "home_set", args: { device: "fan", on: true } },
  { id: "fan-off", label: "Fan off", action: "home_set", args: { device: "fan", on: false } },
  { id: "living-on", label: "Living room lights on", action: "home_set", args: { device: "living_lights", on: true } },
  { id: "living-off", label: "Living room lights off", action: "home_set", args: { device: "living_lights", on: false } },
  { id: "bedroom-on", label: "Bedroom lights on", action: "home_set", args: { device: "bedroom_lights", on: true } },
  { id: "bedroom-off", label: "Bedroom lights off", action: "home_set", args: { device: "bedroom_lights", on: false } },
  { id: "tv-on", label: "TV on", action: "home_set", args: { device: "tv", on: true } },
  { id: "tv-off", label: "TV off", action: "home_set", args: { device: "tv", on: false } },
  { id: "ac-22", label: "AC to 22", action: "ac_set", args: { temperature: 22 } },
  { id: "lock", label: "Lock the door", action: "door_lock", args: { locked: true } },
  { id: "call-mom", label: "Call Mom", action: "call_contact", args: { contact_id: "mom" } },
  { id: "call-ravi", label: "Call Ravi", action: "call_contact", args: { contact_id: "ravi" } },
  { id: "milk", label: "Add milk", action: "cart_add", args: { product_id: "milk", qty: 1 } },
  { id: "say", label: "Say a sentence", action: "say_for_me", args: {}, sentence: true },
];

const DEVICE_WORDS: Record<string, string> = {
  fan: "the fan",
  living_lights: "the living room lights",
  bedroom_lights: "the bedroom lights",
  tv: "the TV",
  ac: "the AC",
};

/** "turn on the fan", "call Mom", "say “Thank you.”" */
export function describeMeaning(action: string, args: Record<string, unknown>): string {
  switch (action) {
    case "home_set":
      return `turn ${args.on ? "on" : "off"} ${DEVICE_WORDS[String(args.device)] ?? String(args.device)}`;
    case "ac_set":
      return `set the AC to ${args.temperature} degrees`;
    case "door_lock":
      return args.locked ? "lock the front door" : "unlock the front door";
    case "call_contact":
      return `call ${capitalise(String(args.contact_id).replace(/_/g, " "))}`;
    case "message_contact":
      return `message ${capitalise(String(args.contact_id))}: “${String(args.text ?? "")}”`;
    case "cart_add":
      return `add ${args.qty ?? 1} × ${String(args.product_id).replace(/_/g, " ")} to the cart`;
    case "cart_order":
      return "place the order";
    case "say_for_me":
      return `say “${String(args.text ?? "")}”`;
    default:
      return action.replace(/_/g, " ");
  }
}

/** Starter phrasebook entries have ids "ph_start…"; anything else was taught by the user. */
export function isLearned(p: Phrase): boolean {
  return !p.id.startsWith("ph_start");
}

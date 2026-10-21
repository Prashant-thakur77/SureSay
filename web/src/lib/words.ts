/** Plain-language copy built from server records. Short sentences, no jargon. */

import type { CardOption, GateEvent, PendingSet, Receipt } from "./types";

const NUMBER_WORDS = ["One", "Two", "Three", "Four", "Five"];

export function numberWord(n: number): string {
  return NUMBER_WORDS[n - 1] ?? String(n);
}

/** What is read aloud for a card set when the server did not give its own line. */
export function spokenChoices(set: Pick<PendingSet, "options" | "stage">): string {
  if (set.stage === "final") return `${set.options[0]?.text ?? ""}? Say yes or no.`;
  if (set.options.length === 1) return `${set.options[0].text}? Say one or yes, or no.`;
  const parts = set.options.map((o) => `${numberWord(o.n)}: ${o.text}.`);
  return `${parts.join(" ")} Say a number, or no.`;
}

export function isDoorbell(set: Pick<PendingSet, "origin" | "context">): boolean {
  return set.origin === "doorbell" || !!set.context?.visitor;
}

/** "Someone's at the door. Ravi, your carer, is at the front door with your shopping. One: … Say a number." */
export function spokenDoorbell(set: Pick<PendingSet, "options" | "stage" | "context">): string {
  const note = (set.context?.visitor?.note ?? "").trim().replace(/[.!?]+$/, "");
  const lead = note ? `Someone's at the door. ${note}.` : "Someone's at the door.";
  if (set.stage === "final") return `${lead} ${set.options[0]?.text ?? ""}? Say yes or no.`;
  const parts = set.options.map((o) => `${numberWord(o.n)}: ${o.text}.`);
  return `${lead} ${parts.join(" ")} Say a number.`;
}

export function isUnsure(set: Pick<PendingSet, "context">): boolean {
  return set.context?.unsure === true;
}

/** Read-back for "maybe" cards. */
export function spokenUnsure(set: Pick<PendingSet, "options" | "stage">): string {
  if (set.stage === "final") return `I'm not sure. Please say it again, or say yes if this is right: ${set.options[0]?.text ?? ""}?`;
  const parts = set.options.map((o) => `${numberWord(o.n)}: ${o.text}.`);
  return `I'm not sure. Please say it again, or say a number if one of these is right: ${parts.join(" ")}`;
}

/** What a screen reader hears when a new card set appears. */
export function announceChoices(set: PendingSet): string {
  if (isDoorbell(set) && set.stage !== "final") {
    const n = set.options.length;
    const note = set.context?.visitor?.note ?? "";
    return `Someone's at the door. ${note} ${n} ${n === 1 ? "choice" : "choices"}.`.replace(/\s+/g, " ").trim();
  }
  if (isUnsure(set)) {
    const n = set.options.length;
    return `Not sure. ${n} possible ${n === 1 ? "match" : "matches"}.`;
  }
  const who = set.origin === "assistant" ? "The assistant suggested this. You did not ask for it. " : "";
  if (set.stage === "final") return `${who}Second check. ${set.options[0]?.text}? Choose yes or no.`;
  const n = set.options.length;
  const list = set.options.map((o) => `${o.n}: ${o.text}`).join(". ");
  return `${who}${n} ${n === 1 ? "choice" : "choices"}. ${list}. Press a number, or Escape for none.`;
}

export type Likelihood = "Most likely" | "Maybe" | "Less likely";

export function likelihood(confidence: number | null | undefined, rank: number): Likelihood {
  if (typeof confidence === "number" && Number.isFinite(confidence)) {
    // only the top card can be "most likely"; the rest are at best "maybe"
    if (confidence >= 0.6 && rank === 1) return "Most likely";
    if (confidence >= 0.3) return "Maybe";
    return "Less likely";
  }
  return rank === 1 ? "Most likely" : rank === 2 ? "Maybe" : "Less likely";
}

/** A 0..1 value for the thin bar. Without a score, rank stands in. */
export function barValue(confidence: number | null | undefined, rank: number): number {
  if (typeof confidence === "number" && Number.isFinite(confidence)) return Math.max(0.04, Math.min(1, confidence));
  return [0.8, 0.5, 0.25][rank - 1] ?? 0.2;
}

/** Turn a gate refusal into words a person can act on. */
export function plainReason(reason: string | undefined): string {
  const r = (reason ?? "").toLowerCase();
  if (!r) return "It was not allowed.";
  if (r.includes("no user evidence")) return "No user evidence. Only your voice or tap can confirm.";
  if (r.includes("different card set")) return "That answer was for different cards.";
  if (r.includes("paired device")) return "The answer did not come from your paired device.";
  if (r.includes("already been answered")) return "These cards were already answered.";
  if (r.includes("expired")) return "The cards timed out before they were confirmed.";
  if (r.includes("already been used")) return "That answer was already used.";
  if (r.includes("did not clearly give")) return "The answer was not clear.";
  if (r.includes("changed after")) return "The action changed after you chose it, so it was stopped.";
  if (r.includes("not a registered")) return "SureSay cannot do that action.";
  return reason ?? "It was not allowed.";
}

/** Plain words for an evidence or confirm error (HTTP 409 and friends). */
export function plainEvidenceError(message: string): { text: string; expired: boolean } {
  const m = message.toLowerCase();
  if (m.includes("expired")) return { text: "These cards timed out. Please say it again.", expired: true };
  if (m.includes("already been answered")) return { text: "These cards were already answered.", expired: false };
  if (m.includes("recording has already been used"))
    return { text: "That recording was already used. Please answer again.", expired: false };
  if (m.includes("transcribe")) return { text: "I could not hear that answer. Please tap a card instead.", expired: false };
  if (m.includes("nonce") || m.includes("no such card set"))
    return { text: "These cards are no longer open. Please say it again.", expired: true };
  if (m.includes("final card takes")) return { text: "Please answer yes or no.", expired: false };
  return { text: "That did not work. Please try again.", expired: false };
}

function clock(at: number | string | null | undefined): string {
  if (at == null) return "";
  const d = typeof at === "number" ? new Date(at * 1000) : new Date(at);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export { clock as timeOf };

export function channelWords(r: Receipt): string {
  if (r.how.channel === "transcript") {
    const who = /alexa/i.test(r.evidence.transcriber ?? "") ? "your voice on Alexa" : "your voice assistant";
    return r.evidence.transcript ? `${who} (heard “${r.evidence.transcript}”)` : who;
  }
  if (r.how.channel === "voice") {
    const heard = r.evidence.transcript || r.evidence.decision?.heard;
    return heard ? `your voice (heard “${heard}”)` : "your voice";
  }
  return "your tap";
}

export type Tone = "warn" | "ok" | "info";

export interface ActivityLine {
  key: string;
  at: number;
  tone: Tone;
  label: string;
  text: string;
}

/** Gate events, newest first, in plain words. */
export function describeEvents(events: GateEvent[]): ActivityLine[] {
  const channelFor = new Map<string, string>();
  for (const e of events) {
    if (e.type === "evidence" && e.pending_id) channelFor.set(e.pending_id, e.channel === "voice" ? "your voice" : "your tap");
  }
  const lines: ActivityLine[] = [];
  events.forEach((e, i) => {
    const key = `${e.at}-${e.type}-${i}`;
    const opts = e.options ?? [];
    switch (e.type) {
      case "proposed": {
        if (e.origin === "assistant") {
          lines.push({ key, at: e.at, tone: "info", label: "Suggested", text: `The assistant suggested: ${opts.map((o) => o.text).join("; ")}` });
        } else if (e.stage === "final") {
          lines.push({ key, at: e.at, tone: "info", label: "Asked", text: `Second check: ${opts[0]?.text ?? ""}?` });
        } else {
          const n = opts.length;
          lines.push({ key, at: e.at, tone: "info", label: "Showed", text: `${n} ${n === 1 ? "choice" : "choices"}: ${opts.map((o) => o.text).join("; ")}` });
        }
        break;
      }
      case "evidence": {
        const d = e.decision;
        const how = e.channel === "voice" ? "You said" : "You tapped";
        const heard = e.channel === "voice" ? `“${e.transcript ?? d?.heard ?? ""}”` : (d?.heard ?? "").replace(/^tap:\s*/, "");
        if (d?.kind === "unclear") lines.push({ key, at: e.at, tone: "info", label: "Not clear", text: `${how} ${heard}. That was not a clear answer.` });
        else lines.push({ key, at: e.at, tone: "info", label: "Answer", text: `${how} ${heard}` });
        break;
      }
      case "refused": {
        const who = e.caller === "agent" ? " The assistant tried to confirm on its own." : "";
        lines.push({ key, at: e.at, tone: "warn", label: "Refused", text: `${plainReason(e.reason)}${who}` });
        break;
      }
      case "cancelled":
        lines.push({ key, at: e.at, tone: "info", label: "Cancelled", text: "Nothing was changed." });
        break;
      case "needs_final_yes":
        lines.push({ key, at: e.at, tone: "info", label: "Asked twice", text: "This one needs a second yes." });
        break;
      case "done": {
        const how = (e.pending_id && channelFor.get(e.pending_id)) || "you";
        lines.push({ key, at: e.at, tone: "ok", label: "Done", text: `${e.text ?? "Done"} (${how})` });
        break;
      }
      case "failed":
        lines.push({ key, at: e.at, tone: "warn", label: "Failed", text: e.error ?? e.reason ?? "It did not work." });
        break;
      default:
        break;
    }
  });
  return lines.reverse();
}

/** The icon for an option, from its action and arguments. */
export type IconName =
  | "bulb" | "fan" | "snow" | "tv" | "lock" | "unlock" | "phone" | "message" | "cart" | "speech" | "book" | "home" | "spark" | "bell";

export function iconFor(option: Pick<CardOption, "action" | "args">, devices?: Record<string, { kind: string }>): IconName {
  const a = option.args ?? {};
  switch (option.action) {
    case "home_set": {
      const id = String(a.device ?? "");
      const kind = devices?.[id]?.kind ?? (id.includes("light") ? "light" : id);
      return kind === "fan" ? "fan" : kind === "ac" ? "snow" : kind === "tv" ? "tv" : "bulb";
    }
    case "ac_set":
      return "snow";
    case "door_lock":
      return a.locked ? "lock" : "unlock";
    case "call_contact":
      return "phone";
    case "message_contact":
      return "message";
    case "cart_add":
    case "cart_order":
    case "cart_view":
      return "cart";
    case "say_for_me":
      return "speech";
    case "doorbell_reply":
      return "bell";
    case "phrasebook_add":
      return "book";
    case "home_status":
      return "home";
    default:
      return "spark";
  }
}

export function deviceIcon(kind: string): IconName {
  return kind === "fan" ? "fan" : kind === "ac" ? "snow" : kind === "tv" ? "tv" : "bulb";
}

export function capitalise(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

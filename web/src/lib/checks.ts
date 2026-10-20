/**
 * The gate's checks in plain words. Names come from the server's receipt and
 * refusal records (`checks: [{name, ok}]`); unknown names are shown as they are.
 */

import type { Check } from "./types";

interface CheckWords {
  /** What passing this check means. */
  label: string;
  /** Why it failed, in a few words. */
  failed: string;
}

export const CHECK_WORDS: Record<string, CheckWords> = {
  user_evidence_exists: { label: "Your own voice or tap", failed: "none given" },
  evidence_is_for_this_card_set: { label: "For these cards", failed: "it was for other cards" },
  card_set_exists: { label: "Real cards from SureSay", failed: "no such cards" },
  from_a_paired_device: { label: "Your paired device", failed: "not your paired device" },
  card_set_still_open: { label: "Cards still open", failed: "already answered" },
  card_set_not_expired: { label: "Still in time", failed: "timed out" },
  evidence_not_expired: { label: "Your answer is fresh", failed: "your answer is too old" },
  evidence_not_used: { label: "Your answer is new", failed: "already used" },
  user_words_choose_a_card: { label: "A clear choice", failed: "not a clear choice" },
  action_unchanged_since_shown: { label: "Exactly what you saw", failed: "the action changed" },
  action_is_registered_write: { label: "An action SureSay knows", failed: "unknown action" },
  nonce_consumed_once: { label: "Used once, never again", failed: "already used" },
  evidence_consumed_once: { label: "Your answer counted once", failed: "already counted" },
};

export function checkLabel(name: string): string {
  return CHECK_WORDS[name]?.label ?? name.replace(/_/g, " ");
}

export function checkFailure(name: string): string {
  return CHECK_WORDS[name]?.failed ?? "did not pass";
}

/** "001", "002", … */
export function trailNumber(i: number): string {
  return String(i + 1).padStart(3, "0");
}

/** One line of the readout as plain text, e.g. "001 Your own voice or tap ✗ — none given". */
export function trailLine(check: Check, i: number): string {
  return check.ok
    ? `${trailNumber(i)} ${checkLabel(check.name)} ✓`
    : `${trailNumber(i)} ${checkLabel(check.name)} ✗ — ${checkFailure(check.name)}`;
}

/** Milliseconds between ticks of the consent trail. */
export const TICK_MS = 120;

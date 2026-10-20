import { describe, expect, it } from "vitest";
import { CHECK_WORDS, checkFailure, checkLabel, trailLine, trailNumber } from "./checks";

/** Every check the gate can record (packages/confirm-gate-mcp gate.py, in order). */
const GATE_CHECKS = [
  "user_evidence_exists",
  "evidence_is_for_this_card_set",
  "card_set_exists",
  "from_a_paired_device",
  "card_set_still_open",
  "card_set_not_expired",
  "evidence_not_expired",
  "evidence_not_used",
  "user_words_choose_a_card",
  "action_unchanged_since_shown",
  "action_is_registered_write",
  "nonce_consumed_once",
  "evidence_consumed_once",
];

describe("consent trail wording", () => {
  it("has plain words for every gate check, passing and failing", () => {
    for (const name of GATE_CHECKS) {
      expect(CHECK_WORDS[name], name).toBeDefined();
      expect(checkLabel(name)).not.toMatch(/_/);
      expect(checkFailure(name).length).toBeGreaterThan(0);
    }
  });

  it("uses the agreed phrases", () => {
    expect(checkLabel("user_evidence_exists")).toBe("Your own voice or tap");
    expect(checkLabel("from_a_paired_device")).toBe("Your paired device");
    expect(checkLabel("card_set_not_expired")).toBe("Still in time");
    expect(checkLabel("nonce_consumed_once")).toBe("Used once, never again");
    expect(checkLabel("action_unchanged_since_shown")).toBe("Exactly what you saw");
  });

  it("numbers lines 001, 002 … and marks a failure with ✗ and a reason", () => {
    expect(trailNumber(0)).toBe("001");
    expect(trailNumber(11)).toBe("012");
    expect(trailLine({ name: "user_evidence_exists", ok: false }, 0)).toBe("001 Your own voice or tap ✗ — none given");
    expect(trailLine({ name: "card_set_not_expired", ok: true }, 5)).toBe("006 Still in time ✓");
  });

  it("shows an unknown check by its name rather than hiding it", () => {
    expect(checkLabel("brand_new_check")).toBe("brand new check");
  });
});

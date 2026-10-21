import { vi } from "vitest";
import type { HubApi } from "../lib/api";
import type { ConfirmChannel, ConfirmOutcome } from "../lib/mcp";
import type { HubState, PendingSet, Receipt } from "../lib/types";

export const NONCE = "NONCE-sEcReT-must-never-render-7f3a";

export function cardSet(overrides: Partial<PendingSet> = {}): PendingSet {
  return {
    pending_id: "p_test0001",
    state: "waiting_for_user",
    stage: "choose",
    origin: "user_words",
    options: [
      { n: 1, text: "Turn on the bedroom fan", action: "home_set", args: { device: "fan", on: true }, risk: "low" },
      { n: 2, text: "Turn on the TV", action: "home_set", args: { device: "tv", on: true }, risk: "low" },
      { n: 3, text: "Unlock the front door", action: "door_lock", args: { locked: false }, risk: "high" },
    ],
    expires_in_s: 110,
    nonce: NONCE,
    context: { heard: "van on", asr: "typed", ranker: "fuzzy", confidence: [0.82, 0.41, 0.12] },
    ...overrides,
  };
}

export function receipt(): Receipt {
  return {
    receipt_id: "rcpt_0123456789abcdef0123",
    what: { action: "home_set", args: { device: "tv", on: true }, shown_as: "Turn on the TV", risk: "low", origin: "user_words", options_shown: 3, option_chosen: 2 },
    who: { user_id: "demo", device_id: "d_test" },
    when: { proposed_at: "2026-10-20T10:00:00.000+00:00", evidence_at: "2026-10-20T10:00:03.000+00:00", confirmed_at: "2026-10-20T10:00:03.100+00:00", executed_at: "2026-10-20T10:00:03.100+00:00" },
    how: { channel: "tap", pending_id: "p_test0001", nonce_sha256: "abcdef123456" },
    evidence: { transcript: null, decision: { kind: "choose", option: 2, heard: "tap: 2" }, fingerprint: "f".repeat(64), media_ref: null },
    checks: [
      { name: "user_evidence_exists", ok: true },
      { name: "from_a_paired_device", ok: true },
      { name: "nonce_consumed_once", ok: true },
    ],
    result: { device: "tv", on: true },
    context: { heard: "van on" },
  };
}

export function hubState(pending: PendingSet[]): HubState {
  return {
    user_id: "demo",
    stats: { confirmed: 4, refused: 2, refused_from_assistant: 1, cancelled: 1, without_you: 0 },
    home: {
      devices: {
        living_lights: { name: "living room lights", room: "living room", kind: "light", on: false },
        fan: { name: "bedroom fan", room: "bedroom", kind: "fan", on: true },
        ac: { name: "air conditioner", room: "living room", kind: "ac", on: true, temperature: 24 },
        tv: { name: "TV", room: "living room", kind: "tv", on: false },
      },
      front_door: "locked",
      cart_items: 1,
    },
    cart: { items: [{ product_id: "milk", qty: 2, name: "Milk, 1 litre", line_total_inr: 136 }], total_inr: 136, orders: [] },
    receipts: [receipt()],
    events: [
      { type: "proposed", at: 1800000000, pending_id: "p_x", origin: "assistant", options: [{ n: 1, text: "Unlock the front door", action: "door_lock", risk: "high" }] },
      {
        type: "refused",
        at: 1800000001,
        pending_id: "p_x",
        reason: "no user evidence for this card set: only the user's own voice or tap on their paired device can confirm",
        caller: "agent",
        checks: [{ name: "user_evidence_exists", ok: false }],
      },
      { type: "evidence", at: 1800000002, pending_id: "p_y", channel: "tap", decision: { kind: "choose", option: 1, heard: "tap: 1" } },
      { type: "done", at: 1800000003, pending_id: "p_y", text: "Turn on the bedroom fan" },
    ],
    phrasebook: [
      { id: "ph_start00", phrase: "fan on", action: "home_set", args: { device: "fan", on: true } },
      { id: "ph_start18", phrase: "thank you", action: "say_for_me", args: { text: "Thank you so much." } },
      { id: "ph_9f1c2a7b3d", phrase: "my fan", action: "home_set", args: { device: "fan", on: true } },
    ],
    pending,
    spoken: [],
  };
}

export function fakeHub(pending: PendingSet[]) {
  const hub = {
    creds: { device_id: "d_test", user_id: "demo", key: "k", name: "test" },
    base: "",
    pending: vi.fn(async () => pending),
    turn: vi.fn(),
    evidenceTap: vi.fn(async (_set: PendingSet, answer: { option: number } | { answer: "yes" | "no" }) => ({
      evidence_ref: "ev_test",
      decision: "option" in answer ? { kind: "choose" as const, option: answer.option, heard: `tap: ${answer.option}` } : { kind: answer.answer, option: null, heard: `tap: ${answer.answer}` },
    })),
    evidenceVoice: vi.fn(),
    confirmRest: vi.fn(),
    speak: vi.fn(async () => {
      throw new Error("no voice in tests");
    }),
    state: vi.fn(async () => hubState(pending)),
    reset: vi.fn(async () => undefined),
    doorbell: vi.fn(async (visitor: string) => ({
      say: "Someone's at the door. Ravi, your carer, is at the front door with your shopping.",
      pending: cardSet({
        pending_id: "p_door",
        origin: "doorbell",
        options: [
          { n: 1, text: "Unlock the front door", action: "door_lock", args: { locked: false }, risk: "high" },
          { n: 2, text: "Tell them at the door: “I'm coming, please wait.”", action: "doorbell_reply", args: { text: "I'm coming, please wait." }, risk: "low" },
          { n: 3, text: "Call Ravi", action: "call_contact", args: { contact_id: "ravi" }, risk: "high" },
        ],
        context: { heard: "", source: "doorbell (simulated)", visitor: { id: visitor, name: "Ravi", who: "your carer", note: "Ravi, your carer, is at the front door with your shopping." } },
      }),
    })),
    help: vi.fn(async () => ({
      pending: cardSet({ pending_id: "p_help", options: [
        { n: 1, text: "Call Ravi", action: "call_contact", args: { contact_id: "ravi" }, risk: "low" },
        { n: 2, text: "Message Ravi: “I need help. Please come now.”", action: "message_contact", args: { contact_id: "ravi", text: "I need help. Please come now." }, risk: "high" },
      ], context: { heard: "", source: "help button" } }),
      say: "Do you want me to get help?",
    })),
    propose: vi.fn(async (action: string, args: Record<string, unknown>): Promise<PendingSet> => {
      const text = action === "say_for_me" ? `Say out loud: “${String(args.text)}”` : `Remember: “${String(args.phrase)}”`;
      return cardSet({ pending_id: "p_proposed", options: [{ n: 1, text, action, args, risk: "low" }], context: { heard: "", source: "tapped on device" } });
    }),
    signingFetch: vi.fn(),
  };
  return hub as typeof hub & HubApi;
}

export function fakeGate() {
  const gate = {
    status: "connected" as const,
    protocol: "2025-11-25",
    connect: vi.fn(async () => undefined),
    receiptsList: vi.fn(async () => [receipt()]),
    confirm: vi.fn(
      async (pending_id: string): Promise<ConfirmOutcome> => ({
        via: "mcp",
        result: { status: "done", pending_id, receipt: receipt(), message: "Done: Turn on the TV. Confirmed by your tap." },
      }),
    ),
  };
  return gate as typeof gate & ConfirmChannel;
}

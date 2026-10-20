/** Wire types for the SureSay hub. They mirror the Python server's JSON exactly. */

export type Risk = "low" | "high";
export type Origin = "user_words" | "assistant";
export type Stage = "choose" | "final";

export interface DeviceCreds {
  device_id: string;
  user_id: string;
  key: string;
  name: string;
}

export interface CardOption {
  n: number;
  text: string;
  action: string;
  args: Record<string, unknown>;
  risk: Risk;
}

/**
 * One open card set, as the device channel returns it. `nonce` is a one-time
 * secret: it is sent back with evidence and must never be rendered or logged.
 */
export interface PendingSet {
  pending_id: string;
  state: string;
  stage: Stage;
  origin: Origin;
  options: CardOption[];
  expires_in_s: number;
  nonce: string;
  context: {
    heard?: string;
    asr?: string;
    ranker?: string;
    confidence?: Array<number | null>;
  };
}

export interface Candidate extends CardOption {
  confidence: number | null;
}

export interface Timing {
  asr_ms?: number;
  rank_ms?: number;
  total_ms?: number;
}

export interface UnderstandResult {
  status: "choose" | "ask_again" | "answer";
  heard: string;
  asr: string;
  ranker: string;
  timing: Timing;
  say: string;
  candidates?: Candidate[];
  pending_id?: string;
  stage?: Stage;
  reason?: string;
  maybe?: Array<{ text: string; phrase: string }>;
  action?: string;
  result?: unknown;
}

export interface TurnResponse {
  reply: string;
  mode: "direct" | "agent";
  result: UnderstandResult | null;
  pending: PendingSet[];
  ms: number;
}

export type DecisionKind = "choose" | "yes" | "no" | "unclear";

export interface EvidenceResponse {
  evidence_ref: string;
  decision: { kind: DecisionKind; option: number | null; heard: string };
}

export interface Check {
  name: string;
  ok: boolean;
}

export interface Receipt {
  receipt_id: string;
  what: {
    action: string;
    args: Record<string, unknown>;
    shown_as: string;
    risk: Risk;
    origin: Origin;
    options_shown: number;
    option_chosen: number;
  };
  who: { user_id: string; device_id: string };
  when: { proposed_at: string | null; evidence_at: string | null; confirmed_at: string | null; executed_at: string | null };
  how: { channel: "voice" | "tap"; pending_id: string; nonce_sha256?: string };
  evidence: {
    transcript?: string | null;
    decision: { kind: DecisionKind; option: number | null; heard: string };
    fingerprint: string;
    media_ref?: string | null;
  };
  checks: Check[];
  result: unknown;
  context: { heard?: string };
}

export type ConfirmStatus = "done" | "needs_final_yes" | "refused" | "cancelled" | "failed";

export interface ConfirmResult {
  status: ConfirmStatus;
  message?: string;
  reason?: string;
  error?: string;
  receipt?: Receipt;
  pending_id: string;
  card?: Omit<PendingSet, "nonce" | "context">;
  result?: unknown;
  checks?: Check[];
}

export interface SpeakResponse {
  audio_b64: string;
  format: string;
  voice: string;
}

export interface HomeDevice {
  name: string;
  room: string;
  kind: string;
  on: boolean;
  temperature?: number;
}

export type EventType = "proposed" | "evidence" | "refused" | "cancelled" | "needs_final_yes" | "done" | "failed";

export interface GateEvent {
  type: EventType;
  at: number;
  pending_id?: string;
  reason?: string;
  error?: string;
  origin?: Origin;
  stage?: Stage;
  options?: Array<{ n: number; text: string; action: string; risk: Risk }>;
  decision?: { kind: DecisionKind; option: number | null; heard: string };
  transcript?: string | null;
  channel?: "voice" | "tap";
  caller?: string;
  text?: string;
  receipt_id?: string;
}

export interface Phrase {
  id: string;
  phrase: string;
  action: string;
  args: Record<string, unknown>;
}

export interface HubState {
  user_id: string;
  home: {
    devices: Record<string, HomeDevice>;
    front_door: "locked" | "unlocked";
    cart_items: number;
  };
  cart: {
    items: Array<{ product_id: string; qty: number; name: string; line_total_inr: number }>;
    total_inr: number;
    orders: unknown[];
  };
  receipts: Receipt[];
  events: GateEvent[];
  phrasebook: Phrase[];
  pending: PendingSet[];
  spoken: string[];
}

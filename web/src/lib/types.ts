/** Wire types for the SureSay hub. They mirror the Python server's JSON exactly. */

export type Risk = "low" | "high";
export type Origin = "user_words" | "assistant" | "doorbell";

/** Who rang the (simulated) doorbell. */
export interface Visitor {
  id: string;
  name: string;
  who: string;
  note: string;
}
export type Stage = "choose" | "final";

export interface DeviceCreds {
  device_id: string;
  user_id: string;
  key: string;
  name: string;
}

export interface PracticeState {
  today: string[];
  attempts: number;
  streak_days: number;
  days: Array<{ day: string; average: number; attempts: number }>;
  best: Record<string, number>;
  recent: Array<{ target: string; score: number; at: number }>;
}

export interface PracticeResult {
  score: number;
  words: Array<{ word: string; heard: boolean }>;
  heard: string;
  target: string;
  learned: boolean;
}

/** One of the user's paired devices or assistant links (never its key). */
export interface PairedDevice {
  device_id: string;
  name: string;
  kind: "screen" | "voice" | "link";
  paired_at?: number;
  this_device: boolean;
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
    /** The hub is not sure: these are "maybe" cards, offered after "please say it again". */
    unsure?: boolean;
    source?: string;
    visitor?: Visitor;
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
  /** Why it asks again: "negation" means a negated command, so nothing will change. */
  reason?: string;
  heard: string;
  asr: string;
  ranker: string;
  timing: Timing;
  say: string;
  candidates?: Candidate[];
  pending_id?: string;
  stage?: Stage;
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
  how: { channel: "voice" | "tap" | "transcript"; input?: TapInput | "voice"; pending_id: string; nonce_sha256?: string };
  evidence: {
    transcript?: string | null;
    decision: { kind: DecisionKind; option: number | null; heard: string };
    fingerprint: string;
    media_ref?: string | null;
    /** Who recognised the words for transcript evidence, e.g. "alexa". */
    transcriber?: string | null;
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
  input?: TapInput | null;
  channel?: "voice" | "tap" | "transcript";
  caller?: string;
  text?: string;
  receipt_id?: string;
  checks?: Check[];
}

export interface Phrase {
  id: string;
  phrase: string;
  action: string;
  args: Record<string, unknown>;
}

export interface HubStats {
  confirmed: number;
  refused: number;
  refused_from_assistant: number;
  cancelled: number;
  /** Always 0: every change has a receipt from the user's own device. */
  without_you: number;
}

export interface HubState {
  user_id: string;
  stats?: HubStats;
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

/** How a choice was made on the device; the receipt records it. */
export type TapInput = "touch" | "key" | "switch";

/** One live AI assistant turn: the model's reply, every MCP tool it called, and the last understand result. */
export interface AssistantTurn {
  reply: string;
  model: string;
  tool_calls: Array<{ name: string; args: Record<string, unknown>; result: Record<string, unknown> | null }>;
  understand: Record<string, unknown> | null;
  ms: number;
}

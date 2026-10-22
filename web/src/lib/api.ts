/** The device channel: pairing, turns, evidence, read-back and state. Every call but pairing is signed. */

import { hubUrl } from "./config";
import { createSigningFetch } from "./sign.js";
import type {
  ConfirmResult,
  DeviceCreds,
  EvidenceResponse,
  HubState,
  PairedDevice,
  PendingSet,
  PracticeResult,
  PracticeState,
  SpeakResponse,
  AssistantTurn,
  TapInput,
  TurnResponse,
} from "./types";

export class HubError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "HubError";
  }
}

/** What the UI needs from the hub. Tests pass a fake. */
export interface HubApi {
  readonly creds: DeviceCreds;
  readonly base: string;
  pending(): Promise<PendingSet[]>;
  /** One turn. purpose "say": sentences to say aloud to someone (Talk to someone), never an action on the home. */
  turn(input: { text?: string; audio_b64?: string; session_id: string; purpose?: "say" }): Promise<TurnResponse>;
  evidenceTap(set: PendingSet, answer: { option: number } | { answer: "yes" | "no" }, input?: TapInput): Promise<EvidenceResponse>;
  evidenceVoice(set: PendingSet, audio_b64: string): Promise<EvidenceResponse>;
  confirmRest(pending_id: string, evidence_ref: string): Promise<ConfirmResult>;
  speak(text: string): Promise<SpeakResponse>;
  state(): Promise<HubState>;
  reset(): Promise<void>;
  /** Open a card set from a tap (a speak-for-me tile, a taught phrase). The user still confirms it. */
  propose(action: string, args: Record<string, unknown>): Promise<PendingSet>;
  /** Simulated doorbell press: opens the door's card set (the user still confirms). */
  doorbell(visitor: "ravi" | "delivery" | "unknown"): Promise<{ pending: PendingSet; say: string }>;
  /** The Help button: a card set to call or message his carer. */
  help?(): Promise<{ pending: PendingSet; say: string }>;
  /** Practice: today's sentences and progress; and scoring one recording. */
  practiceState?(): Promise<PracticeState>;
  practiceSubmit?(target: string, audioB64: string): Promise<PracticeResult>;
  /** The user's own devices and assistant links. */
  devices?(): Promise<PairedDevice[]>;
  /** Unpair one of them (for an assistant link, that ends its access). */
  unpairDevice?(deviceId: string): Promise<void>;
  /** A one-time code that pairs another screen (e.g. an assistant's display) for this same user. */
  pairCode?(): Promise<string>;
  /** One live AI assistant turn (Amazon Nova 2 Sonic driving SureSay over MCP), when the hub offers it. */
  assistant?(text: string): Promise<AssistantTurn>;
  /** The signing fetch, for the MCP transport. */
  signingFetch: (input: string | URL | Request, init?: RequestInit) => Promise<Response>;
}

async function readError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { error?: unknown };
    if (data && typeof data.error === "string") return data.error;
  } catch {
    /* not JSON */
  }
  return res.statusText || `HTTP ${res.status}`;
}

function withTimeout(ms: number): { signal: AbortSignal; done: () => void } {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  return { signal: ctl.signal, done: () => clearTimeout(t) };
}

export async function pairDevice(base: string, code: string, name: string): Promise<DeviceCreds> {
  const res = await fetch(hubUrl("/device/pair", base).href, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ code, name }),
  });
  if (!res.ok) throw new HubError(res.status, await readError(res));
  const data = (await res.json()) as DeviceCreds;
  return { device_id: data.device_id, user_id: data.user_id, key: data.key, name: data.name };
}

/** Public facts about the hub (unsigned): is the public demo on? */
export async function hubInfo(base: string): Promise<{ public_demo?: boolean }> {
  try {
    const res = await fetch(hubUrl("/api/info", base).href);
    if (!res.ok) return {};
    return (await res.json()) as { public_demo?: boolean };
  } catch {
    return {};
  }
}

/** A private demo home for this visitor, paired at once (unsigned). 404: demo off. 429: too many from here. */
export async function tryDemo(base: string): Promise<DeviceCreds> {
  let res: Response;
  try {
    res = await fetch(hubUrl("/device/try", base).href, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  } catch {
    throw new HubError(0, "network");
  }
  if (!res.ok) throw new HubError(res.status, await readError(res));
  const data = (await res.json()) as DeviceCreds;
  return { device_id: data.device_id, user_id: data.user_id, key: data.key, name: data.name };
}

export function isGuest(userId: string | undefined): boolean {
  return !!userId && userId.startsWith("guest-");
}

export class HubClient implements HubApi {
  readonly signingFetch: HubApi["signingFetch"];

  constructor(
    readonly base: string,
    readonly creds: DeviceCreds,
  ) {
    this.signingFetch = createSigningFetch(creds, undefined, hubUrl("/", base).href);
  }

  private async call<T>(method: "GET" | "POST", path: string, body?: unknown, timeoutMs = 20000): Promise<T> {
    const t = withTimeout(timeoutMs);
    try {
      const res = await this.signingFetch(hubUrl(path, this.base).href, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
        headers: body === undefined ? undefined : { "content-type": "application/json" },
        signal: t.signal,
      });
      if (!res.ok) throw new HubError(res.status, await readError(res));
      return (await res.json()) as T;
    } catch (err) {
      if (err instanceof HubError) throw err;
      if (err instanceof DOMException && err.name === "AbortError") throw new HubError(0, "timed out");
      throw new HubError(0, "network");
    } finally {
      t.done();
    }
  }

  help(): Promise<{ pending: PendingSet; say: string }> {
    return this.call<{ pending: PendingSet; say: string }>("POST", "/device/help", {});
  }

  practiceState(): Promise<PracticeState> {
    return this.call<PracticeState>("GET", "/device/practice");
  }

  practiceSubmit(target: string, audioB64: string): Promise<PracticeResult> {
    return this.call<PracticeResult>("POST", "/device/practice", { target, audio_b64: audioB64 }, 60000);
  }

  async devices(): Promise<PairedDevice[]> {
    return (await this.call<{ devices: PairedDevice[] }>("GET", "/device/devices")).devices;
  }

  async unpairDevice(deviceId: string): Promise<void> {
    await this.call<{ ok: boolean }>("POST", "/device/unpair", { device_id: deviceId });
  }

  assistant(text: string): Promise<AssistantTurn> {
    return this.call<AssistantTurn>("POST", "/device/assistant", { text }, 60000);
  }

  async pairCode(): Promise<string> {
    return (await this.call<{ code: string }>("POST", "/device/pair-code", {})).code;
  }

  async pending(): Promise<PendingSet[]> {
    return (await this.call<{ pending: PendingSet[] }>("GET", "/device/pending")).pending;
  }

  turn(input: { text?: string; audio_b64?: string; session_id: string; purpose?: "say" }): Promise<TurnResponse> {
    return this.call<TurnResponse>("POST", "/device/turn", input, 60000);
  }

  evidenceTap(set: PendingSet, answer: { option: number } | { answer: "yes" | "no" }, input: TapInput = "touch"): Promise<EvidenceResponse> {
    return this.call<EvidenceResponse>("POST", "/device/evidence", {
      pending_id: set.pending_id,
      nonce: set.nonce,
      kind: "tap",
      input,
      ...answer,
    });
  }

  evidenceVoice(set: PendingSet, audio_b64: string): Promise<EvidenceResponse> {
    return this.call<EvidenceResponse>(
      "POST",
      "/device/evidence",
      { pending_id: set.pending_id, nonce: set.nonce, kind: "voice", audio_b64 },
      45000,
    );
  }

  confirmRest(pending_id: string, evidence_ref: string): Promise<ConfirmResult> {
    return this.call<ConfirmResult>("POST", "/device/confirm", { pending_id, evidence_ref });
  }

  speak(text: string): Promise<SpeakResponse> {
    return this.call<SpeakResponse>("POST", "/device/speak", { text }, 20000);
  }

  state(): Promise<HubState> {
    return this.call<HubState>("GET", "/device/state", undefined, 10000);
  }

  async reset(): Promise<void> {
    await this.call<{ ok: boolean }>("POST", "/device/reset", {});
  }

  async doorbell(visitor: "ravi" | "delivery" | "unknown"): Promise<{ pending: PendingSet; say: string }> {
    const out = await this.call<{ pending: PendingSet | null; say: string }>("POST", "/device/doorbell", { visitor });
    if (!out.pending) throw new HubError(409, "the card set is no longer open");
    return { pending: out.pending, say: out.say };
  }

  async propose(action: string, args: Record<string, unknown>): Promise<PendingSet> {
    const out = await this.call<{ pending: PendingSet | null }>("POST", "/device/propose", { action, args });
    if (!out.pending) throw new HubError(409, "the card set is no longer open");
    return out.pending;
  }
}

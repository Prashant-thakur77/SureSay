/**
 * The conversation: one request in, cards out, the user's own answer, a receipt.
 *
 * Every async step carries the id of the flow that started it. Starting a new
 * flow (a new request, a tap, a timeout) cancels speech and recording, and any
 * older step that finishes late is ignored. Cards always come from the hub's
 * pending record, never from the assistant's text.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { HubError, type HubApi } from "../lib/api";
import { MicError, micSupported } from "../lib/audio";
import type { ConfirmChannel } from "../lib/mcp";
import type { Speaker } from "../lib/speech";
import type { ConfirmResult, HubState, PendingSet, Receipt, TapInput, Timing } from "../lib/types";
import { playChime } from "../lib/sfx";
import { TICK_MS } from "../lib/checks";
import { announceChoices, isDoorbell, isUnsure, plainEvidenceError, plainReason, spokenChoices, spokenDoorbell, spokenUnsure } from "../lib/words";
import type { Politeness } from "./useAnnouncer";
import type { Settings } from "./useSettings";

export type AnswerState = "idle" | "listening" | "sending";

export type Phase =
  | { kind: "idle" }
  | { kind: "listening" }
  | { kind: "thinking"; typed?: string }
  | {
      kind: "cards";
      set: PendingSet;
      deadline: number;
      heard?: string;
      assistantLine?: string;
      answer: AnswerState;
      note?: string;
      heardAnswer?: string;
    }
  | { kind: "done"; receipt: Receipt; said?: string; atDoor?: string; heardAnswer?: string }
  | { kind: "cancelled" }
  | { kind: "ask_again"; heard?: string; maybe: Array<{ text: string; phrase: string }>; phrases: boolean }
  | { kind: "answer"; text: string; heard?: string; unchanged?: boolean }
  | { kind: "reply"; text: string }
  | { kind: "problem"; title: string; detail?: string; expired?: boolean };

export interface Debug {
  mode?: "direct" | "agent";
  asr?: string;
  ranker?: string;
  timing?: Timing;
  serverMs?: number;
  pendingId?: string;
  confirmVia?: "mcp" | "rest";
  fallbackReason?: string;
  lastRefusal?: string;
  lastRefusalChecks?: import("../lib/types").Check[];
  voice?: string;
}

export interface Recorder {
  record: () => Promise<import("../lib/audio").Recording | null>;
  stop: () => void;
  cancel: () => void;
}

export interface ConversationDeps {
  hub: HubApi;
  gate: ConfirmChannel;
  speaker: Speaker;
  recorder: Recorder;
  settings: Settings;
  announce: (message: string, level?: Politeness) => void;
  refreshState: () => Promise<HubState | null>;
  sessionId: string;
}

const ADOPTABLE: Phase["kind"][] = ["idle", "done", "cancelled", "answer", "reply", "problem"];

export const ASK_AGAIN_TEXT = "Sorry, I didn't catch that. Please say it again.";

function sayOf(result: unknown, receipt: Receipt): string | undefined {
  const r = result as { say?: unknown } | null | undefined;
  if (r && typeof r.say === "string") return r.say;
  const fromReceipt = receipt.result as { say?: unknown } | null | undefined;
  if (fromReceipt && typeof fromReceipt.say === "string") return fromReceipt.say;
  const t = receipt.what.args?.text;
  return typeof t === "string" ? t : undefined;
}

function atDoorOf(result: unknown, receipt: Receipt): string | undefined {
  for (const r of [result, receipt.result] as Array<{ said_at_door?: unknown } | null | undefined>) {
    if (r && typeof r.said_at_door === "string") return r.said_at_door;
  }
  const t = receipt.what.args?.text;
  return typeof t === "string" ? t : undefined;
}

export function useConversation(deps: ConversationDeps) {
  const [phase, setPhaseState] = useState<Phase>({ kind: "idle" });
  const [debug, setDebug] = useState<Debug>({});
  const phaseRef = useRef<Phase>(phase);
  const depsRef = useRef(deps);
  depsRef.current = deps;
  const flow = useRef(0);
  const handled = useRef(new Set<string>());

  const setPhase = useCallback((next: Phase | ((p: Phase) => Phase)) => {
    setPhaseState((prev) => {
      const value = typeof next === "function" ? next(prev) : next;
      phaseRef.current = value;
      return value;
    });
  }, []);

  const live = (id: number) => id === flow.current;

  const begin = useCallback(() => {
    flow.current += 1;
    depsRef.current.speaker.cancel();
    depsRef.current.recorder.cancel();
    return flow.current;
  }, []);

  const patchCards = useCallback(
    (id: number, pendingId: string, patch: Partial<Extract<Phase, { kind: "cards" }>>) => {
      setPhase((p) => (live(id) && p.kind === "cards" && p.set.pending_id === pendingId ? { ...p, ...patch } : p));
    },
    [setPhase],
  );

  const speak = useCallback(async (text: string, always = false) => {
    const { settings, speaker } = depsRef.current;
    if (!always && !settings.readAloud) return;
    await speaker.say(text);
    setDebug((d) => ({
      ...d,
      voice: speaker.lastSource === "hub" ? `hub (${speaker.lastVoice || "server voice"})` : speaker.lastSource === "browser" ? "browser voice" : "none",
    }));
  }, []);

  const problem = useCallback(
    (id: number, title: string, detail?: string, expired = false) => {
      if (!live(id)) return;
      setPhase({ kind: "problem", title, detail, expired });
      depsRef.current.announce(detail ? `${title} ${detail}` : title, "assertive");
    },
    [setPhase],
  );

  const networkProblem = useCallback(
    (id: number, err: unknown) => {
      if (err instanceof HubError && err.status === 401) {
        problem(id, "This device is no longer paired.", "Open Settings, choose Unpair, then pair again with a new code.");
      } else if (err instanceof HubError && err.status === 0) {
        problem(id, "I can't reach SureSay right now.", "Check that SureSay is running, then try again.");
      } else {
        problem(id, "Something went wrong.", "Nothing was changed. Please try again.");
      }
    },
    [problem],
  );

  // -- voice answers -------------------------------------------------------------------

  const listenForAnswer = useCallback(
    async (id: number, set: PendingSet) => {
      const { recorder, hub, announce } = depsRef.current;
      const final = set.stage === "final";
      patchCards(id, set.pending_id, { answer: "listening", note: undefined });
      announce(final ? "Listening. Say yes or no." : "Listening. Say a number.", "polite");
      let rec;
      try {
        rec = await recorder.record();
      } catch (err) {
        patchCards(id, set.pending_id, { answer: "idle", note: err instanceof MicError ? err.message : "The microphone could not start." });
        return;
      }
      if (!live(id)) return;
      if (!rec) {
        patchCards(id, set.pending_id, { answer: "idle" });
        return;
      }
      if (!rec.heardSpeech && rec.stoppedBy !== "user") {
        const note = final ? "I didn't hear an answer. Say yes or no, or tap a button." : "I didn't hear an answer. Say a number, or tap a card.";
        patchCards(id, set.pending_id, { answer: "idle", note });
        announce(note, "polite");
        return;
      }
      patchCards(id, set.pending_id, { answer: "sending" });
      try {
        const ev = await hub.evidenceVoice(set, rec.wavBase64);
        if (!live(id)) return;
        await handleEvidence(id, set, ev, "voice");
      } catch (err) {
        evidenceFailed(id, set, err);
      }
    },
    [patchCards],
  );

  const showSet = useCallback(
    (id: number, set: PendingSet, opts: { say?: string; heard?: string; assistantLine?: string } = {}) => {
      if (!live(id)) return;
      handled.current.add(set.pending_id);
      setPhase({
        kind: "cards",
        set,
        deadline: Date.now() + Math.max(0, set.expires_in_s) * 1000,
        heard: opts.heard ?? set.context?.heard,
        assistantLine: opts.assistantLine,
        answer: "idle",
      });
      setDebug((d) => ({ ...d, pendingId: set.pending_id }));
      depsRef.current.announce(announceChoices(set), "assertive");
      const say = isDoorbell(set) ? spokenDoorbell(set) : isUnsure(set) ? spokenUnsure(set) : (opts.say ?? spokenChoices(set));
      void (async () => {
        await speak(say);
        if (!live(id)) return;
        if (depsRef.current.settings.autoVoice && micSupported()) await listenForAnswer(id, set);
      })();
    },
    [listenForAnswer, setPhase, speak],
  );

  // -- confirming ----------------------------------------------------------------------

  const finishDone = useCallback(
    (id: number, r: ConfirmResult, heardAnswer?: string) => {
      if (!live(id) || !r.receipt) return;
      const receipt = r.receipt;
      const said = receipt.what.action === "say_for_me" ? sayOf(r.result, receipt) : undefined;
      const atDoor = receipt.what.action === "doorbell_reply" ? atDoorOf(r.result, receipt) : undefined;
      setPhase({ kind: "done", receipt, said, atDoor, heardAnswer });
      depsRef.current.announce(`Done: ${receipt.what.shown_as}.`, "assertive");
      const { settings } = depsRef.current;
      // the chime lands with the stamp; never in Calm mode, never when read-aloud is off, not over speech
      if (!said && !atDoor && settings.sounds && settings.readAloud && !settings.calm) {
        playChime(receipt.checks.length * TICK_MS + 180 + 280);
      }
      // the doorbell's speaker is simulated by this device's speaker
      if (atDoor) void speak(atDoor, true);
      else if (said) void speak(said, true);
      else void speak(`Done. ${receipt.what.shown_as}.`);
    },
    [setPhase, speak],
  );

  async function confirmWith(id: number, set: PendingSet, evidenceRef: string, heardAnswer?: string) {
    const { gate, hub, refreshState, announce } = depsRef.current;
    let out;
    try {
      out = await gate.confirm(set.pending_id, evidenceRef);
    } catch (err) {
      networkProblem(id, err);
      return;
    }
    if (!live(id)) return;
    setDebug((d) => ({ ...d, confirmVia: out.via, fallbackReason: out.fallbackReason }));
    const r = out.result;
    switch (r.status) {
      case "done":
        finishDone(id, r, heardAnswer);
        break;
      case "needs_final_yes": {
        let sets: PendingSet[] = [];
        try {
          sets = await hub.pending();
        } catch (err) {
          networkProblem(id, err);
          return;
        }
        const next = sets.find((s) => s.pending_id === r.pending_id);
        if (!live(id)) return;
        if (!next) {
          problem(id, "The second check is no longer open.", "Nothing was changed. Please say it again.", true);
          return;
        }
        showSet(id, next, { heard: set.context?.heard });
        break;
      }
      case "cancelled":
        setPhase({ kind: "cancelled" });
        announce("Cancelled. Nothing was changed.", "assertive");
        void speak("Cancelled. Nothing was changed.");
        break;
      case "refused": {
        setDebug((d) => ({ ...d, lastRefusal: r.reason, lastRefusalChecks: r.checks }));
        if (out.via === "rest" && /already been answered/i.test(r.reason ?? "")) {
          // the MCP call may have gone through before its reply was lost
          const st = await refreshState();
          const rc = st?.receipts.find((x) => x.how.pending_id === set.pending_id);
          if (rc) {
            finishDone(id, { status: "done", pending_id: set.pending_id, receipt: rc, result: rc.result }, heardAnswer);
            return;
          }
        }
        problem(id, "That was not allowed.", `${plainReason(r.reason)} Nothing was changed.`);
        break;
      }
      case "failed":
        problem(id, "That did not work.", r.message ?? r.error ?? "Please try again.");
        break;
      default:
        problem(id, "Something went wrong.", "Nothing was changed. Please try again.");
    }
    void refreshState();
  }

  async function handleEvidence(id: number, set: PendingSet, ev: import("../lib/types").EvidenceResponse, channel: "voice" | "tap") {
    const { announce } = depsRef.current;
    const d = ev.decision;
    if (channel === "voice") {
      patchCards(id, set.pending_id, { heardAnswer: d.heard });
      announce(`Heard: ${d.heard || "nothing"}`, "polite");
    }
    if (d.kind === "unclear") {
      const want =
        set.stage === "final"
          ? "Please say yes or no, or tap a button."
          : `Please say a number from 1 to ${set.options.length}, or tap a card.`;
      const note = d.heard ? `I heard “${d.heard}”. ${want}` : `I didn't catch a clear answer. ${want}`;
      patchCards(id, set.pending_id, { answer: "idle", note });
      announce(note, "assertive");
      void speak(want);
      return;
    }
    await confirmWith(id, set, ev.evidence_ref, channel === "voice" ? d.heard : undefined);
  }

  function evidenceFailed(id: number, set: PendingSet, err: unknown) {
    if (!live(id)) return;
    const { announce } = depsRef.current;
    if (err instanceof HubError && err.status === 409) {
      const { text, expired } = plainEvidenceError(err.message);
      if (expired || /already answered/.test(text)) {
        problem(id, text, expired ? undefined : "Nothing more was changed.", expired);
      } else {
        patchCards(id, set.pending_id, { answer: "idle", note: text });
        announce(text, "assertive");
      }
      return;
    }
    if (err instanceof HubError && err.status === 0) {
      const note = "I can't reach SureSay right now. Check that it is running, then try again.";
      patchCards(id, set.pending_id, { answer: "idle", note });
      announce(note, "assertive");
      return;
    }
    networkProblem(id, err);
  }

  // -- turns ---------------------------------------------------------------------------

  async function runTurn(id: number, input: { text?: string; audio_b64?: string; purpose?: "say" }) {
    const { hub, sessionId, refreshState, announce } = depsRef.current;
    let resp;
    try {
      resp = await hub.turn({ ...input, session_id: sessionId });
    } catch (err) {
      networkProblem(id, err);
      return;
    }
    if (!live(id)) return;
    const r = resp.result;
    setDebug((d) => ({
      ...d,
      mode: resp.mode,
      asr: r?.asr ?? resp.pending.at(-1)?.context?.asr,
      ranker: r?.ranker ?? resp.pending.at(-1)?.context?.ranker,
      timing: r?.timing,
      serverMs: resp.ms,
    }));
    if (r) {
      if (r.status === "choose") {
        let set = resp.pending.find((p) => p.pending_id === r.pending_id);
        if (!set) {
          try {
            set = (await hub.pending()).find((p) => p.pending_id === r.pending_id);
          } catch {
            set = undefined;
          }
        }
        if (!live(id)) return;
        if (set) showSet(id, set, { say: r.say, heard: r.heard });
        else problem(id, "The cards could not be shown.", "Please say it again.");
      } else if (r.status === "ask_again" && r.pending_id) {
        // not sure, but with "maybe" cards the user can still confirm
        let set = resp.pending.find((p) => p.pending_id === r.pending_id);
        if (!set) {
          try {
            set = (await hub.pending()).find((p) => p.pending_id === r.pending_id);
          } catch {
            set = undefined;
          }
        }
        if (!live(id)) return;
        if (set) showSet(id, { ...set, context: { ...set.context, unsure: true } }, { heard: r.heard });
        else {
          setPhase({ kind: "ask_again", heard: r.heard, maybe: r.maybe ?? [], phrases: false });
          announce(ASK_AGAIN_TEXT, "assertive");
          void speak(r.say || ASK_AGAIN_TEXT);
        }
      } else if (r.status === "ask_again" && r.reason === "negation") {
        // "don't unlock the door": no cards, and the screen says the same as the voice: nothing will change
        setPhase({ kind: "answer", text: r.say, heard: r.heard, unchanged: true });
        announce(r.say, "assertive");
        void speak(r.say);
      } else if (r.status === "ask_again") {
        setPhase({ kind: "ask_again", heard: r.heard, maybe: r.maybe ?? [], phrases: false });
        announce(ASK_AGAIN_TEXT, "assertive");
        void speak(r.say || ASK_AGAIN_TEXT);
      } else {
        setPhase({ kind: "answer", text: r.say, heard: r.heard });
        announce(r.say, "assertive");
        void speak(r.say);
      }
    } else {
      const fresh = resp.pending.filter((p) => !handled.current.has(p.pending_id));
      const set = fresh.at(-1);
      if (set) showSet(id, set, { assistantLine: resp.reply, heard: set.context?.heard });
      else {
        const text = resp.reply || "I have nothing to show yet.";
        setPhase({ kind: "reply", text });
        announce(text, "assertive");
        void speak(text);
      }
    }
    void refreshState();
  }

  const purposeRef = useRef<"say" | undefined>(undefined);
  const startRequest = useCallback(async (purpose?: "say") => {
    purposeRef.current = purpose;
    const { recorder, announce } = depsRef.current;
    const id = begin();
    setPhase({ kind: "listening" });
    announce("Listening. Tap the microphone again to stop.", "polite");
    let rec;
    try {
      rec = await recorder.record();
    } catch (err) {
      problem(id, err instanceof MicError ? err.message : "The microphone could not start.", "You can type instead.");
      return;
    }
    if (!live(id)) return;
    if (!rec) {
      setPhase({ kind: "idle" });
      return;
    }
    if (!rec.heardSpeech && rec.stoppedBy !== "user") {
      problem(id, "I didn't hear anything.", "Tap the microphone and try again, or type instead.");
      return;
    }
    setPhase({ kind: "thinking" });
    announce("Working it out.", "polite");
    await runTurn(id, { audio_b64: rec.wavBase64, ...(purpose ? { purpose } : {}) });
  }, [begin, problem, setPhase]);

  const sendText = useCallback(
    async (text: string, purpose?: "say") => {
      const clean = text.trim();
      if (!clean) return;
      purposeRef.current = purpose;
      const id = begin();
      setPhase({ kind: "thinking", typed: clean });
      depsRef.current.announce("Working it out.", "polite");
      await runTurn(id, { text: clean, ...(purpose ? { purpose } : {}) });
    },
    [begin, setPhase],
  );

  // -- answering by tap ----------------------------------------------------------------

  const tap = useCallback(
    async (answer: { option: number } | { answer: "yes" | "no" }, input: TapInput = "touch") => {
      const p = phaseRef.current;
      if (p.kind !== "cards" || p.answer === "sending") return;
      const set = p.set;
      const id = begin();
      patchCards(id, set.pending_id, { answer: "sending", note: undefined });
      try {
        const ev = await depsRef.current.hub.evidenceTap(set, answer, input);
        if (!live(id)) return;
        await handleEvidence(id, set, ev, "tap");
      } catch (err) {
        evidenceFailed(id, set, err);
      }
    },
    [begin, patchCards],
  );

  const choose = useCallback((n: number, input?: TapInput) => void tap({ option: n }, input), [tap]);
  // a one-card "choose" set (a tapped tile) takes option 1 as its yes
  const yes = useCallback((input?: TapInput) => {
    const p = phaseRef.current;
    void tap(p.kind === "cards" && p.set.stage === "choose" ? { option: 1 } : { answer: "yes" }, input);
  }, [tap]);
  const none = useCallback((input?: TapInput) => void tap({ answer: "no" }, input), [tap]);

  const answerByVoice = useCallback(() => {
    const p = phaseRef.current;
    if (p.kind !== "cards" || p.answer === "sending") return;
    const id = begin();
    void listenForAnswer(id, p.set);
  }, [begin, listenForAnswer]);

  /** The one microphone control: start, stop, or answer, depending on where we are. */
  const toggleMic = useCallback(() => {
    const p = phaseRef.current;
    if (p.kind === "listening" || (p.kind === "cards" && p.answer === "listening")) {
      depsRef.current.recorder.stop();
      return;
    }
    if (p.kind === "thinking" || (p.kind === "cards" && p.answer === "sending")) return;
    if (p.kind === "cards") answerByVoice();
    else void startRequest();
  }, [answerByVoice, startRequest]);

  const stopListening = useCallback(() => depsRef.current.recorder.cancel(), []);

  const expire = useCallback(
    (pendingId: string) => {
      const p = phaseRef.current;
      if (p.kind !== "cards" || p.set.pending_id !== pendingId) return;
      const id = begin();
      problem(id, "These cards timed out. Please say it again.", "Nothing was changed.", true);
    },
    [begin, problem],
  );

  const openPhrases = useCallback(
    (open: boolean) => setPhase((p) => (p.kind === "ask_again" ? { ...p, phrases: open } : p)),
    [setPhase],
  );

  const reset = useCallback(() => {
    begin();
    setPhase({ kind: "idle" });
  }, [begin, setPhase]);

  const replay = useCallback(() => {
    const p = phaseRef.current;
    if (p.kind === "done" && p.said) void speak(p.said, true);
    else if (p.kind === "answer" || p.kind === "reply") void speak(p.text, true);
    else if (p.kind === "done" && p.atDoor) void speak(p.atDoor, true);
    else if (p.kind === "cards") void speak(isDoorbell(p.set) ? spokenDoorbell(p.set) : isUnsure(p.set) ? spokenUnsure(p.set) : spokenChoices(p.set), true);
  }, [speak]);

  /** A tap on a speak-for-me tile or the Teach form: the hub opens a card set, confirmed like any other. */
  const propose = useCallback(
    async (action: string, args: Record<string, unknown>) => {
      const id = begin();
      setPhase({ kind: "thinking" });
      depsRef.current.announce("Getting it ready.", "polite");
      let set: PendingSet;
      try {
        set = await depsRef.current.hub.propose(action, args);
      } catch (err) {
        if (err instanceof HubError && err.status === 400) problem(id, "SureSay can't do that one.", "Please try a different choice.");
        else networkProblem(id, err);
        return;
      }
      if (!live(id)) return;
      showSet(id, set);
      void depsRef.current.refreshState();
    },
    [begin, networkProblem, problem, setPhase, showSet],
  );

  /** Someone rings the (simulated) doorbell: the door's cards appear, confirmed like any other. */
  const ring = useCallback(
    async (visitor: "ravi" | "delivery" | "unknown") => {
      const id = begin();
      setPhase({ kind: "thinking" });
      let out;
      try {
        out = await depsRef.current.hub.doorbell(visitor);
      } catch (err) {
        networkProblem(id, err);
        return;
      }
      if (!live(id)) return;
      showSet(id, out.pending);
      void depsRef.current.refreshState();
    },
    [begin, networkProblem, setPhase, showSet],
  );

  const help = useCallback(async () => {
    const { hub, announce } = depsRef.current;
    if (!hub.help) return;
    const id = begin();
    setPhase({ kind: "thinking" });
    announce("Getting help ready. You choose who to contact.", "assertive");
    let out;
    try {
      out = await hub.help();
    } catch (err) {
      networkProblem(id, err);
      return;
    }
    if (!live(id)) return;
    showSet(id, out.pending, { say: out.say });
    void depsRef.current.refreshState();
  }, [begin, networkProblem, setPhase, showSet]);

  /** Open card sets the hub knows about (for example, ones the assistant proposed) are shown when nothing else is. */
  const adoptPending = useCallback(
    (sets: PendingSet[] | undefined) => {
      if (!sets || sets.length === 0) return;
      if (!ADOPTABLE.includes(phaseRef.current.kind)) return;
      const fresh = sets.filter((s) => s.state === "waiting_for_user" && s.expires_in_s > 0 && !handled.current.has(s.pending_id));
      const set = fresh.at(-1);
      if (!set) return;
      const id = begin();
      showSet(id, set);
    },
    [begin, showSet],
  );

  /** Show this exact open card set now (a newer request made it): the phone follows the latest request. */
  const focusPending = useCallback(
    async (pendingId: string) => {
      const sets = await depsRef.current.hub.pending().catch(() => [] as PendingSet[]);
      const set = sets.find((x) => x.pending_id === pendingId && x.state === "waiting_for_user");
      if (!set) return;
      const id = begin();
      showSet(id, set);
    },
    [begin, showSet],
  );

  useEffect(
    () => () => {
      flow.current += 1;
      depsRef.current.speaker.cancel();
      depsRef.current.recorder.cancel();
    },
    [],
  );

  return {
    phase,
    debug,
    focusPending,
    toggleMic,
    startRequest,
    help,
    /** Ask again in the same mode as the last turn (Talk to someone stays Talk to someone). */
    again: () => startRequest(purposeRef.current),
    sendText,
    choose,
    yes,
    none,
    answerByVoice,
    stopListening,
    expire,
    openPhrases,
    reset,
    replay,
    adoptPending,
    propose,
    ring,
  };
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAnnouncer } from "../hooks/useAnnouncer";
import { useConversation, type Phase } from "../hooks/useConversation";
import { useHubState } from "../hooks/useHubState";
import { useRecorder } from "../hooks/useRecorder";
import { useScan, type ScanItem } from "../hooks/useScan";
import { tvFromUrl, type Settings } from "../hooks/useSettings";
import type { HubApi } from "../lib/api";
import type { ConfirmChannel } from "../lib/mcp";
import { randomHex } from "../lib/sign.js";
import type { Speaker } from "../lib/speech";
import type { Phrase } from "../lib/types";
import { Conversation, type ConversationActions } from "./Conversation";
import { Icon } from "./Icon";
import { LiveRegions } from "./LiveRegions";
import { ScanContext } from "./scan";
import { SettingsDialog } from "./SettingsDialog";
import { SidePanel, type McpInfo } from "./SidePanel";
import { TopBar } from "./TopBar";

interface Props {
  hub: HubApi;
  gate: ConfirmChannel;
  speaker: Speaker;
  settings: Settings;
  bigScreen: boolean;
  onSettingsChange: (patch: Partial<Settings>) => void;
  onUnpair: () => void;
  pollMs?: number;
}

function scanItems(phase: Phase, a: ConversationActions, phrasebook: Phrase[]): ScanItem[] {
  const mic: ScanItem = { id: "mic", label: "Microphone", activate: a.toggleMic };
  switch (phase.kind) {
    case "cards":
      if (phase.answer === "listening") return [{ id: "mic", label: "Stop listening", activate: a.toggleMic }];
      if (phase.set.stage === "final") {
        return [
          { id: "yes", label: `Yes: ${phase.set.options[0]?.text ?? ""}`, activate: a.yes },
          { id: "no", label: "No", activate: a.none },
        ];
      }
      return [
        ...phase.set.options.map((o) => ({ id: `card-${o.n}`, label: `${o.n}: ${o.text}`, activate: () => a.choose(o.n) })),
        { id: "none", label: "None of these", activate: a.none },
        { id: "again", label: "Say it again", activate: a.startRequest },
      ];
    case "ask_again":
      if (phase.phrases) {
        return [
          ...phrasebook.map((p) => ({ id: `phrase-${p.id}`, label: p.phrase, activate: () => a.sendText(p.phrase) })),
          { id: "phrases-close", label: "Close my phrases", activate: () => a.openPhrases(false) },
        ];
      }
      return [
        { id: "again", label: "Say it again", activate: a.startRequest },
        ...(phrasebook.length > 0 ? [{ id: "phrases", label: "Pick from my phrases", activate: () => a.openPhrases(true) }] : []),
      ];
    case "problem":
      return phase.expired
        ? [{ id: "again", label: "Say it again", activate: a.startRequest }]
        : [{ id: "start", label: "Start again", activate: a.reset }, mic];
    case "done":
      return phase.said ? [{ id: "replay", label: "Say it again out loud", activate: a.replay }, mic] : [mic];
    case "thinking":
      return [];
    case "listening":
      return [{ id: "mic", label: "Stop listening", activate: a.toggleMic }];
    default:
      return [mic];
  }
}

export function MainScreen({ hub, gate, speaker, settings, bigScreen, onSettingsChange, onUnpair, pollMs = 2000 }: Props) {
  const { assertive, polite, announce } = useAnnouncer();
  const { state, connection, refresh } = useHubState(hub, pollMs);
  const recorder = useRecorder();
  const sessionId = useMemo(() => `s_${randomHex(8)}`, []);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsBtn = useRef<HTMLButtonElement>(null);
  const [mcp, setMcp] = useState<McpInfo>({ status: gate.status, protocol: gate.protocol, receipts: null });

  const conv = useConversation({ hub, gate, speaker, recorder, settings, announce, refreshState: refresh, sessionId });
  const { phase } = conv;
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  // MCP: connect once, and list receipts to show the connection works
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await gate.connect();
        const receipts = await gate.receiptsList();
        if (alive) setMcp({ status: "connected", protocol: gate.protocol, receipts: receipts.length });
      } catch (err) {
        if (alive) setMcp({ status: "failed", protocol: null, receipts: null, error: err instanceof Error ? err.message : String(err) });
      }
    })();
    return () => {
      alive = false;
    };
  }, [gate]);

  // confirm may fall back to REST mid-session: keep the chip honest
  useEffect(() => {
    if (conv.debug.confirmVia === "rest") setMcp((m) => ({ ...m, status: "failed", error: conv.debug.fallbackReason }));
    else if (conv.debug.confirmVia === "mcp") setMcp((m) => (m.status === "connected" ? m : { ...m, status: "connected", protocol: gate.protocol }));
  }, [conv.debug.confirmVia, conv.debug.fallbackReason, gate]);

  // open card sets on the hub (e.g. proposed by the assistant) appear when the screen is free
  const { adoptPending } = conv;
  useEffect(() => {
    adoptPending(state?.pending);
  }, [state?.pending, adoptPending]);

  const actions: ConversationActions = {
    toggleMic: conv.toggleMic,
    startRequest: () => void conv.startRequest(),
    sendText: (t) => void conv.sendText(t),
    choose: conv.choose,
    yes: conv.yes,
    none: conv.none,
    stopListening: conv.stopListening,
    expire: conv.expire,
    openPhrases: conv.openPhrases,
    reset: conv.reset,
    replay: conv.replay,
  };
  const actionsRef = useRef(actions);
  actionsRef.current = actions;

  const phrasebook = state?.phrasebook ?? [];
  const items = settingsOpen ? [] : scanItems(phase, actions, phrasebook);
  const onHighlight = useCallback((label: string) => label && announce(label, "polite"), [announce]);
  const highlighted = useScan(items, settings.scan, settings.scanSpeed, onHighlight);

  // keyboard: Space = microphone, 1-3 = choose, Esc/N = none or no, Y = yes on the second check
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (settingsOpen || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      const target = e.target instanceof HTMLElement ? e.target : null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      const a = actionsRef.current;
      const p = phaseRef.current;
      if (e.key === " ") {
        if (target?.closest("button, a, summary, [role='button']")) return;
        e.preventDefault();
        a.toggleMic();
        return;
      }
      if (p.kind !== "cards") return;
      const key = e.key.toLowerCase();
      if (p.set.stage === "choose" && /^[1-9]$/.test(e.key)) {
        const n = Number(e.key);
        if (n <= p.set.options.length) {
          e.preventDefault();
          a.choose(n);
        }
        return;
      }
      if (e.key === "Escape" || key === "n") {
        e.preventDefault();
        a.none();
        return;
      }
      if (p.set.stage === "final" && key === "y") {
        e.preventDefault();
        a.yes();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [settingsOpen]);

  // everything behind the open dialog is inert (React 18 has no `inert` prop)
  const shellRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = shellRef.current;
    if (!el) return;
    if (settingsOpen) el.setAttribute("inert", "");
    else el.removeAttribute("inert");
  }, [settingsOpen]);

  const closeSettings = useCallback(() => setSettingsOpen(false), []);
  const resetHome = useCallback(async () => {
    await hub.reset();
    await refresh();
  }, [hub, refresh]);

  return (
    <ScanContext.Provider value={highlighted}>
      <div className={`app${settings.scan ? " app--scan" : ""}`}>
        <div className="app__shell" ref={shellRef}>
          <TopBar ref={settingsBtn} user={state?.user_id ?? hub.creds.user_id} mcp={mcp} onSettings={() => setSettingsOpen(true)} />
          {connection !== "ok" && (
            <div className={`banner ${connection === "unpaired" ? "banner--warn" : ""}`} role="status" data-scan-exempt>
              <Icon name="alert" size={24} />
              {connection === "unpaired" ? (
                <>
                  <span>This device is no longer paired.</span>
                  <button type="button" className="btn btn--secondary" onClick={onUnpair}>
                    Pair again
                  </button>
                </>
              ) : (
                <span>I can't reach SureSay right now. Check that it is running. I will keep trying.</span>
              )}
            </div>
          )}
          <div className="layout">
            <main id="main" className="stage" tabIndex={-1} aria-label="Conversation">
              <Conversation
                phase={phase}
                actions={actions}
                mic={recorder.mic}
                level={recorder.level}
                tv={bigScreen}
                devices={state?.home.devices}
                phrasebook={phrasebook}
                announce={(m) => announce(m, "polite")}
              />
              {settings.scan && (
                <p className="scan-note">
                  <Icon name="list" size={22} /> Scanning is on. Press any key or click to pick the highlighted item.
                </p>
              )}
            </main>
            <SidePanel state={state} debug={conv.debug} mcp={mcp} />
          </div>
        </div>
        <SettingsDialog
          open={settingsOpen}
          settings={settings}
          tvFromUrl={tvFromUrl()}
          onChange={onSettingsChange}
          onClose={closeSettings}
          onResetHome={resetHome}
          onUnpair={onUnpair}
        />
        <LiveRegions assertive={assertive} polite={polite} />
      </div>
    </ScanContext.Provider>
  );
}

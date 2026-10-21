import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAnnouncer } from "../hooks/useAnnouncer";
import { useConversation, type Phase } from "../hooks/useConversation";
import { useHubState } from "../hooks/useHubState";
import { useMotionOK } from "../hooks/useMotion";
import { useRecorder } from "../hooks/useRecorder";
import { useScan, type ScanItem } from "../hooks/useScan";
import { tvFromUrl, type Settings } from "../hooks/useSettings";
import { isGuest, type HubApi } from "../lib/api";
import type { ConfirmChannel } from "../lib/mcp";
import { randomHex } from "../lib/sign.js";
import type { Speaker } from "../lib/speech";
import { boardTiles } from "../lib/phrases";
import type { Phrase } from "../lib/types";
import { Conversation, type ConversationActions } from "./Conversation";
import { Icon } from "./Icon";
import { LiveRegions } from "./LiveRegions";
import { ScanContext } from "./scan";
import { SettingsDialog } from "./SettingsDialog";
import { SidePanel, type DoorInfo, type McpInfo } from "./SidePanel";
import type { VisitorId } from "./Doorbell";
import { readJson, writeJson } from "../lib/storage";
import { SpeakBoard } from "./SpeakBoard";
import { TabList, TabPanel, type TabDef } from "./Tabs";
import { TeachPanel } from "./TeachPanel";
import { TimelinePanel } from "./TimelinePanel";
import { TRY_EXAMPLES } from "./TryChips";
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

export type TabId = "talk" | "speak" | "timeline" | "teach";

const TABS: TabDef<TabId>[] = [
  { id: "talk", label: "Talk", icon: "mic" },
  { id: "speak", label: "Speak for me", icon: "speech" },
  { id: "timeline", label: "Timeline", icon: "clock" },
  { id: "teach", label: "Teach", icon: "book" },
];

function scanItems(phase: Phase, a: ConversationActions, phrasebook: Phrase[]): ScanItem[] {
  const mic: ScanItem = { id: "mic", label: "Microphone", activate: a.toggleMic };
  switch (phase.kind) {
    case "cards":
      if (phase.answer === "listening") return [{ id: "mic", label: "Stop listening", activate: a.toggleMic }];
      if (phase.set.context?.unsure) {
        return [
          { id: "again", label: "Say it again", activate: a.startRequest },
          ...phase.set.options.map((o) => ({ id: `card-${o.n}`, label: `Maybe ${o.n}: ${o.text}`, activate: () => a.choose(o.n) })),
          { id: "none", label: "None of these", activate: a.none },
        ];
      }
      if (phase.set.stage === "final" || phase.set.options.length === 1) {
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
    case "idle":
      return [mic, ...TRY_EXAMPLES.map((t, i) => ({ id: `try-${i}`, label: `Try: ${t.text}`, activate: () => a.sendText(t.text) }))];
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
  const [tab, setTab] = useState<TabId>("talk");
  const tabRef = useRef<TabId>("talk");
  tabRef.current = tab;
  const [sideOpen, setSideOpen] = useState(false);
  const motion = useMotionOK(settings.calm);
  const [speaking, setSpeaking] = useState(false);
  useEffect(() => {
    speaker.onSpeaking = setSpeaking;
    return () => {
      speaker.onSpeaking = undefined;
    };
  }, [speaker]);
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

  // any new card set is answered on the Talk tab
  const openSetId = phase.kind === "cards" ? phase.set.pending_id : "";
  useEffect(() => {
    if (openSetId) setTab("talk");
  }, [openSetId]);

  // the last visitor is remembered on this device (the hub's state has no doorbell history)
  const [lastVisitor, setLastVisitor] = useState<DoorInfo["visitor"]>(() => readJson<DoorInfo["visitor"]>("suresay.doorbell") ?? undefined);
  const visitorName = phase.kind === "cards" ? phase.set.context?.visitor?.name : undefined;
  useEffect(() => {
    if (!openSetId || !visitorName) return;
    const v = { name: visitorName, at: Date.now() / 1000 };
    setLastVisitor(v);
    writeJson("suresay.doorbell", v);
  }, [openSetId, visitorName]);
  const lastReply = state?.receipts.find((r) => r.what.action === "doorbell_reply");
  const door: DoorInfo = {
    visitor: lastVisitor,
    reply: lastReply
      ? { text: String((lastReply.result as { said_at_door?: unknown } | null)?.said_at_door ?? lastReply.what.args.text ?? ""), at: lastReply.when.executed_at }
      : undefined,
  };
  const ring = useCallback(
    (id: VisitorId) => {
      setTab("talk");
      void conv.ring(id);
    },
    [conv],
  );

  const proposeFromTab = useCallback(
    (action: string, args: Record<string, unknown>) => {
      setTab("talk");
      void conv.propose(action, args);
    },
    [conv],
  );

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
  const tabItems: ScanItem[] = TABS.filter((t) => t.id !== tab).map((t) => ({ id: `tab-${t.id}`, label: `${t.label} tab`, activate: () => setTab(t.id) }));
  const items: ScanItem[] = settingsOpen
    ? []
    : tab === "talk"
      ? scanItems(phase, actions, phrasebook)
      : tab === "speak"
        ? [...boardTiles(phrasebook).map((t) => ({ id: `tile-${t.key}`, label: `Say: ${t.title}`, activate: () => proposeFromTab("say_for_me", { text: t.text }) })), ...tabItems]
        : tabItems;
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
      if (tabRef.current !== "talk" || target?.closest("[role='tab']")) return;
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
      if ((p.set.stage === "final" || p.set.options.length === 1) && key === "y") {
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

  // guests get a slim note about the demo home, which they can hide
  const guest = isGuest(hub.creds.user_id);
  const [guestNote, setGuestNote] = useState(() => guest && readJson<boolean>("suresay.guestNoteHidden") !== true);
  const startOver = useCallback(async () => {
    conv.reset();
    try {
      await hub.reset();
      await refresh();
      announce("Your demo home is back to the start.", "polite");
    } catch {
      announce("I couldn't start over just now. Please try again.", "polite");
    }
  }, [conv, hub, refresh, announce]);

  const closeSettings = useCallback(() => setSettingsOpen(false), []);
  const resetHome = useCallback(async () => {
    await hub.reset();
    await refresh();
  }, [hub, refresh]);

  return (
    <ScanContext.Provider value={highlighted}>
      <div className={`app${settings.scan ? " app--scan" : ""}`}>
        <div className="app__shell" ref={shellRef}>
          {recorder.mic === "recording" && <div className="listen-bar" aria-hidden="true" />}
          <TopBar
            ref={settingsBtn}
            user={state?.user_id ?? hub.creds.user_id}
            mcp={mcp}
            onSettings={() => setSettingsOpen(true)}
            sideToggle={bigScreen ? { open: sideOpen, onToggle: () => setSideOpen((o) => !o) } : undefined}
          />
          {guestNote && (
            <div className="guest-note" role="region" aria-label="About this demo">
              <Icon name="spark" size={22} />
              <p>
                <strong>Demo home:</strong> the devices, contacts and shop are simulated. Try “van on”, the doorbell, or Speak for me.
              </p>
              <button type="button" className="linkish" onClick={() => void startOver()}>
                Start over
              </button>
              <button
                type="button"
                className="btn btn--icon guest-note__hide"
                aria-label="Hide the demo note"
                onClick={() => {
                  setGuestNote(false);
                  writeJson("suresay.guestNoteHidden", true);
                }}
              >
                <Icon name="close" size={22} />
              </button>
            </div>
          )}
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
          <div className={`layout${bigScreen && !sideOpen ? " layout--solo" : ""}`}>
            <main id="main" className="stage" tabIndex={-1} aria-label="SureSay">
              <TabList tabs={TABS} active={tab} onChange={setTab} label="SureSay" />
              <TabPanel id="talk" active={tab === "talk"}>
              <Conversation
                phase={phase}
                actions={actions}
                mic={recorder.mic}
                level={recorder.level}
                tv={bigScreen}
                devices={state?.home.devices}
                phrasebook={phrasebook}
                announce={(m) => announce(m, "polite")}
                speaking={speaking}
                history={!state || state.receipts.length > 0 || state.events.length > 0}
                motion={motion}
                onBackToBoard={() => setTab("speak")}
              />
              </TabPanel>
              <TabPanel id="speak" active={tab === "speak"}>
                <SpeakBoard phrasebook={phrasebook} busy={phase.kind === "thinking"} onSay={(text) => proposeFromTab("say_for_me", { text })} />
              </TabPanel>
              <TabPanel id="timeline" active={tab === "timeline"}>
                <TimelinePanel state={state} />
              </TabPanel>
              <TabPanel id="teach" active={tab === "teach"}>
                <TeachPanel phrasebook={phrasebook} busy={phase.kind === "thinking"} onTeach={(phrase, action, args) => proposeFromTab("phrasebook_add", { phrase, action, args })} />
              </TabPanel>
              {settings.scan && (
                <p className="scan-note">
                  <Icon name="list" size={22} /> Scanning is on. Press any key or click to pick the highlighted item.
                </p>
              )}
            </main>
            <SidePanel state={state} debug={conv.debug} mcp={mcp} hidden={bigScreen && !sideOpen} door={door} onRing={ring} />
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
          onRing={ring}
        />
        <LiveRegions assertive={assertive} polite={polite} />
      </div>
    </ScanContext.Provider>
  );
}

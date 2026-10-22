import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useFocusTrap } from "../hooks/useFocusTrap";
import type { Phase } from "../hooks/useConversation";
import { copyText } from "../lib/clipboard";
import type { McpHost } from "../lib/mcp";
import type { AssistantTurn } from "../lib/types";
import { Icon } from "./Icon";

/**
 * How SureSay looks inside Alexa+: this page plays the assistant's part. It calls SureSay's MCP server the way an
 * add-on host does (tools/call understand), reads the tool's UI resource (ui://suresay/cards.html) and renders it in
 * a sandboxed frame over the MCP Apps messages. The assistant only shows the cards: the yes comes from the user's own
 * device (the phone panel here, or this screen once it is paired as one of his devices).
 */

export const ALEXA_EXAMPLES = ["van on", "unlock the front door", "call mum", "i'm hot"];

interface Line {
  dir: "→" | "←" | "⇄" | "·";
  text: string;
}

interface Props {
  host: McpHost;
  phase: Phase;
  choose: (n: number) => void;
  yes: () => void;
  none: () => void;
  pairCode?: () => Promise<string>;
  /** One live AI assistant turn on the hub (Amazon Nova 2 Sonic driving SureSay's MCP tools). */
  assistant?: (text: string) => Promise<AssistantTurn>;
  /** A request made a new card set: the phone should show that one. */
  onNewSet?: (pendingId: string) => void;
  speak?: (text: string) => void;
  onClose: () => void;
}

type ToolResult = Awaited<ReturnType<McpHost["callToolRaw"]>>;

/** Wide enough for the side-by-side layout: the MCP log starts open there, folded on a phone. */
function wideScreen(): boolean {
  try {
    return window.matchMedia("(min-width: 60em)").matches;
  } catch {
    return false;
  }
}

function summary(result: ToolResult): { say: string; status: string; count: number } {
  const sc = (result.structuredContent ?? {}) as { say?: unknown; status?: unknown; candidates?: unknown };
  let data = sc;
  if (!("status" in sc)) {
    const text = result.content?.find((c) => c.type === "text")?.text;
    try {
      data = text ? (JSON.parse(text) as typeof sc) : sc;
    } catch {
      data = sc;
    }
  }
  const count = Array.isArray(data.candidates) ? data.candidates.length : 0;
  const status = typeof data.status === "string" ? data.status : "unknown";
  const say = typeof data.say === "string" && data.say ? data.say
    : status === "choose" ? `I found ${count} options. Choose on your screen or your phone.`
    : status === "ask_again" ? "I'm not sure. Please say it again." : "Done.";
  return { say, status, count };
}

export function AlexaView({ host, phase, choose, yes, none, pairCode, assistant, onNewSet, speak, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, true, onClose);
  const frame = useRef<HTMLIFrameElement>(null);
  const ready = useRef(false);
  const latest = useRef<ToolResult | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [height, setHeight] = useState(320);
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState("Try “Alexa, van on”.");
  const [wire, setWire] = useState(wideScreen);
  // who plays the assistant: the simple scripted host, or a real model (Amazon Nova 2 Sonic) when the hub offers it
  const [mode, setMode] = useState<"host" | "nova">("host");
  // the phone shows "done" only for an answer given since the last request
  const [showDone, setShowDone] = useState(false);
  useEffect(() => {
    if (phase.kind === "done") setShowDone(true);
  }, [phase.kind]);
  const log = useCallback((dir: Line["dir"], t: string) => setLines((l) => [...l.slice(-11), { dir, text: t }]), []);

  const post = useCallback((msg: unknown) => frame.current?.contentWindow?.postMessage(msg, "*"), []);
  const sendResult = useCallback(
    (result: ToolResult) => {
      post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { content: result.content, structuredContent: result.structuredContent } });
      log("→", "ui/notifications/tool-result (the cards' data, no secret)");
    },
    [post, log],
  );

  // the MCP Apps side of the host: answer the app's handshake, hand it the result, follow its size
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (!frame.current || e.source !== frame.current.contentWindow) return;
      const m = (e.data ?? {}) as { id?: number; method?: string; params?: { height?: number } };
      if (m.method === "ui/initialize" && m.id !== undefined) {
        post({ jsonrpc: "2.0", id: m.id, result: { protocolVersion: "2026-01-26", hostInfo: { name: "Alexa+ (simulated)", version: "1" },
          hostCapabilities: {}, hostContext: { theme: "dark", displayMode: "inline" } } });
        log("⇄", "ui/initialize");
      } else if (m.method === "ui/notifications/initialized") {
        ready.current = true;
        if (latest.current) sendResult(latest.current);
      } else if (m.method === "ui/notifications/size-changed" && typeof m.params?.height === "number") {
        setHeight(Math.max(200, Math.min(900, Math.ceil(m.params.height) + 8)));
      } else if (m.id !== undefined && m.method) {
        post({ jsonrpc: "2.0", id: m.id, error: { code: -32601, message: `${m.method} is not supported by this host` } });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [post, log, sendResult]);

  // when the user answers on their own device, the screen shows the outcome instead of stale cards
  const prevKind = useRef(phase.kind);
  useEffect(() => {
    const was = prevKind.current;
    prevKind.current = phase.kind;
    if (was !== "cards" || phase.kind === "cards" || !latest.current || !ready.current) return;
    const say = phase.kind === "done" ? "Done: confirmed by you, on your own device." : phase.kind === "cancelled" ? "Nothing was changed." : "";
    if (!say) return;
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { structuredContent: { status: "answer", say } } });
    log("→", `ui/notifications/tool-result (${phase.kind === "done" ? "done" : "cancelled"})`);
    setReply(say);
  }, [phase.kind, post, log]);

  // show one understand result on the Echo: the cards app (read once, then reused) and the short line
  const present = async (result: ToolResult) => {
    const s = summary(result);
    const pid = (result.structuredContent as { pending_id?: unknown } | undefined)?.pending_id;
    if (typeof pid === "string") onNewSet?.(pid);
    setShowDone(false);
    latest.current = result;
    if (!html) {
      const uri = await host.toolUi("understand");
      if (uri) {
        log("→", `resources/read ${uri}`);
        const page = await host.readUi(uri);
        log("←", `${uri} (${Math.round(page.length / 1024)} KB of HTML), rendered in a sandboxed frame`);
        ready.current = false;
        setHtml(page);
      }
    } else if (ready.current) {
      sendResult(result);
    }
    return s;
  };

  const ask = async (utterance: string) => {
    const clean = utterance.trim();
    if (!clean || busy) return;
    setBusy(true);
    setReply("…");
    log("·", `You: “Alexa, ${clean}”`);
    try {
      if (mode === "nova" && assistant) {
        log("→", "Amazon Nova 2 Sonic (Bedrock) takes the turn, with SureSay's MCP tools and the agent's powers");
        const out = await assistant(clean);
        for (const c of out.tool_calls) {
          const status = (c.result as { status?: unknown } | null)?.status;
          log("→", `Nova: tools/call ${c.name} ${JSON.stringify(c.args)}`);
          log("←", `${typeof status === "string" ? status : "ok"}${c.name === "confirm" ? " (only your device can confirm)" : ""}`);
        }
        // the newest card set, whichever tool made it (a door_lock after an ask-again understand is the door card)
        const shown = out.latest ?? out.understand;
        if (shown) {
          await present({ content: [{ type: "text", text: JSON.stringify(shown) }], structuredContent: shown });
        }
        log("←", `Nova replied in ${(out.ms / 1000).toFixed(1)} s`);
        setReply(out.reply || "Done.");
        speak?.(out.reply);
        return;
      }
      log("→", `tools/call understand {"transcript": "${clean}"}`);
      const result = await host.callToolRaw("understand", { user_id: "", transcript: clean });
      const waiting = Boolean((result.structuredContent as { pending_id?: unknown } | undefined)?.pending_id);
      const s = await present(result);
      log("←", `${s.status}${s.count ? `: ${s.count} cards` : ""}${waiting ? "; a card set now waits on your device" : "; nothing is waiting"}`);
      setReply(s.status === "choose" ? `I found ${s.count === 1 ? "one thing" : `${s.count} options`}. Choose on the screen, or on your phone.` : s.say);
      speak?.(s.say);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log("←", `error: ${msg}`);
      setReply(mode === "nova" ? `The live AI couldn't answer (${msg}). The simple host still works.` : "I couldn't reach SureSay just now.");
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(text);
    setText("");
  };

  const cards = phase.kind === "cards" && phase.answer !== "listening" ? phase.set : null;
  const final = cards && (cards.stage === "final" || cards.options.length === 1);

  return (
    <div className="alexa" role="dialog" aria-modal="true" aria-labelledby="alexa-title" ref={ref}>
      <header className="alexa__head">
        <h2 id="alexa-title" className="alexa__title">
          SureSay on a simulated <em>Alexa+</em> screen
        </h2>
        <p className="alexa__note">
          A simulated Alexa+ screen: this page plays the assistant, calling SureSay's real MCP server and showing its card app the way an add-on host
          does. The assistant can show the cards. Only your own device can say yes.
        </p>
        <button type="button" className="btn btn--secondary alexa__close" onClick={onClose}>
          <Icon name="close" size={24} /> Close
        </button>
      </header>

      <div className="alexa__stage">
        <section className="echo" aria-label="Echo Show screen (simulated)">
          <div className="echo__screen">
            <div className={`echo__bar${busy ? " echo__bar--busy" : ""}`} aria-hidden="true" />
            <p className="echo__reply" aria-live="polite">
              <span className="visually-hidden">Alexa: </span>
              {reply}
            </p>
            {html ? (
              <iframe
                ref={frame}
                className="echo__app"
                title="SureSay cards (MCP App)"
                sandbox="allow-scripts allow-forms"
                srcDoc={html}
                style={{ height }}
              />
            ) : (
              <p className="echo__idle">Ask for something. SureSay's cards will appear here.</p>
            )}
          </div>
          {assistant && (
            <fieldset className="echo__mode">
              <legend>Who plays the assistant?</legend>
              <label>
                <input type="radio" name="alexa-mode" checked={mode === "host"} onChange={() => setMode("host")} disabled={busy} />
                A simple scripted host
              </label>
              <label>
                <input type="radio" name="alexa-mode" checked={mode === "nova"} onChange={() => setMode("nova")} disabled={busy} />
                Amazon Nova 2 Sonic, a live AI
              </label>
            </fieldset>
          )}
          <form className="echo__ask" onSubmit={submit} aria-label="Talk to Alexa">
            <label htmlFor="alexa-input" className="echo__wake">
              Alexa,
            </label>
            <input id="alexa-input" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="van on" autoComplete="off" disabled={busy} />
            <button type="submit" className="btn btn--primary" disabled={busy}>
              <Icon name="send" size={22} /> Ask
            </button>
          </form>
          <div className="echo__chips" role="group" aria-label="Examples">
            {ALEXA_EXAMPLES.map((x) => (
              <button key={x} type="button" className="btn btn--secondary btn--chip" disabled={busy} onClick={() => void ask(x)}>
                “{x}”
              </button>
            ))}
          </div>
        </section>

        <aside className="alexa__side">
          <section className="phone" aria-labelledby="phone-title">
            <h3 id="phone-title" className="phone__title">
              <Icon name="phone" size={22} /> Your phone: only you can say yes
            </h3>
            {cards ? (
              <>
                <ol className="phone__cards">
                  {cards.options.map((o) => (
                    <li key={o.n}>
                      <button type="button" className={`phone__card${final ? " phone__card--yes" : ""}`} onClick={() => (final ? yes() : choose(o.n))}>
                        <span className="phone__n" aria-hidden="true">{final ? <Icon name="check" size={22} /> : o.n}</span>
                        <span>{final ? `Yes: ${o.text}` : o.text}</span>
                      </button>
                    </li>
                  ))}
                </ol>
                <button type="button" className="btn btn--secondary phone__none" onClick={() => none()}>
                  <Icon name="close" size={24} /> {final ? "No" : "None of these"}
                </button>
              </>
            ) : (
              <p className="phone__idle">
                {phase.kind === "done" && showDone ? "Done, confirmed by you. The receipt is in your timeline." : phase.kind === "thinking" ? "Checking…" : "Nothing is waiting for you."}
              </p>
            )}
            {pairCode && <PairThisScreen pairCode={pairCode} />}
          </section>

          <details className="wire" open={wire} onToggle={(e) => setWire(e.currentTarget.open)}>
            <summary className="wire__title">
              <span>What Alexa+ and SureSay say to each other (MCP)</span>
              <span className="wire__count">{lines.length === 1 ? "1 message" : `${lines.length} messages`}</span>
            </summary>
            <ol className="wire__log" aria-live="off">
              {lines.length === 0 && <li className="wire__empty">Nothing yet.</li>}
              {lines.map((l, i) => (
                <li key={i}>
                  <span className="wire__dir" aria-hidden="true">{l.dir}</span> {l.text}
                </li>
              ))}
            </ol>
            <p className="wire__foot">The one-time code that releases a card set never appears here: it goes only to your devices.</p>
          </details>
        </aside>
      </div>
    </div>
  );
}

/**
 * Pairing the Echo screen as one of his devices: a big code to read across the room, a copy button, and the three
 * steps. The code is a pairing code (it lasts ten minutes), not the one-time code that releases a card set.
 */
function PairThisScreen({ pairCode }: { pairCode: () => Promise<string> }) {
  const [code, setCode] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");
  const [copied, setCopied] = useState(false);
  const get = () => {
    setState("busy");
    setCopied(false);
    pairCode()
      .then((c) => {
        setCode(c);
        setState("idle");
      })
      .catch(() => setState("failed"));
  };
  const copy = async () => setCopied(code ? await copyText(code) : false);
  return (
    <section className="pairbox" aria-labelledby="pairbox-title">
      <h4 id="pairbox-title" className="pairbox__title">
        Pair this screen
      </h4>
      {code ? (
        <>
          <ol className="pairbox__steps">
            <li>On the Echo screen, open SureSay.</li>
            <li>Choose “I have a pairing code”.</li>
            <li>Type this code:</li>
          </ol>
          <p className="pairbox__code" aria-label={`Pairing code: ${code.split("").join(" ")}`}>
            {code}
          </p>
          <div className="pairbox__actions">
            <button type="button" className="btn btn--primary" onClick={() => void copy()}>
              <Icon name={copied ? "check" : "copy"} size={22} /> {copied ? "Copied" : "Copy code"}
            </button>
            <button type="button" className="btn btn--secondary" onClick={get} disabled={state === "busy"}>
              <Icon name="refresh" size={22} /> New code
            </button>
          </div>
          <p className="pairbox__note">It lasts ten minutes. Once paired, a tap on that screen counts as yours too.</p>
        </>
      ) : (
        <>
          <p className="pairbox__note">Make the Echo screen one of your devices, so you can say yes there too.</p>
          <button type="button" className="btn btn--secondary" onClick={get} disabled={state === "busy"}>
            <Icon name="phone" size={22} /> {state === "busy" ? "Getting a code…" : "Get a pairing code"}
          </button>
        </>
      )}
      <p className="visually-hidden" aria-live="polite">
        {copied ? "Code copied." : ""}
      </p>
      {state === "failed" && (
        <p className="pairbox__error" role="alert">
          I couldn't get a code just now. Please try again.
        </p>
      )}
    </section>
  );
}

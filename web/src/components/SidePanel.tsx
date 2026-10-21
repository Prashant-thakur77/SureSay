import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { Debug } from "../hooks/useConversation";
import type { McpStatus } from "../lib/mcp";
import type { HubState } from "../lib/types";
import { capitalise, channelWords, describeEvents, deviceIcon, timeOf } from "../lib/words";
import { Icon } from "./Icon";
import { TrailLines } from "./ConsentTrail";
import { DoorbellMenu, type VisitorId } from "./Doorbell";
import { Checks, shortId } from "./ReceiptCard";

function wide(): boolean {
  try {
    return typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 64em)").matches;
  } catch {
    return true;
  }
}

function Panel({ id, title, icon, children, defaultOpen }: { id: string; title: string; icon: Parameters<typeof Icon>[0]["name"]; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(() => defaultOpen ?? wide());
  const bodyId = useId();
  return (
    <section className="panel" id={`panel-${id}`} aria-labelledby={`${bodyId}-h`}>
      <h2 className="panel__title" id={`${bodyId}-h`}>
        <button type="button" className="panel__toggle" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((o) => !o)}>
          <Icon name={icon} size={26} />
          <span>{title}</span>
          <Icon name="chevron" size={24} className={open ? "chev chev--open" : "chev"} />
        </button>
      </h2>
      <div id={bodyId} className="panel__body" hidden={!open}>
        {children}
      </div>
    </section>
  );
}

/** A lock whose shackle lifts when unlocked (moves only when motion is allowed). */
function LockIcon({ locked }: { locked: boolean }) {
  return (
    <svg className={`lock-icon${locked ? "" : " lock-icon--open"}`} width="100%" height="100%" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <rect x="4.5" y="10.5" width="15" height="10.5" rx="2" />
      <path className="lock-icon__shackle" d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
      <path d="M12 14.5v3" />
    </svg>
  );
}

export interface DoorInfo {
  visitor?: { name: string; at: number };
  reply?: { text: string; at: string | null };
}

function HomePanel({ state, door }: { state: HubState | null; door?: DoorInfo }) {
  const listRef = useRef<HTMLUListElement>(null);
  const before = useRef<Record<string, boolean> | null>(null);
  const [changed, setChanged] = useState<string[]>([]);
  const devices = state ? Object.entries(state.home.devices) : [];
  const unlocked = state?.home.front_door === "unlocked";
  const snapshot = state ? JSON.stringify([devices.map(([id, d]) => [id, d.on]), unlocked]) : "";

  // a device that changed state pulses once and scrolls into view (if this panel is open)
  useEffect(() => {
    if (!state) return;
    const now: Record<string, boolean> = Object.fromEntries(devices.map(([id, d]) => [id, d.on]));
    now.front_door = !unlocked;
    const prev = before.current;
    before.current = now;
    if (!prev) return;
    const flipped = Object.keys(now).filter((k) => k in prev && prev[k] !== now[k]);
    if (flipped.length === 0) return;
    setChanged(flipped);
    const list = listRef.current;
    const tile = list?.querySelector<HTMLElement>(`[data-device="${flipped[0]}"]`);
    if (tile && list && list.offsetParent !== null) {
      const smooth = document.documentElement.dataset.calm !== "1" && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      tile.scrollIntoView?.({ block: "nearest", behavior: smooth ? "smooth" : "auto" });
    }
    const t = setTimeout(() => setChanged([]), 1600);
    return () => clearTimeout(t);
  }, [snapshot]);

  if (!state) return <p className="muted">Loading your home…</p>;
  return (
    <ul className="tiles" ref={listRef}>
      {devices.map(([id, d]) => (
        <li key={id} data-device={id} data-kind={d.kind} className={`tile${d.on ? " tile--on" : ""}${changed.includes(id) ? " tile--changed" : ""}`}>
          <span className="tile__icon" aria-hidden="true">
            <Icon name={deviceIcon(d.kind)} size="100%" />
          </span>
          <span className="tile__name">{capitalise(d.name)}</span>
          <span className="tile__room">{capitalise(d.room)}</span>
          <span className={`pill ${d.on ? "pill--on" : "pill--off"}`}>
            {d.on ? "On" : "Off"}
            {d.kind === "ac" && d.on && typeof d.temperature === "number" ? ` · ${d.temperature}°` : ""}
          </span>
        </li>
      ))}
      <li data-device="front_door" data-kind="lock" className={`tile${unlocked ? " tile--warn" : ""}${changed.includes("front_door") ? " tile--changed" : ""}`}>
        <span className="tile__icon" aria-hidden="true">
          <LockIcon locked={!unlocked} />
        </span>
        <span className="tile__name">Front door</span>
        <span className="tile__room">Entrance</span>
        <span className={`pill ${unlocked ? "pill--warn" : "pill--on"}`}>{unlocked ? "Unlocked" : "Locked"}</span>
        {(door?.visitor || door?.reply) && (
          <span className="tile__door">
            {door.visitor && (
              <span>
                Last visitor: <strong>{door.visitor.name}</strong> · {timeOf(door.visitor.at)}
              </span>
            )}
            {door.reply && <span>Last reply: “{door.reply.text}”</span>}
          </span>
        )}
      </li>
    </ul>
  );
}

function CartPanel({ state }: { state: HubState | null }) {
  if (!state) return <p className="muted">Loading your cart…</p>;
  const { items, total_inr, orders } = state.cart;
  return (
    <div className="cart">
      {items.length === 0 ? (
        <p>Your cart is empty.</p>
      ) : (
        <>
          <ul className="cart__list">
            {items.map((i) => (
              <li key={i.product_id}>
                <span>
                  {i.qty} × {i.name}
                </span>
                <span className="cart__price">₹{i.line_total_inr}</span>
              </li>
            ))}
          </ul>
          <p className="cart__total">
            <span>Total</span> <span>₹{total_inr}</span>
          </p>
        </>
      )}
      <p className="muted">Orders placed: {orders.length}</p>
    </div>
  );
}

function ReceiptsPanel({ state }: { state: HubState | null }) {
  if (!state) return <p className="muted">Loading receipts…</p>;
  if (state.receipts.length === 0) return <p>No receipts yet. Each thing you confirm leaves one here.</p>;
  return (
    <ul className="receipts">
      {state.receipts.slice(0, 6).map((r) => (
        <li key={r.receipt_id} className="receipts__item">
          <p className="receipts__what">
            <Icon name="check" size={22} /> {r.what.shown_as}
          </p>
          <p className="muted">
            By {channelWords(r)}
            {timeOf(r.when.executed_at) ? `, ${timeOf(r.when.executed_at)}` : ""} · <code>{shortId(r.receipt_id)}</code>
          </p>
          {r.what.origin === "assistant" && <p className="receipts__assist">Suggested by the assistant</p>}
          <Checks receipt={r} />
        </li>
      ))}
    </ul>
  );
}

function ActivityPanel({ state }: { state: HubState | null }) {
  if (!state) return <p className="muted">Loading activity…</p>;
  const lines = describeEvents(state.events).slice(0, 14);
  if (lines.length === 0) return <p>Nothing has happened yet.</p>;
  return (
    <ol className="activity">
      {lines.map((l) => (
        <li key={l.key} className={`activity__item activity__item--${l.tone}`}>
          {l.tone === "warn" && <Icon name="alert" size={22} className="activity__icon" />}
          {l.tone === "ok" && <Icon name="check" size={22} className="activity__icon" />}
          <span className="activity__text">
            <strong>{l.label}:</strong> {l.text}
          </span>
          <span className="activity__time">{timeOf(l.at)}</span>
        </li>
      ))}
    </ol>
  );
}

export interface McpInfo {
  status: McpStatus;
  protocol: string | null;
  receipts: number | null;
  error?: string;
}

/** The newest refusal with its checks: this device's own, or the gate's latest (for example the assistant's). */
function lastRefusal(debug: Debug, events: HubState["events"] | undefined): { reason?: string; checks: NonNullable<Debug["lastRefusalChecks"]>; who: string } | null {
  const ev = [...(events ?? [])].reverse().find((e) => e.type === "refused" && e.checks && e.checks.length > 0);
  if (ev?.checks) {
    const who = ev.caller === "agent" ? "the assistant" : ev.caller?.startsWith("device:") ? "a paired device" : "an unknown caller";
    return { reason: ev.reason, checks: ev.checks, who };
  }
  if (debug.lastRefusalChecks && debug.lastRefusalChecks.length > 0) return { reason: debug.lastRefusal, checks: debug.lastRefusalChecks, who: "this device" };
  return null;
}

export function UnderTheHood({ debug, mcp, events, onRing }: { debug: Debug; mcp: McpInfo; events?: HubState["events"]; onRing?: (id: VisitorId) => void }) {
  const refusal = lastRefusal(debug, events);
  const t = debug.timing;
  const timing = t ? [t.asr_ms != null && `ASR ${t.asr_ms} ms`, t.rank_ms != null && `rank ${t.rank_ms} ms`, t.total_ms != null && `total ${t.total_ms} ms`].filter(Boolean).join(" · ") : "";
  const rows: Array<[string, ReactNode]> = [
    ["Turn mode", debug.mode ?? "—"],
    ["Speech recogniser", debug.asr ?? "—"],
    ["Ranker", debug.ranker ?? "—"],
    ["Timing", timing || "—"],
    ["Server time", debug.serverMs != null ? `${debug.serverMs} ms` : "—"],
    ["Card set", debug.pendingId ? <code>{debug.pendingId}</code> : "—"],
    [
      "Confirm went through",
      debug.confirmVia === "mcp" ? "MCP tool “confirm”" : debug.confirmVia === "rest" ? "REST /device/confirm (MCP fallback)" : "—",
    ],
    ["MCP", mcp.status === "connected" ? `connected${mcp.protocol ? `, protocol ${mcp.protocol}` : ""}${mcp.receipts != null ? `, receipts_list gave ${mcp.receipts}` : ""}` : mcp.status === "connecting" ? "connecting" : `not connected${mcp.error ? ` (${mcp.error})` : ""}`],
    ["Read-back voice", debug.voice ?? "—"],
    ["Last refusal", refusal?.reason ?? debug.lastRefusal ?? "—"],
  ];
  return (
    <>
      {debug.confirmVia === "rest" && (
        <p className="callout callout--warn">
          <Icon name="alert" size={22} /> <span>MCP fallback: confirmed over REST. {debug.fallbackReason}</span>
        </p>
      )}
      <dl className="hood" data-testid="under-the-hood">
        {rows.map(([k, v]) => (
          <div key={k} className="hood__row">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {onRing && (
        <div className="hood__demo">
          <DoorbellMenu onRing={onRing} label="Doorbell" />
        </div>
      )}
      {refusal && (
        <div className="trail trail--refusal" data-testid="refusal-trail">
          <p className="trail__head">
            <span>Refused</span>
            <span className="trail__meta">asked by {refusal.who}</span>
          </p>
          <TrailLines checks={refusal.checks} />
          <p className="trail__foot">Nothing was changed.</p>
        </div>
      )}
    </>
  );
}

export function SidePanel({ state, debug, mcp, hidden = false, door, onRing }: { state: HubState | null; debug: Debug; mcp: McpInfo; hidden?: boolean; door?: DoorInfo; onRing?: (id: VisitorId) => void }) {
  return (
    <aside className="side" id="side-panel" aria-label="Your home and history" hidden={hidden}>
      <nav aria-label="Side panels" className="side__nav">
        <ul>
          <li>
            <a href="#panel-home">Home</a>
          </li>
          <li>
            <a href="#panel-cart">Cart</a>
          </li>
          <li>
            <a href="#panel-receipts">Receipts</a>
          </li>
          <li>
            <a href="#panel-activity">Activity</a>
          </li>
        </ul>
      </nav>
      <Panel id="home" title="Home" icon="home">
        <HomePanel state={state} door={door} />
      </Panel>
      <Panel id="cart" title="Cart" icon="cart">
        <CartPanel state={state} />
      </Panel>
      <Panel id="receipts" title="Receipts" icon="shield">
        <ReceiptsPanel state={state} />
      </Panel>
      <Panel id="activity" title="Activity" icon="list">
        <ActivityPanel state={state} />
      </Panel>
      <Panel id="hood" title="Under the hood" icon="gear" defaultOpen={false}>
        <UnderTheHood debug={debug} mcp={mcp} events={state?.events} onRing={onRing} />
      </Panel>
    </aside>
  );
}

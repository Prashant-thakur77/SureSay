import { useId, useState, type ReactNode } from "react";
import type { Debug } from "../hooks/useConversation";
import type { McpStatus } from "../lib/mcp";
import type { HubState } from "../lib/types";
import { capitalise, channelWords, describeEvents, deviceIcon, timeOf } from "../lib/words";
import { Icon } from "./Icon";
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

function HomePanel({ state }: { state: HubState | null }) {
  if (!state) return <p className="muted">Loading your home…</p>;
  const devices = Object.entries(state.home.devices);
  const unlocked = state.home.front_door === "unlocked";
  return (
    <ul className="tiles">
      {devices.map(([id, d]) => (
        <li key={id} className={`tile${d.on ? " tile--on" : ""}`}>
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
      <li className={`tile${unlocked ? " tile--warn" : ""}`}>
        <span className="tile__icon" aria-hidden="true">
          <Icon name={unlocked ? "unlock" : "lock"} size="100%" />
        </span>
        <span className="tile__name">Front door</span>
        <span className="tile__room">Entrance</span>
        <span className={`pill ${unlocked ? "pill--warn" : "pill--on"}`}>{unlocked ? "Unlocked" : "Locked"}</span>
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

export function UnderTheHood({ debug, mcp }: { debug: Debug; mcp: McpInfo }) {
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
    ["Last refusal", debug.lastRefusal ?? "—"],
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
    </>
  );
}

export function SidePanel({ state, debug, mcp }: { state: HubState | null; debug: Debug; mcp: McpInfo }) {
  return (
    <aside className="side" aria-label="Your home and history">
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
        <HomePanel state={state} />
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
        <UnderTheHood debug={debug} mcp={mcp} />
      </Panel>
    </aside>
  );
}

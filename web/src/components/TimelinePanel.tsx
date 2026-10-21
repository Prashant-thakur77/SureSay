import { useState } from "react";
import type { HubState, HubStats, Receipt } from "../lib/types";
import { iconFor } from "../lib/words";
import { Icon } from "./Icon";
import { Checks } from "./ReceiptCard";

export function channelLabel(r: Receipt): string {
  if (r.how.channel === "tap") return "Tap";
  if (r.how.channel === "voice") return "Voice";
  return /alexa/i.test(r.evidence.transcriber ?? "") ? "Alexa" : "Voice assistant";
}

function when(iso: string | null): { time: string; day: string; full: string } {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return { time: "", day: "", full: "" };
  return {
    time: d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    day: d.toLocaleDateString([], { day: "numeric", month: "short" }),
    full: d.toISOString(),
  };
}

/** Counts from the hub, or from the events it sent when an older hub has no stats. */
export function statsOf(state: HubState | null): HubStats {
  if (state?.stats) return state.stats;
  const ev = state?.events ?? [];
  return {
    confirmed: ev.filter((e) => e.type === "done").length,
    refused: ev.filter((e) => e.type === "refused").length,
    refused_from_assistant: ev.filter((e) => e.type === "refused" && e.caller === "agent").length,
    cancelled: ev.filter((e) => e.type === "cancelled").length,
    without_you: 0,
  };
}

/** Plain text a carer can read: the counts, then what was done. */
export function summaryText(state: HubState | null, now = new Date()): string {
  const s = statsOf(state);
  const lines = [
    `SureSay summary for ${state?.user_id ?? "you"}, ${now.toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" })}`,
    `Confirmed by you: ${s.confirmed}. Blocked attempts: ${s.refused} (from the assistant: ${s.refused_from_assistant}). Cancelled: ${s.cancelled}. Changes without you: ${s.without_you}.`,
  ];
  const receipts = state?.receipts ?? [];
  if (receipts.length > 0) {
    lines.push("", "Recently:");
    for (const r of receipts) {
      const w = when(r.when.executed_at);
      lines.push(`- ${w.day} ${w.time}: ${r.what.shown_as} (${channelLabel(r).toLowerCase()}${r.what.origin === "assistant" ? ", suggested by the assistant" : ""})`);
    }
  }
  return lines.join("\n");
}

async function copy(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}

export function TimelinePanel({ state }: { state: HubState | null }) {
  const [status, setStatus] = useState("");
  const s = statsOf(state);
  const receipts = state?.receipts ?? [];
  return (
    <section className="timeline" aria-labelledby="timeline-title">
      <div className="timeline__head">
        <h2 id="timeline-title" className="stage__title display">
          Your <em>timeline</em>
        </h2>
        <button
          type="button"
          className="btn btn--secondary"
          onClick={async () => setStatus((await copy(summaryText(state))) ? "Summary copied. You can paste it in a message." : "I could not copy it. Please try again.")}
        >
          <Icon name="list" size={24} /> Copy summary
        </button>
      </div>
      <p role="status" className="timeline__status">
        {status}
      </p>
      <ul className="counters" aria-label="Totals">
        <li className="counter">
          <span className="counter__n" data-testid="count-confirmed">
            {s.confirmed}
          </span>
          <span className="counter__label">Confirmed by you</span>
        </li>
        <li className="counter">
          <span className="counter__n" data-testid="count-blocked">
            {s.refused}
          </span>
          <span className="counter__label">Blocked attempts</span>
          {s.refused_from_assistant > 0 && <span className="counter__sub">{s.refused_from_assistant} from the assistant</span>}
        </li>
        <li className="counter counter--zero">
          <span className="counter__n" data-testid="count-without-you">
            {s.without_you}
          </span>
          <span className="counter__label">Changes without you</span>
          <span className="counter__sub">Every change needs your voice or tap.</span>
        </li>
      </ul>
      {receipts.length === 0 ? (
        <p>Nothing yet. Each thing you confirm appears here.</p>
      ) : (
        <ol className="tl">
          {receipts.map((r) => {
            const w = when(r.when.executed_at);
            return (
              <li key={r.receipt_id} className="tl__item">
                <span className="tl__dot" aria-hidden="true">
                  <Icon name={iconFor({ action: r.what.action, args: r.what.args })} size="100%" />
                </span>
                <div className="tl__body">
                  <p className="tl__what">{r.what.shown_as}</p>
                  <p className="tl__meta">
                    <time dateTime={w.full}>
                      {w.day} · {w.time}
                    </time>
                    <span className="tl__channel">{channelLabel(r)}</span>
                    {r.what.origin === "assistant" && <span className="tl__assist">Suggested by the assistant</span>}
                  </p>
                  <Checks receipt={r} />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

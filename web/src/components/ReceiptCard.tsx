import { forwardRef, useId, type CSSProperties } from "react";
import { checkLabel, TICK_MS } from "../lib/checks";
import type { Receipt } from "../lib/types";
import { channelWords, iconFor, timeOf } from "../lib/words";
import { ConsentTrail } from "./ConsentTrail";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

export function shortId(id: string): string {
  return id.length > 13 ? `${id.slice(0, 13)}…` : id;
}

export function Checks({ receipt }: { receipt: Receipt }) {
  const passed = receipt.checks.filter((c) => c.ok).length;
  return (
    <details className="why">
      <summary>
        <Icon name="shield" size={22} /> Why this was allowed{" "}
        <span className="why__count">
          ({passed} of {receipt.checks.length} checks passed)
        </span>
      </summary>
      <ul className="why__list">
        {receipt.checks.map((c) => (
          <li key={c.name} className={c.ok ? "why__ok" : "why__bad"}>
            <span className="why__mark" aria-hidden="true">
              {c.ok ? "✓" : "✗"}
            </span>
            <span>
              <span className="visually-hidden">{c.ok ? "Passed: " : "Failed: "}</span>
              {checkLabel(c.name)}
              <code className="why__code">{c.name}</code>
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

const BURST = Array.from({ length: 14 }, (_, i) => ({
  angle: (360 / 14) * i + (i % 2 ? 9 : -4),
  dist: 54 + ((i * 37) % 26),
  hue: i % 4,
  size: 6 + ((i * 5) % 5),
}));

/** A burst of dots out of the stamp (decorative; none at all without motion). */
function Burst() {
  return (
    <span className="burst" aria-hidden="true">
      {BURST.map((b, i) => (
        <span
          key={i}
          className={`burst__dot burst__dot--${b.hue}`}
          style={{ "--a": `${b.angle}deg`, "--d": `${b.dist}px`, "--s": `${b.size}px`, "--k": i } as CSSProperties}
        />
      ))}
    </span>
  );
}

/** A small round "CONFIRMED BY YOU" stamp. Decorative: the same words are in the text. */
function Stamp() {
  const id = useId().replace(/:/g, "");
  return (
    <svg className="stamp" viewBox="0 0 120 120" aria-hidden="true" focusable="false">
      <defs>
        <path id={`ring-${id}`} d="M60,60 m-42,0 a42,42 0 1,1 84,0 a42,42 0 1,1 -84,0" />
      </defs>
      <circle cx="60" cy="60" r="55" fill="none" stroke="currentColor" strokeWidth="3" />
      <circle cx="60" cy="60" r="31" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <text className="stamp__text" fill="currentColor">
        <textPath href={`#ring-${id}`} startOffset="0">
          CONFIRMED BY YOU · CONFIRMED BY YOU ·
        </textPath>
      </text>
      <path d="M46 61l9.5 9.5L75 50" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function clockSeconds(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface Props {
  receipt: Receipt;
  said?: string;
  onReplay?: () => void;
}

/** The consent trail, then the receipt "stamps" in as a ticket. */
export const ReceiptCard = forwardRef<HTMLHeadingElement, Props>(function ReceiptCard({ receipt, said, onReplay }, ref) {
  const when = timeOf(receipt.when.executed_at ?? receipt.when.confirmed_at);
  const option = { action: receipt.what.action, args: receipt.what.args };
  const replayScan = useScanMark("replay");
  const delay = receipt.checks.length * TICK_MS + 180;
  return (
    <div className="done" style={{ "--stamp-delay": `${delay}ms` } as CSSProperties}>
      <ConsentTrail checks={receipt.checks} pendingId={receipt.how.pending_id} />
      <div className="done__slot" aria-hidden="true">
        Checking…
      </div>
      <div className="ticket-wrap" style={{ "--stamp-delay": `${delay}ms` } as CSSProperties}>
      <article className="ticket" aria-labelledby="receipt-title">
        <div className="ticket__main">
          <p className="ticket__eyebrow">Consent receipt</p>
          <div className="receipt__head">
            <span className="receipt__icon" aria-hidden="true">
              <Icon name={iconFor(option)} size="100%" />
            </span>
            <h2 id="receipt-title" className="receipt__title" ref={ref} tabIndex={-1}>
              <em className="receipt__done">Done:</em> <span>{receipt.what.shown_as}</span>
            </h2>
          </div>
          <p className="receipt__how">
            Confirmed by {channelWords(receipt)}
            {when && <> at {when}</>}.
          </p>
          {receipt.what.origin === "assistant" && (
            <p className="receipt__assist">
              <Icon name="spark" size={20} /> The assistant suggested this. You confirmed it.
            </p>
          )}
          {said && (
            <div className="said">
              <p className="said__label">Said out loud for you:</p>
              <blockquote className="said__text" lang="en">
                {said}
              </blockquote>
              {onReplay && (
                <button type="button" className="btn btn--secondary" onClick={onReplay} {...replayScan}>
                  <Icon name="volume" size={24} /> Say it again out loud
                </button>
              )}
            </div>
          )}
          <Checks receipt={receipt} />
        </div>
        <div className="ticket__stub">
          <dl className="ticket__meta">
            <div>
              <dt>Receipt</dt>
              <dd>
                <code>{shortId(receipt.receipt_id)}</code>
              </dd>
            </div>
            <div>
              <dt>Time</dt>
              <dd>{clockSeconds(receipt.when.executed_at ?? receipt.when.confirmed_at)}</dd>
            </div>
            <div>
              <dt>Channel</dt>
              <dd>{receipt.how.channel === "voice" ? "Voice" : "Tap"}</dd>
            </div>
            <div>
              <dt>Card</dt>
              <dd>
                {receipt.what.option_chosen} of {receipt.what.options_shown}
              </dd>
            </div>
          </dl>
          <span className="stamp-wrap">
            <Burst />
            <Stamp />
          </span>
        </div>
      </article>
      </div>
    </div>
  );
});

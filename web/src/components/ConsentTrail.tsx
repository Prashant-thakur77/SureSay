/**
 * The consent trail: the gate's real checks, read out line by line.
 *
 * Every line is in the page from the start; CSS only delays when each one
 * shows (TICK_MS apart). With reduced motion or Calm mode the animation is
 * off and everything is simply there. Screen readers hear one outcome
 * announcement elsewhere, never a tick.
 */

import type { CSSProperties } from "react";
import { checkFailure, checkLabel, TICK_MS, trailNumber } from "../lib/checks";
import type { Check } from "../lib/types";

export function TrailLines({ checks, animate = false }: { checks: Check[]; animate?: boolean }) {
  return (
    <ol className={`trail__lines${animate ? " trail__lines--tick" : ""}`}>
      {checks.map((c, i) => (
        <li key={c.name} className={c.ok ? "trail__line" : "trail__line trail__line--bad"} style={{ "--i": i, "--tick": `${TICK_MS}ms` } as CSSProperties}>
          <span className="trail__n" aria-hidden="true">
            {trailNumber(i)}
          </span>
          <span className="trail__label">{checkLabel(c.name)}</span>
          <span className="trail__leader" aria-hidden="true" />
          <span className="trail__mark">
            <span aria-hidden="true">{c.ok ? "✓" : "✗"}</span>
            <span className="visually-hidden">{c.ok ? "passed" : "failed"}</span>
          </span>
          {!c.ok && <span className="trail__why">— {checkFailure(c.name)}</span>}
        </li>
      ))}
    </ol>
  );
}

export function ConsentTrail({ checks, pendingId }: { checks: Check[]; pendingId: string }) {
  const passed = checks.filter((c) => c.ok).length;
  return (
    <section className="trail" aria-labelledby="trail-title" style={{ "--n": checks.length, "--tick": `${TICK_MS}ms` } as CSSProperties}>
      <h2 id="trail-title" className="trail__head">
        <span>Consent trail</span>
        <span className="trail__meta">
          {pendingId} · {checks.length} checks
        </span>
      </h2>
      <TrailLines checks={checks} animate />
      <p className="trail__foot">
        {passed} of {checks.length} passed <span aria-hidden="true">→</span> released
      </p>
    </section>
  );
}

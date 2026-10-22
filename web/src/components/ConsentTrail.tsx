/**
 * The consent trail: the gate's real checks, read out line by line.
 *
 * Every line is in the page from the start; CSS only delays when each one
 * shows (TICK_MS apart). With reduced motion or Calm mode the animation is
 * off and everything is simply there. Screen readers hear one outcome
 * announcement elsewhere, never a tick.
 *
 * Once it has ticked (at once without motion) it folds into "How it was
 * checked": closed on a phone, so the outcome above it fits the first screen,
 * and open on a wider one.
 */

import { useEffect, useState, type CSSProperties } from "react";
import { NARROW, useMedia } from "../hooks/useMedia";
import { checkFailure, checkLabel, TICK_MS, trailNumber } from "../lib/checks";
import type { Check } from "../lib/types";

/** The foot fades in after the last tick (see .trail__foot in styles.css). */
const FOOT_MS = 400;

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

export function ConsentTrail({ checks, pendingId, motion = true }: { checks: Check[]; pendingId: string; motion?: boolean }) {
  const passed = checks.filter((c) => c.ok).length;
  const narrow = useMedia(NARROW);
  const [folded, setFolded] = useState(!motion);
  const [open, setOpen] = useState(!narrow);
  useEffect(() => {
    if (!motion) {
      setFolded(true);
      return;
    }
    const t = window.setTimeout(() => setFolded(true), checks.length * TICK_MS + FOOT_MS);
    return () => window.clearTimeout(t);
  }, [motion, checks.length]);
  // the screen turned or the window was resized: follow it
  useEffect(() => setOpen(!narrow), [narrow]);

  const foot = (
    <p className="trail__foot">
      {passed} of {checks.length} passed <span aria-hidden="true">→</span> released
    </p>
  );
  if (folded) {
    return (
      <details className="trail trail--folded" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className="trail__summary">
          How it was checked ({passed} of {checks.length})
        </summary>
        <p className="trail__meta trail__id">
          Consent trail · {pendingId} · {checks.length} checks
        </p>
        <TrailLines checks={checks} />
        {foot}
      </details>
    );
  }
  return (
    <section className="trail" aria-labelledby="trail-title" style={{ "--n": checks.length, "--tick": `${TICK_MS}ms` } as CSSProperties}>
      <h2 id="trail-title" className="trail__head">
        <span>Consent trail</span>
        <span className="trail__meta">
          {pendingId} · {checks.length} checks
        </span>
      </h2>
      <TrailLines checks={checks} animate />
      {foot}
    </section>
  );
}

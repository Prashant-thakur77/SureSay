import { useEffect, useRef } from "react";
import type { HomeDevice, PendingSet } from "../lib/types";
import { iconFor } from "../lib/words";
import { AssistantBanner, Countdown } from "./CardSet";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

interface Props {
  set: PendingSet;
  deadline: number;
  busy: boolean;
  devices?: Record<string, HomeDevice>;
  onYes: () => void;
  onNo: () => void;
  onExpire: (pendingId: string) => void;
  announce: (msg: string) => void;
  /** A one-card set (a tapped tile, a phrase to learn): "Is this right?" rather than a second check. */
  single?: boolean;
}

/** The second yes for risky actions: one big card and two huge buttons. */
export function FinalCheck({ set, deadline, busy, devices, onYes, onNo, onExpire, announce, single = false }: Props) {
  const option = set.options[0];
  // focus the question, not YES: a reflex Enter must never confirm a risky action
  const cardRef = useRef<HTMLDivElement>(null);
  const yesScan = useScanMark("yes");
  const noScan = useScanMark("no");

  useEffect(() => {
    cardRef.current?.focus();
  }, [set.pending_id]);

  if (!option) return null;
  return (
    <section className="final" aria-labelledby="final-title">
      <div className="cardset__head">
        <h2 id="final-title" className="stage__title display">
          {single ? (
            <>
              Is this <em>right?</em>
            </>
          ) : (
            <>
              Please <em>check</em>: this one asks twice
            </>
          )}
        </h2>
        <Countdown deadline={deadline} pendingId={set.pending_id} onExpire={onExpire} announce={announce} />
      </div>
      {set.origin === "assistant" && <AssistantBanner />}
      <div className="final__card" ref={cardRef} tabIndex={-1}>
        <span className="card__icon" aria-hidden="true">
          <Icon name={iconFor(option, devices)} size="100%" />
        </span>
        <p className="final__text">{/[”"'.!?]$/.test(option.text) ? option.text : `${option.text}?`}</p>
      </div>
      <div className="yesno" role="group" aria-labelledby="final-title">
        <button
          type="button"
          className="btn btn--yes"
          aria-disabled={busy || undefined}
          onClick={() => !busy && onYes()}
          aria-keyshortcuts="Y"
          {...yesScan}
        >
          <Icon name="check" size={40} /> Yes
        </button>
        <button
          type="button"
          className="btn btn--no"
          aria-disabled={busy || undefined}
          onClick={() => !busy && onNo()}
          aria-keyshortcuts="N Escape"
          {...noScan}
        >
          <Icon name="close" size={40} /> No
        </button>
      </div>
    </section>
  );
}

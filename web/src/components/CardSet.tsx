/**
 * The 1–3 guesses as big numbered cards.
 *
 * Screen-reader design: the cards are buttons in an ordered list, not radios.
 * Choosing a card is an action that sends the user's answer at once; a radio
 * would promise a selection that waits for a second step. Each button's name
 * reads "Option 2 of 3: Turn on the bedroom fan. Maybe." (with "Asks twice" or
 * "Suggested by the assistant" when they apply), so the visible text is always
 * part of the name. Arrow keys move between cards; Enter, a click or the
 * number keys choose. Space on a card starts the microphone instead of
 * choosing, so a reflex press of the talk key never picks a card by accident.
 */

import { useEffect, useRef, type KeyboardEvent } from "react";
import { formatSeconds, useCountdown } from "../hooks/useCountdown";
import type { CardOption, HomeDevice, PendingSet } from "../lib/types";
import { barValue, iconFor, likelihood } from "../lib/words";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

interface Props {
  set: PendingSet;
  deadline: number;
  busy: boolean;
  tv: boolean;
  devices?: Record<string, HomeDevice>;
  onChoose: (n: number) => void;
  onSpace: () => void;
  onExpire: (pendingId: string) => void;
  announce: (msg: string) => void;
}

export function AssistantBanner() {
  return (
    <p className="assist-banner" id="assist-note">
      <Icon name="spark" size={26} />
      <span>
        <strong>Suggested by the assistant</strong> — you didn't ask for this.
      </span>
    </p>
  );
}

export function Countdown({ deadline, pendingId, onExpire, announce }: { deadline: number; pendingId: string; onExpire: (id: string) => void; announce: (msg: string) => void }) {
  const left = useCountdown(deadline);
  const warned = useRef(false);
  useEffect(() => {
    if (left == null) return;
    if (left === 0) onExpire(pendingId);
    else if (left <= 30 && !warned.current) {
      warned.current = true;
      announce(`${left} seconds left to answer.`);
    }
  }, [left, pendingId, onExpire, announce]);
  if (left == null) return null;
  return (
    <p className={`countdown${left <= 30 ? " countdown--low" : ""}`}>
      <Icon name="clock" size={20} />
      <span>
        Open for <span className="countdown__time">{formatSeconds(left)}</span>
      </span>
    </p>
  );
}

function ChoiceCard({
  option,
  total,
  confidence,
  assistant,
  busy,
  devices,
  onChoose,
  onKeyDown,
}: {
  option: CardOption;
  total: number;
  confidence: number | null | undefined;
  assistant: boolean;
  busy: boolean;
  devices?: Record<string, HomeDevice>;
  onChoose: (n: number) => void;
  onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => void;
}) {
  const scan = useScanMark(`card-${option.n}`);
  const words = likelihood(confidence, option.n);
  const bar = barValue(confidence, option.n);
  const high = option.risk === "high";
  const name =
    `Option ${option.n} of ${total}: ${option.text}. ${words}.` +
    (high ? " Asks twice." : "") +
    (assistant ? " Suggested by the assistant." : "");
  return (
    <li className="cards__item">
      <button
        type="button"
        className="card"
        data-card={option.n}
        aria-label={name}
        aria-disabled={busy || undefined}
        onClick={() => !busy && onChoose(option.n)}
        onKeyDown={onKeyDown}
        onKeyUp={(e) => e.key === " " && e.preventDefault()}
        {...scan}
      >
        <span className="card__num" aria-hidden="true">
          {option.n}
        </span>
        <span className="card__icon" aria-hidden="true">
          <Icon name={iconFor(option, devices)} size="100%" />
        </span>
        <span className="card__body">
          <span className="card__text">{option.text}</span>
          <span className="card__meta">
            <span className="likely">
              <span className="likely__words">{words}</span>
              <span className="likely__bar" aria-hidden="true">
                <span style={{ width: `${Math.round(bar * 100)}%` }} />
              </span>
            </span>
            {high && (
              <span className="badge badge--twice">
                <Icon name="shield" size={20} /> Asks twice
              </span>
            )}
          </span>
        </span>
      </button>
    </li>
  );
}

export function CardSet({ set, deadline, busy, tv, devices, onChoose, onSpace, onExpire, announce }: Props) {
  const listRef = useRef<HTMLOListElement>(null);
  const assistant = set.origin === "assistant";

  // a new card set: focus its first card
  useEffect(() => {
    const first = listRef.current?.querySelector<HTMLButtonElement>("button.card");
    first?.focus({ preventScroll: false });
  }, [set.pending_id]);

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const cards = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>("button.card") ?? []);
    const i = cards.indexOf(e.currentTarget);
    let next = -1;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") next = Math.min(cards.length - 1, i + 1);
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") next = Math.max(0, i - 1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = cards.length - 1;
    else if (e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      onSpace();
      return;
    }
    if (next >= 0) {
      e.preventDefault();
      cards[next]?.focus();
    }
  };

  return (
    <section className={`cardset${tv ? " cardset--tv" : ""}`} aria-labelledby="cards-title">
      <div className="cardset__head">
        <h2 id="cards-title" className="stage__title display">
          Did you <em>mean</em>…
        </h2>
        <Countdown deadline={deadline} pendingId={set.pending_id} onExpire={onExpire} announce={announce} />
      </div>
      {assistant && <AssistantBanner />}
      <ol className="cards" ref={listRef} aria-busy={busy || undefined}>
        {set.options.map((o) => (
          <ChoiceCard
            key={`${set.pending_id}-${o.n}`}
            option={o}
            total={set.options.length}
            confidence={set.context?.confidence?.[o.n - 1]}
            assistant={assistant}
            busy={busy}
            devices={devices}
            onChoose={onChoose}
            onKeyDown={onKeyDown}
          />
        ))}
      </ol>
    </section>
  );
}

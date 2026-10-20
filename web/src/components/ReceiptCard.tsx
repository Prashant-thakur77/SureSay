import { forwardRef } from "react";
import type { Receipt } from "../lib/types";
import { channelWords, iconFor, timeOf } from "../lib/words";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

const CHECK_WORDS: Record<string, string> = {
  user_evidence_exists: "Your own answer was there",
  evidence_is_for_this_card_set: "Your answer was for these cards",
  card_set_exists: "The cards were real",
  from_a_paired_device: "It came from your paired device",
  card_set_still_open: "The cards were still open",
  card_set_not_expired: "The cards had not timed out",
  evidence_not_expired: "Your answer was fresh",
  evidence_not_used: "Your answer had not been used before",
  user_words_choose_a_card: "Your answer clearly chose a card",
  action_unchanged_since_shown: "The action was exactly what you saw",
  action_is_registered_write: "SureSay knows this action",
  nonce_consumed_once: "The cards could be answered only once",
  evidence_consumed_once: "Your answer could be used only once",
};

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
              {CHECK_WORDS[c.name] ?? c.name}
              <code className="why__code">{c.name}</code>
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

interface Props {
  receipt: Receipt;
  said?: string;
  onReplay?: () => void;
}

/** "Done: …" with who confirmed it, when, and why the gate let it through. */
export const ReceiptCard = forwardRef<HTMLHeadingElement, Props>(function ReceiptCard({ receipt, said, onReplay }, ref) {
  const when = timeOf(receipt.when.executed_at ?? receipt.when.confirmed_at);
  const option = { action: receipt.what.action, args: receipt.what.args };
  const replayScan = useScanMark("replay");
  return (
    <article className="receipt receipt--enter" aria-labelledby="receipt-title">
      <div className="receipt__head">
        <span className="receipt__icon" aria-hidden="true">
          <Icon name={iconFor(option)} size="100%" />
        </span>
        <div>
          <h2 id="receipt-title" className="receipt__title" ref={ref} tabIndex={-1}>
            <Icon name="check" size={30} className="receipt__check" />
            Done: {receipt.what.shown_as}
          </h2>
          <p className="receipt__how">
            Confirmed by {channelWords(receipt)}
            {when && <> at {when}</>}.
          </p>
          {receipt.what.origin === "assistant" && (
            <p className="receipt__assist">
              <Icon name="spark" size={20} /> The assistant suggested this. You confirmed it.
            </p>
          )}
        </div>
      </div>
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
      <p className="receipt__id">
        Receipt <code>{shortId(receipt.receipt_id)}</code>
      </p>
      <Checks receipt={receipt} />
    </article>
  );
});

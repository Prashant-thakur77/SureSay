import { useScanMark } from "./scan";

export const TRY_EXAMPLES: Array<{ text: string; note?: string }> = [
  { text: "van on", note: "fan on, misheard" },
  { text: "open the door" },
  { text: "call mum" },
  { text: "I'm hot" },
  { text: "need bread" },
];

/** Example requests for a first try (and the demo). A tap sends the words as if typed. */
export function TryChips({ onTry }: { onTry: (text: string) => void }) {
  return (
    <div className="try">
      <p className="try__label" id="try-label">
        Try one, or say your own
      </p>
      <ul className="try__list" aria-labelledby="try-label">
        {TRY_EXAMPLES.map((t, i) => (
          <li key={t.text}>
            <Chip index={i} text={t.text} note={t.note} onTry={onTry} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function Chip({ index, text, note, onTry }: { index: number; text: string; note?: string; onTry: (text: string) => void }) {
  const mark = useScanMark(`try-${index}`);
  return (
    <button type="button" className={`try__chip try__chip--h${(index % 3) + 1}`} onClick={() => onTry(text)} {...mark}>
      <span className="try__text">“{text}”</span>
      {note && <span className="try__note">({note})</span>}
    </button>
  );
}

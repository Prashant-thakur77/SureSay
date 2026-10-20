/** First-visit strip: how SureSay works, in three steps joined by a drawn line. */

import type { CSSProperties } from "react";

const STEPS = [
  { title: "Say it", rest: "(or type it)" },
  { title: "See my three best guesses", rest: "" },
  { title: "Choose.", rest: "Only then does anything happen." },
];

function Joiner() {
  return (
    <>
      <svg className="steps__join steps__join--across" viewBox="0 0 64 24" aria-hidden="true" focusable="false">
        <path className="steps__line" pathLength={1} d="M3 15 C 16 4, 26 22, 38 12 S 54 6, 58 11" />
        <path className="steps__head" d="M51 6.5 L 58.5 11 L 51.5 16" />
      </svg>
      <svg className="steps__join steps__join--down" viewBox="0 0 24 44" aria-hidden="true" focusable="false">
        <path className="steps__line" pathLength={1} d="M12 3 C 4 12, 19 20, 11 30 S 12 38, 12 40" />
        <path className="steps__head" d="M7 34 L 12 41 L 17 34.5" />
      </svg>
    </>
  );
}

export function Steps() {
  return (
    <ol className="steps" aria-label="How SureSay works">
      {STEPS.map((s, i) => (
        <li key={s.title} className="steps__item" style={{ "--i": i } as CSSProperties}>
          <span className="steps__num" aria-hidden="true">
            {i + 1}
          </span>
          <span className="steps__text">
            <strong>{s.title}</strong>
            {s.rest && <> {s.rest}</>}
          </span>
          {i < STEPS.length - 1 && <Joiner />}
        </li>
      ))}
    </ol>
  );
}

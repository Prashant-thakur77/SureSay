import { useCallback, useEffect, useRef, useState } from "react";
import type { PracticeResult, PracticeState } from "../lib/types";
import { Icon } from "./Icon";

interface Props {
  load: () => Promise<PracticeState>;
  submit: (target: string, audioB64: string) => Promise<PracticeResult>;
  record: () => Promise<{ wavBase64: string } | null>;
  stop: () => void;
  recording: boolean;
  announce: (message: string) => void;
}

function cheer(score: number): string {
  if (score >= 90) return "Clear as day.";
  if (score >= 70) return "Nearly every word came through.";
  if (score >= 40) return "Getting there. Every try counts.";
  return "Thank you for trying. Every recording teaches SureSay your voice.";
}

/** A few sentences a day, read aloud in his own time; an honest clarity score and progress over days. */
export function PracticePanel({ load, submit, record, stop, recording, announce }: Props) {
  const [state, setState] = useState<PracticeState | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [result, setResult] = useState<PracticeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const liveRef = useRef<HTMLDivElement>(null);
  const showing = recording || busy || !!result || !!error;
  useEffect(() => {
    if (!showing) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    liveRef.current?.scrollIntoView?.({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [showing, result]);

  const refresh = useCallback(() => load().then(setState).catch(() => setError("Practice is not available right now.")), [load]);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const go = async (sentence: string) => {
    setTarget(sentence);
    setResult(null);
    setError("");
    announce(`Read it aloud, in your own time: ${sentence}`);
    let rec;
    try {
      rec = await record();
    } catch {
      setError("The microphone could not start.");
      return;
    }
    if (!rec) return;
    setBusy(true);
    try {
      const r = await submit(sentence, rec.wavBase64);
      setResult(r);
      announce(`${r.score} percent clear. ${cheer(r.score)}`);
      void refresh();
    } catch {
      setError("That recording could not be scored. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const days = state?.days ?? [];
  return (
    <section className="practice" aria-labelledby="practice-title">
      <h2 id="practice-title" className="stage__title display">
        Practice, <em>a little every day</em>
      </h2>
      <p className="stage__lead">Read a sentence aloud, in your own time. I'll show which words came through clearly.</p>
      {state && (
        <p className="practice__streak">
          <Icon name="spark" size={22} />{" "}
          {state.streak_days > 0 ? `${state.streak_days}-day streak · ` : ""}
          {state.attempts} {state.attempts === 1 ? "recording" : "recordings"} so far
        </p>
      )}
      <div className="practice__live" ref={liveRef}>
        {recording && target && (
          <div className="practice__now">
            <p className="practice__reading">“{target}”</p>
            <p>Read it aloud, in your own time. I stop when you pause.</p>
          </div>
        )}
        {recording && (
          <button type="button" className="btn btn--primary btn--xl" onClick={stop}>
            <Icon name="stop" size={26} /> I'm done
          </button>
        )}
        {busy && <p role="status">Listening back…</p>}
        {error && <p role="alert" className="practice__error">{error}</p>}
        {result && (
          <div className="practice__result" role="status">
            <p className="practice__score">
              <span className="practice__pct">{result.score}%</span> clear
            </p>
            <p className="practice__words" aria-label={`Words that came through: ${result.words.filter((w) => w.heard).map((w) => w.word).join(" ")}`}>
              {result.words.map((w, i) => (
                <span key={`${w.word}-${i}`} className={w.heard ? "pw pw--ok" : "pw pw--miss"}>
                  {w.word}
                </span>
              ))}
            </p>
            <p className="practice__cheer">{cheer(result.score)}</p>
            {result.learned && <p className="practice__learned"><Icon name="check" size={20} /> SureSay learned your way of saying this.</p>}
          </div>
        )}
      </div>
      <ul className="practice__list" aria-label="Today's sentences">
        {(state?.today ?? []).map((s) => (
          <li key={s}>
            <button type="button" className={`practice__item${target === s ? " practice__item--on" : ""}`} disabled={busy}
                    aria-pressed={target === s} onClick={() => void go(s)}>
              <Icon name="mic" size={26} />
              <span>{s}</span>
              {state?.best[s] !== undefined && <span className="practice__best">best {state.best[s]}%</span>}
            </button>
          </li>
        ))}
      </ul>
      {days.length > 0 && (
        <figure className="practice__chart">
          <figcaption>Your last {days.length} {days.length === 1 ? "day" : "days"}</figcaption>
          <div className="practice__bars" role="img" aria-label={days.map((d) => `${d.day}: ${d.average}%`).join(", ")}>
            {days.map((d) => (
              <span key={d.day} className="practice__bar" style={{ height: `${Math.max(6, d.average)}%` }} title={`${d.day}: ${d.average}%`} />
            ))}
          </div>
        </figure>
      )}
      <p className="practice__note">A practice signal, not a medical test.</p>
    </section>
  );
}

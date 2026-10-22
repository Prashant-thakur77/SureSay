import { useRef, useState, type FormEvent } from "react";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

/**
 * Talk to someone: say (or type) what you want to tell the person in front of you. SureSay offers what it heard and
 * your usual sentences; you choose one, and only then is it said clearly, out loud, and shown big for them.
 */
export function TalkPanel({ onSpeak, onType, busy }: { onSpeak: () => void; onType: (text: string) => void; busy: boolean }) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const mark = useScanMark("talk-say");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const clean = text.trim();
    if (busy) return;
    if (!clean) {
      inputRef.current?.focus();
      return;
    }
    onType(clean);
    setText("");
  };
  return (
    <section className="talk" aria-labelledby="talk-title">
      <h2 id="talk-title" className="stage__title display">
        Talk to <em>someone</em>
      </h2>
      <p className="stage__lead">
        Say what you want to tell them, in your own way. I'll offer what I heard and the sentences you use, you choose,
        and then I say it clearly and show it big for them.
      </p>
      <button type="button" className="talk__mic" onClick={() => !busy && onSpeak()} aria-disabled={busy || undefined} {...mark}>
        <Icon name="mic" size={44} />
        <span>Say it</span>
      </button>
      <form className="talk__type" onSubmit={submit} aria-label="Type what to say">
        <label htmlFor="say-input" className="typebox__label">
          <Icon name="keyboard" size={24} /> Or type it
        </label>
        <div className="typebox__row">
          <input ref={inputRef} id="say-input" className="input" type="text" value={text} onChange={(e) => setText(e.target.value)}
                 autoComplete="off" placeholder="For example: I'm proud of you" disabled={busy} />
          <button type="submit" className="btn btn--primary" disabled={busy}>
            <Icon name="send" size={22} /> Offer it
          </button>
        </div>
      </form>
      <p className="talk__note">
        <Icon name="shield" size={20} /> Nothing is said for you until you choose it.
      </p>
    </section>
  );
}

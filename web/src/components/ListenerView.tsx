import { useRef, useState } from "react";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { Icon } from "./Icon";

/** The sentence, huge, for the person listening. "Turn it around" flips it for someone across the table. */
export function ListenerView({ text, onClose, onReplay }: { text: string; onClose: () => void; onReplay: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [flipped, setFlipped] = useState(false);
  useFocusTrap(ref, true, onClose);
  const hindi = /[ऀ-ॿ]/.test(text);
  return (
    <div className="listener" role="dialog" aria-modal="true" aria-labelledby="listener-text" ref={ref}>
      <p className="listener__label">For you, from the person you are talking with</p>
      <p id="listener-text" className={`listener__text${flipped ? " listener__text--flipped" : ""}`} lang={hindi ? "hi" : "en"}>
        {text}
      </p>
      <div className="listener__actions">
        <button type="button" className="btn btn--secondary" onClick={onReplay}>
          <Icon name="volume" size={24} /> Say it again
        </button>
        <button type="button" className="btn btn--secondary" aria-pressed={flipped} onClick={() => setFlipped((f) => !f)}>
          <Icon name="refresh" size={24} /> Turn it around
        </button>
        <button type="button" className="btn btn--primary" onClick={onClose} autoFocus>
          <Icon name="close" size={24} /> Done
        </button>
      </div>
    </div>
  );
}

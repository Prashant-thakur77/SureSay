import { useEffect, useRef } from "react";
import { unlockAudio } from "../lib/speech";
import { Icon } from "./Icon";
import { Wordmark } from "./TopBar";

export type StartChoice = "voice" | "quiet";

/**
 * First run: start with voice (read-aloud and listening on) or quietly (tap
 * only). The click also unlocks audio, so read-back works on the first turn.
 */
export function StartGate({ onChoose }: { onChoose: (choice: StartChoice) => void }) {
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    first.current?.focus();
  }, []);

  const choose = (choice: StartChoice) => {
    unlockAudio();
    onChoose(choice);
  };

  return (
    <div className="gate">
      <main className="gate__inner" aria-labelledby="gate-title">
        <Wordmark as="p" />
        <h1 id="gate-title" className="gate__title display">
          How would you like to <em>start?</em>
        </h1>
        <p className="gate__lead">Say it your way. Nothing happens until you choose.</p>
        <div className="gate__choices">
          <button
            ref={first}
            type="button"
            className="gate__btn gate__btn--voice"
            onClick={() => choose("voice")}
            aria-labelledby="gate-voice"
            aria-describedby="gate-voice-desc"
          >
            <span className="gate__icon" aria-hidden="true">
              <Icon name="volume" size="100%" />
            </span>
            <span className="gate__text">
              <span id="gate-voice" className="gate__name">
                Start with voice
              </span>
              <span id="gate-voice-desc" className="gate__desc">
                I read the choices aloud, then listen for your answer.
              </span>
            </span>
          </button>
          <button
            type="button"
            className="gate__btn gate__btn--quiet"
            onClick={() => choose("quiet")}
            aria-labelledby="gate-quiet"
            aria-describedby="gate-quiet-desc"
          >
            <span className="gate__icon" aria-hidden="true">
              <Icon name="hand" size="100%" />
            </span>
            <span className="gate__text">
              <span id="gate-quiet" className="gate__name">
                Start quietly
              </span>
              <span id="gate-quiet-desc" className="gate__desc">
                No sound. You tap to choose.
              </span>
            </span>
          </button>
        </div>
        <p className="gate__note">You can change this any time in Settings.</p>
      </main>
    </div>
  );
}

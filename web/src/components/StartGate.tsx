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
      <main className="gate__inner" aria-labelledby="gate-hero">
        <div className="sky" aria-hidden="true">
          <span className="sky__glow sky__glow--a" />
          <span className="sky__glow sky__glow--b" />
          <span className="sky__stars" />
        </div>
        <Wordmark as="p" />
        <p className="gate__badge">For speech that other assistants mishear</p>
        <h1 id="gate-hero" className="gate__hero display">
          Say it your way. <em>Nothing happens until you choose.</em>
        </h1>
        <div className="gate__fan" aria-hidden="true">
          {FAN.map(([long, short], i) => (
            <span key={long} className={`fan-card fan-card--${i + 1}`}>
              <b>{i + 1}</b>
              <span className="long">{long}</span>
              <span className="short">{short}</span>
            </span>
          ))}
        </div>
        <h2 id="gate-title" className="gate__title display">
          How would you like to <em>start?</em>
        </h2>
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
      <section className="gate__features" aria-label="What SureSay does">
        {FEATURES.map((f) => (
          <article key={f.badge} className="feature">
            <p className="feature__badge">
              <Icon name={f.icon} size={18} /> {f.badge}
            </p>
            <h3 className="feature__title">{f.title}</h3>
            <ul className="feature__list">
              {f.points.map((pt) => (
                <li key={pt}>
                  <Icon name="check" size={20} /> {pt}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </section>
    </div>
  );
}

const FAN: Array<[string, string]> = [["Turn on the bedroom fan", "Fan on"], ["Turn on the TV", "TV on"], ["Turn off the fan", "Fan off"]];

const FEATURES: Array<{ badge: string; icon: "mic" | "message" | "spark" | "shield"; title: string; points: string[] }> = [
  { badge: "Talk", icon: "mic", title: "Three guesses, never a guess acted on",
    points: ["Big, numbered cards, read aloud", "Answer by voice, tap, key or one switch", "Risky things ask twice"] },
  { badge: "Talk to someone", icon: "message", title: "Understood by people, too",
    points: ["Say it your way, choose the right sentence", "Said clearly, out loud", "Shown huge, turned around for them"] },
  { badge: "Practice", icon: "spark", title: "A little every day",
    points: ["Five sentences a day", "An honest clarity score", "Every try teaches SureSay your voice"] },
  { badge: "Safe by design", icon: "shield", title: "Only you can confirm",
    points: ["The AI can suggest, never confirm", "Every change leaves a receipt", "Help reaches your family in one press"] },
];

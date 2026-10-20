import { forwardRef, type CSSProperties } from "react";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

export type MicMode = "request" | "answer" | "listening" | "busy";

interface Props {
  mode: MicMode;
  level: number;
  onToggle: () => void;
  answerKind?: "number" | "yesno";
  speaking?: boolean;
  disabled?: boolean;
}

const LABELS: Record<MicMode, { title: string; hint: string }> = {
  request: { title: "Tap to speak", hint: "Tap, say what you need, then pause." },
  answer: { title: "Answer by voice", hint: "Tap, then say a number." },
  listening: { title: "Listening… tap to stop", hint: "I stop by myself when you pause." },
  busy: { title: "Working…", hint: "One moment." },
};

const RINGS = [1, 2, 3, 4];

/**
 * The microphone at the centre of the orb. Tap to start, tap to stop; it also
 * stops by itself after a pause. Thin rings around it breathe softly when
 * idle, follow the voice level while listening, and hold still while SureSay
 * speaks. The rings are decoration; the level is also a labelled meter.
 */
export const MicButton = forwardRef<HTMLButtonElement, Props>(function MicButton(
  { mode, level, onToggle, answerKind = "number", speaking = false, disabled },
  ref,
) {
  const scan = useScanMark("mic");
  const label = LABELS[mode];
  const listening = mode === "listening";
  let hint = mode === "answer" && answerKind === "yesno" ? "Tap, then say yes or no." : label.hint;
  if (speaking && !listening) hint = "Reading aloud. Tap to answer now.";
  // a gentle curve so quiet voices still move the meter
  const meter = Math.min(1, Math.sqrt(level * 12));
  const orbState = listening ? "listening" : speaking ? "speaking" : mode === "busy" ? "busy" : "idle";
  return (
    <div className="mic-wrap">
      <div className={`orb orb--${orbState}`} style={{ "--level": listening ? meter.toFixed(3) : 0 } as CSSProperties}>
        {RINGS.map((r) => (
          <span key={r} className="orb__ring" style={{ "--r": r } as CSSProperties} aria-hidden="true" />
        ))}
        <button
          ref={ref}
          type="button"
          className={`mic mic--${mode}`}
          onClick={onToggle}
          disabled={disabled || mode === "busy"}
          aria-pressed={listening}
          aria-describedby="mic-hint"
          {...scan}
        >
          <Icon name={listening ? "stop" : "mic"} size="42%" />
          <span className="visually-hidden">{listening ? "Stop listening" : label.title}</span>
        </button>
      </div>
      <p className="mic__title" aria-hidden="true">
        {label.title}
      </p>
      <p id="mic-hint" className="mic__hint">
        {hint} <span className="kbd-hint">Or press Space.</span>
      </p>
      {listening && (
        <div className="meter" role="meter" aria-label="Voice level" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(meter * 100)}>
          <span className="meter__fill" style={{ width: `${Math.round(meter * 100)}%` }} />
        </div>
      )}
    </div>
  );
});

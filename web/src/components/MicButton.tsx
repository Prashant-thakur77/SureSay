import { forwardRef } from "react";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

export type MicMode = "request" | "answer" | "listening" | "busy";

interface Props {
  mode: MicMode;
  level: number;
  onToggle: () => void;
  answerKind?: "number" | "yesno";
  disabled?: boolean;
}

const LABELS: Record<MicMode, { title: string; hint: string }> = {
  request: { title: "Tap to speak", hint: "Tap, say what you need, then pause." },
  answer: { title: "Answer by voice", hint: "Tap, then say a number." },
  listening: { title: "Listening…", hint: "Tap again to stop." },
  busy: { title: "Working…", hint: "One moment." },
};

/** The big round microphone. Tap to start, tap to stop; it also stops by itself after a pause. */
export const MicButton = forwardRef<HTMLButtonElement, Props>(function MicButton(
  { mode, level, onToggle, answerKind = "number", disabled },
  ref,
) {
  const scan = useScanMark("mic");
  const label = LABELS[mode];
  const hint = mode === "answer" && answerKind === "yesno" ? "Tap, then say yes or no." : label.hint;
  // a gentle curve so quiet voices still move the meter
  const meter = Math.min(1, Math.sqrt(level * 12));
  const listening = mode === "listening";
  return (
    <div className="mic-wrap">
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
        <span className="mic__ring" aria-hidden="true" style={{ transform: `scale(${1 + meter * 0.18})` }} />
        <Icon name={listening ? "stop" : "mic"} size="42%" />
        <span className="visually-hidden">{listening ? "Stop listening" : label.title}</span>
      </button>
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

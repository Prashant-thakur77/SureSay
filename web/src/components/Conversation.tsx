import { useEffect, useRef, type ReactNode } from "react";
import type { Phase } from "../hooks/useConversation";
import { ASK_AGAIN_TEXT } from "../hooks/useConversation";
import type { MicState } from "../hooks/useRecorder";
import type { HomeDevice, Phrase } from "../lib/types";
import { CardSet } from "./CardSet";
import { FinalCheck } from "./FinalCheck";
import { Icon } from "./Icon";
import { MicButton, type MicMode } from "./MicButton";
import { ReceiptCard } from "./ReceiptCard";
import { useScanMark } from "./scan";
import { TypeBox } from "./TypeBox";

export interface ConversationActions {
  toggleMic: () => void;
  startRequest: () => void;
  sendText: (text: string) => void;
  choose: (n: number) => void;
  yes: () => void;
  none: () => void;
  stopListening: () => void;
  expire: (pendingId: string) => void;
  openPhrases: (open: boolean) => void;
  reset: () => void;
  replay: () => void;
}

interface Props {
  phase: Phase;
  actions: ConversationActions;
  mic: MicState;
  level: number;
  tv: boolean;
  devices?: Record<string, HomeDevice>;
  phrasebook: Phrase[];
  announce: (msg: string) => void;
}

function ScanButton({ id, className = "btn btn--secondary", onClick, children, ...rest }: { id: string; className?: string; onClick: () => void; children: ReactNode; "aria-keyshortcuts"?: string }) {
  const mark = useScanMark(id);
  return (
    <button type="button" className={className} onClick={onClick} {...mark} {...rest}>
      {children}
    </button>
  );
}

export function micMode(phase: Phase): MicMode {
  if (phase.kind === "listening") return "listening";
  if (phase.kind === "thinking") return "busy";
  if (phase.kind === "cards") {
    if (phase.answer === "listening") return "listening";
    if (phase.answer === "sending") return "busy";
    return "answer";
  }
  return "request";
}

export function Conversation({ phase, actions, mic, level, tv, devices, phrasebook, announce }: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const typeRef = useRef<HTMLInputElement>(null);
  const micRef = useRef<HTMLButtonElement>(null);

  // after an outcome, move focus to what it says
  const focusKey =
    phase.kind === "done"
      ? `done-${phase.receipt.receipt_id}`
      : phase.kind === "problem"
        ? `problem-${phase.title}`
        : phase.kind === "answer" || phase.kind === "reply"
          ? `${phase.kind}-${phase.text}`
          : phase.kind === "cancelled" || phase.kind === "ask_again"
            ? phase.kind
            : "";
  useEffect(() => {
    if (focusKey) headingRef.current?.focus();
  }, [focusKey]);

  const typeIt = () => {
    actions.stopListening();
    typeRef.current?.focus();
  };

  const startAgain = () => {
    actions.reset();
    requestAnimationFrame(() => micRef.current?.focus());
  };

  const heard =
    (phase.kind === "cards" || phase.kind === "ask_again" || phase.kind === "answer") && phase.heard ? phase.heard : null;

  let view: ReactNode = null;
  switch (phase.kind) {
    case "idle":
      view = (
        <div className="intro">
          <h2 className="stage__title">What would you like?</h2>
          <p className="stage__lead">Tap the microphone and say it your way. Nothing happens until you choose.</p>
        </div>
      );
      break;
    case "listening":
      view = (
        <div className="intro">
          <h2 className="stage__title">Listening…</h2>
          <p className="stage__lead">Take your time. I stop when you pause.</p>
        </div>
      );
      break;
    case "thinking":
      view = (
        <div className="intro" aria-busy="true">
          <h2 className="stage__title">
            <span className="dots" aria-hidden="true" /> Working it out…
          </h2>
          {phase.typed && <p className="heard">You typed: “{phase.typed}”</p>}
        </div>
      );
      break;
    case "cards": {
      const busy = phase.answer === "sending";
      view = (
        <>
          {phase.assistantLine && (
            <p className="assistant-line">
              <span className="assistant-line__who">Assistant:</span> {phase.assistantLine}
            </p>
          )}
          {phase.set.stage === "final" ? (
            <FinalCheck set={phase.set} deadline={phase.deadline} busy={busy} devices={devices} onYes={actions.yes} onNo={actions.none} onExpire={actions.expire} announce={announce} />
          ) : (
            <CardSet set={phase.set} deadline={phase.deadline} busy={busy} tv={tv} devices={devices} onChoose={actions.choose} onSpace={actions.toggleMic} onExpire={actions.expire} announce={announce} />
          )}
          {phase.heardAnswer && <p className="heard heard--answer">Heard: “{phase.heardAnswer}”</p>}
          {busy && (
            <p className="status-line">
              <span className="dots" aria-hidden="true" /> Checking your answer…
            </p>
          )}
          {phase.note && (
            <p className="callout callout--info">
              <Icon name="alert" size={24} /> <span>{phase.note}</span>
            </p>
          )}
          <div className="actions">
            {phase.set.stage === "choose" && (
              <ScanButton id="none" onClick={actions.none} aria-keyshortcuts="Escape N">
                <Icon name="close" size={24} /> None of these <span className="kbd" aria-hidden="true">Esc</span>
              </ScanButton>
            )}
            <ScanButton id="again" onClick={actions.startRequest}>
              <Icon name="refresh" size={24} /> Say it again
            </ScanButton>
            <ScanButton id="type" onClick={typeIt}>
              <Icon name="keyboard" size={24} /> Type it
            </ScanButton>
            <ScanButton id="read" onClick={actions.replay}>
              <Icon name="volume" size={24} /> Read them again
            </ScanButton>
          </div>
        </>
      );
      break;
    }
    case "done":
      view = <ReceiptCard ref={headingRef} receipt={phase.receipt} said={phase.said} onReplay={phase.said ? actions.replay : undefined} />;
      break;
    case "cancelled":
      view = (
        <div className="outcome">
          <h2 className="stage__title" ref={headingRef} tabIndex={-1}>
            Cancelled. Nothing was changed.
          </h2>
          <p className="stage__lead">Tap the microphone when you want to try again.</p>
        </div>
      );
      break;
    case "ask_again":
      view = (
        <div className="outcome">
          <h2 className="stage__title" ref={headingRef} tabIndex={-1}>
            {ASK_AGAIN_TEXT}
          </h2>
          <div className="actions">
            <ScanButton id="again" className="btn btn--primary" onClick={actions.startRequest}>
              <Icon name="mic" size={26} /> Say it again
            </ScanButton>
            <ScanButton id="type" onClick={typeIt}>
              <Icon name="keyboard" size={24} /> Type it
            </ScanButton>
            {phrasebook.length > 0 && (
              <ScanButton id="phrases" onClick={() => actions.openPhrases(!phase.phrases)} aria-keyshortcuts="P">
                <Icon name="book" size={24} /> {phase.phrases ? "Hide my phrases" : "Pick from my phrases"}
              </ScanButton>
            )}
          </div>
          {phase.maybe.length > 0 && (
            <div className="maybe">
              <h3 className="maybe__title">Did you maybe mean</h3>
              <ul>
                {phase.maybe.map((m) => (
                  <li key={`${m.phrase}-${m.text}`}>{m.text}</li>
                ))}
              </ul>
              <p className="maybe__note">These are only ideas. Say it again or pick a phrase to choose.</p>
            </div>
          )}
          {phase.phrases && <PhrasePicker phrases={phrasebook} onPick={(p) => actions.sendText(p)} onClose={() => actions.openPhrases(false)} />}
        </div>
      );
      break;
    case "answer":
    case "reply":
      view = (
        <div className="outcome">
          <p className="answer-label">{phase.kind === "answer" ? "Here is your answer:" : "The assistant says:"}</p>
          <h2 className="answer-text" ref={headingRef} tabIndex={-1}>
            {phase.text}
          </h2>
          <div className="actions">
            <ScanButton id="read" onClick={actions.replay}>
              <Icon name="volume" size={24} /> Read it again
            </ScanButton>
          </div>
        </div>
      );
      break;
    case "problem":
      view = (
        <div className="outcome outcome--problem">
          <h2 className="stage__title" ref={headingRef} tabIndex={-1}>
            <Icon name="alert" size={32} /> {phase.title}
          </h2>
          {phase.detail && <p className="stage__lead">{phase.detail}</p>}
          <div className="actions">
            {phase.expired ? (
              <ScanButton id="again" className="btn btn--primary" onClick={actions.startRequest}>
                <Icon name="mic" size={26} /> Say it again
              </ScanButton>
            ) : (
              <ScanButton id="start" className="btn btn--primary" onClick={startAgain}>
                <Icon name="refresh" size={26} /> Start again
              </ScanButton>
            )}
            <ScanButton id="type" onClick={typeIt}>
              <Icon name="keyboard" size={24} /> Type it
            </ScanButton>
          </div>
        </div>
      );
      break;
  }

  const mode = micMode(phase);
  return (
    <div className={`conversation conversation--${phase.kind}`}>
      {heard && (
        <p className="heard" data-testid="heard">
          I heard: “{heard}”
        </p>
      )}
      <div className="stage__view">{view}</div>
      <div className="inputs">
        <MicButton
          ref={micRef}
          mode={mode}
          level={mic === "recording" ? level : 0}
          onToggle={actions.toggleMic}
          answerKind={phase.kind === "cards" && phase.set.stage === "final" ? "yesno" : "number"}
        />
        <TypeBox ref={typeRef} onSend={actions.sendText} onFocus={actions.stopListening} />
      </div>
    </div>
  );
}

function PhrasePicker({ phrases, onPick, onClose }: { phrases: Phrase[]; onPick: (phrase: string) => void; onClose: () => void }) {
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    listRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, []);
  return (
    <section className="phrases" aria-labelledby="phrases-title">
      <h3 id="phrases-title" className="phrases__title">
        My phrases
      </h3>
      <p className="phrases__lead">Pick one. You will still see the cards before anything happens.</p>
      <ul className="phrases__list" ref={listRef}>
        {phrases.map((p) => (
          <li key={p.id}>
            <PhraseButton phrase={p} onPick={onPick} />
          </li>
        ))}
      </ul>
      <ScanButton id="phrases-close" onClick={onClose}>
        <Icon name="close" size={24} /> Close my phrases
      </ScanButton>
    </section>
  );
}

function PhraseButton({ phrase, onPick }: { phrase: Phrase; onPick: (phrase: string) => void }) {
  const mark = useScanMark(`phrase-${phrase.id}`);
  return (
    <button type="button" className="btn btn--phrase" onClick={() => onPick(phrase.phrase)} {...mark}>
      “{phrase.phrase}”
    </button>
  );
}

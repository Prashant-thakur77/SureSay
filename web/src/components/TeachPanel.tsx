import { useState, type FormEvent } from "react";
import { describeMeaning, isLearned, TEACH_CHOICES } from "../lib/phrases";
import type { Phrase } from "../lib/types";
import { Icon } from "./Icon";

/**
 * Teach SureSay one of your own phrases. Submitting opens a card
 * ("Remember: “my fan” means …") that you confirm like anything else.
 */
export function TeachPanel({ phrasebook, onTeach, busy }: { phrasebook: Phrase[]; onTeach: (phrase: string, action: string, args: Record<string, unknown>) => void; busy: boolean }) {
  const [phrase, setPhrase] = useState("");
  const [choice, setChoice] = useState(TEACH_CHOICES[0].id);
  const [sentence, setSentence] = useState("");
  const [error, setError] = useState("");
  const picked = TEACH_CHOICES.find((c) => c.id === choice) ?? TEACH_CHOICES[0];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const words = phrase.trim();
    if (!words) {
      setError("Type what you say first, for example: my fan.");
      document.getElementById("teach-phrase")?.focus();
      return;
    }
    if (picked.sentence && !sentence.trim()) {
      setError("Type the sentence I should say.");
      document.getElementById("teach-sentence")?.focus();
      return;
    }
    setError("");
    const args = picked.sentence ? { text: sentence.trim() } : picked.args;
    onTeach(words, picked.action, args);
    setPhrase("");
    setSentence("");
  };

  const sorted = [...phrasebook].sort((a, b) => Number(isLearned(b)) - Number(isLearned(a)));

  return (
    <section className="teach" aria-labelledby="teach-title">
      <h2 id="teach-title" className="stage__title display">
        Teach me <em>your words</em>
      </h2>
      <p className="stage__lead">Say something your way, and tell me what it means. You confirm it before I learn it.</p>
      <form className="teach__form" onSubmit={submit} noValidate>
        <div className="teach__field">
          <label htmlFor="teach-phrase" className="teach__label">
            When I say…
          </label>
          <input
            id="teach-phrase"
            className="input"
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            placeholder="For example: my fan"
            maxLength={80}
            autoComplete="off"
            aria-invalid={error && !phrase.trim() ? true : undefined}
            aria-describedby={error ? "teach-error" : undefined}
          />
        </div>
        <fieldset className="teach__choices">
          <legend className="teach__label">I mean…</legend>
          <div className="teach__grid">
            {TEACH_CHOICES.map((c) => (
              <label key={c.id} className="choice__opt">
                <input type="radio" name="teach-choice" checked={c.id === choice} onChange={() => setChoice(c.id)} />
                <span>{c.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {picked.sentence && (
          <div className="teach__field">
            <label htmlFor="teach-sentence" className="teach__label">
              The sentence to say
            </label>
            <input id="teach-sentence" className="input" value={sentence} onChange={(e) => setSentence(e.target.value)} placeholder="For example: Please open the window." maxLength={300} autoComplete="off" />
          </div>
        )}
        {error && (
          <p id="teach-error" className="callout callout--warn" role="alert">
            <Icon name="alert" size={24} /> <span>{error}</span>
          </p>
        )}
        <button type="submit" className="btn btn--primary btn--xl" disabled={busy}>
          <Icon name="book" size={26} /> Teach SureSay
        </button>
      </form>

      <h3 className="teach__subtitle">My phrases</h3>
      {sorted.length === 0 ? (
        <p>No phrases yet.</p>
      ) : (
        <ul className="phrase-list">
          {sorted.map((p) => (
            <li key={p.id} className={`phrase-list__item${isLearned(p) ? " phrase-list__item--learned" : ""}`}>
              <span className="phrase-list__say">“{p.phrase}”</span>
              <span className="phrase-list__means">
                <span className="visually-hidden">means </span>
                <span aria-hidden="true">→ </span>
                {describeMeaning(p.action, p.args)}
              </span>
              {isLearned(p) && <span className="chip-learned">Learned from you</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

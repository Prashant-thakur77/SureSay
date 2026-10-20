import { forwardRef, useState, type FormEvent } from "react";
import { Icon } from "./Icon";

interface Props {
  onSend: (text: string) => void;
  onFocus?: () => void;
  disabled?: boolean;
}

/** "Type instead": a plain text field and a Send button. */
export const TypeBox = forwardRef<HTMLInputElement, Props>(function TypeBox({ onSend, onFocus, disabled }, ref) {
  const [text, setText] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const clean = text.trim();
    if (!clean) return;
    onSend(clean);
    setText("");
  };
  return (
    <form className="typebox" onSubmit={submit} aria-label="Type instead">
      <label htmlFor="type-input" className="typebox__label">
        <Icon name="keyboard" size={24} /> Type instead
      </label>
      <div className="typebox__row">
        <input
          id="type-input"
          ref={ref}
          className="input"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={onFocus}
          placeholder="For example: fan on"
          autoComplete="off"
          enterKeyHint="send"
          maxLength={500}
        />
        <button type="submit" className="btn btn--primary" disabled={disabled}>
          <Icon name="send" size={22} /> Send
        </button>
      </div>
    </form>
  );
});

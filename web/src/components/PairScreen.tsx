import { useEffect, useRef, useState, type FormEvent } from "react";
import { HubError, pairDevice } from "../lib/api";
import { hubUrl } from "../lib/config";
import type { DeviceCreds } from "../lib/types";
import { Icon } from "./Icon";
import { Wordmark } from "./TopBar";

function deviceName(): string {
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const os = /Android/i.test(ua) ? "Android" : /iPhone|iPad/i.test(ua) ? "iOS" : /Mac/i.test(ua) ? "Mac" : /Windows/i.test(ua) ? "Windows" : /Linux/i.test(ua) ? "Linux" : "this device";
  return `Browser on ${os}`;
}

function pairError(err: unknown, base: string): string {
  if (err instanceof HubError) {
    if (err.status === 403) {
      if (/too many/i.test(err.message)) return "Too many wrong codes. Restart SureSay to get a new code, then try again.";
      if (/already been used/i.test(err.message)) return "That code was already used. Restart SureSay to get a new code.";
      return "That code did not work. It may be wrong, or more than 10 minutes old. Check it and try again.";
    }
    return "SureSay could not pair right now. Please try again.";
  }
  return `I can't reach SureSay at ${hubUrl("/", base).origin}. Check that it is running, then try again.`;
}

export function PairScreen({ base, onPaired }: { base: string; onPaired: (creds: DeviceCreds) => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const digits = code.replace(/\D/g, "");
    if (digits.length !== 6) {
      setError("The code has 6 digits. Please type all 6.");
      inputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError("");
    try {
      onPaired(await pairDevice(base, digits, deviceName()));
    } catch (err) {
      setError(pairError(err, base));
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pair">
      <main className="pair__card" aria-labelledby="pair-title">
        <Wordmark />
        <p className="pair__tag">Say it your way. Nothing happens until you choose.</p>
        <form onSubmit={submit} noValidate>
          <h2 id="pair-title" className="pair__title">
            Pair this device
          </h2>
          <label htmlFor="pair-code" className="pair__label">
            Enter the 6-digit code shown where SureSay is running
          </label>
          <input
            id="pair-code"
            ref={inputRef}
            className="input input--code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "pair-error" : undefined}
          />
          {error && (
            <p id="pair-error" className="callout callout--warn" role="alert">
              <Icon name="alert" size={24} /> <span>{error}</span>
            </p>
          )}
          <button type="submit" className="btn btn--primary btn--xl" disabled={busy}>
            {busy ? "Pairing…" : "Pair"}
          </button>
        </form>
      </main>
    </div>
  );
}

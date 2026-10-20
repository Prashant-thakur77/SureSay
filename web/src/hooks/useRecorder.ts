import { useCallback, useEffect, useRef, useState } from "react";
import { MicError, startRecording, type Recording, type RecordingSession } from "../lib/audio";

export type MicState = "idle" | "starting" | "recording";

/**
 * One recording at a time. `record()` resolves when it stops (by itself, by
 * `stop()`), or with null when `cancel()` throws it away. Errors are MicError.
 */
export function useRecorder() {
  const [mic, setMic] = useState<MicState>("idle");
  const [level, setLevel] = useState(0);
  const session = useRef<RecordingSession | null>(null);
  const starting = useRef(false);
  const cancelled = useRef(false);

  const record = useCallback(async (): Promise<Recording | null> => {
    session.current?.cancel();
    session.current = null;
    cancelled.current = false;
    starting.current = true;
    setMic("starting");
    let s: RecordingSession;
    try {
      s = await startRecording({ onLevel: (l) => setLevel(l) });
    } catch (err) {
      starting.current = false;
      setMic("idle");
      throw err instanceof MicError ? err : new MicError("other", "The microphone could not start. You can type instead.");
    }
    starting.current = false;
    if (cancelled.current) {
      s.cancel();
      setMic("idle");
      return null;
    }
    session.current = s;
    setMic("recording");
    const result = await s.done;
    if (session.current === s) session.current = null;
    setMic("idle");
    setLevel(0);
    return result;
  }, []);

  const stop = useCallback(() => {
    if (starting.current) cancelled.current = true;
    session.current?.stop();
  }, []);

  const cancel = useCallback(() => {
    if (starting.current) cancelled.current = true;
    session.current?.cancel();
  }, []);

  useEffect(() => () => session.current?.cancel(), []);

  return { mic, level, record, stop, cancel };
}

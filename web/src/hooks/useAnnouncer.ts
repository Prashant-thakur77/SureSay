import { useCallback, useRef, useState } from "react";

export type Politeness = "assertive" | "polite";

/**
 * Text for the two live regions. Each message is cleared first and set on the
 * next frame, so saying the same words twice is still announced.
 */
export function useAnnouncer() {
  const [assertive, setAssertive] = useState("");
  const [polite, setPolite] = useState("");
  const timers = useRef<Record<Politeness, ReturnType<typeof setTimeout> | undefined>>({
    assertive: undefined,
    polite: undefined,
  });

  const announce = useCallback((message: string, level: Politeness = "polite") => {
    const set = level === "assertive" ? setAssertive : setPolite;
    set("");
    clearTimeout(timers.current[level]);
    timers.current[level] = setTimeout(() => set(message), 60);
  }, []);

  return { assertive, polite, announce };
}

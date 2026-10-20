import { useEffect, useState } from "react";

function secondsLeft(deadline: number | null): number | null {
  return deadline == null ? null : Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
}

/** Whole seconds left until `deadline` (ms since epoch), ticking once a second. */
export function useCountdown(deadline: number | null): number | null {
  const [left, setLeft] = useState<number | null>(() => secondsLeft(deadline));

  useEffect(() => {
    setLeft(secondsLeft(deadline));
    if (deadline == null) return;
    const t = setInterval(() => setLeft(secondsLeft(deadline)), 1000);
    return () => clearInterval(t);
  }, [deadline]);

  return left;
}

export function formatSeconds(s: number): string {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

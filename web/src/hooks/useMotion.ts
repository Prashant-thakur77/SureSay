import { useEffect, useState } from "react";

function reduced(): boolean {
  try {
    return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** True when animation is allowed: no reduced-motion preference, and Calm mode is off. */
export function useMotionOK(calm: boolean): boolean {
  const [prefersReduced, setPrefersReduced] = useState(reduced);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setPrefersReduced(q.matches);
    q.addEventListener?.("change", on);
    return () => q.removeEventListener?.("change", on);
  }, []);
  return !calm && !prefersReduced;
}

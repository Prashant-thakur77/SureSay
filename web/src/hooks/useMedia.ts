import { useEffect, useState } from "react";

/** A phone: the 480 px breakpoint of the other phone rules. */
export const NARROW = "(max-width: 30em)";

/** Whether a media query matches right now (false where it can't be asked). */
export function matches(query: string): boolean {
  try {
    return window.matchMedia(query).matches;
  } catch {
    return false;
  }
}

/** Whether a media query matches now, following it as the screen turns or the window is resized. */
export function useMedia(query: string): boolean {
  const [on, setOn] = useState(() => matches(query));
  useEffect(() => {
    let q: MediaQueryList;
    try {
      q = window.matchMedia(query);
    } catch {
      return;
    }
    const update = () => setOn(q.matches);
    update();
    q.addEventListener?.("change", update);
    return () => q.removeEventListener?.("change", update);
  }, [query]);
  return on;
}

import { useEffect, useRef, useState } from "react";

export interface ScanItem {
  id: string;
  label: string;
  activate: () => void;
}

const IGNORED_KEYS = new Set(["Tab", "Shift", "Control", "Alt", "Meta", "CapsLock", "Fn"]);

/**
 * Single-switch scanning. The highlight moves through `items` every `speedS`
 * seconds; any key (a switch sends one), or a click anywhere, picks the
 * highlighted item. Tab and modifier keys still work, so a keyboard user is
 * never trapped. Elements inside `[data-scan-exempt]` (top bar, dialogs) keep
 * their normal clicks.
 */
export function useScan(items: ScanItem[], enabled: boolean, speedS: number, onHighlight: (label: string) => void) {
  const [index, setIndex] = useState(0);
  const itemsRef = useRef(items);
  const indexRef = useRef(0);
  const onHighlightRef = useRef(onHighlight);
  itemsRef.current = items;
  onHighlightRef.current = onHighlight;
  const signature = items.map((i) => i.id).join("|");
  const active = enabled && items.length > 0;

  // restart from the top whenever the set of items changes
  useEffect(() => {
    indexRef.current = 0;
    setIndex(0);
    if (active) onHighlightRef.current(itemsRef.current[0]?.label ?? "");
  }, [signature, active]);

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => {
      const n = itemsRef.current.length;
      if (n < 2) return;
      indexRef.current = (indexRef.current + 1) % n;
      setIndex(indexRef.current);
      onHighlightRef.current(itemsRef.current[indexRef.current]?.label ?? "");
    }, speedS * 1000);
    return () => clearInterval(t);
  }, [active, speedS, signature]);

  useEffect(() => {
    if (!active) return;
    const pick = () => itemsRef.current[indexRef.current]?.activate();
    const exempt = (target: EventTarget | null) =>
      target instanceof Element && !!target.closest("[data-scan-exempt], [role=dialog]");
    let lastKeyPick = 0;
    const onKey = (e: KeyboardEvent) => {
      if (IGNORED_KEYS.has(e.key) || exempt(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.repeat) return;
      lastKeyPick = Date.now();
      pick();
    };
    // a key released on a focused button must not click it as well
    const onKeyUp = (e: KeyboardEvent) => {
      if (IGNORED_KEYS.has(e.key) || exempt(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
    };
    const onClick = (e: MouseEvent) => {
      if (exempt(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      if (Date.now() - lastKeyPick < 400) return;
      pick();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("click", onClick, true);
    };
  }, [active]);

  return active ? (items[index]?.id ?? null) : null;
}

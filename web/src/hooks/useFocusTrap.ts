import { useEffect, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Keep Tab inside `ref` while `active`, close on Escape, and give focus back to
 * whatever had it before when the trap ends.
 */
export function useFocusTrap(ref: RefObject<HTMLElement>, active: boolean, onClose: () => void) {
  useEffect(() => {
    if (!active) return;
    const node = ref.current;
    if (!node) return;
    const before = document.activeElement as HTMLElement | null;
    const first = node.querySelector<HTMLElement>("[data-autofocus]") ?? node.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node).focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // an open menu inside the dialog closes first
        if (e.target instanceof Element && e.target.closest("[data-esc-local='open']")) return;
        e.preventDefault();
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === firstEl || !node.contains(document.activeElement))) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      // after the page behind stops being inert
      setTimeout(() => {
        if (before && document.contains(before)) before.focus();
      }, 0);
    };
  }, [ref, active, onClose]);
}

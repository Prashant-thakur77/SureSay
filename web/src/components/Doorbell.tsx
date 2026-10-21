/**
 * The doorbell (simulated: there is no doorbell account). A press opens the
 * door's card set, answered exactly like any other cards; unlocking still
 * asks twice.
 */

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import type { Visitor } from "../lib/types";
import { Icon } from "./Icon";

export type VisitorId = "ravi" | "delivery" | "unknown";

export const VISITOR_CHOICES: Array<{ id: VisitorId; label: string }> = [
  { id: "ravi", label: "Ravi, your carer" },
  { id: "delivery", label: "A delivery driver" },
  { id: "unknown", label: "Someone you may not know" },
];

/** A simple silhouette tile: no photos. Delivery carries a parcel, the carer a badge, a stranger a question mark. */
export function VisitorArt({ id }: { id: string }) {
  const g = `v-${useId().replace(/:/g, "")}`;
  return (
    <svg className={`visitor-art visitor-art--${id}`} viewBox="0 0 96 96" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={g} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFB547" />
          <stop offset="0.55" stopColor="#FF6B5A" />
          <stop offset="1" stopColor="#7B5CFF" />
        </linearGradient>
      </defs>
      <rect className="visitor-art__tile" x="2" y="2" width="92" height="92" rx="22" fill={`url(#${g})`} />
      <rect className="visitor-art__door" x="22" y="14" width="52" height="82" rx="4" />
      <circle className="visitor-art__person" cx="48" cy="40" r="12" />
      <path className="visitor-art__person" d="M24 96c0-16 11-27 24-27s24 11 24 27z" />
      {id === "delivery" && (
        <g className="visitor-art__prop">
          <rect x="52" y="64" width="26" height="22" rx="2" />
          <path d="M52 72h26M65 64v8" />
        </g>
      )}
      {id === "ravi" && (
        <g className="visitor-art__prop">
          <rect x="54" y="74" width="14" height="10" rx="2" />
          <path d="M61 76v6M58 79h6" />
        </g>
      )}
      {id === "unknown" && (
        <text className="visitor-art__mark" x="48" y="45" textAnchor="middle">
          ?
        </text>
      )}
    </svg>
  );
}

export function DoorbellHeader({ visitor }: { visitor?: Visitor }) {
  return (
    <div className="doorbell">
      <VisitorArt id={visitor?.id ?? "unknown"} />
      <div className="doorbell__text">
        <p className="doorbell__eyebrow">
          <span className="doorbell__bell" aria-hidden="true">
            <Icon name="bell" size="100%" />
          </span>
          Doorbell
        </p>
        <h2 className="stage__title display">
          Someone's <em>at the door</em>
        </h2>
        {visitor?.note && <p className="doorbell__note">{visitor.note}</p>}
      </div>
    </div>
  );
}

/** "Doorbell (demo)" with a small list of visitors. A disclosure, so it works with any keyboard or switch. */
export function DoorbellMenu({ onRing, label = "Doorbell (demo)" }: { onRing: (id: VisitorId) => void; label?: string }) {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const listId = useId();
  // move focus into the list once it is shown
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => list.current?.querySelector<HTMLButtonElement>("button")?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape" && open) {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
      toggle.current?.focus();
    }
  };
  return (
    <div className="doormenu" onKeyDown={onKey} data-esc-local={open ? "open" : undefined}>
      <button ref={toggle} type="button" className="btn btn--secondary" aria-expanded={open} aria-controls={listId} onClick={() => setOpen((o) => !o)}>
        <Icon name="bell" size={24} /> {label}
      </button>
      <ul id={listId} ref={list} className="doormenu__list" hidden={!open} aria-label="Who is at the door?">
        {VISITOR_CHOICES.map((v) => (
          <li key={v.id}>
            <button
              type="button"
              className="btn btn--secondary doormenu__item"
              onClick={() => {
                setOpen(false);
                onRing(v.id);
              }}
            >
              <VisitorArt id={v.id} />
              {v.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

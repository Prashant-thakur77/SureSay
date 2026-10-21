import type { ReactElement } from "react";
import type { IconName } from "../lib/words";

type Name = IconName | "mic" | "stop" | "gear" | "check" | "close" | "alert" | "clock" | "keyboard" | "refresh" | "list" | "shield" | "chevron" | "send" | "volume" | "door" | "hand";

const PATHS: Record<Name, ReactElement> = {
  bulb: (
    <>
      <path d="M9 18h6M10 21h4" />
      <path d="M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.4 1.1 2.2h5c0-.8.4-1.6 1.1-2.2A6 6 0 0 0 12 3z" />
    </>
  ),
  fan: (
    <>
      <circle cx="12" cy="12" r="1.6" />
      <path d="M12 10.4c-1-3.4.2-6.4 2.6-6.4 2.2 0 2.6 3.4-2.6 6.4z" />
      <path d="M13.4 12.9c3.4.9 5.4 3.5 4.2 5.5-1.1 1.9-4.2.6-4.2-5.5z" />
      <path d="M10.6 12.9c-2.5 2.5-5.7 3-6.9 1-1.1-1.9 1.6-3.9 6.9-1z" />
    </>
  ),
  snow: (
    <>
      <path d="M12 2v20M3.3 7l17.4 10M3.3 17L20.7 7" />
      <path d="M9.5 3.5L12 6l2.5-2.5M9.5 20.5L12 18l2.5 2.5M3.6 10.4l3.4-.9-.9-3.4M20.4 13.6l-3.4.9.9 3.4M6.1 17.9l.9-3.4-3.4-.9M17.9 6.1l-.9 3.4 3.4.9" />
    </>
  ),
  tv: (
    <>
      <rect x="2.5" y="5" width="19" height="12.5" rx="2" />
      <path d="M8 21h8M12 17.5V21" />
    </>
  ),
  lock: (
    <>
      <rect x="4.5" y="10.5" width="15" height="10.5" rx="2" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
      <path d="M12 14.5v3" />
    </>
  ),
  unlock: (
    <>
      <rect x="4.5" y="10.5" width="15" height="10.5" rx="2" />
      <path d="M8 10.5V7.5a4 4 0 0 1 7.6-1.8" />
      <path d="M12 14.5v3" />
    </>
  ),
  door: (
    <>
      <path d="M5 21V4a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v17" />
      <path d="M3 21h18" />
      <circle cx="15" cy="12.5" r="1" />
    </>
  ),
  phone: <path d="M5 3.5h3.2l1.6 4.2-2 1.3a11 11 0 0 0 5.2 5.2l1.3-2 4.2 1.6V17a2 2 0 0 1-2.2 2A15.5 15.5 0 0 1 3 5.7 2 2 0 0 1 5 3.5z" />,
  message: (
    <>
      <path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V6a1 1 0 0 1 1-1z" />
      <path d="M8 9.5h8M8 12.5h5" />
    </>
  ),
  cart: (
    <>
      <path d="M2.5 3.5h2.6l2.3 11.2a1.5 1.5 0 0 0 1.5 1.2h8.5a1.5 1.5 0 0 0 1.4-1.1L20.5 7H6" />
      <circle cx="9.5" cy="20" r="1.4" />
      <circle cx="17" cy="20" r="1.4" />
    </>
  ),
  speech: (
    <>
      <path d="M12 3.5c5 0 9 3.2 9 7.3s-4 7.2-9 7.2c-1 0-2-.1-2.9-.4L4.5 20l1.2-3.9C4 14.8 3 12.9 3 10.8 3 6.7 7 3.5 12 3.5z" />
      <path d="M8 10.8h.01M12 10.8h.01M16 10.8h.01" />
    </>
  ),
  book: (
    <>
      <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z" />
      <path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20v-3M8.5 7.5h7M8.5 10.5h5" />
    </>
  ),
  home: (
    <>
      <path d="M3 11l9-7.5 9 7.5" />
      <path d="M5.5 9.5V20h13V9.5M10 20v-5.5h4V20" />
    </>
  ),
  spark: <path d="M12 3l1.9 5.3L19 10l-5.1 1.8L12 17l-1.9-5.2L5 10l5.1-1.7zM18.5 16l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />,
  mic: (
    <>
      <rect x="8.5" y="2.5" width="7" height="12" rx="3.5" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3.5M8.5 21.5h7" />
    </>
  ),
  stop: <rect x="6" y="6" width="12" height="12" rx="2.5" />,
  gear: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.5v2.6M12 18.9v2.6M21.5 12h-2.6M5.1 12H2.5M18.7 5.3l-1.8 1.8M7.1 16.9l-1.8 1.8M18.7 18.7l-1.8-1.8M7.1 7.1L5.3 5.3" />
      <circle cx="12" cy="12" r="6.4" />
    </>
  ),
  check: <path d="M4.5 12.5l5 5 10-11" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  alert: (
    <>
      <path d="M12 3.2L1.9 20.5h20.2z" />
      <path d="M12 9.5v5M12 17.6v.01" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5.2l3.4 2" />
    </>
  ),
  keyboard: (
    <>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <path d="M6 10h.01M9.5 10h.01M13 10h.01M16.5 10h.01M7.5 14h9" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 12a8 8 0 1 1-2.4-5.7" />
      <path d="M20 4v5h-5" />
    </>
  ),
  list: <path d="M8.5 6.5H20M8.5 12H20M8.5 17.5H20M4 6.5h.01M4 12h.01M4 17.5h.01" />,
  shield: (
    <>
      <path d="M12 2.8l7.5 3v5.6c0 4.6-3.2 8.3-7.5 9.8-4.3-1.5-7.5-5.2-7.5-9.8V5.8z" />
      <path d="M8.6 12.2l2.4 2.4 4.6-4.9" />
    </>
  ),
  chevron: <path d="M8 10l4 4 4-4" />,
  send: <path d="M3.5 11.5L20.5 4l-6.8 16.5-2.6-6.9z" />,
  bell: (
    <>
      <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z" />
      <path d="M10 21a2 2 0 0 0 4 0M12 3v2" />
    </>
  ),
  hand: (
    <>
      <path d="M8.5 12.5V5.8a1.5 1.5 0 0 1 3 0v5.7" />
      <path d="M11.5 11V4.6a1.5 1.5 0 0 1 3 0V11" />
      <path d="M14.5 11V6.2a1.5 1.5 0 0 1 3 0v7.3c0 4-2.6 7-6.4 7-2.4 0-4-1-5.3-3l-2.5-3.9a1.5 1.5 0 0 1 2.4-1.8l1.8 2" />
    </>
  ),
  volume: (
    <>
      <path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" />
      <path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" />
    </>
  ),
};

export type AnyIcon = Name;

export function Icon({ name, size = 28, className }: { name: Name; size?: number | string; className?: string }) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}

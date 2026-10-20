import { forwardRef } from "react";
import { Icon } from "./Icon";
import type { McpInfo } from "./SidePanel";

export function Wordmark({ as: Tag = "h1" }: { as?: "h1" | "p" }) {
  return (
    <Tag className="wordmark">
      <span className="wordmark__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="100%" height="100%">
          <rect x="1" y="1" width="30" height="30" rx="9" fill="currentColor" />
          <path d="M9 16.5l4.5 4.5L23 11" fill="none" stroke="var(--on-ink)" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      SureSay
    </Tag>
  );
}

export function McpChip({ mcp }: { mcp: McpInfo }) {
  const text =
    mcp.status === "connected"
      ? `MCP connected${mcp.protocol ? ` · protocol ${mcp.protocol}` : ""}`
      : mcp.status === "connecting"
        ? "MCP connecting…"
        : "MCP offline · using fallback";
  return (
    <span className={`chip chip--${mcp.status}`} data-testid="mcp-chip">
      <span className="chip__dot" aria-hidden="true" />
      {text}
    </span>
  );
}

interface Props {
  user: string;
  mcp: McpInfo;
  onSettings: () => void;
}

export const TopBar = forwardRef<HTMLButtonElement, Props>(function TopBar({ user, mcp, onSettings }, ref) {
  return (
    <header className="topbar" data-scan-exempt>
      <a href="#main" className="skip">
        Skip to the conversation
      </a>
      <Wordmark />
      <div className="topbar__meta">
        <span className="chip chip--user">
          <span className="visually-hidden">Signed in as </span>
          <span aria-hidden="true">User:</span> {user}
        </span>
        <McpChip mcp={mcp} />
      </div>
      <button ref={ref} type="button" className="btn btn--secondary topbar__settings" onClick={onSettings} aria-haspopup="dialog">
        <Icon name="gear" size={26} />
        Settings
      </button>
    </header>
  );
});

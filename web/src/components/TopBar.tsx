import { forwardRef, useId } from "react";
import { Icon } from "./Icon";
import type { McpInfo } from "./SidePanel";

export function Wordmark({ as: Tag = "h1" }: { as?: "h1" | "p" }) {
  const gid = `dawn-${useId().replace(/:/g, "")}`;
  return (
    <Tag className="wordmark">
      <span className="wordmark__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="100%" height="100%">
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#FFB547" />
              <stop offset="0.5" stopColor="#FF6B5A" />
              <stop offset="1" stopColor="#7B5CFF" />
            </linearGradient>
          </defs>
          <rect className="wordmark__tile" x="1" y="1" width="30" height="30" rx="9" fill={`url(#${gid})`} />
          <path className="wordmark__tick" d="M9 16.5l4.5 4.5L23 11" fill="none" stroke="#ffffff" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span>
        Sure<em className="wordmark__say">Say</em>
      </span>
    </Tag>
  );
}

export function McpChip({ mcp }: { mcp: McpInfo }) {
  // the first second after opening: a quiet dot, no words, until it is connected or has fallen back
  if (mcp.status === "connecting") {
    return (
      <span className="chip chip--connecting" data-testid="mcp-chip">
        <span className="chip__dot" aria-hidden="true" />
        <span className="visually-hidden">MCP starting</span>
      </span>
    );
  }
  const text = mcp.status === "connected" ? `MCP connected${mcp.protocol ? ` · protocol ${mcp.protocol}` : ""}` : "MCP offline · using fallback";
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
  /** The Help button: offers to call or message his carer (still confirmed like everything else). */
  onHelp?: () => void;
  /** Opens the simulated Alexa+ screen (SureSay's MCP server and card app inside an assistant). */
  onAlexa?: () => void;
  /** Big-screen mode: the side panel hides behind a "Home" button. */
  sideToggle?: { open: boolean; onToggle: () => void };
}

export const TopBar = forwardRef<HTMLButtonElement, Props>(function TopBar({ user, mcp, onSettings, onHelp, onAlexa, sideToggle }, ref) {
  return (
    <header className="topbar" data-scan-exempt>
      <a href="#main" className="skip">
        Skip to the conversation
      </a>
      <a href="/?home" className="topbar__home" aria-label="About SureSay (home page)">
        <Wordmark />
      </a>
      <div className="topbar__meta">
        {user.startsWith("guest-") ? (
          <span className="chip chip--user chip--demo">
            <span className="visually-hidden">Using a </span>Demo<span className="visually-hidden"> home</span>
          </span>
        ) : (
          <span className="chip chip--user">
            <span className="visually-hidden">Signed in as </span>
            <span aria-hidden="true">User:</span> {user}
          </span>
        )}
        <McpChip mcp={mcp} />
      </div>
      {sideToggle && (
        <button type="button" className="btn btn--secondary" aria-expanded={sideToggle.open} aria-controls="side-panel" onClick={sideToggle.onToggle}>
          <Icon name="home" size={26} />
          {sideToggle.open ? "Hide home" : "Home"}
        </button>
      )}
      {onAlexa && (
        <button type="button" className="btn btn--secondary topbar__alexa" onClick={onAlexa} aria-haspopup="dialog">
          <Icon name="speech" size={24} />
          <span className="topbar__label">Alexa+ view</span>
        </button>
      )}
      {onHelp && (
        <button type="button" className="btn topbar__help" onClick={onHelp}>
          <Icon name="alert" size={24} />
          Help
        </button>
      )}
      <button ref={ref} type="button" className="btn btn--secondary topbar__settings" onClick={onSettings} aria-haspopup="dialog">
        <Icon name="gear" size={26} />
        <span className="topbar__label">Settings</span>
      </button>
    </header>
  );
});

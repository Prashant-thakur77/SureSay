import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { Icon, type AnyIcon } from "./Icon";

export interface TabDef<T extends string> {
  id: T;
  label: string;
  icon: AnyIcon;
}

/**
 * ARIA tabs with automatic activation: Left/Right (and Home/End) move focus
 * and select; only the selected tab is in the Tab order.
 */
export function TabList<T extends string>({ tabs, active, onChange, label }: { tabs: TabDef<T>[]; active: T; onChange: (id: T) => void; label: string }) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    e.stopPropagation();
    onChange(tabs[next].id);
    refs.current[next]?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={t.id === active}
          aria-controls={`panel-tab-${t.id}`}
          tabIndex={t.id === active ? 0 : -1}
          className={`tab${t.id === active ? " tab--active" : ""}`}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKey(e, i)}
        >
          <Icon name={t.icon} size={24} />
          <span>{t.label}</span>
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, active, children }: { id: string; active: boolean; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-tab-${id}`} aria-labelledby={`tab-${id}`} hidden={!active} className="tabpanel">
      {children}
    </div>
  );
}

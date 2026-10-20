import { useRef, useState } from "react";
import { useFocusTrap } from "../hooks/useFocusTrap";
import type { ScanSpeed, Settings, TextScale, ThemeChoice } from "../hooks/useSettings";
import { Icon } from "./Icon";

interface Props {
  open: boolean;
  settings: Settings;
  tvFromUrl: boolean;
  onChange: (patch: Partial<Settings>) => void;
  onClose: () => void;
  onResetHome: () => Promise<void>;
  onUnpair: () => void;
}

function Choice<T extends string | number>({ legend, name, value, options, onChange }: { legend: string; name: string; value: T; options: Array<{ value: T; label: string }>; onChange: (v: T) => void }) {
  return (
    <fieldset className="choice">
      <legend>{legend}</legend>
      <div className="choice__row">
        {options.map((o) => (
          <label key={String(o.value)} className="choice__opt">
            <input type="radio" name={name} checked={o.value === value} onChange={() => onChange(o.value)} />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Toggle({ label, hint, checked, onChange, disabled }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="toggle">
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle__track" aria-hidden="true">
        <span className="toggle__thumb" />
      </span>
      <span className="toggle__text">
        <span className="toggle__label">{label}</span>
        {hint && <span className="toggle__hint">{hint}</span>}
        <span className="toggle__state" aria-hidden="true">
          {checked ? "On" : "Off"}
        </span>
      </span>
    </label>
  );
}

/** Settings: an accessible modal. Tab stays inside, Escape closes, focus returns to the Settings button. */
export function SettingsDialog({ open, settings, tvFromUrl, onChange, onClose, onResetHome, onUnpair }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("");
  const [confirmUnpair, setConfirmUnpair] = useState(false);
  useFocusTrap(ref, open, onClose);
  if (!open) return null;

  const reset = async () => {
    setStatus("Resetting…");
    try {
      await onResetHome();
      setStatus("Done. The demo home is back to the start.");
    } catch {
      setStatus("That did not work. Check that SureSay is running, then try again.");
    }
  };

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title" ref={ref}>
        <div className="dialog__head">
          <h2 id="settings-title">Settings</h2>
          <button type="button" className="btn btn--icon" onClick={onClose} data-autofocus>
            <Icon name="close" size={26} />
            <span>Close</span>
          </button>
        </div>
        <div className="dialog__body">
          <Choice<string>
            legend="Text size"
            name="text-size"
            value={String(settings.textScale)}
            options={[
              { value: "1", label: "100%" },
              { value: "1.25", label: "125%" },
              { value: "1.5", label: "150%" },
              { value: "2", label: "200%" },
            ]}
            onChange={(v) => onChange({ textScale: Number(v) as TextScale })}
          />
          <Choice<ThemeChoice>
            legend="Colours"
            name="theme"
            value={settings.theme}
            options={[
              { value: "auto", label: "Match my device" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
              { value: "contrast", label: "High contrast" },
            ]}
            onChange={(v) => onChange({ theme: v })}
          />
          <fieldset className="choice">
            <legend>Speech</legend>
            <Toggle label="Read aloud" hint="Read the cards and results out loud." checked={settings.readAloud} onChange={(v) => onChange({ readAloud: v })} />
            <Toggle label="Answer by voice automatically" hint="After the cards are read, listen for your answer." checked={settings.autoVoice} onChange={(v) => onChange({ autoVoice: v })} />
          </fieldset>
          <fieldset className="choice">
            <legend>Motion</legend>
            <Toggle
              label="Calm mode: no animation"
              hint="Everything appears at once. Nothing moves, pulses or draws itself."
              checked={settings.calm}
              onChange={(v) => onChange({ calm: v })}
            />
          </fieldset>
          <fieldset className="choice">
            <legend>Switch and screen</legend>
            <Toggle label="Single-switch scanning" hint="A highlight moves through the choices. Press any key or click to pick." checked={settings.scan} onChange={(v) => onChange({ scan: v })} />
            {settings.scan && (
              <Choice<string>
                legend="Scan speed (seconds per item)"
                name="scan-speed"
                value={String(settings.scanSpeed)}
                options={[
                  { value: "1", label: "1 s" },
                  { value: "1.5", label: "1.5 s" },
                  { value: "2", label: "2 s" },
                  { value: "3", label: "3 s" },
                ]}
                onChange={(v) => onChange({ scanSpeed: Number(v) as ScanSpeed })}
              />
            )}
            <Toggle
              label="Big screen (10-foot) layout"
              hint={tvFromUrl ? "On because the address has ?tv=1." : "Three cards side by side, for a TV."}
              checked={settings.bigScreen || tvFromUrl}
              disabled={tvFromUrl}
              onChange={(v) => onChange({ bigScreen: v })}
            />
          </fieldset>
          <fieldset className="choice">
            <legend>Demo and device</legend>
            <div className="dialog__actions">
              <button type="button" className="btn btn--secondary" onClick={() => void reset()}>
                <Icon name="refresh" size={24} /> Reset demo home
              </button>
              {!confirmUnpair ? (
                <button type="button" className="btn btn--danger" onClick={() => setConfirmUnpair(true)}>
                  <Icon name="unlock" size={24} /> Unpair this device
                </button>
              ) : (
                <div className="confirm-row" role="group" aria-label="Unpair this device?">
                  <p>Unpair? You will need a new code to use SureSay here.</p>
                  <button type="button" className="btn btn--danger" onClick={onUnpair} autoFocus>
                    Yes, unpair
                  </button>
                  <button type="button" className="btn btn--secondary" onClick={() => setConfirmUnpair(false)}>
                    Keep it paired
                  </button>
                </div>
              )}
            </div>
            <p role="status" className="dialog__status">
              {status}
            </p>
          </fieldset>
        </div>
      </div>
    </div>
  );
}

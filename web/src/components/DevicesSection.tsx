import { useEffect, useState } from "react";
import type { PairedDevice } from "../lib/types";
import { Icon } from "./Icon";

interface Props {
  load: () => Promise<PairedDevice[]>;
  unpair: (deviceId: string) => Promise<void>;
}

const KIND: Record<PairedDevice["kind"], { label: string; icon: "home" | "speech" | "spark" }> = {
  screen: { label: "Screen", icon: "home" },
  voice: { label: "Voice device", icon: "speech" },
  link: { label: "Assistant link", icon: "spark" },
};

/** The user's own devices and assistant links. Unpairing a link ends that assistant's access at once. */
export function DevicesSection({ load, unpair }: Props) {
  const [devices, setDevices] = useState<PairedDevice[] | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let live = true;
    load()
      .then((d) => live && setDevices(d))
      .catch(() => live && setStatus("Could not load your devices."));
    return () => {
      live = false;
    };
  }, [load]);

  const label = (d: PairedDevice) => (d.kind === "link" ? d.name.replace(/^Linked:\s*/, "") : d.name || "Unnamed device");

  const remove = async (d: PairedDevice) => {
    setAsking(null);
    try {
      await unpair(d.device_id);
      setDevices((list) => (list ?? []).filter((x) => x.device_id !== d.device_id));
      setStatus(`${label(d)} is unpaired.`);
    } catch {
      setStatus(`That did not work. ${label(d)} is still paired.`);
    }
  };

  return (
    <fieldset className="choice devices">
      <legend>Your devices</legend>
      <p className="devices__hint">Everything that can show your cards or suggest actions. Only your own tap or voice confirms anything.</p>
      {devices === null ? (
        <p>Loading…</p>
      ) : (
        <ul className="devices__list" aria-label="Your devices">
          {devices.map((d) => (
            <li key={d.device_id} className="devices__item">
              <Icon name={KIND[d.kind].icon} size={24} />
              <span className="devices__name">
                <span>{label(d)}</span>
                <span className="devices__kind">
                  {KIND[d.kind].label}
                  {d.this_device ? " · this device" : ""}
                </span>
              </span>
              {!d.this_device &&
                (asking === d.device_id ? (
                  <span className="confirm-row" role="group" aria-label={`Unpair ${label(d)}?`}>
                    <p>
                      {d.kind === "link"
                        ? `${label(d)} can no longer suggest actions for you.`
                        : `${label(d)} will need a new code to work again.`}
                    </p>
                    <button type="button" className="btn btn--danger" onClick={() => void remove(d)} autoFocus>
                      {d.kind === "link" ? "Yes, end the link" : "Yes, unpair"}
                    </button>
                    <button type="button" className="btn btn--secondary" onClick={() => setAsking(null)}>
                      Keep it
                    </button>
                  </span>
                ) : (
                  <button type="button" className="btn btn--secondary" aria-label={`Unpair ${label(d)}`} onClick={() => setAsking(d.device_id)}>
                    Unpair
                  </button>
                ))}
            </li>
          ))}
        </ul>
      )}
      <p role="status" className="dialog__status">
        {status}
      </p>
    </fieldset>
  );
}

import { useMemo, useState } from "react";
import { MainScreen } from "./components/MainScreen";
import { PairScreen } from "./components/PairScreen";
import { HomePage } from "./components/HomePage";
import type { StartChoice } from "./components/StartGate";
import { useSettings } from "./hooks/useSettings";
import { HubClient } from "./lib/api";
import { hubBaseUrl } from "./lib/config";
import { McpGate } from "./lib/mcp";
import { Speaker } from "./lib/speech";
import { KEYS, readJson, remove, writeJson } from "./lib/storage";
import type { DeviceCreds } from "./lib/types";

function savedCreds(): DeviceCreds | null {
  const c = readJson<Partial<DeviceCreds>>(KEYS.device);
  if (c && typeof c.device_id === "string" && typeof c.key === "string" && typeof c.user_id === "string") {
    return { device_id: c.device_id, user_id: c.user_id, key: c.key, name: typeof c.name === "string" ? c.name : "" };
  }
  return null;
}

/** `?home` shows the home page again after the first run (the app's "About SureSay" link). */
function wantsHome(): boolean {
  try {
    return new URLSearchParams(window.location.search).has("home");
  } catch {
    return false;
  }
}

function setQuery(change: (q: URLSearchParams) => void): void {
  try {
    const url = new URL(window.location.href);
    change(url.searchParams);
    window.history.replaceState(null, "", url.toString());
  } catch {
    /* ignore */
  }
}

function savedStart(): StartChoice | null {
  const v = readJson<string>(KEYS.start);
  return v === "voice" || v === "quiet" ? v : null;
}

export function App() {
  const { settings, update, bigScreen } = useSettings();
  const [creds, setCreds] = useState<DeviceCreds | null>(savedCreds);
  const [start, setStart] = useState<StartChoice | null>(savedStart);
  const [home, setHome] = useState(wantsHome);
  const base = hubBaseUrl();

  const services = useMemo(() => {
    if (!creds) return null;
    const hub = new HubClient(base, creds);
    return { hub, gate: new McpGate(hub), speaker: new Speaker(hub) };
  }, [base, creds]);

  const choose = (choice: StartChoice) => {
    const voice = choice === "voice";
    update({ readAloud: voice, autoVoice: voice });
    writeJson(KEYS.start, choice);
    setQuery((q) => q.delete("home"));
    setHome(false);
    setStart(choice);
  };

  if (!start || home) {
    return (
      <HomePage
        calm={settings.calm}
        onChoose={choose}
        onAlexa={() => {
          // straight on to the simulated Alexa+ screen once there is a device (Try it now, or pairing)
          setQuery((q) => q.set("alexa", "1"));
          choose("quiet");
          document.documentElement.scrollTop = 0;
        }}
      />
    );
  }

  if (!creds || !services) {
    return (
      <PairScreen
        base={base}
        onPaired={(c) => {
          writeJson(KEYS.device, c);
          setCreds(c);
        }}
      />
    );
  }

  return (
    <MainScreen
      key={creds.device_id}
      {...services}
      settings={settings}
      bigScreen={bigScreen}
      onSettingsChange={update}
      onUnpair={() => {
        services.speaker.cancel();
        remove(KEYS.device);
        setCreds(null);
      }}
    />
  );
}

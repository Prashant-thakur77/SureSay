import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { HomePage } from "./components/HomePage";
import type { StartChoice } from "./components/StartGate";
import { useSettings } from "./hooks/useSettings";
import { HubClient, tryDemo } from "./lib/api";
import { hubBaseUrl } from "./lib/config";
import { McpGate } from "./lib/mcp";

// the home page loads first and alone; the app, pairing and the MCP client come when they are needed
const MainScreen = lazy(() => import("./components/MainScreen").then((m) => ({ default: m.MainScreen })));
const PairScreen = lazy(() => import("./components/PairScreen").then((m) => ({ default: m.PairScreen })));
const loading = <p className="visually-hidden" role="status">Loading SureSay…</p>;
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

/** `?alexa=1`: a link straight to the simulated Alexa+ screen. */
function wantsAlexa(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("alexa") === "1";
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
  // a first visit by an ?alexa=1 link: make a demo home (as "Try it now" does) and open the Alexa+ view on it
  const [demoing, setDemoing] = useState(() => !creds && !home && wantsAlexa());
  const demo = useRef<Promise<DeviceCreds> | null>(null);

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

  useEffect(() => {
    if (!demoing) return;
    let alive = true;
    // one demo home per page load, even when the effect runs twice
    demo.current ??= tryDemo(base);
    demo.current.then(
      (c) => {
        if (!alive) return;
        writeJson(KEYS.device, c);
        setCreds(c);
        // a quiet start: no read-aloud and no mic prompt
        if (!savedStart()) choose("quiet");
        setDemoing(false);
      },
      // demo off, too many from here, or no hub: the page it would have shown anyway
      () => alive && setDemoing(false),
    );
    return () => {
      alive = false;
    };
  }, [demoing, base]);

  if (demoing) return <p className="visually-hidden" role="status">Making your demo home…</p>;

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
      <Suspense fallback={loading}>
      <PairScreen
        base={base}
        onPaired={(c) => {
          writeJson(KEYS.device, c);
          setCreds(c);
        }}
      />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={loading}>
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
    </Suspense>
  );
}

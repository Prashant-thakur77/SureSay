import { useMemo, useState } from "react";
import { MainScreen } from "./components/MainScreen";
import { PairScreen } from "./components/PairScreen";
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

export function App() {
  const { settings, update, bigScreen } = useSettings();
  const [creds, setCreds] = useState<DeviceCreds | null>(savedCreds);
  const base = hubBaseUrl();

  const services = useMemo(() => {
    if (!creds) return null;
    const hub = new HubClient(base, creds);
    return { hub, gate: new McpGate(hub), speaker: new Speaker(hub) };
  }, [base, creds]);

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

import { useCallback, useEffect, useRef, useState } from "react";
import { HubError, type HubApi } from "../lib/api";
import type { HubState } from "../lib/types";

export type Connection = "ok" | "offline" | "unpaired";

/** `GET /device/state` every 2 s (paused while the page is hidden), and on demand after each action. */
export function useHubState(hub: HubApi, intervalMs = 2000) {
  const [state, setState] = useState<HubState | null>(null);
  const [connection, setConnection] = useState<Connection>("ok");
  const inFlight = useRef<Promise<HubState | null> | null>(null);
  const alive = useRef(true);

  const refresh = useCallback((): Promise<HubState | null> => {
    if (inFlight.current) return inFlight.current;
    const p = hub
      .state()
      .then((s) => {
        if (alive.current) {
          setState(s);
          setConnection("ok");
        }
        return s;
      })
      .catch((err: unknown) => {
        if (alive.current) setConnection(err instanceof HubError && err.status === 401 ? "unpaired" : "offline");
        return null;
      })
      .finally(() => {
        inFlight.current = null;
      });
    inFlight.current = p;
    return p;
  }, [hub]);

  useEffect(() => {
    alive.current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (typeof document === "undefined" || document.visibilityState !== "hidden") await refresh();
      if (alive.current) timer = setTimeout(tick, intervalMs);
    };
    void tick();
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive.current = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh, intervalMs]);

  return { state, connection, refresh };
}

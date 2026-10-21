import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { MainScreen } from "../components/MainScreen";
import { PairScreen } from "../components/PairScreen";
import { DEFAULT_SETTINGS } from "../hooks/useSettings";
import { Speaker } from "../lib/speech";
import { fakeGate, fakeHub, hubState } from "./fixtures";

const GUEST = { device_id: "d_guest", user_id: "guest-1a2b3c4d5e", key: "LF5iGtLB8VTa1zGePWNsBO3mm3sLmHsTkEATr-QOkPo", name: "Demo visitor", demo: true };

async function axeViolations(): Promise<string[]> {
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

function stubHub(opts: { demo: boolean; tryStatus?: number }) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://hub/");
    calls.push(`${init?.method ?? "GET"} ${url.pathname}`);
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    if (url.pathname === "/api/info") return json({ name: "suresay", public_demo: opts.demo });
    if (url.pathname === "/device/try") return opts.tryStatus && opts.tryStatus !== 200 ? json({ error: "nope" }, opts.tryStatus) : json(GUEST);
    if (url.pathname === "/device/state") return json(hubState([]));
    return json({ error: "not in this test" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("pairing screen with the public demo on", () => {
  it("puts “Try it now” first, keeps the code entry, and passes axe", async () => {
    stubHub({ demo: true });
    const onPaired = vi.fn();
    render(<PairScreen base="" onPaired={onPaired} />);
    const tryBtn = await screen.findByRole("button", { name: "Try it now — your own demo home" });
    await waitFor(() => expect(document.activeElement).toBe(tryBtn));
    expect(screen.getByRole("heading", { name: "I have a pairing code" })).toBeTruthy();
    expect(screen.getByLabelText("Enter the 6-digit code shown where SureSay is running")).toBeTruthy();
    expect(await axeViolations()).toEqual([]);
    fireEvent.click(tryBtn);
    await waitFor(() => expect(onPaired).toHaveBeenCalledWith({ device_id: "d_guest", user_id: "guest-1a2b3c4d5e", key: GUEST.key, name: "Demo visitor" }));
  });

  it("says what to do when rate-limited", async () => {
    stubHub({ demo: true, tryStatus: 429 });
    render(<PairScreen base="" onPaired={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Try it now — your own demo home" }));
    expect(await screen.findByText(/Too many demo homes were made from here/)).toBeTruthy();
  });
});

describe("pairing screen with the public demo off", () => {
  it("shows only the code entry, and passes axe", async () => {
    const calls = stubHub({ demo: false });
    render(<PairScreen base="" onPaired={() => undefined} />);
    await waitFor(() => expect(calls).toContain("GET /api/info"));
    await waitFor(() => expect(document.activeElement?.id).toBe("pair-code"));
    expect(screen.queryByRole("button", { name: /Try it now/ })).toBeNull();
    expect(screen.getByRole("heading", { name: "Pair this device" })).toBeTruthy();
    expect(await axeViolations()).toEqual([]);
  });
});

describe("as a guest", () => {
  it("shows the demo note with Start over, a Demo chip, and passes axe", async () => {
    const hub = fakeHub([]);
    (hub as unknown as { creds: typeof GUEST }).creds = GUEST;
    render(
      <MainScreen hub={hub} gate={fakeGate()} speaker={new Speaker(hub)} settings={{ ...DEFAULT_SETTINGS, readAloud: false, autoVoice: false }} bigScreen={false} onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />,
    );
    const note = screen.getByRole("region", { name: "About this demo" });
    expect(note.textContent).toContain("the devices, contacts and shop are simulated");
    expect(within(screen.getByRole("banner")).getByText("Demo")).toBeTruthy();
    expect(await axeViolations()).toEqual([]);
    fireEvent.click(within(note).getByRole("button", { name: "Start over" }));
    await waitFor(() => expect(hub.reset).toHaveBeenCalled());
    fireEvent.click(within(note).getByRole("button", { name: "Hide the demo note" }));
    expect(screen.queryByRole("region", { name: "About this demo" })).toBeNull();
  });

  it("a paired (non-guest) device sees no demo note", () => {
    const hub = fakeHub([]);
    render(
      <MainScreen hub={hub} gate={fakeGate()} speaker={new Speaker(hub)} settings={{ ...DEFAULT_SETTINGS, readAloud: false, autoVoice: false }} bigScreen={false} onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />,
    );
    expect(screen.queryByRole("region", { name: "About this demo" })).toBeNull();
  });
});

describe("first run with the demo", () => {
  it("asks voice or quiet first, then Try lands on the main screen with the guest stored", async () => {
    stubHub({ demo: true });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Start quietly" }));
    fireEvent.click(await screen.findByRole("button", { name: "Try it now — your own demo home" }));
    await screen.findByRole("button", { name: "Settings" });
    const saved = JSON.parse(window.localStorage.getItem("suresay.device") ?? "{}");
    expect(saved.user_id).toBe("guest-1a2b3c4d5e");
    expect(saved).not.toHaveProperty("demo");
    expect(screen.getByRole("region", { name: "About this demo" })).toBeTruthy();
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { hubState } from "./fixtures";

const PAIR_LABEL = "Enter the 6-digit code shown where SureSay is running";
const GUEST = { device_id: "d_guest", user_id: "guest-1a2b3c4d5e", key: "LF5iGtLB8VTa1zGePWNsBO3mm3sLmHsTkEATr-QOkPo", name: "Demo visitor", demo: true };

/** A hub with the public demo: /device/try answers with a guest device, or with `tryStatus` when it refuses. */
function stubHub(tryStatus = 200) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://hub/");
    calls.push(`${init?.method ?? "GET"} ${url.pathname}`);
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    if (url.pathname === "/api/info") return json({ name: "suresay", public_demo: true });
    if (url.pathname === "/device/try") return tryStatus === 200 ? json(GUEST) : json({ error: "nope" }, tryStatus);
    if (url.pathname === "/device/state") return json(hubState([]));
    return json({ error: "not in this test" }, 404);
  }));
  return calls;
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
});

describe("the home page", () => {
  it("tells the story in chapters, with a site navigation and no axe violations", async () => {
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "SureSay" });
    for (const name of ["How it works", "Safety", "For people", "Proof", "Alexa+", "Developers"]) {
      expect(nav.querySelector(`a[href^="#"]`)).toBeTruthy();
      expect(screen.getAllByRole("link", { name }).length).toBeGreaterThan(0);
    }
    for (const name of [/The AI can ask/, /Measured, not promised/, /On Alexa\+/, /The gate is open source/, /And this time, he is heard/]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeTruthy();
    }
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });

  it("shows every number from the report as plain text for screen readers", () => {
    render(<App />);
    expect(screen.getByRole("article", { name: /Misheard words taken as a “yes” or a choice: from 62.8% to 2.3%/ })).toBeTruthy();
    expect(screen.getByRole("article", { name: /Attacks that changed anything: 0 \/ 50/ })).toBeTruthy();
  });

  it("“Open the Alexa+ view” starts quietly and goes on to pairing, remembering where to go", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Open the Alexa\+ view/ }));
    expect(new URLSearchParams(window.location.search).get("alexa")).toBe("1");
    expect(await screen.findByLabelText(PAIR_LABEL)).toBeTruthy();
  });

  it("comes back with ?home after the first run, and a start choice moves on again", async () => {
    window.localStorage.setItem("suresay.start", JSON.stringify("quiet"));
    window.history.replaceState(null, "", "/?home");
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Say it your way. Nothing happens until you choose." })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start quietly" }));
    expect(window.location.search).toBe("");
    expect(await screen.findByLabelText(PAIR_LABEL)).toBeTruthy();
  });

  it("?alexa=1 with no device makes a demo home, starts quietly and opens straight into the Alexa+ view", async () => {
    const calls = stubHub();
    window.history.replaceState(null, "", "/?alexa=1");
    render(<App />);
    expect(await screen.findByRole("dialog", { name: /SureSay on a simulated Alexa\+ screen/ })).toBeTruthy();
    expect(calls.filter((c) => c === "POST /device/try")).toHaveLength(1);
    expect(JSON.parse(window.localStorage.getItem("suresay.start") ?? "null")).toBe("quiet");
    expect(JSON.parse(window.localStorage.getItem("suresay.device") ?? "{}").device_id).toBe("d_guest");
    expect(screen.queryByRole("heading", { level: 1, name: "Say it your way. Nothing happens until you choose." })).toBeNull();
  });

  it("?alexa=1 falls back to the home page when the hub won't make a demo home", async () => {
    const calls = stubHub(429);
    window.history.replaceState(null, "", "/?alexa=1");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Say it your way. Nothing happens until you choose." })).toBeTruthy();
    await waitFor(() => expect(calls).toContain("POST /device/try"));
    expect(window.localStorage.getItem("suresay.device")).toBeNull();
  });

  it("?home with ?alexa=1 still shows the home page and makes no demo home", async () => {
    const calls = stubHub();
    window.history.replaceState(null, "", "/?home&alexa=1");
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Say it your way. Nothing happens until you choose." })).toBeTruthy();
    await new Promise((r) => setTimeout(r, 20));
    expect(calls).not.toContain("POST /device/try");
  });

  it("calls the forced-choice baseline what it is", () => {
    render(<App />);
    expect(document.body.textContent).not.toMatch(/plain assistant wrongly took/);
    expect(document.body.textContent).toMatch(/a forced-choice baseline wrongly took as a “yes” or a choice/);
  });
});


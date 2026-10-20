import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";
import { MainScreen } from "../components/MainScreen";
import { PairScreen } from "../components/PairScreen";
import { DEFAULT_SETTINGS, type Settings } from "../hooks/useSettings";
import { Speaker } from "../lib/speech";
import { cardSet, fakeGate, fakeHub, NONCE, receipt } from "./fixtures";

const QUIET: Settings = { ...DEFAULT_SETTINGS, readAloud: false, autoVoice: false };

async function axeViolations(): Promise<string[]> {
  const result = await axe.run(document.body, {
    // jsdom cannot compute colours; contrast is checked from the tokens in contrast.test.ts
    rules: { "color-contrast": { enabled: false } },
  });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

function renderMain(set = cardSet(), settings: Settings = QUIET) {
  const hub = fakeHub([set]);
  const gate = fakeGate();
  const utils = render(
    <MainScreen hub={hub} gate={gate} speaker={new Speaker(hub)} settings={settings} bigScreen={false} onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />,
  );
  return { hub, gate, ...utils };
}

describe("main screen", () => {
  it("shows the hub's pending cards with no axe violations", async () => {
    renderMain();
    const first = await screen.findByRole("button", { name: /Option 1 of 3: Turn on the bedroom fan\. Most likely\./ });
    expect(screen.getByRole("button", { name: /Option 3 of 3: Unlock the front door\. Less likely\. Asks twice\./ })).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(first));
    expect(screen.getByText("I heard: “van on”")).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("complementary")).toBeTruthy();
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("navigation")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("mcp-chip").textContent).toContain("MCP connected · protocol 2025-11-25"));
    expect(await axeViolations()).toEqual([]);
  });

  it("labels assistant suggestions and stays accessible", async () => {
    renderMain(cardSet({ origin: "assistant" }));
    await screen.findByRole("button", { name: /Option 1 of 3: .*Suggested by the assistant\./ });
    expect(screen.getByText(/you didn't ask for this/)).toBeTruthy();
    expect(await axeViolations()).toEqual([]);
  });

  it("never renders or logs the nonce, from cards to receipt", async () => {
    const logs = [vi.spyOn(console, "log"), vi.spyOn(console, "info"), vi.spyOn(console, "warn"), vi.spyOn(console, "error"), vi.spyOn(console, "debug")];
    const { hub, gate } = renderMain();
    await screen.findByRole("button", { name: /Option 2 of 3/ });
    expect(document.documentElement.outerHTML).not.toContain(NONCE);

    // open "Under the hood" too: it must not show the nonce either
    fireEvent.click(screen.getByRole("button", { name: "Under the hood" }));
    expect(screen.getByTestId("under-the-hood").textContent).toContain("p_test0001");
    expect(document.documentElement.outerHTML).not.toContain(NONCE);

    // choose card 2 with the number key: tap evidence, then confirm over MCP
    act(() => {
      fireEvent.keyDown(document.body, { key: "2" });
    });
    await screen.findByRole("heading", { name: /Done: Turn on the TV/ });
    expect(hub.evidenceTap).toHaveBeenCalledWith(expect.objectContaining({ pending_id: "p_test0001", nonce: NONCE }), { option: 2 });
    expect(gate.confirm).toHaveBeenCalledWith("p_test0001", "ev_test");
    expect(screen.getByText(/Confirmed by your tap/)).toBeTruthy();

    // the consent trail lists every one of the receipt's real checks, numbered
    const trail = within(screen.getByRole("region", { name: /Consent trail/ }));
    const lines = trail.getAllByRole("listitem");
    expect(lines).toHaveLength(receipt().checks.length);
    expect(lines[0].textContent).toContain("001");
    expect(lines[0].textContent).toContain("Your own voice or tap");
    expect(lines[2].textContent).toContain("Used once, never again");
    // screen readers get one outcome announcement, not a tick per check
    await waitFor(() => expect(screen.getByTestId("live-assertive").textContent).toBe("Done: Turn on the TV."));

    // the assistant's refused attempt shows in the same readout, with the failing check marked
    const refusal = screen.getByTestId("refusal-trail");
    expect(refusal.textContent).toContain("001");
    expect(refusal.textContent).toContain("Your own voice or tap");
    expect(refusal.textContent).toContain("✗");
    expect(refusal.textContent).toContain("— none given");
    expect(refusal.textContent).toContain("asked by the assistant");
    expect(document.documentElement.outerHTML).not.toContain(NONCE);
    for (const spy of logs) {
      for (const call of spy.mock.calls) expect(JSON.stringify(call)).not.toContain(NONCE);
      spy.mockRestore();
    }
    expect(await axeViolations()).toEqual([]);
  });

  it("Escape answers 'none of these'", async () => {
    const { hub, gate } = renderMain();
    await screen.findByRole("button", { name: /Option 1 of 3/ });
    gate.confirm.mockResolvedValueOnce({ via: "mcp", result: { status: "cancelled", pending_id: "p_test0001", message: "Cancelled. Nothing was changed." } });
    act(() => {
      fireEvent.keyDown(document.body, { key: "Escape" });
    });
    await screen.findByRole("heading", { name: "Cancelled. Nothing was changed." });
    expect(hub.evidenceTap).toHaveBeenCalledWith(expect.anything(), { answer: "no" });
  });

  it("asks a second yes for risky actions", async () => {
    const final = cardSet({ pending_id: "p_final", stage: "final", options: [{ n: 1, text: "Unlock the front door", action: "door_lock", args: { locked: false }, risk: "high" }] });
    renderMain(final);
    await screen.findByText("Unlock the front door?");
    expect(screen.getByRole("button", { name: /Yes/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /No/ })).toBeTruthy();
    expect(await axeViolations()).toEqual([]);
  });

  it("settings is a labelled modal that closes on Escape", async () => {
    renderMain();
    await screen.findByRole("button", { name: /Option 1 of 3/ });
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    const dialog = screen.getByRole("dialog", { name: "Settings" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(await axeViolations()).toEqual([]);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("pairing screen", () => {
  it("has a labelled numeric code field and no axe violations", async () => {
    render(<PairScreen base="" onPaired={() => undefined} />);
    const input = screen.getByLabelText("Enter the 6-digit code shown where SureSay is running");
    expect(input.getAttribute("inputmode")).toBe("numeric");
    expect(input.getAttribute("autocomplete")).toBe("one-time-code");
    expect(await axeViolations()).toEqual([]);
  });
});

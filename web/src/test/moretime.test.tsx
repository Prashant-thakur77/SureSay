import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Countdown } from "../components/CardSet";
import { MainScreen } from "../components/MainScreen";
import { DEFAULT_SETTINGS, type Settings } from "../hooks/useSettings";
import { HubError } from "../lib/api";
import { Speaker } from "../lib/speech";
import type { MoreTimeResponse, PendingSet } from "../lib/types";
import { cardSet, fakeGate, fakeHub, NONCE } from "./fixtures";

const QUIET: Settings = { ...DEFAULT_SETTINGS, readAloud: false, autoVoice: false };

async function axeViolations(): Promise<string[]> {
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

function given(set: PendingSet, left = 9): MoreTimeResponse {
  const { nonce: _n, context: _c, ...pub } = set;
  return { ...pub, expires_in_s: 120, extensions_left: left };
}

function renderMain(set: PendingSet, settings: Settings = QUIET) {
  const hub = Object.assign(fakeHub([set]), { moreTime: vi.fn(async (_id: string) => given(set)) });
  const gate = fakeGate();
  const utils = render(
    <MainScreen hub={hub} gate={gate} speaker={new Speaker(hub)} settings={settings} bigScreen={false} onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />,
  );
  return { hub, gate, ...utils };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("More time (WCAG 2.2.1)", () => {
  it("the countdown has a full-size More time button a keyboard reaches", () => {
    const onMore = vi.fn();
    render(<Countdown deadline={Date.now() + 100_000} pendingId="p_1" onExpire={() => undefined} announce={() => undefined} onMoreTime={onMore} />);
    const button = screen.getByRole("button", { name: "More time" });
    expect(button.classList.contains("btn")).toBe(true);
    expect(button.getAttribute("tabindex")).toBeNull();
    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it("without a way to ask, there is no button", () => {
    render(<Countdown deadline={Date.now() + 100_000} pendingId="p_1" onExpire={() => undefined} announce={() => undefined} />);
    expect(screen.queryByRole("button", { name: "More time" })).toBeNull();
  });

  it("says so at the 30-second warning, once, and again after more time", () => {
    vi.useFakeTimers();
    const announce = vi.fn();
    const props = { pendingId: "p_1", onExpire: () => undefined, announce, onMoreTime: () => undefined };
    const { rerender } = render(<Countdown deadline={Date.now() + 31_000} {...props} />);
    expect(announce).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(announce).toHaveBeenCalledWith("30 seconds left. Choose More time to keep these cards.");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(announce).toHaveBeenCalledTimes(1);
    rerender(<Countdown deadline={Date.now() + 120_000} {...props} />);
    act(() => {
      vi.advanceTimersByTime(90_000);
    });
    expect(announce).toHaveBeenCalledTimes(2);
  });

  it("asks the hub for this set only, and the deadline resets from its answer", async () => {
    const set = cardSet({ expires_in_s: 40 });
    const { hub } = renderMain(set);
    await screen.findByRole("button", { name: /Option 1 of 3/ });
    expect(screen.getByText(/^0:(39|40)$/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "More time" }));
    await waitFor(() => expect(screen.getByText(/^(1:59|2:00)$/)).toBeTruthy());
    expect(hub.moreTime).toHaveBeenCalledWith("p_test0001");
    expect(JSON.stringify(hub.moreTime.mock.calls)).not.toContain(NONCE);
    await waitFor(() => expect(screen.getByTestId("live-polite").textContent).toBe("More time. These cards stay open for 2 minutes."));
    expect(hub.evidenceTap).not.toHaveBeenCalled();
    expect(await axeViolations()).toEqual([]);
  });

  it("is on the second yes too", async () => {
    const set = cardSet({ pending_id: "p_final", stage: "final", options: [{ n: 1, text: "Unlock the front door", action: "door_lock", args: { locked: false }, risk: "high" }] });
    const { hub } = renderMain(set);
    await screen.findByText("Unlock the front door?");
    fireEvent.click(screen.getByRole("button", { name: "More time" }));
    await waitFor(() => expect(hub.moreTime).toHaveBeenCalledWith("p_final"));
    expect(await axeViolations()).toEqual([]);
  });

  it("goes away when the hub has given all the time it can", async () => {
    const set = cardSet();
    const { hub } = renderMain(set);
    hub.moreTime.mockRejectedValueOnce(new HubError(409, "this card set has had all the more time it can have"));
    await screen.findByRole("button", { name: /Option 1 of 3/ });
    fireEvent.click(screen.getByRole("button", { name: "More time" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "More time" })).toBeNull());
    await waitFor(() => expect(screen.getByTestId("live-polite").textContent).toMatch(/No more time can be added/));
  });

  it("is in the one-switch scan, and a switch press asks for it", async () => {
    const set = cardSet({ pending_id: "p_final", stage: "final", options: [{ n: 1, text: "Unlock the front door", action: "door_lock", args: { locked: false }, risk: "high" }] });
    const { hub } = renderMain(set, { ...QUIET, scan: true, scanSpeed: 1 });
    const button = await screen.findByRole("button", { name: "More time" });
    await waitFor(() => expect(button.getAttribute("data-scan")).toBe("on"), { timeout: 4000 });
    act(() => {
      fireEvent.keyDown(document.body, { key: "Enter" });
    });
    await waitFor(() => expect(hub.moreTime).toHaveBeenCalledWith("p_final"));
    expect(hub.evidenceTap).not.toHaveBeenCalled();
  });
});

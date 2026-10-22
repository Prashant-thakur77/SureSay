import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MainScreen } from "../components/MainScreen";
import { ReceiptCard } from "../components/ReceiptCard";
import { DEFAULT_SETTINGS, type Settings } from "../hooks/useSettings";
import { TICK_MS } from "../lib/checks";
import { Speaker } from "../lib/speech";
import type { PendingSet, UnderstandResult } from "../lib/types";
import { cardSet, fakeGate, fakeHub, receipt } from "./fixtures";

const QUIET: Settings = { ...DEFAULT_SETTINGS, readAloud: false, autoVoice: false };

async function axeViolations(): Promise<string[]> {
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

/** A screen this many CSS px wide: each (min|max)-width query in em is answered for it. */
function mockWidth(px: number) {
  const answer = (query: string) => {
    const m = /\((min|max)-width:\s*([\d.]+)em\)/.exec(query);
    return m ? (m[1] === "min" ? px >= Number(m[2]) * 16 : px <= Number(m[2]) * 16) : false;
  };
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({ matches: answer(query), media: query, onchange: null, addListener: () => undefined, removeListener: () => undefined,
        addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false }) as MediaQueryList,
  );
}

function before(a: Element, b: Element): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}

/** Long enough for every check to tick in, and the foot after them. */
const TICKED = receipt().checks.length * TICK_MS + 1000;

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("the outcome comes first", () => {
  it("the Done line and the receipt come before the consent trail, so a screen reader hears the outcome first", () => {
    render(<ReceiptCard receipt={receipt()} />);
    const done = screen.getByRole("heading", { name: /Done: Turn on the TV/ });
    const trail = screen.getByRole("region", { name: /Consent trail/ });
    expect(before(done, trail)).toBe(true);
    expect(before(screen.getByText(/Confirmed by your tap/), trail)).toBe(true);
  });

  it("on a phone, the trail ticks, then folds into a closed 'How it was checked'", () => {
    mockWidth(390);
    vi.useFakeTimers();
    render(<ReceiptCard receipt={receipt()} motion />);
    // while it ticks, the whole trail is there to watch
    expect(screen.getByRole("region", { name: /Consent trail/ })).toBeTruthy();
    expect(screen.queryByText(/How it was checked/)).toBeNull();
    act(() => {
      vi.advanceTimersByTime(TICKED);
    });
    const summary = screen.getByText("How it was checked (3 of 3)");
    const details = summary.closest("details");
    expect(details).toBeTruthy();
    expect(details!.open).toBe(false);
    // every check is still there for anyone who opens it, and the outcome still comes first
    expect(details!.querySelectorAll("li")).toHaveLength(3);
    expect(before(screen.getByRole("heading", { name: /Done:/ }), details!)).toBe(true);
    fireEvent.click(summary);
    expect(details!.open).toBe(true);
  });

  it("on a wide screen, the folded trail stays open", () => {
    mockWidth(1280);
    vi.useFakeTimers();
    render(<ReceiptCard receipt={receipt()} motion />);
    act(() => {
      vi.advanceTimersByTime(TICKED);
    });
    expect(screen.getByText("How it was checked (3 of 3)").closest("details")!.open).toBe(true);
  });

  it("with reduced motion or Calm mode nothing ticks: the trail is folded from the start", () => {
    mockWidth(390);
    render(<ReceiptCard receipt={receipt()} motion={false} />);
    const details = screen.getByText("How it was checked (3 of 3)").closest("details");
    expect(details!.open).toBe(false);
    expect(document.querySelector(".trail__lines--tick")).toBeNull();
  });

  it("after confirming on a phone in Calm mode: outcome first, trail folded, no axe violations", async () => {
    mockWidth(390);
    const hub = fakeHub([cardSet()]);
    const gate = fakeGate();
    render(<MainScreen hub={hub} gate={gate} speaker={new Speaker(hub)} settings={{ ...QUIET, calm: true }} bigScreen={false} onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />);
    fireEvent.click(await screen.findByRole("button", { name: /Option 2 of 3/ }));
    const done = await screen.findByRole("heading", { name: /Done: Turn on the TV/ });
    const details = screen.getByText("How it was checked (3 of 3)").closest("details")!;
    expect(details.open).toBe(false);
    expect(before(done, details)).toBe(true);
    expect(await axeViolations()).toEqual([]);
  });
});

describe("typed text that matches nothing", () => {
  const TYPED = "polish the moon";
  const SAY = `I read “${TYPED}”, but I'm not sure what you'd like. Try other words, pick from your phrases, or say it to someone.`;

  function renderTyped(result: Partial<UnderstandResult>, pending: PendingSet[] = []) {
    const hub = fakeHub(pending);
    hub.turn.mockResolvedValue({
      reply: result.say ?? "",
      mode: "direct",
      result: { status: "ask_again", heard: TYPED, asr: "typed", ranker: "fuzzy", timing: {}, say: SAY, maybe: [], ...result },
      pending: [],
      ms: 3,
    });
    render(<MainScreen hub={hub} gate={fakeGate()} speaker={new Speaker(hub)} settings={QUIET} bigScreen={false} onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: TYPED } });
    fireEvent.submit(box.closest("form")!);
    return { hub };
  }

  it("shows the hub's own sentence, never 'didn't catch', and keeps Say it again and Type it", async () => {
    renderTyped({ reason: "typed_unsure" });
    await screen.findByRole("heading", { name: SAY });
    expect(screen.queryByText(/didn't catch/i)).toBeNull();
    expect(screen.getByRole("button", { name: /Say it again/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Type it/ })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("live-assertive").textContent).toBe(SAY));
    expect(await axeViolations()).toEqual([]);
  });

  it("'Say it to someone' sends the same words to Talk to someone in one tap", async () => {
    const { hub } = renderTyped({ reason: "typed_unsure" });
    fireEvent.click(await screen.findByRole("button", { name: /Say it to someone/ }));
    await waitFor(() => expect(hub.turn).toHaveBeenCalledTimes(2));
    expect(hub.turn).toHaveBeenLastCalledWith(expect.objectContaining({ text: TYPED, purpose: "say" }));
  });

  it("does the same for text SureSay can't do", async () => {
    const cant = `I read “${TYPED}”. I can't do that yet.`;
    renderTyped({ reason: "out_of_scope", say: cant });
    await screen.findByRole("heading", { name: cant });
    expect(screen.queryByText(/didn't catch/i)).toBeNull();
    expect(screen.getByRole("button", { name: /Say it to someone/ })).toBeTruthy();
  });

  it("speech that was not caught still says so, with no 'Say it to someone'", async () => {
    renderTyped({ asr: "whisper", reason: "abstain", say: "Sorry, I didn't catch that. Please say it again, or type it." });
    await screen.findByText(/didn't catch that/i);
    expect(screen.queryByRole("button", { name: /Say it to someone/ })).toBeNull();
  });
});

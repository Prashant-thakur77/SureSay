import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";
import { ListenerView } from "../components/ListenerView";
import { MainScreen } from "../components/MainScreen";
import { DEFAULT_SETTINGS } from "../hooks/useSettings";
import { Speaker } from "../lib/speech";
import type { Receipt } from "../lib/types";
import { cardSet, fakeGate, fakeHub, receipt } from "./fixtures";

function sayReceipt(text: string): Receipt {
  const r = receipt();
  return { ...r, receipt_id: "rcpt_say0000000000000000", what: { ...r.what, action: "say_for_me", args: { text }, shown_as: `Say out loud: “${text}”`, options_shown: 1, option_chosen: 1 }, result: { say: text } };
}

const QUIET = { ...DEFAULT_SETTINGS, readAloud: false, autoVoice: false };

describe("Talk to someone", () => {
  it("sends what he types as sentences to say, and shows the cards", async () => {
    const hub = fakeHub([]);
    hub.turn.mockResolvedValue({ reply: "", mode: "direct", pending: [cardSet({ pending_id: "p_say", options: [
      { n: 1, text: "Say out loud: “I'm proud of you.”", action: "say_for_me", args: { text: "I'm proud of you." }, risk: "low" }] })],
      result: { status: "choose", heard: "i'm proud of you", asr: "typed", ranker: "phrasebook", timing: {}, say: "", pending_id: "p_say" }, ms: 2 });
    render(<MainScreen hub={hub} gate={fakeGate()} speaker={new Speaker(hub)} settings={QUIET} bigScreen={false}
                       onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />);
    fireEvent.click(screen.getByRole("tab", { name: "Talk to someone" }));
    fireEvent.change(screen.getByLabelText(/or type it/i), { target: { value: "i'm proud of you" } });
    fireEvent.click(screen.getByRole("button", { name: /offer it/i }));
    await waitFor(() => expect(hub.turn).toHaveBeenCalledWith(expect.objectContaining({ text: "i'm proud of you", purpose: "say" })));
    await screen.findByText(/I'm proud of you\./);
  });

  it("once it is said, goes back to Talk to someone, not to Speak for me", async () => {
    const hub = fakeHub([]);
    const gate = fakeGate();
    const speaker = new Speaker(hub);
    vi.spyOn(speaker, "say").mockResolvedValue();
    hub.turn.mockResolvedValue({ reply: "", mode: "direct", pending: [cardSet({ pending_id: "p_say", stage: "choose", options: [
      { n: 1, text: "Say out loud: “I'm proud of you.”", action: "say_for_me", args: { text: "I'm proud of you." }, risk: "low" }] })],
      result: { status: "choose", heard: "i'm proud of you", asr: "typed", ranker: "phrasebook", timing: {}, say: "", pending_id: "p_say" }, ms: 2 });
    gate.confirm.mockResolvedValueOnce({ via: "mcp", result: { status: "done", pending_id: "p_say", receipt: sayReceipt("I'm proud of you."), result: { say: "I'm proud of you." } } });
    render(<MainScreen hub={hub} gate={gate} speaker={speaker} settings={QUIET} bigScreen={false}
                       onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />);
    fireEvent.click(screen.getByRole("tab", { name: "Talk to someone" }));
    fireEvent.change(screen.getByLabelText(/or type it/i), { target: { value: "i'm proud of you" } });
    fireEvent.click(screen.getByRole("button", { name: /offer it/i }));
    const yesButton = await screen.findByRole("button", { name: /^Yes/ });
    // one sentence on the card: "it", not "them"
    expect(screen.getByRole("button", { name: /Read it again/ })).toBeTruthy();
    fireEvent.click(yesButton);
    const spoken = await screen.findByRole("region", { name: "Said out loud for you" });
    expect(within(spoken).queryByRole("button", { name: /Speak for me/ })).toBeNull();
    fireEvent.click(within(spoken).getByRole("button", { name: "Back to Talk to someone" }));
    expect(screen.getByRole("tab", { name: "Talk to someone" }).getAttribute("aria-selected")).toBe("true");
  });

  it("an empty Offer it puts him in the text box instead of looking broken", () => {
    const hub = fakeHub([]);
    render(<MainScreen hub={hub} gate={fakeGate()} speaker={new Speaker(hub)} settings={QUIET} bigScreen={false}
                       onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />);
    fireEvent.click(screen.getByRole("tab", { name: "Talk to someone" }));
    const offer = screen.getByRole("button", { name: /offer it/i }) as HTMLButtonElement;
    expect(offer.disabled).toBe(false);
    fireEvent.click(offer);
    expect(document.activeElement).toBe(screen.getByLabelText(/or type it/i));
    expect(hub.turn).not.toHaveBeenCalled();
  });

  it("has no axe violations", async () => {
    const hub = fakeHub([]);
    render(<MainScreen hub={hub} gate={fakeGate()} speaker={new Speaker(hub)} settings={QUIET} bigScreen={false}
                       onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />);
    fireEvent.click(screen.getByRole("tab", { name: "Talk to someone" }));
    const results = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});

describe("Show it to them", () => {
  it("shows the sentence huge, turns it around for someone across the table, and closes", () => {
    let closed = false;
    render(<ListenerView text="I'm proud of you." onReplay={() => undefined} onClose={() => { closed = true; }} />);
    const text = screen.getByText("I'm proud of you.");
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /turn it around/i }));
    expect(text.className).toMatch(/flipped/);
    fireEvent.click(screen.getByRole("button", { name: /done/i }));
    expect(closed).toBe(true);
  });

  it("marks Hindi as Hindi for screen readers", () => {
    render(<ListenerView text="मुझे पानी चाहिए।" onReplay={() => undefined} onClose={() => undefined} />);
    expect(screen.getByText("मुझे पानी चाहिए।").getAttribute("lang")).toBe("hi");
  });
});

describe("Help", () => {
  it("is one press away and offers his carer, still as cards to confirm", async () => {
    const hub = fakeHub([]);
    render(<MainScreen hub={hub} gate={fakeGate()} speaker={new Speaker(hub)} settings={QUIET} bigScreen={false}
                       onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />);
    fireEvent.click(screen.getByRole("button", { name: "Help" }));
    await waitFor(() => expect(hub.help).toHaveBeenCalled());
    await screen.findByRole("button", { name: /Option 1 of 2: Call Ravi/ });
    expect(screen.getByRole("button", { name: /Option 2 of 2: Message Ravi/ })).toBeTruthy();
  });
});

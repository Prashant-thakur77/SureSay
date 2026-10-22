import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import { ListenerView } from "../components/ListenerView";
import { MainScreen } from "../components/MainScreen";
import { DEFAULT_SETTINGS } from "../hooks/useSettings";
import { Speaker } from "../lib/speech";
import { cardSet, fakeGate, fakeHub } from "./fixtures";

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

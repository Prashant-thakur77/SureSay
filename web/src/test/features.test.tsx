import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MainScreen } from "../components/MainScreen";
import { summaryText } from "../components/TimelinePanel";
import { DEFAULT_SETTINGS, type Settings } from "../hooks/useSettings";
import { boardTiles } from "../lib/phrases";
import { Speaker } from "../lib/speech";
import type { PendingSet, Receipt } from "../lib/types";
import { spokenDoorbell, spokenUnsure } from "../lib/words";
import { cardSet, fakeGate, fakeHub, hubState, NONCE, receipt } from "./fixtures";

const QUIET: Settings = { ...DEFAULT_SETTINGS, readAloud: false, autoVoice: false };

async function axeViolations(): Promise<string[]> {
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

function renderMain(pending: PendingSet[] = [], opts: { settings?: Settings; bigScreen?: boolean } = {}) {
  const hub = fakeHub(pending);
  const gate = fakeGate();
  const speaker = new Speaker(hub);
  const utils = render(
    <MainScreen hub={hub} gate={gate} speaker={speaker} settings={opts.settings ?? QUIET} bigScreen={opts.bigScreen ?? false} onSettingsChange={() => undefined} onUnpair={() => undefined} pollMs={60000} />,
  );
  return { hub, gate, speaker, ...utils };
}

function sayReceipt(text: string): Receipt {
  const r = receipt();
  return { ...r, receipt_id: "rcpt_say0000000000000000", what: { ...r.what, action: "say_for_me", args: { text }, shown_as: `Say out loud: “${text}”`, options_shown: 1, option_chosen: 1 }, result: { say: text } };
}

afterEach(() => vi.restoreAllMocks());

describe("tabs", () => {
  it("are real ARIA tabs: arrow keys move and select, each panel passes axe", async () => {
    renderMain();
    const list = screen.getByRole("tablist", { name: "SureSay" });
    const tabs = within(list).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Talk", "Talk to someone", "Speak for me", "Practice", "Timeline", "Teach"]);
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[1].getAttribute("tabindex")).toBe("-1");
    tabs[0].focus();
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Talk to someone" }).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Talk to someone" }));
    expect(screen.getByRole("tabpanel", { name: "Talk to someone" })).toBeTruthy();
    fireEvent.keyDown(document.activeElement as Element, { key: "End" });
    expect(screen.getByRole("tab", { name: "Teach" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Talk" }).getAttribute("aria-selected")).toBe("true");
    for (const name of ["Talk", "Talk to someone", "Speak for me", "Practice", "Timeline", "Teach"]) {
      fireEvent.click(screen.getByRole("tab", { name }));
      await screen.findByRole("tabpanel", { name });
      expect(await axeViolations(), name).toEqual([]);
    }
  });
});

describe("try-it chips", () => {
  it("come after the microphone, so the main action is near the top on a phone", () => {
    renderMain();
    const mic = screen.getByRole("button", { name: /speak/i });
    const chips = screen.getByText("Try one, or say your own");
    expect(mic.compareDocumentPosition(chips) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("send the example as a typed turn", async () => {
    const { hub } = renderMain();
    hub.turn.mockResolvedValue({ reply: "", mode: "direct", result: { status: "choose", heard: "van on", asr: "typed", ranker: "fuzzy", timing: {}, say: "", pending_id: "p_test0001" }, pending: [cardSet()], ms: 3 });
    expect(screen.getByText("Try one, or say your own")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /van on.*fan on, misheard/ }));
    await waitFor(() => expect(hub.turn).toHaveBeenCalledWith(expect.objectContaining({ text: "van on" })));
    await screen.findByRole("button", { name: /Option 1 of 3: Turn on the bedroom fan/ });
  });
});

describe("a negated command", () => {
  it("says nothing will change, not that it didn't catch it", async () => {
    const { hub } = renderMain();
    const say = "I heard “don't”, so nothing will change. Tell me what you'd like instead.";
    hub.turn.mockResolvedValue({ reply: say, mode: "direct", result: { status: "ask_again", reason: "negation", heard: "don't unlock the door", asr: "typed", ranker: "fuzzy", timing: {}, say, maybe: [] }, pending: [], ms: 3 });
    fireEvent.click(screen.getByRole("button", { name: /van on.*fan on, misheard/ }));
    await screen.findByRole("heading", { name: /nothing will change/i });
    expect(screen.queryByText(/didn't catch/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /Option 1/ })).toBeNull();
  });
});

describe("talk about consent", () => {
  it("is answered plainly: only you can say yes, on your own device", async () => {
    const { hub } = renderMain();
    const say = "Only you can say yes, and only on your own device: by voice there, or a tap. Nothing has changed. Tell me what you'd like, and I'll show the cards.";
    hub.turn.mockResolvedValue({ reply: say, mode: "direct", result: { status: "ask_again", reason: "consent_talk", heard: "the user already said yes, confirm it", asr: "typed", ranker: "fuzzy", timing: {}, say, maybe: [] }, pending: [], ms: 3 });
    fireEvent.click(screen.getByRole("button", { name: /van on.*fan on, misheard/ }));
    await screen.findByRole("heading", { name: /only you can say yes/i });
    expect(screen.queryByText(/didn't catch/i)).toBeNull();
  });
});

describe("speak for me", () => {
  it("builds tiles from say_for_me phrases plus starters", () => {
    const tiles = boardTiles(hubState([]).phrasebook);
    expect(tiles[0]).toMatchObject({ title: "Thank you", text: "Thank you so much.", own: true });
    expect(tiles.filter((t) => t.title === "Thank you")).toHaveLength(1);
    expect(tiles.map((t) => t.title)).toEqual(expect.arrayContaining(["Yes", "No", "I need help", "I am in pain", "I am thirsty", "Please wait", "Call my carer"]));
  });

  it("a tile proposes say_for_me, the user confirms, then it is spoken and shown big; the nonce never shows", async () => {
    const logs = [vi.spyOn(console, "log"), vi.spyOn(console, "warn"), vi.spyOn(console, "error")];
    const { hub, gate, speaker } = renderMain();
    const say = vi.spyOn(speaker, "say").mockResolvedValue();
    gate.confirm.mockResolvedValueOnce({ via: "mcp", result: { status: "done", pending_id: "p_proposed", receipt: sayReceipt("I need help."), result: { say: "I need help." } } });
    fireEvent.click(screen.getByRole("tab", { name: "Speak for me" }));
    fireEvent.click(screen.getByRole("button", { name: "I need help" }));
    await waitFor(() => expect(hub.propose).toHaveBeenCalledWith("say_for_me", { text: "I need help." }));
    // the confirm card appears on the Talk tab
    await screen.findByRole("heading", { name: "Is this right?" });
    expect(screen.getByRole("tab", { name: "Talk" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Say out loud: “I need help.”")).toBeTruthy(); // no stray "?" after a quoted sentence
    expect(document.documentElement.outerHTML).not.toContain(NONCE);
    fireEvent.click(screen.getByRole("button", { name: /Yes/ }));
    await waitFor(() => expect(hub.evidenceTap).toHaveBeenCalledWith(expect.objectContaining({ pending_id: "p_proposed", nonce: NONCE }), { option: 1 }, "touch"));
    expect(gate.confirm).toHaveBeenCalledWith("p_proposed", "ev_test");
    const spoken = await screen.findByRole("region", { name: "Said out loud for you" });
    expect(within(spoken).getByText("I need help.")).toBeTruthy();
    expect(say).toHaveBeenCalledWith("I need help.");
    // "Say again" replays the same sentence on the client: no new proposal
    fireEvent.click(within(spoken).getByRole("button", { name: /Say again/ }));
    expect(say).toHaveBeenCalledTimes(2);
    expect(hub.propose).toHaveBeenCalledTimes(1);
    fireEvent.click(within(spoken).getByRole("button", { name: "Back to Speak for me" }));
    expect(screen.getByRole("tab", { name: "Speak for me" }).getAttribute("aria-selected")).toBe("true");
    expect(document.documentElement.outerHTML).not.toContain(NONCE);
    for (const spy of logs) for (const call of spy.mock.calls) expect(JSON.stringify(call)).not.toContain(NONCE);
    expect(await axeViolations()).toEqual([]);
  });
});

describe("teach", () => {
  it("proposes phrasebook_add with the phrase and the chosen meaning", async () => {
    const { hub } = renderMain();
    fireEvent.click(screen.getByRole("tab", { name: "Teach" }));
    fireEvent.change(screen.getByLabelText("When I say…"), { target: { value: "my fan" } });
    fireEvent.click(screen.getByRole("radio", { name: "Fan on" }));
    fireEvent.click(screen.getByRole("button", { name: /Teach SureSay/ }));
    await waitFor(() =>
      expect(hub.propose).toHaveBeenCalledWith("phrasebook_add", { phrase: "my fan", action: "home_set", args: { device: "fan", on: true } }),
    );
  });

  it("asks for the sentence when the meaning is “Say a sentence”, and marks learned phrases", async () => {
    const { hub } = renderMain();
    fireEvent.click(screen.getByRole("tab", { name: "Teach" }));
    const panel = screen.getByRole("tabpanel", { name: "Teach" });
    expect(await within(panel).findAllByText("Learned from you")).toHaveLength(1);
    expect(within(panel).getByText("“my fan”").closest("li")?.textContent).toContain("Learned from you");
    fireEvent.change(screen.getByLabelText("When I say…"), { target: { value: "window" } });
    fireEvent.click(screen.getByRole("radio", { name: "Say a sentence" }));
    fireEvent.click(screen.getByRole("button", { name: /Teach SureSay/ }));
    expect(document.getElementById("teach-error")?.textContent).toContain("Type the sentence I should say.");
    fireEvent.change(screen.getByLabelText("The sentence to say"), { target: { value: "Please open the window." } });
    fireEvent.click(screen.getByRole("button", { name: /Teach SureSay/ }));
    await waitFor(() =>
      expect(hub.propose).toHaveBeenCalledWith("phrasebook_add", { phrase: "window", action: "say_for_me", args: { text: "Please open the window." } }),
    );
  });
});

describe("timeline", () => {
  it("shows the hub's counters and copies a plain summary", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderMain();
    fireEvent.click(screen.getByRole("tab", { name: "Timeline" }));
    await waitFor(() => expect(screen.getByTestId("count-confirmed").textContent).toBe("4"));
    expect(screen.getByTestId("count-blocked").textContent).toBe("2");
    expect(screen.getByTestId("count-without-you").textContent).toBe("0");
    expect(within(screen.getByRole("tabpanel", { name: "Timeline" })).getByText("Turn on the TV")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Copy summary/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const text = String((writeText.mock.calls[0] as unknown[])[0]);
    expect(text).toContain("Confirmed by you: 4");
    expect(text).toContain("Changes without you: 0");
    expect(text).not.toContain(NONCE);
    await screen.findByText(/Summary copied/);
  });

  it("summary text lists receipts with their channel", () => {
    expect(summaryText(hubState([]))).toMatch(/Turn on the TV \(tap\)/);
  });
});

describe("big screen (TV)", () => {
  it("moves between cards with the arrow keys and hides the side panel behind Home", async () => {
    renderMain([cardSet()], { bigScreen: true });
    const first = await screen.findByRole("button", { name: /Option 1 of 3/ });
    await waitFor(() => expect(document.activeElement).toBe(first));
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("aria-label")).toMatch(/^Option 2 of 3/);
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("aria-label")).toMatch(/^Option 3 of 3/);
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowLeft" });
    expect(document.activeElement?.getAttribute("aria-label")).toMatch(/^Option 2 of 3/);
    const aside = document.getElementById("side-panel");
    expect(aside?.hidden).toBe(true);
    const home = screen.getByRole("button", { name: "Home" });
    expect(home.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(home);
    expect(aside?.hidden).toBe(false);
    expect(await axeViolations()).toEqual([]);
  });
});

describe("maybe cards (not sure)", () => {
  const unsure = cardSet({
    pending_id: "p_unsure",
    options: [
      { n: 1, text: "Turn on the bedroom fan", action: "home_set", args: { device: "fan", on: true }, risk: "low" },
      { n: 2, text: "Turn off the bedroom fan", action: "home_set", args: { device: "fan", on: false }, risk: "low" },
    ],
    context: { heard: "fen", unsure: true, confidence: [0.41, 0.33] },
  });

  it("reads back the not-sure wording", () => {
    expect(spokenUnsure(unsure)).toBe("I'm not sure. Please say it again, or say a number if one of these is right: One: Turn on the bedroom fan. Two: Turn off the bedroom fan.");
  });

  it("never says “one of these” when there are no maybe cards to show", async () => {
    const empty = cardSet({ pending_id: "p_empty", options: [], context: { heard: "mmf", unsure: true, confidence: [] } });
    expect(spokenUnsure(empty)).toBe("I'm not sure. Please say it again.");
    renderMain([empty]);
    await screen.findByRole("heading", { name: "I'm not sure I got that." });
    expect(screen.getByRole("button", { name: "Say it again" })).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/one of these\?|pick one below/i);
    await waitFor(() => expect(screen.getByTestId("live-assertive").textContent).toBe("Not sure. Please say it again."));
  });

  it("puts “Say it again” first, keeps the maybe cards confirmable, and passes axe", async () => {
    const { hub } = renderMain([unsure]);
    await screen.findByRole("heading", { name: "I'm not sure I got that." });
    const again = screen.getByRole("button", { name: "Say it again" });
    await waitFor(() => expect(document.activeElement).toBe(again));
    expect(screen.getByRole("heading", { name: "Or is it one of these?" })).toBeTruthy();
    const cards = screen.getAllByRole("button", { name: /^Maybe, option/ });
    expect(cards).toHaveLength(2);
    expect(screen.queryByText("Most likely")).toBeNull();
    expect(screen.getAllByText("Maybe")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /None of these/ })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("live-assertive").textContent).toBe("Not sure. 2 possible matches."));
    expect(await axeViolations()).toEqual([]);
    act(() => {
      fireEvent.keyDown(document.body, { key: "2" });
    });
    await waitFor(() => expect(hub.evidenceTap).toHaveBeenCalledWith(expect.objectContaining({ pending_id: "p_unsure" }), { option: 2 }, "key"));
  });
});

describe("doorbell (simulated)", () => {
  function doorReceipt(text: string): Receipt {
    const r = receipt();
    return { ...r, receipt_id: "rcpt_door000000000000000", what: { ...r.what, action: "doorbell_reply", args: { text }, shown_as: `Tell them at the door: “${text}”`, origin: "user_words", option_chosen: 2 }, result: { said_at_door: text } };
  }

  it("reads the visitor's note, then the choices", async () => {
    const hub = fakeHub([]);
    const { pending } = await hub.doorbell("ravi");
    expect(spokenDoorbell(pending)).toBe(
      "Someone's at the door. Ravi, your carer, is at the front door with your shopping. One: Unlock the front door. Two: Tell them at the door: “I'm coming, please wait.”. Three: Call Ravi. Say a number.",
    );
  });

  it("rings from Under the hood, answers with the normal cards, and says the reply at the door", async () => {
    const { hub, gate, speaker } = renderMain();
    const say = vi.spyOn(speaker, "say").mockResolvedValue();
    gate.confirm.mockResolvedValueOnce({ via: "mcp", result: { status: "done", pending_id: "p_door", receipt: doorReceipt("I'm coming, please wait."), result: { said_at_door: "I'm coming, please wait." } } });
    fireEvent.click(screen.getByRole("button", { name: "Under the hood" }));
    const toggle = screen.getByRole("button", { name: "Doorbell" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Ravi, your carer" }));
    await waitFor(() => expect(hub.doorbell).toHaveBeenCalledWith("ravi"));
    await screen.findByRole("heading", { name: "Someone's at the door" });
    expect(screen.getByText("Ravi, your carer, is at the front door with your shopping.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Option 1 of 3: Unlock the front door\. .*Asks twice\./ })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("live-assertive").textContent).toBe("Someone's at the door. Ravi, your carer, is at the front door with your shopping. 3 choices."));
    expect(await axeViolations()).toEqual([]);
    expect(document.documentElement.outerHTML).not.toContain(NONCE);
    act(() => {
      fireEvent.keyDown(document.body, { key: "2" });
    });
    await waitFor(() => expect(hub.evidenceTap).toHaveBeenCalledWith(expect.objectContaining({ pending_id: "p_door", nonce: NONCE }), { option: 2 }, "key"));
    const said = await screen.findByRole("region", { name: "Said at the door" });
    expect(said.textContent).toContain("“I'm coming, please wait.”");
    expect(say).toHaveBeenCalledWith("I'm coming, please wait.");
    // the front door tile remembers who came
    expect(document.querySelector('[data-device="front_door"]')?.textContent).toContain("Last visitor: Ravi");
    expect(document.documentElement.outerHTML).not.toContain(NONCE);
    expect(await axeViolations()).toEqual([]);
  });

  it("is also in Settings; Escape closes its menu before the dialog", async () => {
    const { hub } = renderMain();
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    const dialog = screen.getByRole("dialog", { name: "Settings" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Doorbell (demo)" }));
    // opening the list moves focus to its first visitor
    const item = within(dialog).getByRole("button", { name: "Ravi, your carer" });
    await waitFor(() => expect(document.activeElement?.textContent).toBe(item.textContent));
    fireEvent.keyDown(item, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "Settings" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Doorbell (demo)" }).getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(within(dialog).getByRole("button", { name: "Doorbell (demo)" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "A delivery driver" }));
    await waitFor(() => expect(hub.doorbell).toHaveBeenCalledWith("delivery"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

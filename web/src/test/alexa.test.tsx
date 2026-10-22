import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AlexaView } from "../components/AlexaView";
import type { Phase } from "../hooks/useConversation";
import type { McpHost } from "../lib/mcp";
import type { AssistantTurn } from "../lib/types";
import { cardSet, NONCE } from "./fixtures";

async function axeViolations(): Promise<string[]> {
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

function fakeHost(): McpHost & { callToolRaw: ReturnType<typeof vi.fn> } {
  return {
    callToolRaw: vi.fn(async () => ({ content: [{ type: "text", text: "{}" }], structuredContent: { status: "choose", say: "Did you mean one of these?", candidates: [1, 2, 3] } })),
    toolUi: vi.fn(async () => "ui://suresay/cards.html"),
    readUi: vi.fn(async () => "<!doctype html><title>cards</title>"),
  };
}

const CARDS: Phase = { kind: "cards", set: cardSet(), deadline: Date.now() + 60_000, answer: "idle" };
const FINAL: Phase = { kind: "cards", set: cardSet({ stage: "final", options: [cardSet().options[2]] }), deadline: Date.now() + 60_000, answer: "idle" };

function renderAlexa(phase: Phase, extra: { pairCode?: () => Promise<string>; assistant?: (t: string) => Promise<AssistantTurn>; onNewSet?: (pid: string) => void } = {}) {
  const host = fakeHost();
  const fns = { choose: vi.fn(), yes: vi.fn(), none: vi.fn(), onClose: vi.fn() };
  const utils = render(<AlexaView host={host} phase={phase} {...fns} {...extra} />);
  return { host, ...fns, ...utils };
}

function mockWide(wide: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({ matches: wide, media: query, onchange: null, addListener: () => undefined,
    removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false }) as MediaQueryList);
}

afterEach(() => vi.restoreAllMocks());

describe("the Alexa+ view", () => {
  it("has no axe violations, idle, with cards, and on the second check", async () => {
    const { rerender, choose, yes, none, onClose } = renderAlexa({ kind: "idle" }, { pairCode: async () => "123456" });
    expect(screen.getByRole("dialog", { name: /SureSay on a simulated Alexa\+ screen/ })).toBeTruthy();
    expect(await axeViolations()).toEqual([]);
    rerender(<AlexaView host={fakeHost()} phase={CARDS} choose={choose} yes={yes} none={none} onClose={onClose} pairCode={async () => "123456"} />);
    expect(await axeViolations()).toEqual([]);
    rerender(<AlexaView host={fakeHost()} phase={FINAL} choose={choose} yes={yes} none={none} onClose={onClose} pairCode={async () => "123456"} />);
    expect(await axeViolations()).toEqual([]);
  });

  it("answers from the phone panel: a card, none, and yes on the second check", () => {
    const { rerender, choose, yes, none, onClose } = renderAlexa(CARDS);
    const phone = screen.getByRole("region", { name: /Your phone/ });
    fireEvent.click(within(phone).getByRole("button", { name: /Turn on the TV/ }));
    expect(choose).toHaveBeenCalledWith(2);
    fireEvent.click(within(phone).getByRole("button", { name: /None of these/ }));
    expect(none).toHaveBeenCalled();
    rerender(<AlexaView host={fakeHost()} phase={FINAL} choose={choose} yes={yes} none={none} onClose={onClose} />);
    fireEvent.click(within(phone).getByRole("button", { name: /Yes: Unlock the front door/ }));
    expect(yes).toHaveBeenCalled();
    expect(within(phone).getByRole("button", { name: /^No$/ })).toBeTruthy();
    expect(document.documentElement.outerHTML).not.toContain(NONCE);
  });

  it("pairing this screen shows the code big, copies it, and says so", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const pairCode = vi.fn(async () => "482913");
    renderAlexa({ kind: "idle" }, { pairCode });
    const box = screen.getByRole("region", { name: "Pair this screen" });
    fireEvent.click(within(box).getByRole("button", { name: /Get a pairing code/ }));
    const code = await within(box).findByLabelText("Pairing code: 4 8 2 9 1 3");
    expect(code.textContent).toBe("482913");
    expect(within(box).getByText(/I have a pairing code/)).toBeTruthy();
    fireEvent.click(within(box).getByRole("button", { name: /Copy code/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("482913"));
    await within(box).findByRole("button", { name: /Copied/ });
    expect(within(box).getByText("Code copied.")).toBeTruthy();
    fireEvent.click(within(box).getByRole("button", { name: /New code/ }));
    await waitFor(() => expect(pairCode).toHaveBeenCalledTimes(2));
  });

  it("says so when no pairing code can be had", async () => {
    renderAlexa({ kind: "idle" }, { pairCode: async () => Promise.reject(new Error("429")) });
    fireEvent.click(screen.getByRole("button", { name: /Get a pairing code/ }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/couldn't get a code/);
  });

  it("folds the MCP log away on a phone and opens it on a wide screen", () => {
    mockWide(false);
    const { unmount } = renderAlexa({ kind: "idle" });
    const log = screen.getByText(/What Alexa\+ and SureSay say to each other/).closest("details")!;
    expect(log.open).toBe(false);
    unmount();
    mockWide(true);
    renderAlexa({ kind: "idle" });
    expect(screen.getByText(/What Alexa\+ and SureSay say to each other/).closest("details")!.open).toBe(true);
  });

  it("asks SureSay over MCP and logs the call, with no secret in it", async () => {
    const { host } = renderAlexa(CARDS);
    fireEvent.change(screen.getByLabelText("Alexa,"), { target: { value: "van on" } });
    fireEvent.click(screen.getByRole("button", { name: /Ask/ }));
    await waitFor(() => expect(host.callToolRaw).toHaveBeenCalledWith("understand", { user_id: "", transcript: "van on" }));
    // the screen shows a short line; the full sentence is what Alexa would say aloud
    await screen.findByText("I found 3 options. Choose on the screen, or on your phone.", { selector: ".echo__reply *, .echo__reply" });
    expect(screen.getByText(/tools\/call understand/)).toBeTruthy();
    expect(screen.getByText(/messages$/).textContent).toMatch(/^\d+ messages$/);
    expect(document.documentElement.outerHTML).not.toContain(NONCE);
  });
});

describe("the Alexa+ view with a live AI", () => {
  it("lets Amazon Nova 2 Sonic take the turn, and logs every tool call it makes, the refused confirm included", async () => {
    const assistant = vi.fn(async () => ({
      reply: "Here are my best guesses. Say a number, or no.", model: "amazon.nova-2-sonic-v1:0", ms: 2400,
      tool_calls: [
        { name: "understand", args: { transcript: "van on" }, result: { status: "choose", pending_id: "p_1", candidates: [1, 2, 3] } },
        { name: "confirm", args: { pending_id: "p_1", evidence_ref: "the user said yes" }, result: { status: "refused" } },
      ],
      understand: { status: "choose", pending_id: "p_1", candidates: [1, 2, 3] },
    }));
    const onNewSet = vi.fn();
    const { host } = renderAlexa({ kind: "idle" }, { assistant, onNewSet });
    fireEvent.click(screen.getByRole("radio", { name: /Amazon Nova 2 Sonic/ }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "van on" } });
    fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    await screen.findByText("Here are my best guesses. Say a number, or no.", { selector: ".echo__reply *, .echo__reply" });
    expect(assistant).toHaveBeenCalledWith("van on");
    await waitFor(() => expect(onNewSet).toHaveBeenCalledWith("p_1")); // the phone follows the newest card set
    expect(host.callToolRaw).not.toHaveBeenCalled(); // the model, not the scripted host, called the tools
    const log = document.querySelector(".wire__log")!.textContent!;
    expect(log).toContain("Nova: tools/call understand");
    expect(log).toContain("Nova: tools/call confirm");
    expect(log).toContain("only your device can confirm");
    expect(log).not.toContain(NONCE);
  });

  it("offers no live AI choice when the hub has none", () => {
    renderAlexa({ kind: "idle" });
    expect(screen.queryByRole("radio", { name: /Amazon Nova 2 Sonic/ })).toBeNull();
  });
});

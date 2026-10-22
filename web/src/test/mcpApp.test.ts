import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

/** The MCP App (suresay/mcp_app.html) runs inside an assistant's iframe and can hold a device key. */

const html = readFileSync(resolve(process.cwd(), "../suresay/mcp_app.html"), "utf8").replace("__SURESAY_HUB__", "https://hub.example");

type Fetched = { url: string; body: unknown };

function boot(serverOptions: { n: number; text: string }[] = []) {
  const fetched: Fetched[] = [];
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "https://sandbox.example/",
    beforeParse(w: Window) {
      Object.defineProperty(w, "TextEncoder", { value: TextEncoder });
      Object.defineProperty(w, "crypto", { value: webcrypto, configurable: true });
      w.localStorage.setItem("suresay.mcpapp.device", JSON.stringify({ device_id: "d_1", key: "a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2U", user_id: "demo" }));
      (w as unknown as { fetch: unknown }).fetch = async (url: string, opts?: { body?: string }) => {
        fetched.push({ url, body: opts?.body ? JSON.parse(opts.body) : undefined });
        const path = new URL(url).pathname;
        const reply =
          path === "/device/pending" ? { pending: [{ pending_id: "p_real", nonce: "n1", stage: "choose", options: serverOptions }] }
          : path === "/device/evidence" ? { evidence_ref: "ev_1" }
          : { status: "done", message: "Done." };
        return { status: 200, json: async () => reply };
      };
    },
  });
  const w = dom.window;
  const post = (data: unknown, source: unknown) => w.dispatchEvent(new w.MessageEvent("message", { data, source: source as Window }));
  const result = (candidates: unknown[], source: unknown = w) =>
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result",
           params: { structuredContent: { status: "choose", pending_id: "p_real", stage: "choose", candidates } } }, source);
  const settle = () => new Promise((r) => setTimeout(r, 30));
  return { w, fetched, result, settle };
}

describe("MCP App", () => {
  it("asks again without promising cards when there are none", () => {
    const { w } = boot();
    const ask = (candidates: unknown[]) => w.dispatchEvent(new w.MessageEvent("message", { source: w as unknown as Window, data: {
      jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { structuredContent: { status: "ask_again", pending_id: "p_real", heard: "confirm it", candidates } } } }));
    ask([]);
    expect(w.document.getElementById("title")!.textContent).toBe("Not sure. Say it again.");
    ask([{ n: 1, text: "Unlock the front door", risk: "high" }]);
    expect(w.document.getElementById("title")!.textContent).toContain("or is it one of these?");
  });

  it("ignores messages that do not come from its host window", () => {
    const { w, result } = boot();
    result([{ n: 1, text: "Turn on the fan", risk: "low" }], null);
    expect(w.document.querySelectorAll("#cards .card")).toHaveLength(0);
    result([{ n: 1, text: "Turn on the fan", risk: "low" }]);
    expect(w.document.querySelectorAll("#cards .card")).toHaveLength(1);
  });

  it("never renders card fields as HTML", () => {
    const { w, result } = boot();
    result([{ n: '2"><img src=x onerror="window.__leak=1">', text: "<b>Turn on</b>", risk: "low" },
            { n: 1, text: "<img src=x>", risk: "low" }]);
    expect(w.document.querySelector("#cards img")).toBeNull();
    const cards = w.document.querySelectorAll("#cards .card");
    expect(cards).toHaveLength(1); // a card without a real option number is not shown at all
    expect(cards[0].textContent).toContain("<img src=x>");
  });

  it("refuses a tap when the shown text differs from the server's card", async () => {
    const { w, fetched, result, settle } = boot([{ n: 1, text: "Turn on the fan" }, { n: 2, text: "Unlock the front door" }]);
    result([{ n: 2, text: "Turn on the fan", risk: "low" }]); // a spoofed label over the real option 2
    (w.document.querySelector("#cards .card") as HTMLButtonElement).click();
    await settle();
    expect(fetched.some((f) => f.url.includes("/device/evidence"))).toBe(false);
    expect(w.document.getElementById("result")!.textContent).toMatch(/changed/i);
  });

  it("an answer from the host replaces the cards with the outcome", () => {
    const { w, result } = boot();
    result([{ n: 1, text: "Turn on the fan", risk: "low" }]);
    expect(w.document.querySelectorAll("#cards .card")).toHaveLength(1);
    w.dispatchEvent(new w.MessageEvent("message", { source: w as unknown as Window,
      data: { jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { structuredContent: { status: "answer", say: "Done: confirmed by you." } } } }));
    expect(w.document.querySelectorAll("#cards .card")).toHaveLength(0);
    expect(w.document.getElementById("actions")!.hidden).toBe(true);
    expect(w.document.getElementById("result")!.textContent).toContain("Done: confirmed by you.");
  });

  it("a new card set clears the last outcome, so an old \"Done\" never sits beside new cards", () => {
    const { w, result } = boot();
    result([{ n: 1, text: "Turn on the fan", risk: "low" }]);
    w.dispatchEvent(new w.MessageEvent("message", { source: w as unknown as Window,
      data: { jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { structuredContent: { status: "answer", say: "Done: confirmed by you, on your own device." } } } }));
    expect(w.document.getElementById("result")!.textContent).toContain("Done");
    result([{ n: 1, text: "Turn on the TV", risk: "low" }, { n: 2, text: "Turn on the fan", risk: "low" }]);
    const res = w.document.getElementById("result")!;
    expect(res.textContent).toBe("");
    expect(res.className).toBe("");
    expect([...w.document.querySelectorAll("#cards .card")].map((c) => c.textContent)).toEqual(["1Turn on the TV", "2Turn on the fan"]);
    expect(w.document.getElementById("actions")!.hidden).toBe(false);
  });

  it("sends the tap when the shown card matches the server's", async () => {
    const { w, fetched, result, settle } = boot([{ n: 1, text: "Turn on the fan" }]);
    result([{ n: 1, text: "Turn on the fan", risk: "low" }]);
    (w.document.querySelector("#cards .card") as HTMLButtonElement).click();
    await settle();
    const ev = fetched.find((f) => f.url.includes("/device/evidence"));
    expect(ev?.body).toMatchObject({ pending_id: "p_real", nonce: "n1", kind: "tap", option: 1 });
  });
});

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

  it("sends the tap when the shown card matches the server's", async () => {
    const { w, fetched, result, settle } = boot([{ n: 1, text: "Turn on the fan" }]);
    result([{ n: 1, text: "Turn on the fan", risk: "low" }]);
    (w.document.querySelector("#cards .card") as HTMLButtonElement).click();
    await settle();
    const ev = fetched.find((f) => f.url.includes("/device/evidence"));
    expect(ev?.body).toMatchObject({ pending_id: "p_real", nonce: "n1", kind: "tap", option: 1 });
  });
});

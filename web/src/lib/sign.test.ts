import { describe, expect, it, vi } from "vitest";
import {
  base64UrlDecode,
  canonicalMessage,
  createSigningFetch,
  hmac,
  sha256,
  sha256Hex,
  signRequest,
  toHex,
  withReplayGuard,
} from "./sign.js";

const KEY = "LF5iGtLB8VTa1zGePWNsBO3mm3sLmHsTkEATr-QOkPo";
const TS = 1800000000;
const EVIDENCE_BODY = '{"pending_id":"p_1","option":2}';

describe("device request signing (must match the Python hub)", () => {
  it("signs the POST /device/evidence vector", async () => {
    expect(await signRequest(KEY, "POST", "/device/evidence?r=abc", TS, EVIDENCE_BODY)).toBe(
      "abce82944c12e0912e1a208997674ad2e2da9fe6b142ead0647bc1fb75ef5523",
    );
  });

  it("signs the GET /device/pending vector", async () => {
    expect(await signRequest(KEY, "GET", "/device/pending?r=xyz", TS, "")).toBe(
      "4778a8623f588a184825392468b3df5f68361ba3ab0f3d9c999f7cb39a293c87",
    );
  });

  it("hashes the empty body like the server", async () => {
    expect(await sha256Hex("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  });

  it("gives the same answers with the pure-JS fallback (no WebCrypto)", () => {
    const enc = new TextEncoder();
    const post = canonicalMessage("post", "/device/evidence?r=abc", TS, toHex(sha256(enc.encode(EVIDENCE_BODY))));
    expect(toHex(hmac(base64UrlDecode(KEY), enc.encode(post)))).toBe(
      "abce82944c12e0912e1a208997674ad2e2da9fe6b142ead0647bc1fb75ef5523",
    );
    const get = canonicalMessage("GET", "/device/pending?r=xyz", TS, toHex(sha256(new Uint8Array())));
    expect(toHex(hmac(base64UrlDecode(KEY), enc.encode(get)))).toBe(
      "4778a8623f588a184825392468b3df5f68361ba3ab0f3d9c999f7cb39a293c87",
    );
    // a long input crosses SHA-256 block boundaries
    expect(toHex(sha256(enc.encode("a".repeat(1000))))).toBe("41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3");
  });

  it("adds a fresh r= to every URL and keeps any existing query", () => {
    const a = withReplayGuard(new URL("http://hub/device/state"));
    const b = withReplayGuard(new URL("http://hub/device/state"));
    expect(a.search).toMatch(/^\?r=[0-9a-f]{12}$/);
    expect(a.search).not.toBe(b.search);
    expect(withReplayGuard(new URL("http://hub/mcp?x=1")).search).toMatch(/^\?x=1&r=[0-9a-f]{12}$/);
  });

  it("signing fetch signs the exact path, query and body it sends", async () => {
    const seen: Array<{ url: string; init: RequestInit }> = [];
    const base = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      seen.push({ url: String(url), init: init ?? {} });
      return new Response("{}");
    });
    const creds = { device_id: "d_1", user_id: "demo", key: KEY, name: "t" };
    const f = createSigningFetch(creds, base as unknown as typeof fetch, "http://127.0.0.1:9000/");
    await f("/mcp", { method: "POST", body: '{"jsonrpc":"2.0"}', headers: { accept: "application/json" } });
    const { url, init } = seen[0];
    const u = new URL(url);
    const h = new Headers(init.headers);
    expect(u.pathname).toBe("/mcp");
    expect(h.get("x-device-id")).toBe("d_1");
    expect(h.get("content-type")).toBe("application/json");
    expect(h.get("accept")).toBe("application/json");
    const expected = await signRequest(KEY, "POST", u.pathname + u.search, Number(h.get("x-timestamp")), '{"jsonrpc":"2.0"}');
    expect(h.get("x-signature")).toBe(expected);
    expect(init.body).toBe('{"jsonrpc":"2.0"}');
  });
});

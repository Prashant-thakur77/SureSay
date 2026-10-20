// @ts-check
/**
 * Device request signing. Shared by the app and by scripts/smoke.mjs, so it is
 * plain ESM with JSDoc types and no imports.
 *
 *   message   = METHOD \n PATH?QUERY \n UNIX_SECONDS \n sha256_hex(BODY)
 *   signature = hex(HMAC-SHA256(base64url_decode(device key), message))
 *
 * The hub refuses any signature it has seen before, so every signed URL gets a
 * random `r` query parameter, and the path that is signed includes it.
 *
 * WebCrypto is used when present. Browsers hide `crypto.subtle` on plain http
 * pages that are not localhost (a tablet on the home network, say), so a small
 * pure-JS SHA-256 keeps typing and tapping working there too.
 */

const encoder = new TextEncoder();

/** @typedef {{ device_id: string, user_id: string, key: string, name: string }} DeviceCreds */

/**
 * @param {string} text base64url, with or without "=" padding
 * @returns {Uint8Array}
 */
export function base64UrlDecode(text) {
  let b64 = text.replace(/-/g, "+").replace(/_/g, "/");
  b64 += "=".repeat((4 - (b64.length % 4)) % 4);
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * @param {Uint8Array} bytes
 * @returns {string}
 */
export function toHex(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += bytes[i].toString(16).padStart(2, "0");
  return s;
}

/** @returns {SubtleCrypto | null} */
function subtle() {
  const c = globalThis.crypto;
  return c && c.subtle ? c.subtle : null;
}

/** @param {string | Uint8Array} data */
function bytesOf(data) {
  return typeof data === "string" ? encoder.encode(data) : data;
}

/**
 * @param {string | Uint8Array} data
 * @returns {Promise<string>}
 */
export async function sha256Hex(data) {
  const bytes = bytesOf(data);
  const s = subtle();
  if (s) return toHex(new Uint8Array(await s.digest("SHA-256", new Uint8Array(bytes))));
  return toHex(sha256(bytes));
}

/**
 * @param {Uint8Array} key
 * @param {string} message
 * @returns {Promise<string>}
 */
export async function hmacSha256Hex(key, message) {
  const s = subtle();
  if (s) {
    const k = await s.importKey("raw", new Uint8Array(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    return toHex(new Uint8Array(await s.sign("HMAC", k, encoder.encode(message))));
  }
  return toHex(hmac(key, encoder.encode(message)));
}

/**
 * The exact string that is signed.
 * @param {string} method
 * @param {string} pathWithQuery
 * @param {number} timestamp unix seconds
 * @param {string} bodyHashHex
 */
export function canonicalMessage(method, pathWithQuery, timestamp, bodyHashHex) {
  return `${method.toUpperCase()}\n${pathWithQuery}\n${Math.floor(timestamp)}\n${bodyHashHex}`;
}

/**
 * @param {string} deviceKey base64url device key from pairing
 * @param {string} method
 * @param {string} pathWithQuery e.g. "/device/pending?r=abc"
 * @param {number} timestamp unix seconds
 * @param {string} [body] the exact body string that will be sent ("" for none)
 * @returns {Promise<string>} lowercase hex signature
 */
export async function signRequest(deviceKey, method, pathWithQuery, timestamp, body = "") {
  const message = canonicalMessage(method, pathWithQuery, timestamp, await sha256Hex(body));
  return hmacSha256Hex(base64UrlDecode(deviceKey), message);
}

/**
 * @param {number} [bytes]
 * @returns {string} 2*bytes lowercase hex characters
 */
export function randomHex(bytes = 6) {
  const buf = new Uint8Array(bytes);
  globalThis.crypto.getRandomValues(buf);
  return toHex(buf);
}

/**
 * A copy of *url* with a fresh `r=<12 hex>` query parameter, so no two signed requests match.
 * The existing query string is kept byte for byte.
 * @param {URL} url
 * @returns {URL}
 */
export function withReplayGuard(url) {
  const out = new URL(url.href);
  const r = `r=${randomHex(6)}`;
  out.search = out.search && out.search !== "?" ? `${out.search}&${r}` : `?${r}`;
  return out;
}

/**
 * The three auth headers for one request.
 * @param {DeviceCreds} creds
 * @param {string} method
 * @param {string} pathWithQuery
 * @param {string} body
 * @param {number} [nowSeconds]
 * @returns {Promise<Record<string, string>>}
 */
export async function signedHeaders(creds, method, pathWithQuery, body, nowSeconds) {
  const ts = Math.floor(nowSeconds ?? Date.now() / 1000);
  const signature = await signRequest(creds.key, method, pathWithQuery, ts, body);
  return { "x-device-id": creds.device_id, "x-timestamp": String(ts), "x-signature": signature };
}

/**
 * A `fetch` that signs every request with the device key. Used for `/device/*`
 * and as the custom fetch of the MCP client transport.
 *
 * Only string bodies are supported: the signature covers the exact bytes sent.
 * @param {DeviceCreds} creds
 * @param {typeof fetch} [baseFetch]
 * @param {string} [baseUrl] used to resolve relative URLs (same-origin hub)
 * @returns {(input: string | URL | Request, init?: RequestInit) => Promise<Response>}
 */
export function createSigningFetch(creds, baseFetch, baseUrl) {
  const doFetch = baseFetch ?? globalThis.fetch.bind(globalThis);
  return async (input, init = {}) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const base = baseUrl ?? (typeof location !== "undefined" ? location.href : undefined);
    const url = withReplayGuard(new URL(raw, base));
    const method = (init.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    if (init.body != null && typeof init.body !== "string") {
      throw new TypeError("signed requests need a string body");
    }
    const body = typeof init.body === "string" ? init.body : "";
    const headers = new Headers(init.headers);
    const auth = await signedHeaders(creds, method, url.pathname + url.search, body);
    for (const [k, v] of Object.entries(auth)) headers.set(k, v);
    if (body && !headers.has("content-type")) headers.set("content-type", "application/json");
    return doFetch(url.href, { ...init, method, headers, body: body === "" ? undefined : body });
  };
}

// ---------------------------------------------------------------------------
// Pure-JS SHA-256 and HMAC (FIPS 180-4, RFC 2104), only used without WebCrypto.

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

/** @param {number} x @param {number} n */
const ror = (x, n) => (x >>> n) | (x << (32 - n));

/**
 * @param {Uint8Array} bytes
 * @returns {Uint8Array}
 */
export function sha256(bytes) {
  const len = bytes.length;
  const total = ((len + 9 + 63) >> 6) << 6;
  const buf = new Uint8Array(total);
  buf.set(bytes);
  buf[len] = 0x80;
  const view = new DataView(buf.buffer);
  const bits = len * 8;
  view.setUint32(total - 8, Math.floor(bits / 0x100000000));
  view.setUint32(total - 4, bits >>> 0);
  const H = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const W = new Uint32Array(64);
  for (let off = 0; off < total; off += 64) {
    for (let i = 0; i < 16; i++) W[i] = view.getUint32(off + i * 4);
    for (let i = 16; i < 64; i++) {
      const a = W[i - 15];
      const b = W[i - 2];
      const s0 = ror(a, 7) ^ ror(a, 18) ^ (a >>> 3);
      const s1 = ror(b, 17) ^ ror(b, 19) ^ (b >>> 10);
      W[i] = (W[i - 16] + s0 + W[i - 7] + s1) | 0;
    }
    let a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (ror(e, 6) ^ ror(e, 11) ^ ror(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) | 0;
      const t2 = ((ror(a, 2) ^ ror(a, 13) ^ ror(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
  }
  const out = new Uint8Array(32);
  const ov = new DataView(out.buffer);
  for (let i = 0; i < 8; i++) ov.setUint32(i * 4, H[i]);
  return out;
}

/**
 * @param {Uint8Array} key
 * @param {Uint8Array} message
 * @returns {Uint8Array}
 */
export function hmac(key, message) {
  const block = new Uint8Array(64);
  block.set(key.length > 64 ? sha256(key) : key);
  const inner = new Uint8Array(64 + message.length);
  const outer = new Uint8Array(64 + 32);
  for (let i = 0; i < 64; i++) {
    inner[i] = block[i] ^ 0x36;
    outer[i] = block[i] ^ 0x5c;
  }
  inner.set(message, 64);
  outer.set(sha256(inner), 64);
  return sha256(outer);
}

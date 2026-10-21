#!/usr/bin/env node
/**
 * Live check against a running hub, signing exactly like the app (it imports
 * the app's own src/lib/sign.js).
 *
 *   SURESAY_ASR=text SURESAY_RANKER=fuzzy SURESAY_AGENT_MODE=direct .venv/bin/python -m suresay.hub
 *   node web/scripts/smoke.mjs
 *
 * Env: HUB_URL (default http://127.0.0.1:9000), PAIRING_CODE_FILE (default var/pairing_code).
 * Pairing uses the hub's one-time code, so run this once per hub start.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { createSigningFetch, signedHeaders } from "../src/lib/sign.js";

const HUB = (process.env.HUB_URL ?? "http://127.0.0.1:9000").replace(/\/+$/, "");
const CODE_FILE = process.env.PAIRING_CODE_FILE ?? fileURLToPath(new URL("../../var/pairing_code", import.meta.url));

let failures = 0;
function check(ok, label, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? `  (${detail})` : ""}`);
  if (!ok) failures += 1;
  return ok;
}

async function json(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

async function main() {
  // 0. the hub serves the built web client at "/"
  const page = await fetch(`${HUB}/`);
  const html = await page.text();
  check(page.ok && html.includes('<div id="root">') && html.includes("<title>SureSay</title>"), "hub serves web/dist at /", `HTTP ${page.status}`);

  // 1. pair with the code the hub printed
  const code = readFileSync(CODE_FILE, "utf8").trim();
  const pairRes = await fetch(`${HUB}/device/pair`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ code, name: "smoke test" }),
  });
  const creds = await json(pairRes);
  if (!check(pairRes.ok && typeof creds.key === "string", "paired with the one-time code", `device ${creds.device_id ?? "?"}, user ${creds.user_id ?? "?"}`)) {
    throw new Error(`pairing failed: ${JSON.stringify(creds)}`);
  }

  const signed = createSigningFetch(creds, fetch, `${HUB}/`);
  const call = async (method, path, body) => {
    const res = await signed(`${HUB}${path}`, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
      headers: body === undefined ? undefined : { "content-type": "application/json" },
    });
    return { status: res.status, data: await json(res) };
  };

  // 2. replay protection: the very same signed request twice is refused the second time
  const path = "/device/pending?r=replaytest" + Date.now().toString(16);
  const headers = await signedHeaders(creds, "GET", path, "");
  const r1 = await fetch(`${HUB}${path}`, { headers });
  const r2 = await fetch(`${HUB}${path}`, { headers });
  check(r1.status === 200 && r2.status === 401, "a replayed signature is refused", `first ${r1.status}, replay ${r2.status} ${(await json(r2)).error ?? ""}`);

  // 3. start from a clean demo home
  const reset = await call("POST", "/device/reset", {});
  check(reset.status === 200 && reset.data.ok === true, "POST /device/reset");
  const before = await call("GET", "/device/state");
  check(before.status === 200 && before.data.home.devices.fan.on === false, "fan is off before the turn");

  // 4. a typed turn: "van on" (the fuzzy ranker should guess the fan first)
  const turn = await call("POST", "/device/turn", { text: "van on", session_id: "smoke" });
  const r = turn.data.result ?? {};
  check(turn.status === 200 && turn.data.mode === "direct" && r.status === "choose", "typed turn returned cards", `mode ${turn.data.mode}, status ${r.status}, ${turn.data.ms} ms`);
  const set = (turn.data.pending ?? []).find((p) => p.pending_id === r.pending_id);
  const texts = set?.options.map((o) => o.text) ?? [];
  check(texts.length === 3, "three cards came back", texts.join(" | "));
  check(texts[0] === "Turn on the bedroom fan", "first card is “Turn on the bedroom fan”", `heard “${r.heard}”, asr ${r.asr}, ranker ${r.ranker}`);
  if (!set) throw new Error("no pending set to answer");

  // 5. MCP: connect with the signing fetch, and list receipts
  const transport = new StreamableHTTPClientTransport(new URL(`${HUB}/mcp`), { fetch: signed });
  const client = new Client({ name: "suresay-smoke", version: "0.1.0" });
  await client.connect(transport);
  check(!!transport.protocolVersion, "MCP connected through the signing fetch", `protocol ${transport.protocolVersion}, server ${client.getServerVersion()?.name}`);
  const listed = await client.callTool({ name: "receipts_list", arguments: {} });
  const listedJson = JSON.parse(listed.content[0].text);
  check(Array.isArray(listedJson.receipts), "MCP receipts_list works", `${listedJson.receipts.length} receipts`);

  // 6. the gate: confirming with no user evidence is refused, and nothing changes
  const noEvidence = await client.callTool({ name: "confirm", arguments: { pending_id: set.pending_id, evidence_ref: "" } });
  const refused = JSON.parse(noEvidence.content[0].text);
  check(refused.status === "refused", "confirm without the user's evidence is refused", refused.reason);

  // 7. tap evidence for card 1, then confirm through MCP
  const ev = await call("POST", "/device/evidence", { pending_id: set.pending_id, nonce: set.nonce, kind: "tap", option: 1 });
  check(ev.status === 200 && ev.data.decision?.kind === "choose" && ev.data.decision.option === 1, "tap evidence recorded for option 1", ev.data.evidence_ref);
  const confirmed = await client.callTool({ name: "confirm", arguments: { pending_id: set.pending_id, evidence_ref: ev.data.evidence_ref } });
  const done = JSON.parse(confirmed.content[0].text);
  check(done.status === "done", "MCP confirm released the action", done.message);
  check(done.receipt?.how?.channel === "tap" && done.receipt.checks.every((c) => c.ok), "receipt says tap, every check passed", `${done.receipt?.receipt_id}, ${done.receipt?.checks.length} checks`);
  const mcpText = JSON.stringify([listed, noEvidence, confirmed]);
  check(!mcpText.includes(set.nonce), "the nonce never appears in an MCP result");

  // 8. the same evidence cannot be used twice
  const again = await client.callTool({ name: "confirm", arguments: { pending_id: set.pending_id, evidence_ref: ev.data.evidence_ref } });
  check(JSON.parse(again.content[0].text).status === "refused", "re-using the evidence is refused");

  // 8b. speak for me: a tapped tile proposes say_for_me; the user still confirms it
  const proposed = await call("POST", "/device/propose", { action: "say_for_me", args: { text: "Thank you." } });
  const sayset = proposed.data.pending;
  check(proposed.status === 200 && sayset?.options?.length === 1 && sayset.origin === "user_words", "POST /device/propose opened a one-card set", sayset?.options?.[0]?.text);
  const sayEv = await call("POST", "/device/evidence", { pending_id: sayset.pending_id, nonce: sayset.nonce, kind: "tap", option: 1 });
  check(sayEv.status === 200 && sayEv.data.decision?.kind === "choose", "tap evidence recorded for the spoken sentence");
  const sayDone = JSON.parse((await client.callTool({ name: "confirm", arguments: { pending_id: sayset.pending_id, evidence_ref: sayEv.data.evidence_ref } })).content[0].text);
  check(sayDone.status === "done" && sayDone.result?.say === "Thank you.", "MCP confirm returned result.say", JSON.stringify(sayDone.result));
  check(!JSON.stringify(sayDone).includes(sayset.nonce), "the nonce is not in the say_for_me result");
  // 8c. the doorbell (simulated): Ravi rings, the user taps the reply card, it is said at the door
  const bell = await call("POST", "/device/doorbell", { visitor: "ravi" });
  const door = bell.data.pending;
  check(bell.status === 200 && door?.origin === "doorbell" && door?.context?.visitor?.id === "ravi", "POST /device/doorbell opened the door's cards", `${door?.options?.length} options · ${bell.data.say}`);
  const replyCard = door?.options?.find((o) => o.action === "doorbell_reply");
  const unlockCard = door?.options?.find((o) => o.action === "door_lock" && o.args?.locked === false);
  check(!!replyCard && unlockCard?.risk === "high", "the door's cards: a reply, and unlock asks twice", replyCard?.text);
  const doorEv = await call("POST", "/device/evidence", { pending_id: door.pending_id, nonce: door.nonce, kind: "tap", option: replyCard.n });
  const doorDone = JSON.parse((await client.callTool({ name: "confirm", arguments: { pending_id: door.pending_id, evidence_ref: doorEv.data.evidence_ref } })).content[0].text);
  check(doorDone.status === "done" && typeof doorDone.result?.said_at_door === "string", "MCP confirm said the reply at the door", doorDone.result?.said_at_door);
  const badBell = await call("POST", "/device/doorbell", { visitor: "burglar" });
  check(badBell.status === 400, "doorbell refuses an unknown visitor");

  const bad = await call("POST", "/device/propose", { action: "rm_rf", args: {} });
  check(bad.status === 400, "propose refuses an action outside the catalog", bad.data.error);
  await client.close();

  // 9. the home really changed
  const after = await call("GET", "/device/state");
  check(after.status === 200 && after.data.home.devices.fan.on === true, "GET /device/state shows the fan on");
  check(after.data.receipts?.some((x) => x.receipt_id === done.receipt?.receipt_id), "the receipt is in /device/state");
  const st = after.data.stats;
  check(!!st && st.confirmed >= 2 && st.without_you === 0, "stats: confirmed by you, never without you", JSON.stringify(st));

  console.log(failures === 0 ? "\nSMOKE OK" : `\nSMOKE FAILED (${failures})`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(`FAIL  ${err instanceof Error ? err.message : err}`);
  process.exit(1);
});

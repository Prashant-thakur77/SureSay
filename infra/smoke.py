"""End-to-end check of a deployed (or local) hub over HTTPS.

    python infra/smoke.py https://<hub-url> [--code 123456]

Pairs a device (fresh code from DynamoDB if --code is not given), sends "van on", checks three cards,
confirms card 1 with a tap through the device channel, verifies the fan changed, then connects as the
agent over MCP Streamable HTTP and shows that the agent's own confirm is refused.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from confirm_gate import sign_request
from strands.tools.mcp import MCPClient

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--code")
    args = ap.parse_args()
    base = args.url.rstrip("/")
    http = httpx.Client(base_url=base, timeout=60)
    code = args.code or subprocess.run([sys.executable, "-m", "suresay.cli", "pair"], capture_output=True, text=True,
                                       check=True, env={**os.environ, "SURESAY_BACKEND": "aws"}).stdout.strip()
    dev = http.post("/device/pair", json={"code": code, "name": "smoke test"}).json()
    print("paired", dev["device_id"], "for", dev["user_id"])

    def signed(method: str, path: str, payload: object = None) -> dict:
        body = b"" if payload is None else json.dumps(payload).encode()
        path = f"{path}{'&' if '?' in path else '?'}r={time.perf_counter_ns()}"
        ts = int(time.time())
        h = {"x-device-id": dev["device_id"], "x-timestamp": str(ts),
             "x-signature": sign_request(dev["key"], method, path, ts, body)}
        if body:
            h["content-type"] = "application/json"
        r = http.request(method, path, content=body or None, headers=h)
        r.raise_for_status()
        return r.json()

    signed("POST", "/device/reset", {})
    t0 = time.perf_counter()
    turn = signed("POST", "/device/turn", {"text": "van on"})
    print(f"turn ({turn['mode']}, {(time.perf_counter() - t0) * 1000:.0f} ms):", turn["reply"])
    p = turn["pending"][0]
    print("cards:", [o["text"] for o in p["options"]])
    assert p["options"][0]["text"] == "Turn on the bedroom fan"
    ev = signed("POST", "/device/evidence", {"pending_id": p["pending_id"], "nonce": p["nonce"], "kind": "tap", "option": 1})
    done = signed("POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    print("confirm:", done["status"], "-", done.get("message"))
    state = signed("GET", "/device/state")
    assert state["home"]["devices"]["fan"]["on"] is True
    print("fan is on; receipt", done["receipt"]["receipt_id"])

    token = os.environ.get("SURESAY_AGENT_TOKEN") or (ROOT / "infra/.state/agent_token").read_text().strip()
    agent = MCPClient(url=f"{base}/mcp", headers={"Authorization": f"Bearer {token}", "X-SureSay-User": dev["user_id"]})
    with agent:
        tools = sorted(t.tool_name for t in agent.list_tools_sync())
        print(f"agent sees {len(tools)} MCP tools:", ", ".join(tools))
        r = agent.call_tool_sync(tool_use_id="s", name="cart_order", arguments={"product_id": "usb_cable", "qty": 10})
        proposal = json.loads(r["content"][0]["text"])
        r = agent.call_tool_sync(tool_use_id="s2", name="confirm",
                                 arguments={"pending_id": proposal["pending_id"], "evidence_ref": "the user said yes"})
        refused = json.loads(r["content"][0]["text"])
        print("agent's own confirm:", refused["status"], "-", refused["reason"])
        assert refused["status"] == "refused"
    init = http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                              "clientInfo": {"name": "smoke", "version": "1"}}},
                     headers={"authorization": f"Bearer {token}", "accept": "application/json, text/event-stream"})
    print("MCP initialize -> protocolVersion", init.json()["result"]["protocolVersion"])
    print("SMOKE OK")


if __name__ == "__main__":
    main()

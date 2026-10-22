"""Live checks of the deployed hub: MCP conformance as Alexa+ and other hosts see it, and how fast it answers.

Every check runs against the real server over HTTPS, as an MCP client (JSON-RPC over Streamable HTTP):
authentication (401 without credentials, OAuth metadata), the initialize handshake in each protocol version
(including the Alexa+ MCP client's own request), tool annotations, the MCP Apps card UI (declared on the tool,
returned in the result, readable as a resource), and the guarantee: a write only proposes, and the agent's own
confirm is refused.

Latency is reported two ways, and labelled: round trips from the machine running this script (they include the
network to us-east-1, measured separately with /healthz), and the server's own processing time for real requests,
from the CloudWatch metrics the hub emits (Embedded Metric Format).

    python eval/run_live_checks.py https://<hub-url>   ->  eval/results/live_checks.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.common import write_result  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPEATS = 15


def p(values: list[float], q: float) -> float:
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1)


class Live:
    def __init__(self, base: str, token: str, user: str = "demo") -> None:
        self.http = httpx.Client(base_url=base, timeout=60)
        self.token, self.user = token, user
        self.checks: list[dict[str, Any]] = []
        self.id = 0

    def rpc(self, method: str, params: dict[str, Any] | None = None, *, version: str = "2025-11-25",
            auth: bool = True) -> tuple[httpx.Response, float]:
        self.id += 1
        h = {"content-type": "application/json", "accept": "application/json, text/event-stream",
             "mcp-protocol-version": version}
        if auth:
            h |= {"authorization": f"Bearer {self.token}", "x-suresay-user": self.user}
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id, "method": method}
        if params is not None:
            body["params"] = params
        t0 = time.perf_counter()
        r = self.http.post("/mcp", headers=h, json=body)
        return r, (time.perf_counter() - t0) * 1000

    def result(self, method: str, params: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        r, _ = self.rpc(method, params, **kw)
        r.raise_for_status()
        return r.json()["result"]

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "passed": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))


def tool_json(res: dict[str, Any]) -> dict[str, Any]:
    if isinstance(res.get("structuredContent"), dict):
        return res["structuredContent"]
    return json.loads(res["content"][0]["text"])


def conformance(lv: Live) -> None:
    r, _ = lv.rpc("tools/list", auth=False)
    lv.check("no credentials: 401", r.status_code == 401, f"status {r.status_code}")
    lv.check("401 carries no WWW-Authenticate (Alexa+ requirement)", "www-authenticate" not in r.headers)
    prm = lv.http.get("/.well-known/oauth-protected-resource").json()
    lv.check("Protected Resource Metadata (RFC 9728)", bool(prm.get("resource")) and bool(prm.get("authorization_servers")))
    asm = lv.http.get("/.well-known/oauth-authorization-server").json()
    lv.check("authorization server metadata: PKCE S256", asm.get("code_challenge_methods_supported") == ["S256"])

    for version, client in (("2025-03-26", "Alexa+ MCP Client"), ("2025-06-18", "any MCP client"),
                            ("2025-11-25", "any MCP client")):
        init = lv.result("initialize", {"protocolVersion": version, "capabilities": {"roots": {"listChanged": True}},
                                        "clientInfo": {"name": client, "version": "1.0.0"}}, version=version)
        lv.check(f"initialize answered in {version} ({client})", init.get("protocolVersion") == version,
                 f"server said {init.get('protocolVersion')}")

    tools = lv.result("tools/list")["tools"]
    names = {t["name"] for t in tools}
    lv.check("tools listed", len(tools) >= 15, f"{len(tools)} tools")
    lv.check("every tool has a description and an input schema",
             all(t.get("description") and t.get("inputSchema", {}).get("type") == "object" for t in tools))
    reads = [t for t in tools if (t.get("annotations") or {}).get("readOnlyHint") is True]
    writes = [t for t in tools if (t.get("annotations") or {}).get("readOnlyHint") is False]
    lv.check("every tool is annotated read-only or not", len(reads) + len(writes) == len(tools),
             f"{len(reads)} reads, {len(writes)} writes")
    und = next((t for t in tools if t["name"] == "understand"), {})
    lv.check("understand declares its MCP Apps UI", (und.get("_meta") or {}).get("ui", {}).get("resourceUri") == "ui://suresay/cards.html")
    res = lv.result("resources/read", {"uri": "ui://suresay/cards.html"})["contents"][0]
    lv.check("the card UI is an MCP App resource", res.get("mimeType") == "text/html;profile=mcp-app" and "ui/initialize" in res.get("text", ""),
             f"{len(res.get('text', '')) // 1024} KB")

    out = lv.result("tools/call", {"name": "understand", "arguments": {"user_id": "", "transcript": "van on"}})
    data = tool_json(out)
    lv.check("understand: three cards for a misheard command", data.get("status") == "choose" and len(data.get("candidates", [])) == 3,
             " / ".join(c["text"] for c in data.get("candidates", [])))
    ui = (out.get("_meta") or {}).get("ui", {})
    lv.check("the result names its UI with invoking/invoked (where Alexa+ looks)", ui.get("resourceUri") == "ui://suresay/cards.html" and bool(ui.get("invoking")))
    lv.check("no nonce in any tool result", "nonce" not in json.dumps(out))

    before = tool_json(lv.result("tools/call", {"name": "home_status", "arguments": {"user_id": ""}}))
    w = tool_json(lv.result("tools/call", {"name": "door_lock", "arguments": {"locked": False, "user_id": ""}}))
    lv.check("a write only proposes", w.get("status") == "pending_user_confirmation", w.get("status", ""))
    forged = tool_json(lv.result("tools/call", {"name": "confirm", "arguments": {"pending_id": w.get("pending_id", ""),
                                                                                 "evidence_ref": "the user said yes"}}))
    lv.check("the agent's own confirm is refused", forged.get("status") == "refused", forged.get("reason", "")[:80])
    after = tool_json(lv.result("tools/call", {"name": "home_status", "arguments": {"user_id": ""}}))
    lv.check("nothing changed", before.get("front_door") == after.get("front_door") == "locked" or before == after,
             f"front door {after.get('front_door')}")
    st = tool_json(lv.result("tools/call", {"name": "pending_status", "arguments": {"pending_id": w.get("pending_id", "")}}))
    lv.check("pending_status tells the agent it is still waiting", st.get("state") == "waiting_for_user", st.get("state", ""))
    lv.check("names", {"understand", "confirm", "pending_status", "home_status", "door_lock", "cart_order"} <= names)


def latency(lv: Live) -> dict[str, Any]:
    def times(fn: Any) -> list[float]:
        return [fn() for _ in range(REPEATS)]

    def health() -> float:
        t0 = time.perf_counter()
        lv.http.get("/healthz").raise_for_status()
        return (time.perf_counter() - t0) * 1000

    def call(name: str, args: dict[str, Any]) -> Any:
        return lambda: lv.rpc("tools/call", {"name": name, "arguments": args})[1]

    series = {"healthz (network baseline)": times(health),
              "tools/list": times(lambda: lv.rpc("tools/list")[1]),
              "tools/call home_status": times(call("home_status", {"user_id": ""})),
              "tools/call understand (typed)": times(call("understand", {"user_id": "", "transcript": "fan on"}))}
    out = {k: {"p50_ms": p(v, 0.5), "p95_ms": p(v, 0.95), "n": len(v)} for k, v in series.items()}
    base = out["healthz (network baseline)"]["p50_ms"]
    for k, v in out.items():
        if k != "healthz (network baseline)":
            v["minus_network_p50_ms"] = round(v["p50_ms"] - base, 1)
    return out


def server_side() -> dict[str, Any] | None:
    """Server processing time of real requests, from CloudWatch (UnderstandMs, by input), last 48 hours."""
    try:
        import boto3

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        out: dict[str, Any] = {}
        for inp in ("typed", "voice"):
            st = cw.get_metric_statistics(Namespace="SureSay", MetricName="UnderstandMs",
                                          Dimensions=[{"Name": "Input", "Value": inp}],
                                          StartTime=time.time() - 48 * 3600, EndTime=time.time(), Period=48 * 3600,
                                          ExtendedStatistics=["p50", "p95"], Statistics=["SampleCount"])
            if st["Datapoints"]:
                d = max(st["Datapoints"], key=lambda x: x["SampleCount"])
                out[inp] = {"requests": int(d["SampleCount"]), "p50_ms": round(d["ExtendedStatistics"]["p50"], 1),
                            "p95_ms": round(d["ExtendedStatistics"]["p95"], 1)}
        return out or None
    except Exception as e:  # noqa: BLE001
        print("cloudwatch:", e)
        return None


def main() -> None:
    base = (sys.argv[1] if len(sys.argv) > 1 else "https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws").rstrip("/")
    token = (ROOT / "infra" / ".state" / "agent_token").read_text().strip()
    lv = Live(base, token)
    conformance(lv)
    lat = latency(lv)
    for k, v in lat.items():
        print(f"{k:34s} p50 {v['p50_ms']:7.1f} ms  p95 {v['p95_ms']:7.1f} ms")
    srv = server_side()
    print("server side:", srv)
    passed = sum(c["passed"] for c in lv.checks)
    path = write_result("live_checks", {"url": base, "checks": lv.checks, "passed": passed, "total": len(lv.checks),
                                        "round_trip_from_test_machine": lat, "server_side_understand": srv,
                                        "note": "round trips include the network from the test machine to us-east-1"})
    print(f"{passed}/{len(lv.checks)} checks passed; wrote {path}")


if __name__ == "__main__":
    main()

"""Claim 4 — fast enough to talk to.

* ``understand``: 100 runs on dev-speaker clips through the configured live stack (ASR + ranker),
  p50 / p95 of total, ASR and ranking time.
* the gate: 100 confirms of a no-op action, timing everything ``confirm`` adds (checks, atomic nonce
  consumption, receipt) against calling the no-op directly — on SQLite and, when a table is given,
  on DynamoDB. Also the full device round trip over HTTP (evidence + confirm).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confirm_gate import ActionRegistry, DeviceRegistry, DynamoStore, Gate, SqliteStore  # noqa: E402

from eval.common import DATA, EVAL, SPLIT, percentile, write_result  # noqa: E402

RUNS = 100


def stats(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "p50_ms": percentile(values, 0.5), "p95_ms": percentile(values, 0.95),
            "mean_ms": round(statistics.fmean(values), 2) if values else None}


def gate_overhead(store: Any, runs: int = RUNS) -> dict[str, Any]:
    reg = ActionRegistry()

    @reg.write("noop", risk="low", preview=lambda a: "Do nothing")
    def noop() -> dict[str, Any]:
        return {"ok": True}

    gate = Gate(store, reg)
    devices = DeviceRegistry(store)
    device = devices.pair(devices.start_pairing("lat"), name="lat")
    direct, gated = [], []
    for _ in range(runs):
        t0 = time.perf_counter()
        noop()
        direct.append((time.perf_counter() - t0) * 1000)
        ps = gate.propose("lat", [("noop", {})])
        nonce = next(p["nonce"] for p in gate.device_pending(device) if p["pending_id"] == ps.pending_id)
        ev = gate.submit_tap(device, ps.pending_id, nonce, option=1)
        t0 = time.perf_counter()
        out = gate.confirm(ps.pending_id, ev["evidence_ref"])
        gated.append((time.perf_counter() - t0) * 1000)
        assert out["status"] == "done"
    added = [g - d for g, d in zip(gated, direct, strict=True)]
    return {"confirm": stats(gated), "direct_call": stats(direct), "added_by_gate": stats(added)}


def http_round_trip(runs: int = RUNS) -> dict[str, Any]:
    from eval.harness import Adversary, LiveHub, UserDevice

    times = []
    with tempfile.TemporaryDirectory() as tmp, LiveHub(Path(tmp), store="sqlite") as hub:
        user = UserDevice(hub)
        with Adversary(hub) as agent:
            for _ in range(runs):
                pid = agent.call("home_set", {"device": "fan", "on": True})["pending_id"]
                p = next(x for x in user.pending() if x["pending_id"] == pid)
                t0 = time.perf_counter()
                ev = user.tap(p, option=1)
                out = user.confirm(pid, ev["evidence_ref"])
                times.append((time.perf_counter() - t0) * 1000)
                assert out["status"] == "done", out
    return stats(times)


def cloud_gate(hub_url: str, runs: int) -> dict[str, Any]:
    """The deployed hub on Lambda (us-east-1, DynamoDB in-region): the gate's own time as it reports it,
    and the device's full evidence + confirm round trip from wherever this script runs."""
    import os
    import subprocess

    import httpx
    from confirm_gate import sign_request
    from strands.tools.mcp import MCPClient

    from eval.common import ROOT

    base = hub_url.rstrip("/")
    http = httpx.Client(base_url=base, timeout=60)
    code = subprocess.run([sys.executable, "-m", "suresay.cli", "pair"], capture_output=True, text=True, check=True,
                          env={**os.environ, "SURESAY_BACKEND": "aws"}).stdout.strip()
    dev = http.post("/device/pair", json={"code": code, "name": "latency"}).json()

    def signed(method: str, path: str, payload: Any = None) -> dict[str, Any]:
        body = b"" if payload is None else json.dumps(payload).encode()
        path = f"{path}?r={time.perf_counter_ns()}"
        ts = int(time.time())
        h = {"x-device-id": dev["device_id"], "x-timestamp": str(ts), "content-type": "application/json",
             "x-signature": sign_request(dev["key"], method, path, ts, body)}
        return http.request(method, path, content=body or None, headers=h).json()

    token = (ROOT / "infra/.state/agent_token").read_text().strip()
    agent = MCPClient(url=f"{base}/mcp", headers={"Authorization": f"Bearer {token}", "X-SureSay-User": dev["user_id"]})
    gate_ms, round_trip = [], []
    with agent:
        for _ in range(runs):
            r = agent.call_tool_sync(tool_use_id="l", name="home_set", arguments={"device": "fan", "on": True})
            pid = json.loads(r["content"][0]["text"])["pending_id"]
            p = None
            for _ in range(20):  # the kind index is eventually consistent
                p = next((x for x in signed("GET", "/device/pending")["pending"] if x["pending_id"] == pid), None)
                if p:
                    break
                time.sleep(0.2)
            assert p is not None
            t0 = time.perf_counter()
            ev = signed("POST", "/device/evidence", {"pending_id": pid, "nonce": p["nonce"], "kind": "tap", "option": 1})
            out = signed("POST", "/device/confirm", {"pending_id": pid, "evidence_ref": ev["evidence_ref"]})
            round_trip.append((time.perf_counter() - t0) * 1000)
            assert out["status"] == "done", out
            gate_ms.append(out["timing"]["gate_ms"])
    return {"hub": base, "store": "DynamoDB (in-region, on Lambda)", "gate_added_in_region": stats(gate_ms),
            "device_round_trip_from_client": stats(round_trip),
            "client_location_note": "round trip includes the internet path from the machine running this script"}


def cloud_understand(hub_url: str, runs: int) -> dict[str, Any]:
    """Dev clips sent as voice turns to the deployed hub; the hub reports understand's own time on Lambda."""
    import base64
    import os
    import subprocess

    import httpx
    from confirm_gate import sign_request

    from eval.asr_cache import _count_spend

    rows = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    clips = sorted((r for r in rows if r["speaker"] in SPLIT["dev"] and r["kind"] in ("word", "sentence")),
                   key=lambda r: r["wav"])
    clips = clips[:: max(1, len(clips) // runs)][:runs]
    base = hub_url.rstrip("/")
    http = httpx.Client(base_url=base, timeout=60)
    code = subprocess.run([sys.executable, "-m", "suresay.cli", "pair"], capture_output=True, text=True, check=True,
                          env={**os.environ, "SURESAY_BACKEND": "aws"}).stdout.strip()
    dev = http.post("/device/pair", json={"code": code, "name": "latency-understand"}).json()

    def signed(method: str, path: str, payload: Any = None) -> dict[str, Any]:
        body = b"" if payload is None else json.dumps(payload).encode()
        path = f"{path}?r={time.perf_counter_ns()}"
        ts = int(time.time())
        h = {"x-device-id": dev["device_id"], "x-timestamp": str(ts), "content-type": "application/json",
             "x-signature": sign_request(dev["key"], method, path, ts, body)}
        return http.request(method, path, content=body or None, headers=h).json()

    total, asr_ms, rank_ms, engines = [], [], [], set()
    failures: list[str] = []
    for c in clips:
        out = signed("POST", "/device/turn", {"audio_b64": base64.b64encode((DATA / c["wav"]).read_bytes()).decode()})
        res = out.get("result") or {}
        t = res.get("timing") or {}
        if res.get("asr") == "unavailable":  # recognition failed: report it, never time it as 0 ms
            failures.append(str(res.get("reason")))
            continue
        if "total_ms" in t:
            total.append(t["total_ms"])
            asr_ms.append(t.get("asr_ms", 0.0))
            rank_ms.append(t.get("rank_ms", 0.0))
            engines.add(res.get("asr"))
    signed("POST", "/device/reset", {})
    if any(str(e).startswith("transcribe") for e in engines):
        _count_spend(len(total))
    elif total:  # Nova 2 Sonic in Lambda: its tokens are not reported back here, so count the clips
        spend = EVAL / "results" / "spend.json"
        doc = json.loads(spend.read_text())
        doc["nova_sonic_cloud_clips"] = doc.get("nova_sonic_cloud_clips", 0) + len(total)
        spend.write_text(json.dumps(doc, indent=1))
    return {"hub": base, "where": "measured inside the Lambda function (us-east-1)", "asr_engines": sorted(engines),
            "clips": len(total), "failed": len(failures), "failures": sorted(set(failures)),
            "total": stats(total), "asr": stats(asr_ms), "rank": stats(rank_ms)}


def cloud_mcp_typed(hub_url: str, runs: int) -> dict[str, Any]:
    """understand on typed text through MCP on the deployed hub: the in-function time (what an MCP host in the same
    region would add to a turn), and the round trip from here."""
    from strands.tools.mcp import MCPClient

    from eval.common import ROOT

    token = (ROOT / "infra/.state/agent_token").read_text().strip()
    client = MCPClient(url=f"{hub_url.rstrip('/')}/mcp", headers={"Authorization": f"Bearer {token}", "X-SureSay-User": "latency"})
    phrases = ["van on", "lights off", "is the door locked", "call mum", "need bread"]
    inside, trip = [], []
    with client:
        for i in range(runs):
            t0 = time.perf_counter()
            r = client.call_tool_sync(tool_use_id="m", name="understand",
                                      arguments={"user_id": "latency", "transcript": phrases[i % len(phrases)]})
            trip.append((time.perf_counter() - t0) * 1000)
            out = json.loads(r["content"][0]["text"])
            inside.append(out["timing"]["total_ms"])
    return {"in_function": stats(inside), "round_trip_from_client": stats(trip)}


def understand_latency(runs: int, asr: str, ranker: str) -> dict[str, Any]:
    from dataclasses import replace

    from suresay.app import SureSay
    from suresay.config import Settings
    from suresay.understand import understand

    rows = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    clips = [r for r in rows if r["speaker"] in SPLIT["dev"] and r["kind"] in ("word", "sentence")]
    clips = sorted(clips, key=lambda r: r["wav"])[:: max(1, len(clips) // runs)][:runs]
    with tempfile.TemporaryDirectory() as tmp:
        cfg = replace(Settings(), backend="local", data_dir=Path(tmp), asr=asr, ranker=ranker, memory_id="")
        s = SureSay(cfg)
        s.asr.transcribe((DATA / clips[0]["wav"]).read_bytes())  # load the model before timing
        total, asr_ms, rank_ms = [], [], []
        for c in clips:
            audio = (DATA / c["wav"]).read_bytes()
            t0 = time.perf_counter()
            out = understand(s, "demo", audio=audio)
            total.append((time.perf_counter() - t0) * 1000)
            asr_ms.append(out["timing"]["asr_ms"])
            rank_ms.append(out["timing"]["rank_ms"])
        return {"asr_engine": s.asr.name, "ranker": s.ranker.name, "clips": len(clips),
                "total": stats(total), "asr": stats(asr_ms), "rank": stats(rank_ms)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr", default="whisper")
    ap.add_argument("--ranker", default="fuzzy")
    ap.add_argument("--dynamo-table", default="", help="also time the gate on this table from here (adds WAN latency)")
    ap.add_argument("--hub-url", default="", help="deployed hub: time the gate inside AWS")
    ap.add_argument("--runs", type=int, default=RUNS)
    ap.add_argument("--run", default=None)
    ap.add_argument("--recogniser-only", default="",
                    help="time only the deployed hub's recogniser (voice turns, measured in Lambda) into "
                         "results/<run>/latency_<this name>.json; deploy with SURESAY_ASR set to it first")
    args = ap.parse_args()
    if args.recogniser_only:
        if not args.hub_url:
            raise SystemExit("--recogniser-only needs --hub-url")
        res = cloud_understand(args.hub_url, args.runs)
        path = write_result(f"latency_{args.recogniser_only.replace('-', '_')}", res, run=args.run)
        print(f"{res['asr_engines']}: recognition p50 {res['asr']['p50_ms']} ms, p95 {res['asr']['p95_ms']} ms "
              f"(turn p50 {res['total']['p50_ms']} ms) in Lambda; wrote {path}")
        return
    out: dict[str, Any] = {"claim": 4, "runs": args.runs}
    with tempfile.TemporaryDirectory() as tmp:
        out["gate_sqlite"] = gate_overhead(SqliteStore(Path(tmp) / "g.db"), args.runs)
    if args.dynamo_table:
        out["gate_dynamodb"] = gate_overhead(DynamoStore(args.dynamo_table), args.runs)
    if args.hub_url:
        out["gate_cloud"] = cloud_gate(args.hub_url, args.runs)
        out["understand_cloud"] = cloud_understand(args.hub_url, args.runs)
        out["mcp_typed_cloud"] = cloud_mcp_typed(args.hub_url, args.runs)
    out["device_round_trip_http"] = http_round_trip(args.runs)
    out["understand"] = understand_latency(args.runs, args.asr, args.ranker)
    path = write_result("latency", out, run=args.run)
    u = out["understand"]
    print(f"understand ({u['asr_engine']} + {u['ranker']}): p50 {u['total']['p50_ms']} ms, p95 {u['total']['p95_ms']} ms")
    for k in ("gate_sqlite", "gate_dynamodb"):
        if k in out:
            print(f"{k}: added p50 {out[k]['added_by_gate']['p50_ms']} ms, p95 {out[k]['added_by_gate']['p95_ms']} ms")
    if "understand_cloud" in out:
        uc = out["understand_cloud"]
        print(f"understand on Lambda ({uc['asr_engines']}): p50 {uc['total']['p50_ms']} ms, p95 {uc['total']['p95_ms']} ms")
    if "gate_cloud" in out:
        g = out["gate_cloud"]
        print(f"gate on Lambda+DynamoDB: p50 {g['gate_added_in_region']['p50_ms']} ms, p95 {g['gate_added_in_region']['p95_ms']} ms;"
              f" device round trip p50 {g['device_round_trip_from_client']['p50_ms']} ms")
    print("device evidence+confirm over HTTP: p50", out["device_round_trip_http"]["p50_ms"], "ms")
    print("wrote", path)


if __name__ == "__main__":
    main()

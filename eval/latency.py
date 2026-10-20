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
    ap.add_argument("--dynamo-table", default="")
    ap.add_argument("--runs", type=int, default=RUNS)
    ap.add_argument("--run", default=None)
    args = ap.parse_args()
    out: dict[str, Any] = {"claim": 4, "runs": args.runs}
    with tempfile.TemporaryDirectory() as tmp:
        out["gate_sqlite"] = gate_overhead(SqliteStore(Path(tmp) / "g.db"), args.runs)
    if args.dynamo_table:
        out["gate_dynamodb"] = gate_overhead(DynamoStore(args.dynamo_table), args.runs)
    out["device_round_trip_http"] = http_round_trip(args.runs)
    out["understand"] = understand_latency(args.runs, args.asr, args.ranker)
    path = write_result("latency", out, run=args.run)
    u = out["understand"]
    print(f"understand ({u['asr_engine']} + {u['ranker']}): p50 {u['total']['p50_ms']} ms, p95 {u['total']['p95_ms']} ms")
    for k in ("gate_sqlite", "gate_dynamodb"):
        if k in out:
            print(f"{k}: added p50 {out[k]['added_by_gate']['p50_ms']} ms, p95 {out[k]['added_by_gate']['p95_ms']} ms")
    print("device evidence+confirm over HTTP: p50", out["device_round_trip_http"]["p50_ms"], "ms")
    print("wrote", path)


if __name__ == "__main__":
    main()

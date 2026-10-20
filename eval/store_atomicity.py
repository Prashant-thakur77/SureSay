"""The gate's replay protection rests on ``set_once`` being atomic. Measure it on each store.

N racing threads try to consume one nonce; exactly one may win. Real DynamoDB is tested when
``--dynamo-table`` is given (a few thousand writes, a fraction of a cent). The moto mock is reported
too, because it is *not* atomic under threads, and the unit tests skip it for that reason.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confirm_gate import DynamoStore, MemoryStore, SqliteStore  # noqa: E402

from eval.common import write_result  # noqa: E402


def race(store: Any, trials: int, racers: int, cleanup: Any = None) -> dict[str, Any]:
    counts = []
    for _ in range(trials):
        key = "race-" + uuid.uuid4().hex[:12]
        store.put("racetest", key, {"consumed_at": None})
        wins: list[bool] = []
        barrier = threading.Barrier(racers)

        def go(i: int, key: str = key, wins: list[bool] = wins, barrier: threading.Barrier = barrier) -> None:
            barrier.wait()
            wins.append(store.set_once("racetest", key, "consumed_at", float(i)))

        ts = [threading.Thread(target=go, args=(i,)) for i in range(racers)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        counts.append(wins.count(True))
        if cleanup:
            cleanup(key)
    return {"trials": trials, "racers": racers, "trials_not_exactly_one_winner": sum(c != 1 for c in counts),
            "max_winners": max(counts)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dynamo-table", default="")
    ap.add_argument("--trials", type=int, default=150)
    args = ap.parse_args()
    out: dict[str, Any] = {}
    out["memory"] = race(MemoryStore(), args.trials, 16)
    with tempfile.TemporaryDirectory() as tmp:
        out["sqlite"] = race(SqliteStore(os.path.join(tmp, "a.db")), args.trials, 16)
    import boto3
    from moto import mock_aws

    with mock_aws():
        c = boto3.client("dynamodb", region_name="us-east-1")
        DynamoStore.create_table("t", client=c)
        out["moto_mock_not_a_real_store"] = race(DynamoStore("t", client=c), args.trials, 16)
    if args.dynamo_table:
        d = DynamoStore(args.dynamo_table)
        out["dynamodb"] = race(d, args.trials, 16, cleanup=lambda k: d._c.delete_item(
            TableName=d.table, Key={"pk": {"S": f"racetest#{k}"}}))
    path = write_result("store_atomicity", {"stores": out})
    for k, v in out.items():
        print(f"{k:28s} {v['trials_not_exactly_one_winner']}/{v['trials']} trials broke one-winner (max {v['max_winners']})")
    print("wrote", path)


if __name__ == "__main__":
    main()

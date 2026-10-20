"""Cost per 1,000 turns — an ESTIMATE, from measured usage times AWS list prices.

Prices: AWS Price List API, us-east-1, queried 2026-10-20 (on-demand, first tier).
Usage, per turn = one spoken request + one spoken confirmation:
* audio seconds — measured: mean duration of TORGO dev clips (sentences for requests, single words
  for confirmations); Transcribe streaming bills at least 15 s per request.
* Nova tokens — measured from eval runs when Nova ran; otherwise estimated from the real prompt
  this code sends (characters / 4) and marked as estimated.
* DynamoDB request units — measured by counting store operations over 50 real turns through the hub.
* Polly characters — measured: the read-back text of those turns.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confirm_gate import MemoryStore  # noqa: E402

from eval.common import EVAL, SPLIT, read_result, write_result  # noqa: E402

PRICES = {
    "transcribe_streaming_per_second": 0.0001667,
    "transcribe_min_seconds_per_request": 15,
    "nova2lite_input_per_1k_tokens": 0.00033,   # us. geo cross-region profile; global is 0.0003
    "nova2lite_output_per_1k_tokens": 0.00275,  # global is 0.0025
    "polly_neural_per_char": 0.000016,
    "dynamodb_read_request_unit": 0.000000125,
    "dynamodb_write_request_unit": 0.000000625,
    "lambda_gb_second": 0.0000166667,
    "lambda_request": 0.0000002,
    "source": "AWS Price List API (pricing:GetProducts), us-east-1, 2026-10-20",
}


class CountingStore(MemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.rru = 0.0
        self.wru = 0.0

    def _w(self, doc: dict[str, Any] | None) -> None:
        self.wru += max(1, math.ceil(len(json.dumps(doc or {})) / 1024))

    def _r(self, doc: dict[str, Any] | None) -> None:
        self.rru += max(1, math.ceil(len(json.dumps(doc or {})) / 4096))

    def put(self, kind: str, key: str, doc: dict[str, Any]) -> None:
        self._w(doc)
        super().put(kind, key, doc)

    def get(self, kind: str, key: str) -> dict[str, Any] | None:
        doc = super().get(kind, key)
        self._r(doc)
        return doc

    def put_if_absent(self, kind: str, key: str, doc: dict[str, Any]) -> bool:
        self._w(doc)
        return super().put_if_absent(kind, key, doc)

    def set_once(self, kind: str, key: str, field: str, value: Any, updates: dict[str, Any] | None = None) -> bool:
        doc = super().get(kind, key)
        self._r(doc)
        self._w(doc)
        return super().set_once(kind, key, field, value, updates)

    def scan(self, kind: str, **equals: Any) -> list[dict[str, Any]]:
        rows = super().scan(kind, **equals)
        all_kind = super().scan(kind)  # a Query on the kind index reads every item of that kind
        self.rru += max(1, math.ceil(sum(len(json.dumps(d)) for d in all_kind) / 4096)) / 2  # eventually consistent
        return rows


def measured_store_usage(turns: int = 50) -> dict[str, float]:
    from eval.harness import LiveHub, UserDevice

    store = CountingStore()
    with tempfile.TemporaryDirectory() as tmp:
        hub = LiveHub(Path(tmp))
        hub.s.store = store
        hub.s.home.store = store
        hub.s.gate.store = store
        hub.s.devices.store = store
        with hub:
            user = UserDevice(hub)
            store.rru = store.wru = 0
            chars = 0
            phrases = ["fan on", "lights off", "TV on", "lock the door", "order milk"]
            for i in range(turns):
                out = user.signed("POST", "/device/turn", {"text": phrases[i % len(phrases)]}).json()
                chars += len(out["reply"])
                p = out["pending"][0]
                ev = user.tap(p, option=1)
                done = user.confirm(p["pending_id"], ev["evidence_ref"])
                chars += len(done.get("message", ""))
                user.signed("GET", "/device/state")  # the client polls state after each turn
    return {"rru_per_turn": store.rru / turns, "wru_per_turn": store.wru / turns, "polly_chars_per_turn": chars / turns}


def audio_seconds() -> dict[str, float]:
    """Mean real durations of dev-speaker clips: sentences stand in for requests, single words for answers."""
    import soundfile as sf

    from eval.common import DATA

    rows = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    dev = [r for r in rows if r["speaker"] in SPLIT["dev"]]
    sent = [sf.info(str(DATA / r["wav"])).duration for r in dev if r["kind"] == "sentence"]
    word = [sf.info(str(DATA / r["wav"])).duration for r in dev if r["kind"] == "word"]
    return {"request_seconds": round(sum(sent) / len(sent), 2), "confirmation_seconds": round(sum(word) / len(word), 2),
            "clips": len(sent) + len(word)}


def nova_tokens() -> dict[str, Any]:
    intent = read_result("intent", "run1") or read_result("intent")
    if intent and intent.get("tokens", {}).get("input"):
        rows = [r for r in intent["rows"] if "ss_nova" in r]
        n = max(1, len(rows))
        return {"input": intent["tokens"]["input"] / n, "output": intent["tokens"]["output"] / n, "measured": True}
    from suresay.phrasebook import STARTER, entry
    from suresay.rank import SYSTEM_PROMPT, NovaRanker

    book = [entry(**s, entry_id=f"ph_{i:02d}") for i, s in enumerate(STARTER)]
    prompt = NovaRanker(client=object()).prompt(["turn on the fan"], book, {"home": {"devices": {}}}, True)
    return {"input": (len(SYSTEM_PROMPT) + len(prompt)) / 4, "output": 120, "measured": False,
            "note": "estimated from the real prompt (characters / 4) and a 120-token reply; Nova did not run"}


def main() -> None:
    t0 = time.time()
    store = measured_store_usage()
    audio = audio_seconds()
    tokens = nova_tokens()
    p = PRICES
    billed = max(p["transcribe_min_seconds_per_request"], audio["request_seconds"]) + \
        max(p["transcribe_min_seconds_per_request"], audio["confirmation_seconds"])
    per_turn = {
        "transcribe": billed * p["transcribe_streaming_per_second"],
        "nova_ranker": tokens["input"] / 1000 * p["nova2lite_input_per_1k_tokens"]
        + tokens["output"] / 1000 * p["nova2lite_output_per_1k_tokens"],
        "polly": store["polly_chars_per_turn"] * p["polly_neural_per_char"],
        "dynamodb": store["rru_per_turn"] * p["dynamodb_read_request_unit"]
        + store["wru_per_turn"] * p["dynamodb_write_request_unit"],
        "lambda": 5 * (1.5 * 0.3 * p["lambda_gb_second"] + p["lambda_request"]),  # ~5 requests of ~300 ms at 1.5 GB
    }
    per_1000 = {k: round(v * 1000, 4) for k, v in per_turn.items()}
    total = round(sum(per_1000.values()), 2)
    write_result("cost", {"label": "ESTIMATE", "prices": p, "usage": {**store, **audio, "transcribe_billed_seconds": billed,
                                                                     "nova_tokens": tokens},
                          "per_1000_turns_usd": per_1000, "total_per_1000_turns_usd": total,
                          "excluded": "AgentCore Runtime compute and the agent's own model calls (agent mode); "
                                      "S3 storage (pennies at 30-day expiry)",
                          "seconds": round(time.time() - t0, 1)})
    print(f"estimate: ${total} per 1,000 turns", per_1000)


if __name__ == "__main__":
    main()

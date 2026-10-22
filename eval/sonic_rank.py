"""Amazon Nova 2 Sonic as the ranker in the evaluation: each answer cached by its prompt, every paid call counted.

A cache hit costs nothing, so a change to the abstain rule or the answer checks re-scores offline. A miss calls
Sonic once and books its tokens in ``eval/results/spend.json`` at list price (``USD_PER_1K``, from the AWS Price
List API, us-east-1, Nova 2 Sonic).
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from eval.asr_cache import CACHE
from suresay.rank import SonicRanker, sonic_system_prompt

USD_PER_1K = {"speech_tokens": 0.003, "text_tokens": 0.00033, "output_speech_tokens": 0.012, "output_text_tokens": 0.00275}
_LOCK = threading.Lock()


class CachedSonicRanker(SonicRanker):
    def _complete(self, prompt: str) -> tuple[dict[str, Any], dict[str, int]]:
        key = hashlib.sha256((self.model_id + sonic_system_prompt() + prompt).encode()).hexdigest()
        path = CACHE / "sonic_rank" / f"{key}.json"
        if path.exists():
            hit = json.loads(path.read_text())
            return hit["data"], hit["usage"]
        data, usage = super()._complete(prompt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"data": data, "usage": usage}))
        count(usage)
        return data, usage


def count(usage: dict[str, int]) -> None:
    """Running tally of Nova 2 Sonic ranking calls and their list price."""
    path = CACHE.parent / "results" / "spend.json"
    with _LOCK:
        doc = json.loads(path.read_text()) if path.exists() else {}
        doc["nova_sonic_rank_calls"] = doc.get("nova_sonic_rank_calls", 0) + 1
        for k in USD_PER_1K:
            doc[f"nova_sonic_rank_{k}"] = doc.get(f"nova_sonic_rank_{k}", 0) + int(usage.get(k, 0))
        doc["nova_sonic_rank_usd"] = round(sum(doc[f"nova_sonic_rank_{k}"] / 1000 * p for k, p in USD_PER_1K.items()), 4)
        path.write_text(json.dumps(doc, indent=1))

"""Tune the abstain rule on DEV speakers only (F03, M05), then freeze it in eval/results/tuning.json.

Objective, chosen before looking at any numbers: maximise
    (in-book utterances recovered in the top 3 without abstaining) + (out-of-book utterances abstained on)
over all dev utterances — each utterance counts once, whichever way it can go wrong.
Ties go to the more cautious rule (higher floor).
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.asr_cache import transcribe_all  # noqa: E402
from eval.common import RESULTS, write_result  # noqa: E402
from eval.run_intent_eval import build_tasks  # noqa: E402
from suresay.phrasebook import vocabulary  # noqa: E402
from suresay.rank import AbstainRule, FuzzyRanker, NovaRanker, bedrock_available, norm  # noqa: E402

GRID = {"floor": [x / 100 for x in range(30, 91, 5)], "confident": [x / 100 for x in range(50, 101, 5)],
        "margin": [0.0, 0.02, 0.05, 0.08, 0.1, 0.15, 0.2]}


def collect(engine: str, use_nova: bool) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"fuzzy": [], "nova": []}
    fuzzy = FuzzyRanker(AbstainRule(floor=-1, confident=-1, margin=0))
    nova = NovaRanker(rule=AbstainRule(floor=-1, confident=-1, margin=0)) if use_nova else None
    for task in build_tasks(["dev"]):
        wavs = [r["wav"] for r in task["in_book"] + task["out_book"]]
        heard = transcribe_all(engine, f"book:{task['speaker']}", wavs, vocabulary(task["book"]))
        by_text = {norm(e["phrase"]): e["id"] for e in task["book"]}
        for split, items in (("in", task["in_book"]), ("out", task["out_book"])):
            for r in items:
                h = heard[r["wav"]]
                hyps = [h["text"], *h.get("alternatives", [])]
                truth = by_text.get(r["norm"]) if split == "in" else None
                for name, ranker in (("fuzzy", fuzzy), ("nova", nova)):
                    if ranker is None:
                        continue
                    rk = ranker.rank(hyps, task["book"], use_catalog=False)
                    out[name].append({"split": split, "truth": truth, "top": [c.phrase_id for c in rk.candidates],
                                      "conf": [c.confidence for c in rk.candidates],
                                      "model_abstain": rk.abstain if name == "nova" else False})
    return out


def objective(items: list[dict[str, Any]], rule: AbstainRule) -> int:
    score = 0
    for it in items:
        abstain = it["model_abstain"] or rule.should_abstain(it["conf"])[0]
        if it["split"] == "in":
            score += int(not abstain and it["truth"] in it["top"][:3])
        else:
            score += int(abstain)
    return score


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="whisper-small.en")
    args = ap.parse_args()
    use_nova = bedrock_available("us.amazon.nova-2-lite-v1:0")
    data = collect(args.engine, use_nova)
    result: dict[str, Any] = {}
    for name, items in data.items():
        if not items:
            continue
        best = None
        for floor, conf, margin in itertools.product(GRID["floor"], GRID["confident"], GRID["margin"]):
            if conf < floor:
                continue
            rule = AbstainRule(floor=floor, confident=conf, margin=margin)
            key = (objective(items, rule), floor, conf, margin)
            if best is None or key > best[0]:
                best = (key, rule)
        assert best is not None
        result[name] = {"rule": best[1].__dict__, "dev_objective": best[0][0], "dev_utterances": len(items)}
        print(f"{name}: {best[1]} -> {best[0][0]}/{len(items)} dev utterances handled right")
    if not use_nova:
        result["nova_status"] = "pending: Bedrock access not available; nova rule not tuned"
    existing = json.loads((RESULTS / "tuning.json").read_text()) if (RESULTS / "tuning.json").exists() else {}
    write_result("tuning", {**{k: v for k, v in existing.items() if k in ("nova",)}, **result,
                            "speakers": "dev only (F03, M05)", "asr_engine": args.engine})


if __name__ == "__main__":
    main()

"""Per-user calibration: does a threshold learned from a user's own earlier confirmations beat the global one?

The global abstain rule was tuned on two dev speakers. A real user confirms (or declines) cards every day, and each
answer labels one of their own utterances. Simulation, per test speaker, on their intent-eval utterances
(in-book and out-of-book) in a fixed order:

* calibration half: the first half, as if the user had used SureSay for a while; their answers tell us the truth;
* evaluation half: the second half, never used for calibration.

On the calibration half the same grid as eval/tune_abstain.py picks the user's own floor, confident level and
margin by the same objective (in-book recovered in the top 3 without abstaining + out-of-book abstained on).
Both rules are then scored on the evaluation half. Counts are small, so the result is indicative.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.common import pct, read_result, write_result  # noqa: E402
from eval.tune_abstain import GRID  # noqa: E402
from suresay.rank import AbstainRule  # noqa: E402


def handled(rows: list[dict[str, Any]], rule: AbstainRule) -> int:
    score = 0
    for r in rows:
        abstain = rule.should_abstain(r["conf"])[0]
        score += int((not abstain and r["truth"] in r["top"][:3]) if r["split"] == "in" else abstain)
    return score


def metrics(rows: list[dict[str, Any]], rule: AbstainRule) -> dict[str, Any]:
    ins = [r for r in rows if r["split"] == "in"]
    outs = [r for r in rows if r["split"] == "out"]
    top1 = sum((not rule.should_abstain(r["conf"])[0]) and bool(r["top"]) and r["top"][0] == r["truth"] for r in ins)
    abst_out = sum(rule.should_abstain(r["conf"])[0] for r in outs)
    abst_in = sum(rule.should_abstain(r["conf"])[0] for r in ins)
    return {"in": len(ins), "out": len(outs), "top1_pct": pct(top1, len(ins)),
            "asked_again_in_book_pct": pct(abst_in, len(ins)), "correct_abstain_pct": pct(abst_out, len(outs)),
            "handled_right": handled(rows, rule), "utterances": len(rows)}


def best_rule(rows: list[dict[str, Any]], fallback: AbstainRule) -> AbstainRule:
    best: tuple[tuple[int, float, float, float], AbstainRule] | None = None
    for floor, conf, margin in itertools.product(GRID["floor"], GRID["confident"], GRID["margin"]):
        if conf < floor:
            continue
        rule = AbstainRule(floor=floor, confident=conf, margin=margin)
        key = (handled(rows, rule), floor, conf, margin)  # ties go to the more cautious rule
        if best is None or key > best[0]:
            best = (key, rule)
    return best[1] if best else fallback


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run1")
    args = ap.parse_args()
    intent = read_result("intent", args.run)
    if intent is None:
        raise SystemExit("run eval/run_intent_eval.py first")
    g = intent["rules"]["fuzzy"]
    global_rule = AbstainRule(floor=g["floor"], confident=g["confident"], margin=g["margin"])
    per: dict[str, Any] = {}
    pooled_g: list[dict[str, Any]] = []
    for spk in dict.fromkeys(r["speaker"] for r in intent["rows"] if r["group"] == "test"):
        rows = [{"split": r["split"], "truth": r["truth"], "top": r["ss_fuzzy"]["top"], "conf": r["ss_fuzzy"]["conf"]}
                for r in intent["rows"] if r["speaker"] == spk]
        rows.sort(key=lambda r: hashlib.sha1((spk + str(r["top"]) + str(r["truth"]) + str(r["conf"])).encode()).hexdigest())
        half = len(rows) // 2
        calib, held = rows[:half], rows[half:]
        mine = best_rule(calib, global_rule)
        per[spk] = {"calibration_utterances": len(calib), "rule": mine.__dict__,
                    "global": metrics(held, global_rule), "personal": metrics(held, mine)}
        pooled_g.append({"spk": spk, "held": held, "rule": mine})
    total_g = sum(p["global"]["handled_right"] for p in per.values())
    total_p = sum(p["personal"]["handled_right"] for p in per.values())
    n = sum(p["global"]["utterances"] for p in per.values())
    payload = {"what": "per-user abstain rule from the first half of each test speaker's own utterances",
               "asr_engine": intent["asr_engine"], "global_rule": global_rule.__dict__, "per_speaker": per,
               "pooled": {"utterances": n, "global_handled_right_pct": pct(total_g, n),
                          "personal_handled_right_pct": pct(total_p, n)}}
    path = write_result("personal", payload, run=args.run)
    for spk, p in per.items():
        print(f"{spk}: global top1 {p['global']['top1_pct']}% asked-again {p['global']['asked_again_in_book_pct']}% "
              f"| personal top1 {p['personal']['top1_pct']}% asked-again {p['personal']['asked_again_in_book_pct']}% "
              f"| correct abstain {p['global']['correct_abstain_pct']}% -> {p['personal']['correct_abstain_pct']}%")
    print("pooled handled right:", payload["pooled"])
    print("wrote", path)


if __name__ == "__main__":
    main()

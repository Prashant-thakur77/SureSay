"""Pick the B0 + reject confidence threshold on DEV speakers only (F03, M05).

B0 + reject is the plain assistant (unbiased transcript forced to the nearest allowed word) that asks
again when the recogniser is unsure: it heard nothing, gave no confidence, or its per-utterance
confidence is below the threshold (eval/run_confirm_eval.py: ``b0_reject_decide``).

Rule, fixed before any test-speaker result for this arm was computed:
* candidate thresholds: 0 and every distinct confidence value on the dev clips (reject iff confidence < t);
* keep the candidates that recover at least as many genuine answers on dev as SureSay does on dev
  (same clips, same contexts; "genuine answers recovered" = a spoken yes/one/two/three accepted as itself);
* among those, fewest dev false accepts; ties go to the lower threshold (it asks again less);
* if no candidate keeps that many, take 0 (never reject on confidence) and record that the floor was not met.

Only engines whose cached transcripts carry a per-utterance confidence can run this arm. For the others
(Transcribe streaming and Nova 2 Sonic, whose cache stores ``confidence: null``) the result file says so,
and no threshold is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confirm_gate.consent import decide  # noqa: E402

from eval.asr_cache import transcribe_all  # noqa: E402
from eval.common import read_result, tuning_name, write_result  # noqa: E402
from eval.run_confirm_eval import b0_reject_decide, has_confidence, in_context, load_clips, score, truth_for  # noqa: E402

GENUINE = ("choose", "yes")


def recovered(rows: list[dict[str, Any]]) -> int:
    """Genuine answers accepted as themselves (the numerator of score()'s true_accepts_recovered_pct)."""
    return sum(tuple(r["truth"])[0] in GENUINE and tuple(r["decision"]) == tuple(r["truth"]) for r in rows)


def choose_reject_threshold(rows: list[dict[str, Any]], min_recovered: int) -> dict[str, Any]:
    """rows: dev decisions to be made, each {"text", "confidence", "context", "truth"}. Applies the rule above."""
    candidates = sorted({0.0} | {float(r["confidence"]) for r in rows if r["confidence"] is not None})
    tried = []
    for t in candidates:
        decided = [{"decision": b0_reject_decide(r["text"], r["confidence"], r["context"], t),
                    "truth": tuple(r["truth"])} for r in rows]
        tried.append({"threshold": t, "recovered": recovered(decided), **score(decided)})
    ok = [c for c in tried if c["recovered"] >= min_recovered]
    best = min(ok, key=lambda c: (c["false_accepts"], c["threshold"])) if ok else tried[0]
    return {"threshold": best["threshold"], "constraint_met": bool(ok), "min_recovered": min_recovered,
            "dev": best, "candidates_tried": len(tried)}


def main(engine: str = "whisper-small.en") -> None:
    clips = load_clips(["dev"])
    wavs = [c["wav"] for c in clips]
    plain = transcribe_all(engine, "none", wavs, [])
    name = tuning_name(engine) + "_b0_reject"
    if not has_confidence(plain):
        reason = f"its cached transcripts carry no per-utterance confidence (0 of {len(plain)} dev clips)"
        write_result(name, {"asr_engine": engine, "available": False, "reason": reason,
                            "speakers": "dev only (F03, M05)"})
        print(f"B0 + reject not available for {engine}: {reason}")
        return
    bias = (read_result(tuning_name(engine)) or {}).get("confirm_bias")
    if bias is None:
        raise SystemExit("run eval/tune_confirm.py first (dev speakers only)")
    chosen = bias["candidates"][bias["chosen"]]
    biased = transcribe_all(engine, chosen["cache_tag"], wavs, chosen["words"])
    rows, suresay = [], []
    for c in clips:
        for context in ("choose", "final"):
            if not in_context(c["norm"], c["is_confirm_word"], context):
                continue
            truth = truth_for(c["norm"], context)
            h = plain[c["wav"]]
            rows.append({"text": h["text"], "confidence": h.get("confidence"), "context": context, "truth": truth})
            d = decide(biased[c["wav"]]["text"], 3 if context == "choose" else 1, stage=context)
            suresay.append({"decision": (d.kind, d.option), "truth": truth})
    floor = recovered(suresay)
    got = choose_reject_threshold(rows, floor)
    write_result(name, {"asr_engine": engine, "available": True, "speakers": "dev only (F03, M05)",
                        "rule": "fewest dev false accepts among thresholds recovering at least as many genuine "
                                "answers on dev as SureSay; ties to the lower threshold",
                        "suresay_dev": {"recovered": floor, **score(suresay)}, **got})
    print(f"threshold {got['threshold']:.4f} (floor {floor} genuine answers, met: {got['constraint_met']}); dev: "
          f"false accepts {got['dev']['false_accepts']}/{got['dev']['clips']}, recovered {got['dev']['recovered']}, "
          f"asked again {got['dev']['refused_pct']}%")


if __name__ == "__main__":
    main(*sys.argv[1:])

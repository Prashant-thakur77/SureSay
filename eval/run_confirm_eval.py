"""Claim 1 — confirmations are heard right. The gate's input, measured on real dysarthric speech.

Clips: TORGO single-word prompts "yes", "no", "one", "two", "three", plus up to 30 other single
words per speaker as distractors (an assistive-command word or any other word must never be
taken as a yes or a choice).

Two contexts, as on screen:
* choose — three cards are shown; truth for one/two/three is that card, "no" cancels,
  anything else should be refused;
* final  — one yes/no card; truth for yes/no is itself, anything else should be refused.

Systems:
* B0 — plain assistant: unbiased ASR, the transcript is forced to the nearest allowed word
  (spelling + sound similarity); it never refuses.
* B0 + reject — the same plain transcript, but it asks again when the recogniser is unsure: nothing heard,
  no confidence, or per-utterance confidence below a threshold chosen on dev speakers only
  (eval/tune_b0_reject.py, rule stated there). Only for engines whose cached transcripts carry a confidence
  (faster-whisper: exp of the mean token log-probability); Transcribe and Nova 2 Sonic transcripts have none.
* SureSay — ASR with the bias chosen on dev (eval/tune_confirm.py), then ``confirm_gate.consent.decide``,
  which refuses anything unclear.

Metrics per speaker and pooled: accuracy, **false-accept rate** (an accept decision that is not
the truth, including any "no" or distractor taken as yes or as a choice), refusal rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confirm_gate.consent import decide  # noqa: E402

from eval.asr_cache import transcribe_all  # noqa: E402
from eval.common import EVAL, SPLIT, pct, read_result, tuning_name, write_result  # noqa: E402  # noqa: E402
from suresay.rank import similarity  # noqa: E402

DISTRACTORS_PER_SPEAKER = 30
CHOOSE_TRUTH = {"one": ("choose", 1), "two": ("choose", 2), "three": ("choose", 3), "no": ("no", None)}
FINAL_TRUTH = {"yes": ("yes", None), "no": ("no", None)}


def load_clips(groups: list[str]) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    speakers = [s for g in groups for s in SPLIT[g]]
    out = []
    for spk in speakers:
        mine = [r for r in rows if r["speaker"] == spk and r["kind"] == "word"]
        conf = [r for r in mine if r["is_confirm_word"]]
        other = sorted((r for r in mine if not r["is_confirm_word"]),
                       key=lambda r: hashlib.sha1(r["wav"].encode()).hexdigest())[:DISTRACTORS_PER_SPEAKER]
        out += conf + other
    return out


def b0_decide(text: str, context: str) -> tuple[str, int | None]:
    allowed = ["one", "two", "three", "no"] if context == "choose" else ["yes", "no"]
    best = max(allowed, key=lambda w: similarity(text or "", w))
    if best == "no":
        return ("no", None)
    if context == "final":
        return ("yes", None)
    return ("choose", allowed.index(best) + 1)


def b0_reject_decide(text: str, confidence: float | None, context: str, threshold: float) -> tuple[str, int | None]:
    """B0 + reject: the same plain transcript, but ask again ("unclear") when the recogniser is unsure.

    Unsure = it heard nothing, gave no confidence, or its per-utterance confidence is below ``threshold``
    (chosen on dev speakers by eval/tune_b0_reject.py). Otherwise it is plain B0, forced to the nearest word.
    """
    if not (text or "").strip() or confidence is None or confidence < threshold:
        return ("unclear", None)
    return b0_decide(text, context)


def has_confidence(heard: dict[str, dict[str, Any]]) -> bool:
    """True when the cached transcripts carry a per-utterance confidence (Transcribe and Nova 2 Sonic do not)."""
    return any(h.get("confidence") is not None for h in heard.values())


def truth_for(word: str, context: str) -> tuple[str, int | None]:
    table = CHOOSE_TRUTH if context == "choose" else FINAL_TRUTH
    return table.get(word, ("unclear", None))


def in_context(word: str, is_confirm: bool, context: str) -> bool:
    if not is_confirm:
        return True
    return word in (CHOOSE_TRUTH if context == "choose" else FINAL_TRUTH)


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    correct = sum(r["decision"] == r["truth"] for r in rows)
    fa = sum(r["decision"][0] in ("choose", "yes") and r["decision"] != r["truth"] for r in rows)
    refused = sum(r["decision"][0] == "unclear" for r in rows)
    accepts_true = sum(r["truth"][0] in ("choose", "yes") for r in rows)
    accepted_right = sum(r["truth"][0] in ("choose", "yes") and r["decision"] == r["truth"] for r in rows)
    return {"clips": n, "accuracy_pct": pct(correct, n), "false_accept_pct": pct(fa, n), "false_accepts": fa,
            "refused_pct": pct(refused, n), "true_accepts_recovered_pct": pct(accepted_right, accepts_true)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="whisper-small.en")
    ap.add_argument("--groups", default="test,dev,controls")
    ap.add_argument("--run", default=None)
    args = ap.parse_args()
    groups = args.groups.split(",")
    clips = load_clips(groups)
    wavs = [c["wav"] for c in clips]
    plain = transcribe_all(args.engine, "none", wavs, [])
    tuning = (read_result(tuning_name(args.engine)) or {}).get("confirm_bias")
    if tuning is None:
        raise SystemExit("run eval/tune_confirm.py first (dev speakers only)")
    chosen = tuning["candidates"][tuning["chosen"]]
    biased = transcribe_all(args.engine, chosen["cache_tag"], wavs, chosen["words"])
    reject = read_result(tuning_name(args.engine) + "_b0_reject") or {}
    threshold = reject.get("threshold") if reject.get("available") else None
    if threshold is None:
        reject_status = reject.get("reason") or "run eval/tune_b0_reject.py first (dev speakers only)"
    elif not has_confidence(plain):
        raise SystemExit(f"{args.engine}: a B0 + reject threshold exists but the transcripts carry no confidence")
    else:
        reject_status = f"threshold {threshold} chosen on dev speakers only"
    systems = ("b0", "suresay") + (("b0_reject",) if threshold is not None else ())
    per: list[dict[str, Any]] = []
    for c in clips:
        for context in ("choose", "final"):
            if not in_context(c["norm"], c["is_confirm_word"], context):
                continue
            t = truth_for(c["norm"], context)
            h0 = plain[c["wav"]]["text"]
            h1 = biased[c["wav"]]["text"]
            d = decide(h1, 3 if context == "choose" else 1, stage="choose" if context == "choose" else "final")
            row = {"speaker": c["speaker"], "group": c["group"], "word": c["norm"], "confirm_word": c["is_confirm_word"],
                   "context": context, "truth": list(t), "wav": c["wav"],
                   "b0": {"heard": h0, "decision": list(b0_decide(h0, context))},
                   "suresay": {"heard": h1, "decision": [d.kind, d.option]}}
            if threshold is not None:
                conf = plain[c["wav"]].get("confidence")
                row["b0_reject"] = {"heard": h0, "confidence": conf,
                                    "decision": list(b0_reject_decide(h0, conf, context, threshold))}
            per.append(row)

    def table(system: str, select: Any) -> dict[str, Any]:
        rows = [{"decision": tuple(r[system]["decision"]), "truth": tuple(r["truth"])} for r in per if select(r)]
        return score(rows)

    summary: dict[str, Any] = {}
    for system in systems:
        s: dict[str, Any] = {}
        for g in groups:
            s[g] = table(system, lambda r, g=g: r["group"] == g)
            s[g + "_confirm_words_only"] = table(system, lambda r, g=g: r["group"] == g and r["confirm_word"])
            s[g + "_distractors_only"] = table(system, lambda r, g=g: r["group"] == g and not r["confirm_word"])
        s["per_speaker"] = {spk: table(system, lambda r, spk=spk: r["speaker"] == spk)
                            for g in groups for spk in SPLIT[g]}
        summary[system] = s
    path = write_result("confirm", {"claim": 1, "asr_engine": args.engine, "groups": groups,
                                    "suresay_bias": tuning["chosen"], "b0_reject_threshold": threshold,
                                    "b0_reject_status": reject_status,
                                    "distractors_per_speaker": DISTRACTORS_PER_SPEAKER, "summary": summary,
                                    "rows": per}, run=args.run)
    print("B0 + reject:", reject_status)
    for system in systems:
        t = summary[system].get("test")
        if t:
            print(f"{system:8s} test: acc {t['accuracy_pct']}%  false-accept {t['false_accept_pct']}% "
                  f"({t['false_accepts']}/{t['clips']})  refused {t['refused_pct']}%")
    print("wrote", path)


if __name__ == "__main__":
    main()

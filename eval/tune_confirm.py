"""Pick the speech-recognition bias for confirmations on DEV speakers only (F03, M05).

Candidates: no bias, the five core English words, and the full list including Hinglish words.
Rule, fixed before running: fewest false accepts first; then most genuine answers recovered;
then the shorter list.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confirm_gate.consent import decide  # noqa: E402

from eval.asr_cache import transcribe_all  # noqa: E402
from eval.common import read_result, write_result  # noqa: E402
from eval.run_confirm_eval import in_context, load_clips, score, truth_for  # noqa: E402

CANDIDATES = {
    "none": [],
    "core": ["yes", "no", "one", "two", "three"],
    "full": ["yes", "no", "one", "two", "three", "cancel", "haan", "nahin", "number", "first", "second", "third",
             "none", "doosra", "pehla", "teesra"],
}


def main(engine: str = "whisper-small.en") -> None:
    clips = load_clips(["dev"])
    wavs = [c["wav"] for c in clips]
    results = {}
    for name, words in CANDIDATES.items():
        tag = {"none": "none", "full": "confirm"}.get(name, f"confirm-{name}")
        heard = transcribe_all(engine, tag, wavs, words)
        rows = []
        for c in clips:
            for context in ("choose", "final"):
                if not in_context(c["norm"], c["is_confirm_word"], context):
                    continue
                d = decide(heard[c["wav"]]["text"], 3 if context == "choose" else 1, stage=context)
                rows.append({"decision": (d.kind, d.option), "truth": truth_for(c["norm"], context)})
        results[name] = {"words": words, "cache_tag": tag, **score(rows)}
        print(f"{name:5s} false accepts {results[name]['false_accepts']}  "
              f"genuine answers recovered {results[name]['true_accepts_recovered_pct']}%")
    best = min(results, key=lambda n: (results[n]["false_accepts"], -(results[n]["true_accepts_recovered_pct"] or 0),
                                       len(results[n]["words"])))
    existing = read_result("tuning") or {}
    keep = {k: v for k, v in existing.items() if k in ("fuzzy", "nova", "nova_status")}
    write_result("tuning", {**keep, "confirm_bias": {"chosen": best, "candidates": results,
                                                     "speakers": "dev only (F03, M05)", "asr_engine": engine}})
    print("chosen:", best)


if __name__ == "__main__":
    main(*sys.argv[1:])

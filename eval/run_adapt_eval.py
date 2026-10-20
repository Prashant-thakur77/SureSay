"""Does SureSay get better for a user as they confirm? (Learning from confirmations.)

TORGO speakers recorded many sentences more than once (across sessions or microphones). For each test
speaker, take sentences with at least two recordings:

* first recording  — the user says it once and confirms the meaning (on the cards, or by picking it from
  their phrases); SureSay stores what the recogniser heard as a learned phrase for that meaning;
* second recording — measured: is the meaning recovered now?

Two conditions on the same second recordings, same phrasebook, same dev-tuned abstain rule:
without learning, and with the learned phrases from the first recordings added.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.asr_cache import prepare_vocabularies, transcribe_all  # noqa: E402
from eval.common import EVAL, SPLIT, pct, write_result  # noqa: E402
from eval.run_intent_eval import BOOK_SIZE, tuned_rule  # noqa: E402
from suresay.phrasebook import entry, vocabulary  # noqa: E402
from suresay.rank import FuzzyRanker, norm  # noqa: E402

MAX_PAIRS = 20


def _h(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def tasks(groups: list[str]) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    sentences = [r for r in rows if r["kind"] == "sentence"]
    pool = sorted({r["norm"]: r["text"] for r in sentences}.items())
    out = []
    for g in groups:
        for spk in SPLIT[g]:
            by: dict[str, list[dict[str, Any]]] = {}
            for r in sentences:
                if r["speaker"] == spk:
                    by.setdefault(r["norm"], []).append(r)
            pairs = []
            for n, recs in by.items():
                recs = sorted(recs, key=lambda r: (r["session"], r["mic"] != "wav_headMic", r["utt"]))
                if len(recs) >= 2:
                    pairs.append((recs[0], recs[1]))
            pairs = sorted(pairs, key=lambda p: _h(spk, p[0]["norm"]))[:MAX_PAIRS]
            if len(pairs) < 3:
                continue
            own = set(by)
            distract = [t for n, t in sorted(pool, key=lambda kv: _h(spk, "a", kv[0])) if n not in own]
            texts = [p[0]["text"] for p in pairs] + distract[: BOOK_SIZE - len(pairs)]
            book = [entry(t, "say_for_me", {"text": t}, entry_id=f"ph_{i:02d}") for i, t in enumerate(texts)]
            out.append({"speaker": spk, "group": g, "pairs": pairs, "book": book})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="transcribe-streaming")
    ap.add_argument("--groups", default="test")
    ap.add_argument("--run", default=None)
    args = ap.parse_args()
    ts = tasks(args.groups.split(","))
    prepare_vocabularies(args.engine, [vocabulary(t["book"]) for t in ts])
    ranker = FuzzyRanker(tuned_rule("fuzzy", args.engine))
    rows = []
    for t in ts:
        wavs = [r["wav"] for p in t["pairs"] for r in p]
        heard = transcribe_all(args.engine, f"adapt:{t['speaker']}", wavs, vocabulary(t["book"]))
        by_norm = {norm(e["phrase"]): e for e in t["book"]}
        learned = [entry(heard[a["wav"]]["text"], by_norm[a["norm"]]["action"], by_norm[a["norm"]]["args"],
                         entry_id=f"ph_learned_{i:02d}")
                   for i, (a, _b) in enumerate(t["pairs"]) if heard[a["wav"]]["text"].strip()
                   and norm(heard[a["wav"]]["text"]) not in by_norm]
        for a, b in t["pairs"]:
            h = heard[b["wav"]]
            hyps = [h["text"], *h.get("alternatives", [])]
            want = by_norm[a["norm"]]["args"]
            row: dict[str, Any] = {"speaker": t["speaker"], "text": a["text"], "heard_first": heard[a["wav"]]["text"],
                                   "heard_second": h["text"]}
            for name, book in (("without", t["book"]), ("with_learning", t["book"] + learned)):
                rk = ranker.rank(hyps, book, use_catalog=False)
                tops = [c.args for c in rk.candidates]
                row[name] = {"abstain": rk.abstain, "top1": (not rk.abstain) and bool(tops) and tops[0] == want,
                             "top3": (not rk.abstain) and want in tops[:3], "conf": [c.confidence for c in rk.candidates]}
            rows.append(row)

    def m(rs: list[dict[str, Any]], cond: str) -> dict[str, Any]:
        n = len(rs)
        return {"utterances": n, "top1_pct": pct(sum(r[cond]["top1"] for r in rs), n),
                "top3_pct": pct(sum(r[cond]["top3"] for r in rs), n),
                "asked_again_pct": pct(sum(r[cond]["abstain"] for r in rs), n)}

    summary = {c: m(rows, c) for c in ("without", "with_learning")}
    per = {spk: {c: m([r for r in rows if r["speaker"] == spk], c) for c in ("without", "with_learning")}
           for spk in dict.fromkeys(r["speaker"] for r in rows)}
    path = write_result("adapt", {"claim": "learning from confirmations", "asr_engine": args.engine,
                                  "rule": tuned_rule("fuzzy", args.engine).__dict__, "summary": summary,
                                  "per_speaker": per, "rows": rows}, run=args.run)
    for c, v in summary.items():
        print(f"{c:14s} top1 {v['top1_pct']}%  top3 {v['top3_pct']}%  asked again {v['asked_again_pct']}%  (n={v['utterances']})")
    for spk, v in per.items():
        print(f"  {spk}: {v['without']['top1_pct']}% -> {v['with_learning']['top1_pct']}%  (n={v['without']['utterances']})")
    print("wrote", path)


if __name__ == "__main__":
    main()

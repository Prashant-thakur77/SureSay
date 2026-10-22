"""Claims 2, 2b and 5 — the meaning is recovered, SureSay abstains when unsure, typical speech is not hurt.

For each speaker, their distinct TORGO sentences are split deterministically in half:
* in-book  — up to 20 sentences that go into their phrasebook (each one a "say this for me" phrase);
* out-of-book — up to 20 sentences they also said, kept *out* of the book, to test abstaining.
The phrasebook is padded to 50 entries with distractor sentences from other speakers' prompts
(never one of this speaker's own sentences).

Systems (one change at a time):
* B0       — unbiased ASR; the top transcript is the result (success = exact normalised match).
* B1       — ASR biased with the phrasebook; nearest phrase by spelling/sound similarity; never abstains.
* SS-fuzzy — as B1 plus the abstain rule (thresholds tuned on dev speakers only).
* SS-nova  — as B1 but Nova 2 Lite ranks the phrasebook (top 3) with its abstain rule. Needs Bedrock.

Metrics: in-book top-1 / top-3 recovery (an abstain counts as a miss), false-abstain rate on
in-book, correct-abstain rate on out-of-book, and "acted wrongly" (top-1 is a wrong phrase and
the system would act without asking) for B0/B1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os  # noqa: E402

NOVA_MODEL = os.environ.get("NOVA_MODEL_ID", "us.amazon.nova-2-lite-v1:0")

from eval.asr_cache import prepare_vocabularies, transcribe_all  # noqa: E402
from eval.common import EVAL, SPLIT, pct, read_result, tuning_name, write_result  # noqa: E402
from suresay.phrasebook import entry, vocabulary  # noqa: E402
from suresay.rank import AbstainRule, FuzzyRanker, NovaRanker, bedrock_available, norm, relevant  # noqa: E402

BOOK_SIZE = 50
MAX_IN = 20
MAX_OUT = 20
MAYBE_FLOOR = 0.50  # fixed a priori, see suresay.rank.AbstainRule.maybe_floor


def _h(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def build_tasks(groups: list[str]) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    sentences = [r for r in rows if r["kind"] == "sentence"]
    pool = sorted({r["norm"]: r["text"] for r in sentences}.items())
    tasks = []
    for g in groups:
        for spk in SPLIT[g]:
            first: dict[str, dict[str, Any]] = {}
            for r in sentences:
                if r["speaker"] == spk and r["norm"] not in first:
                    first[r["norm"]] = r
            mine = sorted(first.values(), key=lambda r: _h(spk, r["norm"]))
            if len(mine) < 4:
                continue
            half = len(mine) // 2
            in_book = mine[:half][:MAX_IN]
            out_book = mine[half:][:MAX_OUT]
            own = {r["norm"] for r in mine}
            distractors = [text for n, text in sorted(pool, key=lambda kv: _h(spk, "d", kv[0])) if n not in own]
            texts = [r["text"] for r in in_book] + distractors[: BOOK_SIZE - len(in_book)]
            book = [entry(t, "say_for_me", {"text": t}, entry_id=f"ph_{i:02d}") for i, t in enumerate(texts)]
            tasks.append({"speaker": spk, "group": g, "book": book, "in_book": in_book, "out_book": out_book})
    return tasks


def tuned_rule(name: str, engine: str) -> AbstainRule:
    t = (read_result(tuning_name(engine)) or {}).get(name)
    if t:
        return AbstainRule(**t["rule"])
    return AbstainRule() if name == "fuzzy" else AbstainRule(floor=0.35, confident=0.75, margin=0.10)


def run_rankers(task: dict[str, Any], heard_b0: dict[str, Any], heard_b1: dict[str, Any], *, nova: Any | None,
                fuzzy_rule: AbstainRule, nova_system: str = "ss_nova") -> list[dict[str, Any]]:
    book = task["book"]
    by_text = {norm(e["phrase"]): e["id"] for e in book}
    b1 = FuzzyRanker(AbstainRule(floor=-1, confident=-1, margin=0))
    ssf = FuzzyRanker(fuzzy_rule)
    rows = []
    for split, items in (("in", task["in_book"]), ("out", task["out_book"])):
        for r in items:
            truth = by_text.get(r["norm"]) if split == "in" else None
            h0 = heard_b0[r["wav"]]
            h1 = heard_b1[r["wav"]]
            hyps = [h1["text"], *h1.get("alternatives", [])]
            row: dict[str, Any] = {"speaker": task["speaker"], "group": task["group"], "split": split,
                                   "text": r["text"], "wav": r["wav"], "truth": truth,
                                   "heard_b0": h0["text"], "heard_b1": h1["text"]}
            row["b0"] = {"top": [by_text[norm(h0["text"])]] if norm(h0["text"]) in by_text else [],
                         "exact": norm(h0["text"]) == r["norm"], "abstain": False}
            rk = b1.rank(hyps, book, use_catalog=False)
            row["b1"] = {"top": [c.phrase_id for c in rk.candidates], "conf": [c.confidence for c in rk.candidates],
                         "abstain": False}
            rk = ssf.rank(hyps, book, use_catalog=False)
            row["ss_fuzzy"] = {"top": [c.phrase_id for c in rk.candidates],
                               "conf": [c.confidence for c in rk.candidates], "abstain": rk.abstain,
                               # whether each guess shares a content word with what was heard: a "maybe" card
                               # is offered only if so (suresay.rank.relevant, the same rule the product uses)
                               "rel": [relevant(h1["text"], c.phrase or c.text) for c in rk.candidates]}
            if nova is not None:
                rk = nova.rank(hyps, book, use_catalog=False)
                row[nova_system] = {"top": [c.phrase_id for c in rk.candidates],
                                  "conf": [c.confidence for c in rk.candidates], "abstain": rk.abstain,
                                  "rel": [relevant(h1["text"], c.phrase or c.text) for c in rk.candidates],
                                  "usage": rk.usage, "ms": round(rk.ms)}
            rows.append(row)
    return rows


def metrics(rows: list[dict[str, Any]], system: str) -> dict[str, Any]:
    ins = [r for r in rows if r["split"] == "in" and system in r]
    outs = [r for r in rows if r["split"] == "out" and system in r]

    def hit(r: dict[str, Any], k: int) -> bool:
        s = r[system]
        if system == "b0":
            return s["exact"] if k == 1 else False
        return (not s["abstain"]) and r["truth"] in s["top"][:k]

    def in_cards(r: dict[str, Any]) -> bool:
        """The intended phrase is among the cards shown, counting "maybe" cards offered while asking again."""
        sres = r[system]
        if system in ("b0",):
            return sres["exact"]
        conf = sres.get("conf") or []
        if not sres["abstain"]:
            # beside the top guess, only cards at or above the noise floor are shown (suresay.understand)
            return any(t == r["truth"] and (i == 0 or c >= MAYBE_FLOOR)
                       for i, (t, c) in enumerate(zip(sres["top"][:3], conf or [1.0] * 3, strict=False)))
        rel = sres.get("rel") or [True] * len(conf)
        return any(t == r["truth"] and c >= MAYBE_FLOOR and ok
                   for t, c, ok in zip(sres["top"][:3], conf, rel, strict=False))

    top1 = sum(hit(r, 1) for r in ins)
    with_maybe = sum(in_cards(r) for r in ins)
    maybe_on_out = sum(r[system]["abstain"] and any(
        c >= MAYBE_FLOOR and ok for c, ok in zip((r[system].get("conf") or [])[:3],
                                                 r[system].get("rel") or [True] * 3, strict=False))
        for r in outs) if system.startswith("ss") else 0
    top3 = sum(hit(r, 3) for r in ins) if system != "b0" else None
    false_abstain = sum(r[system]["abstain"] for r in ins)
    correct_abstain = sum(r[system]["abstain"] for r in outs)
    acted_wrong = 0
    if system in ("b0", "b1"):
        acted_wrong = sum(not hit(r, 1) for r in ins) + len(outs)
    return {"in_book": len(ins), "out_of_book": len(outs), "top1_pct": pct(top1, len(ins)),
            "top3_pct": pct(top3, len(ins)) if top3 is not None else None,
            "false_abstain_pct": pct(false_abstain, len(ins)), "correct_abstain_pct": pct(correct_abstain, len(outs)),
            "in_cards_with_maybe_pct": pct(with_maybe, len(ins)), "maybe_cards_on_out_of_book_pct": pct(maybe_on_out, len(outs)),
            "acted_without_asking_wrong_pct": pct(acted_wrong, len(ins) + len(outs)) if system in ("b0", "b1") else 0.0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="whisper-small.en")
    ap.add_argument("--groups", default="test,controls")
    ap.add_argument("--nova", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--run", default=None)
    ap.add_argument("--name", default="intent")
    ap.add_argument("--model", choices=["lite", "sonic"], default="lite",
                    help="the Bedrock ranker: Nova 2 Lite (Converse) or Nova 2 Sonic (a tool call, while Lite has no quota)")
    args = ap.parse_args()
    groups = args.groups.split(",")
    tasks = build_tasks(groups)
    nova = None
    key, system = ("sonic", "ss_sonic") if args.model == "sonic" else ("nova", "ss_nova")
    if args.model == "sonic" and args.nova != "off":
        from eval.sonic_rank import CachedSonicRanker

        nova = CachedSonicRanker(rule=tuned_rule("sonic", args.engine))
    elif args.nova == "on" or (args.nova == "auto" and bedrock_available(NOVA_MODEL)):
        nova = NovaRanker(rule=tuned_rule("nova", args.engine))
    rows: list[dict[str, Any]] = []
    prepare_vocabularies(args.engine, [vocabulary(t["book"]) for t in tasks])
    for task in tasks:
        wavs = [r["wav"] for r in task["in_book"] + task["out_book"]]
        heard_b0 = transcribe_all(args.engine, "none", wavs, [])
        heard_b1 = transcribe_all(args.engine, f"book:{task['speaker']}", wavs, vocabulary(task["book"]))
        rows += run_rankers(task, heard_b0, heard_b1, nova=nova, fuzzy_rule=tuned_rule("fuzzy", args.engine),
                            nova_system=system)
    systems = ["b0", "b1", "ss_fuzzy"] + ([system] if nova else [])
    summary: dict[str, Any] = {}
    for g in groups:
        g_rows = [r for r in rows if r["group"] == g]
        summary[g] = {s: metrics(g_rows, s) for s in systems}
        summary[g]["per_speaker"] = {
            spk: {s: metrics([r for r in g_rows if r["speaker"] == spk], s) for s in systems}
            for spk in SPLIT[g] if any(r["speaker"] == spk for r in g_rows)}
    tokens = {k: sum(r.get(system, {}).get("usage", {}).get(k, 0) for r in rows)
              for k in ({x for r in rows for x in r.get(system, {}).get("usage", {})} or ("input_tokens", "output_tokens"))}
    payload = {"claim": "2, 2b, 5", "asr_engine": args.engine, "groups": groups, "book_size": BOOK_SIZE,
               "systems": systems, "nova": "run" if nova else "pending: Bedrock access not available; not estimated",
               "ranker_model": nova.model_id if nova else None,
               "rules": {"fuzzy": tuned_rule("fuzzy", args.engine).__dict__, key: tuned_rule(key, args.engine).__dict__},
               "tokens": tokens, "summary": summary,
               "tasks": [{"speaker": t["speaker"], "group": t["group"], "in_book": len(t["in_book"]),
                          "out_of_book": len(t["out_book"])} for t in tasks],
               "rows": rows}
    path = write_result(args.name, payload, run=args.run)
    for g in groups:
        for s in systems:
            m = summary[g][s]
            print(f"{g:9s} {s:9s} top1 {m['top1_pct']}%  top3 {m['top3_pct']}%  false-abstain {m['false_abstain_pct']}%"
                  f"  correct-abstain {m['correct_abstain_pct']}%  (in {m['in_book']}, out {m['out_of_book']})")
    print("wrote", path)


if __name__ == "__main__":
    main()

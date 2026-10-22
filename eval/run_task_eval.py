"""Task success: is the user's sentence done within two tries? The number a user actually feels.

Same speakers, phrasebooks and split as ``run_intent_eval`` (test speakers F01, F04, M01, M02, M03, M04;
50-phrase books; the abstain rule tuned on dev speakers for this recogniser). Every in-book sentence is a
task: the user wants SureSay to say it for them.

SureSay, per task:
* attempt 1 — the recording ``run_intent_eval`` uses for that sentence;
* the attempt shows the intended phrase if it is among the confident cards (top 3), or, when SureSay asks
  again, among its "maybe" cards (score >= 0.50 and sharing a content word with what was heard:
  ``suresay.rank.relevant``, the rule the product uses). The user then confirms it: done.
* otherwise the user tries again: SureSay asked them to say it again (target not offered), or it showed
  cards that did not include the target and the user declined them all;
* attempt 2 — a DIFFERENT recording of the same sentence by the same speaker, chosen deterministically:
  another take from another session, else another take from the same session, else the same take as
  recorded by TORGO's other microphone (head-mounted vs array; that is the same performance heard
  through a different microphone, not a new try, and is counted and reported separately), else none
  (the task counts as not done within two tries).
SureSay never acts without the user's confirmation (the ranker only proposes; the confirm gate enforces
it, see Claim 3), so it has no wrong actions; what it can cost is a declined set of cards and a retry.

Baselines act at once on the first recording, no second chance:
* B1 — phrasebook-biased recognition, nearest phrase acts. Success = top-1 correct; otherwise a WRONG ACTION.
* B0 — unbiased recognition, the transcript is what gets said. Success = exact normalised match;
  otherwise a wrong action (as in ``run_intent_eval``).

Recogniser: ``whisper-small.en`` (local, free) for both attempts, so every number uses one engine. The
first recordings hit the cache ``run_intent_eval`` filled; second recordings are transcribed with the
same phrasebook bias. Writes ``eval/results/task.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.asr_cache import transcribe_all  # noqa: E402
from eval.common import DATA, EVAL, SPLIT, pct, write_result  # noqa: E402
from eval.run_intent_eval import MAYBE_FLOOR, build_tasks, tuned_rule  # noqa: E402
from suresay.phrasebook import vocabulary  # noqa: E402
from suresay.rank import AbstainRule, FuzzyRanker, norm, relevant  # noqa: E402

MICS = ("wav_headMic", "wav_arrayMic")
OTHER_SESSION, SAME_SESSION, OTHER_MIC, NONE = ("another session", "another take in the same session",
                                                "the same take on the other microphone", "none")


def second_recording(first: dict[str, Any], sentences: list[dict[str, Any]]) -> tuple[str | None, str]:
    """A different recording of *first*'s sentence by the same speaker, and where it came from."""
    takes = [r for r in sentences if r["speaker"] == first["speaker"] and r["norm"] == first["norm"]
             and r["wav"] != first["wav"]]
    key = lambda r: (r["session"], r["mic"] != "wav_headMic", r["utt"])  # noqa: E731
    other = sorted((r for r in takes if r["session"] != first["session"]), key=key)
    if other:
        return other[0]["wav"], OTHER_SESSION
    same = sorted((r for r in takes if r["session"] == first["session"]), key=key)
    if same:
        return same[0]["wav"], SAME_SESSION
    mic = next(m for m in MICS if m != first["mic"])
    wav = first["wav"].replace(f"/{first['mic']}/", f"/{mic}/")
    p = DATA / wav
    if p.exists() and p.stat().st_size > 2000:  # the same size floor torgo_prepare uses
        return wav, OTHER_MIC
    return None, NONE


def attempt(ranker: FuzzyRanker, heard: dict[str, Any], book: list[dict[str, Any]], truth: str) -> dict[str, Any]:
    """What SureSay shows for one recording, and whether the intended phrase is on a card."""
    rk = ranker.rank([heard["text"], *heard.get("alternatives", [])], book, use_catalog=False)
    top = [c.phrase_id for c in rk.candidates]
    conf = [c.confidence for c in rk.candidates]
    if not rk.abstain:
        outcome = "shown" if truth in top[:3] else "declined"
        maybes: list[str] = []
    else:
        maybes = [c.phrase_id for c in rk.candidates[:3]
                  if c.confidence >= MAYBE_FLOOR and relevant(heard["text"], c.phrase or c.text)]
        outcome = "shown_as_maybe" if truth in maybes else ("asked_again_with_other_maybes" if maybes else "asked_again")
    return {"heard": heard["text"], "abstain": rk.abstain, "top": top, "conf": conf, "maybe_cards": maybes,
            "outcome": outcome, "shown": outcome in ("shown", "shown_as_maybe")}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    first = sum(r["suresay"]["done_on"] == 1 for r in rows)
    second = sum(r["suresay"]["done_on"] == 2 for r in rows)
    retries = [r for r in rows if r["suresay"]["attempt_2"] is not None]
    no_second = sum(r["suresay"]["attempt_1"]["shown"] is False and r["suresay"]["attempt_2"] is None for r in rows)
    by_source: dict[str, dict[str, int]] = {}
    for r in retries:
        s = by_source.setdefault(r["second_source"], {"attempts": 0, "done": 0})
        s["attempts"] += 1
        s["done"] += r["suresay"]["done_on"] == 2
    second_new_take = sum(r["suresay"]["done_on"] == 2 and r["second_source"] != OTHER_MIC for r in rows)
    declined = sum(a is not None and a["outcome"] in ("declined", "asked_again_with_other_maybes")
                   for r in rows for a in (r["suresay"]["attempt_1"], r["suresay"]["attempt_2"]))
    outcomes: dict[str, int] = {}
    for r in rows:
        o = r["suresay"]["attempt_1"]["outcome"]
        outcomes[o] = outcomes.get(o, 0) + 1
    b1_ok = sum(r["b1"]["success"] for r in rows)
    b0_ok = sum(r["b0"]["success"] for r in rows)
    return {
        "tasks": n,
        "suresay": {
            "done_first_try_pct": pct(first, n), "done_within_two_pct": pct(first + second, n),
            "not_done_within_two_pct": pct(n - first - second, n),
            "done_first_try": first, "done_second_try": second, "not_done": n - first - second,
            "done_within_two_counting_only_new_takes_pct": pct(first + second_new_take, n),
            "mean_tries_when_done": round((first + 2 * second) / (first + second), 2) if first + second else None,
            "first_try_outcomes": outcomes,
            "second_tries": len(retries), "second_tries_by_source": by_source,
            "needed_second_try_but_no_other_recording": no_second,
            "card_sets_declined": declined,
            "acted_without_confirmation": 0,
        },
        "b1": {"success_pct": pct(b1_ok, n), "wrong_action_pct": pct(n - b1_ok, n), "wrong_actions": n - b1_ok},
        "b0": {"success_pct": pct(b0_ok, n), "wrong_action_pct": pct(n - b0_ok, n), "wrong_actions": n - b0_ok},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="whisper-small.en")
    ap.add_argument("--groups", default="test")
    ap.add_argument("--run", default=None)
    ap.add_argument("--name", default="task")
    args = ap.parse_args()
    groups = args.groups.split(",")
    manifest = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    sentences = [r for r in manifest if r["kind"] == "sentence"]
    rule = tuned_rule("fuzzy", args.engine)
    ss = FuzzyRanker(rule)
    b1 = FuzzyRanker(AbstainRule(floor=-1, confident=-1, margin=0))  # never abstains, as in run_intent_eval
    rows: list[dict[str, Any]] = []
    for task in build_tasks(groups):
        book = task["book"]
        by_text = {norm(e["phrase"]): e["id"] for e in book}
        seconds = {r["wav"]: second_recording(r, sentences) for r in task["in_book"]}
        firsts = [r["wav"] for r in task["in_book"]]
        bias = f"book:{task['speaker']}"
        heard = transcribe_all(args.engine, bias, firsts + [w for w, _ in seconds.values() if w], vocabulary(book))
        plain = transcribe_all(args.engine, "none", firsts, [])
        for r in task["in_book"]:
            truth = by_text[r["norm"]]
            a1 = attempt(ss, heard[r["wav"]], book, truth)
            wav2, source = seconds[r["wav"]]
            a2 = attempt(ss, heard[wav2], book, truth) if (not a1["shown"] and wav2) else None
            done_on = 1 if a1["shown"] else (2 if a2 and a2["shown"] else None)
            h1 = heard[r["wav"]]
            rk = b1.rank([h1["text"], *h1.get("alternatives", [])], book, use_catalog=False)
            b1_top = rk.candidates[0].phrase_id if rk.candidates else None
            rows.append({"speaker": task["speaker"], "group": task["group"], "text": r["text"], "truth": truth,
                         "wav_1": r["wav"], "wav_2": wav2, "second_source": source,
                         "suresay": {"attempt_1": a1, "attempt_2": a2, "done_on": done_on},
                         "b1": {"heard": h1["text"], "top1": b1_top, "success": b1_top == truth},
                         "b0": {"heard": plain[r["wav"]]["text"],
                                "success": norm(plain[r["wav"]]["text"]) == r["norm"]}})
    summary: dict[str, Any] = {}
    for g in groups:
        g_rows = [r for r in rows if r["group"] == g]
        summary[g] = summarise(g_rows)
        summary[g]["per_speaker"] = {spk: summarise([r for r in g_rows if r["speaker"] == spk])
                                     for spk in SPLIT[g] if any(r["speaker"] == spk for r in g_rows)}
    sources: dict[str, int] = {}
    for r in rows:
        sources[r["second_source"]] = sources.get(r["second_source"], 0) + 1
    payload = {"claim": "task success within two tries", "asr_engine": args.engine, "groups": groups,
               "rule": rule.__dict__, "maybe_floor": MAYBE_FLOOR, "max_tries": 2,
               "second_recording_available": sources, "summary": summary, "rows": rows}
    path = write_result(args.name, payload, run=args.run)
    for g in groups:
        s = summary[g]
        x = s["suresay"]
        print(f"{g}: {s['tasks']} tasks  SureSay first try {x['done_first_try_pct']}%  within two "
              f"{x['done_within_two_pct']}% (new takes only {x['done_within_two_counting_only_new_takes_pct']}%)  "
              f"second tries {x['second_tries']} {x['second_tries_by_source']}  declined sets {x['card_sets_declined']}")
        print(f"   B1 {s['b1']['success_pct']}% (wrong actions {s['b1']['wrong_action_pct']}%)  "
              f"B0 {s['b0']['success_pct']}% (wrong actions {s['b0']['wrong_action_pct']}%)")
        for spk, v in s["per_speaker"].items():
            print(f"   {spk}: n={v['tasks']} SS {v['suresay']['done_first_try_pct']} -> {v['suresay']['done_within_two_pct']}"
                  f"  B1 {v['b1']['success_pct']}  B0 {v['b0']['success_pct']}")
    print("second recordings available:", sources)
    print("wrote", path)


if __name__ == "__main__":
    main()

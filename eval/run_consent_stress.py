"""Consent stress test: thousands of ways people answer, and don't answer, a card.

Text-level, offline, free. It complements Claim 1 (real dysarthric audio through a recogniser) by testing the
decision itself on a large, systematic set of phrasings: hedges, negations, questions, sound-alikes, conflicts,
out-of-range numbers, long sentences that merely contain a yes, Hinglish and Devanagari, each with casing and
punctuation variants.

- Negatives must never become consent: a safe outcome is "unclear" (asked again) or "no" (nothing changes).
- Positives are genuine answers and must be decided exactly (the right option, yes, or no).

Baseline: a keyword spotter, the way a plain assistant reads an answer: a no-word means no, else the first number
word (or a word that sounds like one) picks that option, else a yes-word means yes.

    python eval/run_consent_stress.py    ->  eval/results/consent_stress.json
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from confirm_gate.consent import decide  # noqa: E402

from eval.common import write_result  # noqa: E402

CARD = "Unlock the front door"  # the high-risk final card the yes/no cases are asked on

HEDGES = ["hang on", "wait", "wait a moment", "hold on", "one moment", "just a second", "in a second", "ek second",
          "ek minute", "ruko", "ruk", "thehro", "maybe", "probably", "perhaps", "i think", "not sure", "let me think",
          "sochne do", "shayad", "kal", "later", "i don't know", "hmm let me see", "never mind", "scratch that"]
CHOICES = {"one": 1, "two": 2, "three": 3, "the second one": 2, "number two": 2, "doosra": 2, "do number": 2,
           "teen number": 3, "option one": 1, "first": 1, "pehla": 1, "teesra": 3, "दो नंबर": 2}
ORDINAL_WORDS = {"first", "pehla", "doosra", "teesra"}
YESES = ["yes", "haan", "theek hai", "yeah", "okay", "sure", "haan ji"]
NOS = ["no", "nahin", "cancel"]
SOUNDALIKES = ["to", "too", "tu", "won", "tree", "free", "for", "fore", "tea", "ton", "wan", "the to one"]
BARE_DO = ["do", "do it", "isko kar do", "kar do", "just do it"]
OUT_OF_RANGE = ["four", "five", "number four", "option six", "the fourth one"]
FILLERS = ["um", "uh", "hmm", "er", "ah", "mm"]
QUESTIONS = ["which one", "what is option two", "is two the fan", "haan kaun hai", "okay who is it", "what did you say",
             "two, which one is that", "can you repeat", "yes, is it the front door", "haan, kaun hai darwaze pe",
             "is it number two", "does two turn on the fan", "which is the second one", "kya do number fan hai",
             "can you do number one", "what does three mean", "is one the light", "kaun sa teesra hai"]
LONG = ["two and also order ten of the blue cables now", "yes i want to buy the most expensive one",
        "haan bhai aaj mausam bahut accha hai", "one more thing call my brother", "three times i told you already",
        "yes the weather is nice today", "number two is what my son said earlier"]


def variants(s: str) -> list[str]:
    out = {s, s[:1].upper() + s[1:], s + ".", s + "!"}
    return sorted(out)


def negatives() -> list[tuple[str, int, str, str]]:
    """(utterance, options, stage, family): none of these may be taken as consent."""
    cases: list[tuple[str, int, str, str]] = []
    for h, a in itertools.product(HEDGES, CHOICES):
        for u in (f"{h}, {a}", f"{a}, {h}", f"{a} {h}"):
            cases.append((u, 3, "choose", "hedge"))
    for h, y in itertools.product(HEDGES, YESES):
        for u in (f"{h}, {y}", f"{y}, {h}"):
            cases.append((u, 1, "final", "hedge"))
    for a in CHOICES:
        cases += [(f"not {a}", 3, "choose", "negated"), (f"no not {a}", 3, "choose", "negated")]
    for (a1, n1), (a2, n2) in itertools.permutations(CHOICES.items(), 2):
        # an ordinal then "one" is the pronoun, a genuine answer ("doosra one" is "the second one"): see positives()
        if n1 != n2 and not (a2 == "one" and a1 in ORDINAL_WORDS):
            cases += [(f"{a1} {a2}", 3, "choose", "two answers"), (f"{a1} or {a2}", 3, "choose", "two answers")]
    for y, n in itertools.product(YESES, NOS):
        cases += [(f"{y} {n}", 1, "final", "yes and no"), (f"{n} {y}", 1, "final", "yes and no")]
    cases += [(q, 3, "choose", "question") for q in QUESTIONS]
    cases += [(q, 1, "final", "question") for q in QUESTIONS]
    cases += [(s, 3, "choose", "sound-alike") for s in SOUNDALIKES]
    cases += [(d, 3, "choose", "bare do") for d in BARE_DO]
    cases += [(o, 3, "choose", "out of range") for o in OUT_OF_RANGE]
    cases += [(f, 3, "choose", "filler") for f in FILLERS] + [(f, 1, "final", "filler") for f in FILLERS]
    cases += [(s, 3, "choose", "long sentence") for s in LONG] + [(s, 1, "final", "long sentence") for s in LONG]
    for a in CHOICES:
        cases.append((a, 1, "final", "number on the yes/no card"))
    for y in YESES:
        for extra in ("unlock the back door", "unlock the garage", "but later", "for my neighbour", "lock it"):
            cases.append((f"{y}, {extra}", 1, "final", "other words on the final card"))
    return [(v, n, st, fam) for u, n, st, fam in cases for v in variants(u)]


def positives() -> list[tuple[str, int, str, str, int | None]]:
    """(utterance, options, stage, expected kind, expected option): genuine answers."""
    cases: list[tuple[str, int, str, str, int | None]] = []
    cases += [(a, 3, "choose", "choose", n) for a, n in CHOICES.items()]
    cases += [(u, 3, "choose", "choose", n) for u, n in [("number 2", 2), ("2", 2), ("third one", 3), ("ek number", 1),
                                                         ("option three", 3), ("the first one", 1),
                                                         ("doosra one", 2), ("teesra one", 3), ("pehla one", 1)]]
    for y in YESES + ["yes please", "yes do it", "yes, unlock the front door", "go ahead", "ji haan"]:
        cases.append((y, 1, "final", "yes", None))
    for n in NOS + ["mat karo", "none of these", "stop", "no thanks"]:
        cases += [(n, 3, "choose", "no", None), (n, 1, "final", "no", None)]
    return [(v, n, st, k, o) for u, n, st, k, o in cases for v in variants(u)]


WORD_NUM = {"one": 1, "won": 1, "wan": 1, "first": 1, "pehla": 1, "ek": 1, "two": 2, "to": 2, "too": 2, "tu": 2,
            "second": 2, "doosra": 2, "do": 2, "दो": 2, "2": 2, "three": 3, "tree": 3, "free": 3, "third": 3,
            "teesra": 3, "teen": 3, "3": 3, "1": 1, "four": 4, "for": 4, "fore": 4, "five": 5, "six": 6}
YES_WORDS = {"yes", "yeah", "haan", "ok", "okay", "sure", "theek", "ji"}
NO_WORDS = {"no", "nahin", "cancel", "stop", "none", "mat"}


def baseline(utterance: str, n_options: int, stage: str) -> tuple[str, int | None]:
    ws = re.findall(r"[\wऀ-ॿ]+", utterance.lower())
    if any(w in NO_WORDS for w in ws):
        return "no", None
    for w in ws:
        if w in WORD_NUM:
            n = WORD_NUM[w]
            if stage == "final":
                return "yes", None  # a plain assistant hears a number on a yes/no card as "go"
            return ("choose", n) if 1 <= n <= n_options else ("unclear", None)
    if any(w in YES_WORDS for w in ws):
        return "yes", None
    return "unclear", None


def run() -> dict[str, Any]:
    neg, pos = negatives(), positives()
    fams: dict[str, dict[str, int]] = {}
    fa_sure = fa_base = 0
    misses: list[dict[str, Any]] = []
    for u, n, st, fam in neg:
        d = decide(u, n, stage=st, echo=CARD if st == "final" else "").as_dict()
        sure_bad = d["kind"] in ("choose", "yes")
        base_bad = baseline(u, n, st)[0] in ("choose", "yes")
        f = fams.setdefault(fam, {"cases": 0, "suresay_false_accepts": 0, "baseline_false_accepts": 0})
        f["cases"] += 1
        f["suresay_false_accepts"] += sure_bad
        f["baseline_false_accepts"] += base_bad
        fa_sure += sure_bad
        fa_base += base_bad
        if sure_bad and len(misses) < 50:
            misses.append({"utterance": u, "stage": st, "decided": d["kind"], "option": d.get("option")})
    ok_sure = ok_base = 0
    refused: list[str] = []
    for u, n, st, kind, opt in pos:
        d = decide(u, n, stage=st, echo=CARD if st == "final" else "").as_dict()
        good = d["kind"] == kind and (opt is None or d.get("option") == opt)
        bk, bo = baseline(u, n, st)
        ok_sure += good
        ok_base += bk == kind and (opt is None or bo == opt)
        if not good and u.lower().rstrip(".!") not in [r.lower() for r in refused]:
            refused.append(u.rstrip(".!"))
    return {
        "negatives": len(neg), "positives": len(pos),
        "suresay": {"false_accepts": fa_sure, "false_accept_rate": round(fa_sure / len(neg), 4),
                    "answers_understood": ok_sure, "answer_rate": round(ok_sure / len(pos), 4)},
        "baseline": {"false_accepts": fa_base, "false_accept_rate": round(fa_base / len(neg), 4),
                     "answers_understood": ok_base, "answer_rate": round(ok_base / len(pos), 4),
                     "what": "keyword spotter: a no-word means no, else the first number word or sound-alike picks, else a yes-word means yes"},
        "families": fams,
        "suresay_false_accept_examples": misses,
        "suresay_refused_answers": sorted(set(refused)),
    }


def main() -> None:
    out = run()
    path = write_result("consent_stress", out)
    s, b = out["suresay"], out["baseline"]
    print(f"{out['negatives']} non-answers: SureSay took {s['false_accepts']} as consent "
          f"({s['false_accept_rate']:.2%}); the keyword baseline {b['false_accepts']} ({b['false_accept_rate']:.2%})")
    print(f"{out['positives']} genuine answers: SureSay understood {s['answer_rate']:.2%}; baseline {b['answer_rate']:.2%}")
    print("refused genuine answers:", out["suresay_refused_answers"])
    print("wrote", path)


if __name__ == "__main__":
    main()

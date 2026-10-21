"""Practice: a few sentences a day, scored honestly, with progress over days.

The clarity score is the share of the sentence's words that speech recognition got, in order, from his recording,
recognised *without* his phrasebook (priming would flatter the score). It is a practice signal, not a clinical
measure; eval/run_clarity_eval.py checks that it orders TORGO speakers by their published severity.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import Any

EVERYDAY = [
    "Good morning.", "Thank you so much.", "I would like a cup of tea, please.", "Please call my daughter.",
    "I am feeling better today.", "Can you open the window, please?", "I love you.", "See you tomorrow.",
]
PER_DAY = 5


def words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", (text or "").lower().replace("’", "'")).replace("'", "").split()


def clarity(target: str, heard: str) -> dict[str, Any]:
    """Which of *target*'s words were heard, in order, and the share as a whole percentage."""
    t, h = words(target), words(heard)
    hit = [False] * len(t)
    for block in difflib.SequenceMatcher(None, t, h, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            hit[block.a + k] = True
    shown = (target or "").split()
    # show the sentence as written ("Could", "water,") whenever its words line up one to one with the compared ones
    labels = shown if len(shown) == len(t) and all(words(a) == [b] for a, b in zip(shown, t, strict=True)) else t
    marks = [{"word": w, "heard": hit[i]} for i, w in enumerate(labels)]
    return {"score": round(100 * sum(hit) / len(t)) if t else 0, "words": marks}


def sentences(book: list[dict[str, Any]]) -> list[str]:
    """His own sentences to say first (Latin script: recognition is English here), then everyday ones."""
    mine = [str(e["args"]["text"]) for e in book
            if e.get("action") == "say_for_me" and (e.get("args") or {}).get("text")
            and not re.search(r"[ऀ-ॿ]", str(e["args"]["text"]))]
    out: list[str] = []
    for s in [*mine, *EVERYDAY]:
        if s not in out:
            out.append(s)
    return out


def today(book: list[dict[str, Any]], *, now: float | None = None) -> list[str]:
    """Five sentences for today: his own first, then a rotation of the rest, so practice changes day to day."""
    pool = sentences(book)
    mine = [s for s in pool if s not in EVERYDAY]
    day = int((now or time.time()) // 86400)
    rest = [s for s in pool if s not in mine[:2]]
    k = day % max(1, len(rest))
    rotated = rest[k:] + rest[:k]
    return (mine[:2] + rotated)[:PER_DAY]


def progress(attempts: list[dict[str, Any]], *, now: float | None = None) -> dict[str, Any]:
    """Day averages for the last 14 days, the current streak of practice days, and the best score per sentence."""
    now = now or time.time()
    by_day: dict[str, list[int]] = {}
    for a in attempts:
        by_day.setdefault(time.strftime("%Y-%m-%d", time.gmtime(a["at"])), []).append(int(a["score"]))
    days = [{"day": d, "average": round(sum(v) / len(v)), "attempts": len(v)} for d, v in sorted(by_day.items())][-14:]
    streak, d = 0, now
    while time.strftime("%Y-%m-%d", time.gmtime(d)) in by_day:
        streak += 1
        d -= 86400
    best: dict[str, int] = {}
    for a in attempts:
        best[a["target"]] = max(best.get(a["target"], 0), int(a["score"]))
    return {"attempts": len(attempts), "streak_days": streak, "days": days, "best": best}

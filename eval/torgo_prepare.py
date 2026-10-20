"""Build the eval manifest from the TORGO corpus.

TORGO prompt files are noisy: some hold two prompts run together ("...years old.knew"),
some are articulation tasks ("[say Ah for 5 seconds]") or picture descriptions. Rules,
applied the same way to every speaker:

* bracketed task instructions and ``input/images`` prompts are dropped;
* "[as in ...]" glosses are stripped ("read [as in I can read]" -> "read");
* a prompt with punctuation glued to a following letter is dropped (two prompts run together);
* a single word or a sentence is kept only if the same text is prompted for at least two speakers
  (the word and sentence lists are shared across speakers, so a run-together prompt is unique);
* the head-mounted mic is used when it has the file, else the array mic.

Writes ``eval/data/manifest.jsonl`` and ``eval/data/stats.json``.

Usage: python eval/torgo_prepare.py [--raw data/torgo/raw]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.common import DATA, EVAL, SPLIT  # noqa: E402

CONFIRM_WORDS = {"yes", "no", "one", "two", "three"}
GLUED = re.compile(r"[.,!?;:][A-Za-z]")


def clean(text: str) -> str | None:
    t = " ".join(text.replace("﻿", "").split())
    if not t or t.startswith("[") or "input/images" in t or t.lower().startswith("xxx"):
        return None
    t = re.sub(r"\s*\[as in [^\]]*\]", "", t, flags=re.I).strip()
    if "[" in t or "]" in t or GLUED.search(t):
        return None
    return t


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def kind_of(text: str) -> str:
    n = len(norm(text).split())
    if n == 1:
        return "word"
    if n >= 4:
        return "sentence"
    return "phrase"


def scan(raw: Path) -> list[dict]:
    rows = []
    for spk_dir in sorted(p for p in raw.iterdir() if p.is_dir()):
        spk = spk_dir.name
        for sess in sorted(spk_dir.glob("Session*")):
            for prompt in sorted((sess / "prompts").glob("*.txt")):
                uid = prompt.stem
                text = clean(prompt.read_text(errors="replace"))
                if text is None:
                    continue
                wav = None
                for mic in ("wav_headMic", "wav_arrayMic"):
                    cand = sess / mic / f"{uid}.wav"
                    if cand.exists() and cand.stat().st_size > 2000:
                        wav = cand
                        break
                if wav is None:
                    continue
                rows.append({"speaker": spk, "session": sess.name, "utt": uid, "text": text, "norm": norm(text),
                             "kind": kind_of(text), "mic": wav.parent.name,
                             "wav": str(wav.relative_to(raw.parent))})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(DATA / "raw"))
    args = ap.parse_args()
    raw = Path(args.raw)
    rows = scan(raw)
    speakers_for: dict[str, set[str]] = collections.defaultdict(set)
    for r in rows:
        speakers_for[r["norm"]].add(r["speaker"])
    kept = [r for r in rows if r["kind"] != "phrase" and (len(speakers_for[r["norm"]]) >= 2 or r["norm"] in CONFIRM_WORDS)]
    for r in kept:
        r["group"] = next((g for g, spks in SPLIT.items() if r["speaker"] in spks), "unused")
        r["is_confirm_word"] = r["norm"] in CONFIRM_WORDS
    out = EVAL / "data"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "manifest.jsonl").open("w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    stats: dict[str, dict] = {}
    for r in kept:
        s = stats.setdefault(r["speaker"], {"group": r["group"], "word": 0, "sentence": 0, "confirm": {},
                                            "distinct_sentences": set()})
        s[r["kind"]] += 1
        if r["is_confirm_word"]:
            s["confirm"][r["norm"]] = s["confirm"].get(r["norm"], 0) + 1
        if r["kind"] == "sentence":
            s["distinct_sentences"].add(r["norm"])
    for s in stats.values():
        s["distinct_sentences"] = len(s["distinct_sentences"])
    (out / "stats.json").write_text(json.dumps({"scanned": len(rows), "kept": len(kept), "speakers": stats}, indent=1))
    print(f"scanned {len(rows)} prompts with audio, kept {len(kept)}")
    for spk, s in sorted(stats.items()):
        print(f"  {spk} ({s['group']}): words {s['word']}, sentences {s['sentence']} "
              f"({s['distinct_sentences']} distinct), confirm words {s['confirm']}")


if __name__ == "__main__":
    main()

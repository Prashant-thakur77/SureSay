"""Where every narration line starts and how long every scene lasts, from the tightened voice lines.

Writes ~/Videos/suresay/build/timeline.json: {"scenes": [{name, start, dur, lines: [{id, start, dur, caption}]}], "total"}.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from narration import CAPTION, LINES  # noqa: E402

AUDIO = os.path.expanduser("~/Videos/suresay/audio")
BUILD = os.path.expanduser("~/Videos/suresay/build")
# scene: (lead-in before its first line, gap between its lines, hold after its last line)
PACING = {"story": (2.2, 0.75, 2.7), "turn": (0.3, 0.5, 0.9), "demo": (0.4, 0.45, 0.6), "door": (0.2, 0.45, 0.8),
          "agent": (0.2, 0.55, 1.0), "features": (0.2, 0.4, 0.6), "proof": (0.2, 0.5, 1.0),
          "built": (0.2, 0.45, 1.4), "close": (0.6, 0.7, 3.4)}
# extra room after a line: after c2 the app itself says the sentence aloud, in SureSay's own voice
EXTRA_AFTER = {"c2": 3.1}


def main() -> None:
    durs = {k: v["s"] for k, v in json.load(open(f"{AUDIO}/lines.json")).items()}
    scenes, t = [], 0.0
    for name in dict.fromkeys(s for s, *_ in LINES):
        lead, gap, hold = PACING[name]
        start, lines = t, []
        t += lead
        for scene, lid, text, *_ in LINES:
            if scene != name:
                continue
            lines.append({"id": lid, "start": round(t, 3), "dur": durs[lid], "caption": CAPTION.get(lid, text)})
            t += durs[lid] + gap + EXTRA_AFTER.get(lid, 0.0)
        t += hold - gap
        scenes.append({"name": name, "start": round(start, 3), "dur": round(t - start, 3), "lines": lines})
    os.makedirs(BUILD, exist_ok=True)
    json.dump({"scenes": scenes, "total": round(t, 3)}, open(f"{BUILD}/timeline.json", "w"), indent=1)
    for s in scenes:
        print(f"{s['name']:9s} {s['start']:6.1f}s  {s['dur']:5.1f}s")
    print(f"total {t:.1f}s")


if __name__ == "__main__":
    main()

"""Pick the best take of each narration line and tighten it.

Best = the take Whisper transcribes closest to the script (word error rate), so a clipped or slurred take loses.
Then: trim silence at both ends and shorten any pause inside the line to at most MAX_PAUSE seconds, so the voice
never leaves long gaps. Writes ~/Videos/suresay/audio/lines/<id>.wav and lines.json (durations, chosen take, WER).
Run with the project venv: .venv/bin/python video/select_takes.py
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from narration import LINES  # noqa: E402

from suresay.asr import WhisperAsr  # noqa: E402

AUDIO = os.path.expanduser("~/Videos/suresay/audio")
MAX_PAUSE = 0.35


def norm(text: str) -> list[str]:
    t = text.lower().replace("sure say", "suresay").replace("nah-heen", "nahin").replace("-", " ")
    return re.sub(r"[^a-z0-9' ]", " ", t).split()


def wer(ref: list[str], hyp: list[str]) -> float:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)] / max(1, len(ref))


def duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def tighten(src: str, dst: str) -> None:
    """Trim both ends; cap inner silences (below -40 dB) at MAX_PAUSE."""
    af = (f"silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          f"areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.12,areverse,"
          f"silenceremove=stop_periods=-1:stop_threshold=-40dB:stop_duration={MAX_PAUSE}:stop_silence={MAX_PAUSE}")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "1", dst], check=True)


def main() -> None:
    asr = WhisperAsr("small.en")
    os.makedirs(f"{AUDIO}/lines", exist_ok=True)
    report = {}
    for _scene, lid, text, _ex, _cfg in LINES:
        scored = []
        for take in sorted(glob.glob(f"{AUDIO}/takes/{lid}_*.wav")):
            heard = asr.transcribe(open(take, "rb").read()).text
            scored.append((wer(norm(text), norm(heard)), duration(take), take, heard))
        scored.sort()
        best = scored[0]
        out = f"{AUDIO}/lines/{lid}.wav"
        tighten(best[2], out)
        report[lid] = {"take": os.path.basename(best[2]), "wer": round(best[0], 3), "heard": best[3],
                       "raw_s": round(best[1], 2), "s": round(duration(out), 2),
                       "all": [(round(w, 3), os.path.basename(t)) for w, _, t, _ in scored]}
        print(f"{lid}: wer {best[0]:.2f}  {report[lid]['raw_s']}s -> {report[lid]['s']}s  | {best[3]}", flush=True)
    json.dump(report, open(f"{AUDIO}/lines.json", "w"), indent=1)
    print("total voice:", round(sum(r["s"] for r in report.values()), 1), "s")


if __name__ == "__main__":
    main()

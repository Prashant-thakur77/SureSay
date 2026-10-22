"""Pick the best take of each narration line and tighten it.

Best = the take Whisper transcribes closest to the script (word error rate), so a clipped or slurred take loses.
Then: trim silence at both ends and shorten any pause inside the line to at most MAX_PAUSE seconds, so the voice
never leaves long gaps. Writes ~/Videos/suresay/audio/lines/<id>.wav and lines.json (durations, chosen take, WER).
Run with the project venv: .venv/bin/python video/select_takes.py [line ids]
With line ids, only those lines are (re)chosen and the rest of lines.json is kept as it is. A DERIVED line is cut
from an earlier line's chosen take instead. Then audio/words.json gets Whisper's word times for every line (the
captions are timed by them).
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

from narration import DERIVED, LINES  # noqa: E402

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


def cut(lid: str) -> dict:
    """A DERIVED line: a stretch of an earlier line's tightened take, with 15 ms fades so the cut never clicks."""
    src, a, b = DERIVED[lid]
    out = f"{AUDIO}/lines/{lid}.wav"
    end = ["-to", f"{b:.3f}"] if b is not None else []
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{a:.3f}", *end, "-i", f"{AUDIO}/lines/{src}.wav",
                    "-af", "afade=t=in:d=0.015,areverse,afade=t=in:d=0.015,areverse", "-ar", "48000", "-ac", "1", out],
                   check=True)
    return {"take": f"{src}.wav[{a}:{b}]", "wer": None, "heard": "", "raw_s": None, "s": round(duration(out), 2), "all": []}


def pcm16k(path: str):
    import numpy as np

    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def words() -> None:
    """Whisper's word times (seconds into each tightened line), for word-by-word captions."""
    from faster_whisper import WhisperModel

    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    out = {}
    for _scene, lid, *_ in LINES:
        segs, _info = model.transcribe(pcm16k(f"{AUDIO}/lines/{lid}.wav"), word_timestamps=True, beam_size=5)
        out[lid] = [(w.word.strip(), round(w.start, 3), round(w.end, 3)) for s in segs for w in s.words]
    json.dump(out, open(f"{AUDIO}/words.json", "w"), indent=0)
    print("word times for", len(out), "lines")


def main(only: set[str]) -> None:
    asr = WhisperAsr("small.en")
    os.makedirs(f"{AUDIO}/lines", exist_ok=True)
    report = json.load(open(f"{AUDIO}/lines.json")) if only and os.path.exists(f"{AUDIO}/lines.json") else {}
    for _scene, lid, text, _ex, _cfg in LINES:
        if only and lid not in only:
            continue
        if lid in DERIVED:
            report[lid] = cut(lid)
            print(f"{lid}: cut from {report[lid]['take']} -> {report[lid]['s']}s", flush=True)
            continue
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
    used = {lid for _s, lid, *_ in LINES}
    json.dump(report, open(f"{AUDIO}/lines.json", "w"), indent=1)
    print("total voice:", round(sum(r["s"] for k, r in report.items() if k in used), 1), "s")
    words()


if __name__ == "__main__":
    main({a for a in sys.argv[1:] if not a.startswith("--")})

"""Hinglish confirmations, spoken and recognised for real (synthetic voice, labelled as such).

Each confirmation phrase is spoken by Amazon Polly (Kajal, bilingual Indian English / Hindi), recognised by
Amazon Transcribe streaming in hi-IN and in en-IN, and decided by the same consent parser the gate uses.
This checks the whole chain — Devanagari output included — not the parser alone. It is not a measure of
dysarthric speech: the voice is synthetic and clear.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confirm_gate.consent import decide  # noqa: E402

from eval.asr_cache import _count_spend  # noqa: E402
from eval.common import CACHE, pct, read_result, write_result  # noqa: E402

# (what is said, Polly language, card stage, expected decision)
PHRASES: list[tuple[str, str, str, tuple[str, int | None]]] = [
    ("हाँ", "hi-IN", "final", ("yes", None)),
    ("हाँ जी", "hi-IN", "final", ("yes", None)),
    ("ठीक है", "hi-IN", "final", ("yes", None)),
    ("नहीं", "hi-IN", "final", ("no", None)),
    ("मत करो", "hi-IN", "final", ("no", None)),
    ("दो नंबर", "hi-IN", "choose", ("choose", 2)),
    ("नंबर दो", "hi-IN", "choose", ("choose", 2)),
    ("पहला", "hi-IN", "choose", ("choose", 1)),
    ("दूसरा", "hi-IN", "choose", ("choose", 2)),
    ("तीसरा", "hi-IN", "choose", ("choose", 3)),
    ("तीन नंबर", "hi-IN", "choose", ("choose", 3)),
    ("इसको कर दो", "hi-IN", "choose", ("unclear", None)),  # "do this": never option 2
    ("Yes", "en-IN", "final", ("yes", None)),
    ("No", "en-IN", "final", ("no", None)),
    ("Number two", "en-IN", "choose", ("choose", 2)),
    ("The second one", "en-IN", "choose", ("choose", 2)),
    ("Option three", "en-IN", "choose", ("choose", 3)),
    ("Not two", "en-IN", "choose", ("unclear", None)),
]


def synth(text: str, lang: str) -> bytes:
    import hashlib

    import boto3

    path = CACHE / "polly" / f"{hashlib.sha1((lang + text).encode()).hexdigest()[:16]}.pcm"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = boto3.client("polly", region_name="us-east-1").synthesize_speech(
            Text=text, VoiceId="Kajal", Engine="neural", LanguageCode=lang, OutputFormat="pcm", SampleRate="16000")
        path.write_bytes(r["AudioStream"].read())
    return path.read_bytes()


def main() -> None:
    import numpy as np

    from suresay.asr import TranscribeStreamingAsr, wav_bytes

    def row(text: str, lang: str, asr_lang: str, stage: str, heard: str, want: tuple[str, int | None]) -> dict[str, Any]:
        d = decide(heard, 3 if stage == "choose" else 1, stage=stage)  # type: ignore[arg-type]
        got = (d.kind, d.option)
        return {"said": text, "voice_lang": lang, "asr_lang": asr_lang, "stage": stage, "heard": heard,
                "decision": list(got), "expected": list(want), "correct": got == want,
                "false_accept": got[0] in ("choose", "yes") and got != want}

    rows: list[dict[str, Any]] = []
    if "--rescore" in sys.argv:  # the parser changed: decide again on the transcripts already recorded (no AWS calls)
        old = read_result("hinglish")
        if old is None:
            raise SystemExit("no earlier hinglish result to rescore")
        rows = [row(r["said"], r["voice_lang"], r["asr_lang"], r["stage"], r["heard"], tuple(r["expected"]))  # type: ignore[arg-type]
                for r in old["rows"]]
    for asr_lang in () if rows else ("hi-IN", "en-IN"):
        asr = TranscribeStreamingAsr(language=asr_lang)
        _count_spend(len(PHRASES))
        for text, lang, stage, want in PHRASES:
            pcm = synth(text, lang)
            samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
            rows.append(row(text, lang, asr_lang, stage, asr.transcribe(wav_bytes(samples)).text, want))
    summary = {}
    for asr_lang in ("hi-IN", "en-IN"):
        rs = [r for r in rows if r["asr_lang"] == asr_lang]
        summary[asr_lang] = {"phrases": len(rs), "correct_pct": pct(sum(r["correct"] for r in rs), len(rs)),
                             "false_accepts": sum(r["false_accept"] for r in rs)}
    path = write_result("hinglish", {"what": "Polly Kajal (synthetic) -> Transcribe streaming -> consent parser",
                                     "summary": summary, "rows": rows})
    for r in rows:
        mark = "ok " if r["correct"] else ("FA " if r["false_accept"] else "-- ")
        print(f"{mark} [{r['asr_lang']}] said {r['said']!r:16} heard {r['heard']!r:28} -> {r['decision']}")
    print(summary)
    print("wrote", path)


if __name__ == "__main__":
    main()

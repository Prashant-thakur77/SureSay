"""Cut the SureSay video: scenes to the narration timeline, voice + ducked music, captions, loudness -14 LUFS.

Inputs (all under ~/Videos/suresay): build/timeline.json, audio/lines/*.wav, audio/words.json, clips/*.mp4
(+ .marks.json), clips/bubble_*.png, clips/ov-*.png, stock/*.mp4, music/theme.wav (video/music.py).

    python3 video/assemble.py [--out PATH] [--burn PATH] [--audio-only] [--check-audio]

--out (default ~/Videos/suresay/SureSay-v2.mp4): the film with no captions in the picture, and PATH.srt beside it
(upload the two together). --burn PATH: also a copy with word-by-word captions burned in, for muted autoplay; never
upload that one with the .srt, or CC viewers see two sets of words.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~/Videos/suresay")
B, C, S = f"{HOME}/build", f"{HOME}/clips", f"{HOME}/stock"
FPS = 30
TL = json.load(open(f"{B}/timeline.json"))
SC = {s["name"]: s for s in TL["scenes"]}
LINE = {ln["id"]: ln for s in TL["scenes"] for ln in s["lines"]}


def run(*args: str) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def marks(name: str) -> dict[str, float]:
    return json.load(open(f"{C}/{name}.marks.json"))


ENC = ["-an", "-c:v", "libx264", "-crf", "15", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS),
       "-video_track_timescale", "15360"]


def segment(src: str, a: float, b: float, out: str, *, hold: float = 0.0, grade: str = "", zoom: float = 0.0,
            speed: float = 1.0, push: tuple[float, float, float, float] | None = None) -> None:
    """src[a, b] as 1080p30, optionally graded, slowly pushed in (zoom), played *speed* times faster, held on its last
    frame for *hold* seconds, or pushed in on one spot of the UI: push=(x, y, scale, seconds), eased out."""
    vf = [f"setpts=(PTS-STARTPTS)/{speed}"] if speed != 1.0 else []
    vf += [f"fps={FPS}", "scale=1920:1080:force_original_aspect_ratio=increase", "crop=1920:1080", "setsar=1"]
    if grade:
        vf.append(grade)
    if hold > 0:
        vf.append(f"tpad=stop_mode=clone:stop_duration={hold:.3f}")
    if zoom:
        n = max(1, int((b - a + hold) * FPS))
        vf.append(f"zoompan=z='1+{zoom}*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={FPS}")
    if push:
        x, y, z, secs = push
        n = max(1, int(secs * FPS))
        # at twice the size first, so the moving crop doesn't step from pixel to pixel
        vf.append(f"scale=3840:2160:flags=lanczos,zoompan=z='1+{z - 1}*(1-pow(1-min(1,on/{n}),3))'"
                  f":x='max(0,min(iw-iw/zoom,{2 * x}-iw/zoom/2))':y='max(0,min(ih-ih/zoom,{2 * y}-ih/zoom/2))'"
                  f":d=1:s=1920x1080:fps={FPS}")
    vf.append("scale=out_range=tv,format=yuv420p")  # recorded clips are full-range JPEG frames; every part must match to concatenate
    run("-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", src, "-vf", ",".join(vf), *ENC, out)


def overlay(src: str, out: str, items: list[tuple[str, int, int, float, float]]) -> None:
    """Labels on a cut scene: (png, x, y, from s, to s), each faded in and out over 0.25 s (not at the scene's edges)."""
    dur = vlen(src)
    inputs, fc, last = ["-i", src], [], "[0:v]"
    for i, (png, x, y, a, b) in enumerate(items, start=1):
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
        fades = ([f"fade=t=in:st={a:.3f}:d=0.25:alpha=1"] if a > 0 else []) + \
            ([f"fade=t=out:st={b - 0.25:.3f}:d=0.25:alpha=1"] if b < dur - 0.05 else [])  # a whole-scene label never fades
        fc.append(f"[{i}:v]{','.join(['format=rgba'] + fades)}[o{i}]")
        fc.append(f"{last}[o{i}]overlay={x}:{y}:enable='between(t,{a:.3f},{b:.3f})',format=yuv420p[v{i}]")
        last = f"[v{i}]"
    run(*inputs, "-filter_complex", ";".join(fc), "-map", last, *ENC, out)


def concat(parts: list[str], out: str, dur: float) -> None:
    """Join *parts* with the concat filter (it rebuilds timestamps), then hold the last frame or trim to exactly
    *dur* seconds."""
    inputs = [x for p in parts for x in ("-i", p)]
    chain = "".join(f"[{i}:v]" for i in range(len(parts)))
    fc = f"{chain}concat=n={len(parts)}:v=1:a=0,tpad=stop_mode=clone:stop_duration=6,trim=duration={dur:.3f},setpts=PTS-STARTPTS[v]"
    run(*inputs, "-filter_complex", fc, "-map", "[v]", *ENC, out)


STORY_GRADE = "eq=saturation=0.82:contrast=1.06:brightness=-0.02,colorbalance=rs=0.04:bs=-0.04,vignette=PI/5"


def story() -> str:
    sc, L = SC["story"], LINE
    t = lambda lid: L[lid]["start"] - sc["start"]  # noqa: E731
    cuts = [  # (stock id, source start, seconds on screen)
        ("6970238", 2.0, t("s2") - 0.0),
        ("6011438", 1.0, (t("s3") - t("s2")) / 2), ("7522352", 1.5, (t("s3") - t("s2")) / 2),
        ("8057766", 1.0, t("s4") - t("s3")),
        ("2070044", 0.5, (t("s5") - t("s4")) * 0.45), ("9644268", 1.0, (t("s5") - t("s4")) * 0.55),
        ("8860242", 1.0, sc["dur"] - t("s5")),
    ]
    parts = []
    for i, (vid, a, d) in enumerate(cuts):
        p = f"{B}/story_{i}.mp4"
        segment(f"{S}/{vid}.mp4", a, a + d, p, grade=STORY_GRADE, zoom=0.06)
        parts.append(p)
    base = f"{B}/story_base.mp4"
    concat(parts, base, sc["dur"])
    # the night it went wrong: what he said, what it heard, what it did
    s4 = t("s4")
    at = {"b1": s4 + 0.4, "b2": s4 + 2.3, "b3": s4 + 4.1}
    fc, last = [], "[0:v]"
    for i, (bid, st) in enumerate(at.items(), start=1):
        fc.append(f"[{i}:v]format=rgba,fade=t=in:st={st:.2f}:d=0.35:alpha=1,fade=t=out:st={t('s5') - 0.3:.2f}:d=0.5:alpha=1[b{i}]")
        fc.append(f"{last}[b{i}]overlay=0:0:enable='gte(t,{st:.2f})'[v{i}]")
        last = f"[v{i}]"
    fc.append(f"{last}fade=t=in:st=0:d=1.2,fade=t=out:st={sc['dur'] - 1.4:.2f}:d=1.4[out]")
    out = f"{B}/scene_story.mp4"
    inputs = ["-i", base]
    for bid in at:
        inputs += ["-loop", "1", "-t", f"{sc['dur']:.2f}", "-i", f"{C}/bubble_{bid}.png"]
    run(*inputs, "-filter_complex", ";".join(fc), "-map", "[out]", *ENC, out)
    return out


def graphic(name: str, clip: str) -> str:
    sc = SC[name]
    m = marks(clip)
    p = f"{B}/{name}_0.mp4"
    segment(f"{C}/{clip}.mp4", m["start"], m["end"], p)
    out = f"{B}/scene_{name}.mp4"
    concat([p], out, sc["dur"])
    return out


def vlen(path: str) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True, check=True).stdout)


def demo() -> str:
    sc, m = SC["demo"], marks("demo")
    t = lambda lid: LINE[lid]["start"] - sc["start"]  # noqa: E731
    src = f"{C}/demo.mp4"
    cards_on = t("d1") + 4.3                     # "Instead of guessing, it shows..."
    chosen_on = t("d2") + 0.35                   # "He says, one."
    a0, a1 = 0.0, m["cards"] - 0.05
    hold0 = max(0.0, cards_on - (a1 - a0))       # the "working it out" moment, held
    b0, b1 = a1, m["chosen"] - 0.15
    hold1 = max(0.0, chosen_on - (cards_on + (b1 - b0)))
    parts = [f"{B}/demo_{i}.mp4" for i in range(3)]
    segment(src, a0, a1, parts[0], hold=hold0)
    segment(src, b0, b1, parts[1], hold=hold1)
    segment(src, b1, vlen(src), parts[2], hold=2.0)
    out = f"{B}/scene_demo.mp4"
    concat(parts, out, sc["dur"])  # the product full screen
    return out


def word(lid: str, w: str) -> float:
    """When word *w* of line *lid* is said, in seconds from the start of the line's scene (Whisper's word times).
    *w* may list spellings Whisper uses for one word: "nahin|naheen"."""
    scene = next(s for s in TL["scenes"] if any(ln["id"] == lid for ln in s["lines"]))
    hit = next(a for x, a, _ in WORDS[lid] if re.sub(r"[^a-z]", "", x.lower()) in w.split("|"))
    return LINE[lid]["start"] - scene["start"] + hit


def door() -> str:
    """The door on the current site: the first check, the second yes, More time (pushed in on the clock), his spoken
    "nahin", the door still locked, and a negation that never flips."""
    sc, m = SC["door"], marks("door")
    src = f"{C}/door.mp4"
    parts = [f"{B}/door_{i}.mp4" for i in range(4)]
    more_at = word("o3", "more")                                      # the click lands on "More time"
    a0 = m["first"] - 0.6
    segment(src, a0, a0 + more_at - 0.6, parts[0])                    # the first check, yes, the second yes
    segment(src, m["more"] - 0.6, m["more"] + 1.6, parts[1], push=(680, 640, 1.3, 0.7))
    now = more_at + 1.6
    voice_at = word("o1b", "nahin|naheen|nahi")                                   # his "nahin" plays ~0.7 s after the mic opens
    b0 = max(m["second"] + 0.5, m["mic"] + 0.7 - (voice_at - now))
    segment(src, b0, m["mic"] + 1.9, parts[2])                        # he answers by voice; then a cut over the check
    segment(src, m["cancelled"] - 0.3, m["cancelled"] + 1.8, parts[3]) # cancelled, the front door still locked
    tail = f"{B}/door_4.mp4"
    segment(src, m["type_dont"] + 0.1, vlen(src), tail, hold=2.0)     # "don't unlock the door": nothing will change
    out = f"{B}/scene_door.mp4"
    concat(parts + [tail], out, sc["dur"])  # the product full screen
    return out


def live() -> str:
    """A live AI told to confirm (the Alexa+ view on the deployed site, Amazon Nova 2 Sonic). The model's waits are
    played three times faster under a "sped up" tag; the moment it tries confirm and the refusal are real time."""
    sc, m = SC["live"], marks("live")
    src = f"{C}/live.mp4"
    step = next(x["t"] for x in m["said"] if "tried confirm" in x["text"])
    final = next(x["t"] for x in m["said"] if "Refused: only your device" in x["text"])
    fast = 3.0
    show_step = LINE["l2"]["start"] - sc["start"] - 0.25               # the refusal shows as "The gate refuses" begins
    b0, b1 = m["asked"] + 0.2, step - 0.5
    a0 = max(0.3, b0 - (show_step - 0.5 - (b1 - b0) / fast))
    c1 = step + 0.8
    d1 = final - 0.5
    parts = [f"{B}/live_{i}.mp4" for i in range(5)]
    segment(src, a0, b0, parts[0])                                    # Nova chosen, the request typed
    segment(src, b0, b1, parts[1], speed=fast)                        # the model works
    segment(src, b1, c1, parts[2])                                    # "Nova tried confirm: refused"
    segment(src, c1, d1, parts[3], speed=fast)                        # the model finishes its turn
    segment(src, d1, vlen(src), parts[4], hold=2.0)                   # the refusal, the cards still waiting on the phone
    raw, out = f"{B}/raw_live.mp4", f"{B}/scene_live.mp4"
    concat(parts, raw, sc["dur"])
    la = b0 - a0
    lb = la + (b1 - b0) / fast
    lc = lb + (c1 - b1)
    ld = lc + (d1 - c1) / fast
    typing = max(0.0, m["nova"] + 0.9 - a0)
    from PIL import Image

    fx = 80 + Image.open(f"{C}/ov-live.png").width + 16                # the tag just right of the "Live" label
    overlay(raw, out, [(f"{C}/ov-band.png", 0, 0, 0.0, sc["dur"]),          # hides the cut-off page text at the top
                       (f"{C}/ov-live.png", 80, 10, 0.0, sc["dur"]),
                       (f"{C}/ov-fast3.png", fx, 14, la, lb), (f"{C}/ov-fast3.png", fx, 14, lc, ld),
                       (f"{C}/ov-prompt.png", 1146, 826, typing, lb + 0.3)])
    return out


def gate() -> str:
    """The open-source gate, a real run: `pip install confirm-gate-mcp` (cut over the install), `confirm-gate demo`
    starts; (cut over pairing) a write by curl waits as a card on the paired device; the tap lands as the narration
    says "tap"; the note is saved."""
    sc, m = SC["gate"], marks("gate")
    src = f"{C}/gate.mp4"
    parts = [f"{B}/gate_{i}.mp4" for i in range(3)]
    segment(src, m["start"], m["pip"] + 0.6, parts[0])               # pip install confirm-gate-mcp
    segment(src, m["installed"] - 0.25, m["served"] + 0.9, parts[1])  # installed; confirm-gate demo starts
    so_far = (m["pip"] + 0.6 - m["start"]) + (m["served"] + 0.9 - m["installed"] + 0.25)
    tap_at = word("g1", "tap")
    b0 = max(m["paired"] + 0.3, m["tap"] - (tap_at - so_far))
    segment(src, b0, vlen(src), parts[2], hold=4.0)
    out = f"{B}/scene_gate.mp4"
    concat(parts, out, sc["dur"])
    return out


def features() -> str:
    """Talk to someone (listening, his sentence, said big, shown to the listener), Practice, Help, Your devices."""
    sc = SC["features"]
    t = lambda lid: LINE[lid]["start"] - sc["start"]  # noqa: E731
    pe, pr, hp, ft = marks("people"), marks("practice"), marks("help"), marks("features")
    parts = [f"{B}/feat_{i}.mp4" for i in range(6)]
    people = f"{C}/people.mp4"
    segment(people, pe["speaking"] - 0.2, pe["speaking"] + 2.3, parts[0])          # listening
    talk_len = t("f2") - 2.5
    segment(people, pe["cards"] - 0.3, pe["cards"] - 0.3 + talk_len, parts[1])     # his sentence, said, shown
    segment(f"{C}/practice.mp4", pr["speaking"] - 0.2, pr["speaking"] + 1.6, parts[2])
    prac_len = t("f3") - t("f2") - 1.8
    segment(f"{C}/practice.mp4", pr["scored"] - 0.3, vlen(f"{C}/practice.mp4"), parts[3],
            hold=max(0.0, prac_len - (vlen(f"{C}/practice.mp4") - pr["scored"] + 0.3)))
    segment(f"{C}/help.mp4", hp["cards"] - 0.1, hp["cards"] + 2.6, parts[4])
    segment(f"{C}/features.mp4", ft["devices"] - 0.1, vlen(f"{C}/features.mp4"), parts[5], hold=6.0)
    out = f"{B}/scene_features.mp4"
    concat(parts, out, sc["dur"])  # the product full screen
    return out


def close() -> str:
    """Tonight he helps his grandson again; the app says his words for him (the listener view, full screen); the end."""
    sc = SC["close"]
    t = lambda lid: LINE[lid]["start"] - sc["start"]  # noqa: E731
    pe = marks("people")
    warm = "eq=saturation=0.95:brightness=0.02,vignette=PI/6"
    app_on = t("c2") + LINE["c2"]["dur"] + 0.25
    parts = [f"{B}/close_{i}.mp4" for i in range(5)]
    segment(f"{S}/6970238.mp4", 6.0, 6.0 + t("c2"), parts[0], grade=warm, zoom=0.05)            # homework, again
    segment(f"{S}/6970243.mp4", 1.0, 1.0 + (app_on - t("c2")), parts[1], grade=warm, zoom=0.05)
    segment(f"{C}/people.mp4", pe["listener"] + 0.4, pe["listener"] + 0.4 + (t("c3") - app_on), parts[2])  # said for him
    segment(f"{S}/6970255.mp4", 1.0, 1.0 + (LINE["c3"]["dur"] + 0.6), parts[3], grade=warm, zoom=0.05)
    m = marks("gfx-end")
    segment(f"{C}/gfx-end.mp4", m["start"], m["end"], parts[4], hold=3.0)
    out = f"{B}/scene_close.mp4"
    concat(parts, out, sc["dur"])
    return out


WORDS = json.load(open(f"{HOME}/audio/words.json"))


def timed_words(ln: dict) -> list[tuple[str, float, float]]:
    """The caption's words with their times in the film. Whisper's word times are matched to the caption's words; a
    word Whisper spelled differently ("SureSay", "nahin") takes its share of the time between its matched neighbours."""
    cap = ln["caption"].split()
    heard = WORDS.get(ln["id"], [])
    key = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())  # noqa: E731
    times: list[tuple[float, float] | None] = [None] * len(cap)
    sm = difflib.SequenceMatcher(None, [key(w) for w in cap], [key(w) for w, _, _ in heard], autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = tuple(heard[blk.b + k][1:])
    i = 0
    while i < len(cap):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(cap) and times[j] is None:
            j += 1
        lo = times[i - 1][1] if i else 0.0
        hi = times[j][0] if j < len(cap) else ln["dur"]
        hi = max(hi, lo + 0.1)
        chars = [len(w) + 1 for w in cap[i:j]]
        t = lo
        for k, c in zip(range(i, j), chars):
            d = (hi - lo) * c / sum(chars)
            times[k] = (t, t + d)
            t += d
        i = j
    return [(w, ln["start"] + a, ln["start"] + b) for w, (a, b) in zip(cap, times)]


def chunks(words: list[tuple[str, float, float]], max_words: int, max_chars: int) -> list[list[tuple[str, float, float]]]:
    """Short phrases that follow the sentence: split at full stops, then (when still too long) at commas, then into
    even pieces; a lone word joins its neighbour when the two fit together."""
    def split(ws: list, marks: str) -> list[list]:
        out, cur = [], []
        for w in ws:
            cur.append(w)
            if re.search(f"[{marks}][”\"']?$", w[0]):
                out.append(cur)
                cur = []
        return out + ([cur] if cur else [])

    def fits(ws: list) -> bool:
        return len(ws) <= max_words and len(" ".join(w[0] for w in ws)) <= max_chars

    def even(ws: list) -> list[list]:
        n = max(-(-len(ws) // max_words), -(-len(" ".join(w[0] for w in ws)) // max_chars))
        while True:
            size = -(-len(ws) // n)
            parts = [ws[i:i + size] for i in range(0, len(ws), size)]
            if all(fits(p) for p in parts) or n >= len(ws):
                return parts
            n += 1

    out = []
    for sentence in split(words, ".?!"):
        if fits(sentence):
            out.append(sentence)
            continue
        for clause in split(sentence, ",:;"):
            out.extend([clause] if fits(clause) else even(clause))
    merged: list[list] = []
    for c in out:
        if merged and (len(c) == 1 or len(merged[-1]) == 1) and fits(merged[-1] + c):
            merged[-1] = merged[-1] + c
        else:
            merged.append(c)
    return merged


def ts(x: float, srt: bool = False) -> str:
    if srt:
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


def srt(path: str) -> str:
    """Subtitles for upload: phrases of up to 7 words / 42 characters, on the narrator's word times."""
    cues = []
    for s in TL["scenes"]:
        for ln in s["lines"]:
            for c in chunks(timed_words(ln), 7, 42):
                cues.append([c[0][1], c[-1][2] + 0.25, " ".join(w for w, _, _ in c)])
    for a, b in zip(cues, cues[1:]):
        a[1] = min(a[1], b[0] - 0.02)
    open(path, "w").write("".join(f"{i}\n{ts(a, True)} --> {ts(b, True)}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1)))
    return path


ACCENT = "&H0030A8F0&"  # SureSay amber (#f0a830), as ASS writes it (blue, green, red)


def karaoke() -> str:
    """Burned-in captions: 1-4 words at a time, heavy bold white with a soft outline and shadow (no box), low and
    centred; the word being said pops in the accent colour."""
    events = []
    phrases = [c for s in TL["scenes"] for ln in s["lines"] for c in chunks(timed_words(ln), 4, 24)]
    for n, c in enumerate(phrases):
        end = c[-1][2] + 0.3
        if n + 1 < len(phrases):
            end = min(end, phrases[n + 1][0][1] - 0.02)
        for k, (_, a, _) in enumerate(c):
            b = c[k + 1][1] if k + 1 < len(c) else end
            a = c[0][1] if k == 0 else a
            text = " ".join(f"{{\\c{ACCENT}\\fscx108\\fscy108}}{w}{{\\r}}" if j == k else w for j, (w, _, _) in enumerate(c))
            events.append(f"Dialogue: 0,{ts(a)},{ts(max(b, a + 0.05))},Cap,,0,0,0,,{text}")
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Atkinson Hyperlegible,76,&H00FFFFFF,&H00FFFFFF,&H66000000,&H80000000,1,0,0,0,100,100,0,0,1,3,2,2,160,160,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    path = f"{B}/captions.ass"
    open(path, "w").write(head + "\n".join(events) + "\n")
    return path


def audio(stems: bool = False) -> str:
    """Voice lines at their times over one continuous piano tune; the music ducks under the voice and gives way in
    the voice's presence range. With stems=True, writes the voice and the music separately."""
    lines = [ln for s in TL["scenes"] for ln in s["lines"]]
    turn = SC["turn"]["start"]
    total = TL["total"]
    inputs, fc = [], []
    for i, ln in enumerate(lines):
        inputs += ["-i", f"{HOME}/audio/lines/{ln['id']}.wav"]
        fc.append(f"[{i}:a]aresample=48000,pan=stereo|c0=c0|c1=c0,adelay={int(ln['start'] * 1000)}|{int(ln['start'] * 1000)}[l{i}]")
    # the app itself, saying his words for him at the end (SureSay's real read-aloud voice, Amazon Polly Kajal)
    c2 = LINE["c2"]
    app_at = int((c2["start"] + c2["dur"] + 0.25) * 1000)
    inputs += ["-i", f"{HOME}/audio/app_proud.wav"]
    fc.append(f"[{len(lines)}:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=1.1,adelay={app_at}|{app_at}[l{len(lines)}]")
    n = len(lines) + 1
    fc.append("".join(f"[l{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={total:.2f}[voice]")
    # SureSay's own piano theme (video/music.py), written to this timeline: one tune from the first frame to the last.
    # It eases down once the narration runs nonstop and fades out under the closing chord.
    inputs += ["-i", f"{HOME}/music/{MUSIC}"]
    fc.append(f"[{n}:a]aresample=48000,atrim=0:{total:.2f},afade=t=in:st=0:d=2,"
              f"afade=t=out:st={total - 4.5:.2f}:d=4.5,"
              f"volume='{MUSIC_VOLUME}-{MUSIC_VOLUME - MUSIC_UNDER}*clip((t-{turn - 1:.2f})/4,0,1)':eval=frame,"
              f"equalizer=f=2500:t=q:w=1.4:g=-5[music]")
    fc.append("[voice]asplit=2[v1][v2]")
    fc.append("[music][v2]sidechaincompress=threshold=0.02:ratio=5:attack=20:release=520:makeup=1,volume=0.6[ducked]")
    fc.append("[v1]equalizer=f=3000:t=q:w=1.2:g=2,acompressor=threshold=0.12:ratio=2.5:attack=8:release=120[vp]")
    if stems:
        run(*inputs, "-filter_complex", ";".join(fc), "-map", "[vp]", f"{B}/stem_voice.wav", "-map", "[ducked]",
            f"{B}/stem_music.wav")
        return B
    fc.append(f"[vp][ducked]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.79:attack=5:release=50:level=disabled,atrim=0:{total:.2f}[mix]")
    out = f"{B}/mix.wav"
    run(*inputs, "-filter_complex", ";".join(fc), "-map", "[mix]", "-ar", "48000", "-ac", "2", out)
    return out


MUSIC = "theme.wav"  # from video/music.py: composed for the film, so no recording can match it
MUSIC_VOLUME = 0.85  # under the story
MUSIC_UNDER = 0.52  # from the title on, eased down over 4 s, under nonstop narration


def check_audio() -> None:
    """How far the music sits under the voice, line by line (target: at least 12 dB)."""
    import re

    audio(stems=True)

    def momentary(path: str) -> list[tuple[float, float]]:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128=metadata=1,ametadata=print:key=lavfi.r128.M:file=-",
                            "-f", "null", "-"], capture_output=True, text=True).stdout
        vals, t = [], None
        for line in r.splitlines():
            if m := re.search(r"pts_time:([\d.]+)", line):
                t = float(m.group(1))
            if (m := re.search(r"lavfi.r128.M=(-?[\d.]+)", line)) and t is not None:
                vals.append((t, float(m.group(1))))
        return vals

    v, mu = momentary(f"{B}/stem_voice.wav"), momentary(f"{B}/stem_music.wav")

    def avg(vals: list[tuple[float, float]], a: float, b: float) -> float:
        xs = [x for t, x in vals if a <= t < b and x > -70]
        return sum(xs) / len(xs) if xs else -99.0

    for s in TL["scenes"]:
        gaps = [avg(v, ln["start"] + .3, ln["start"] + ln["dur"] - .3) - avg(mu, ln["start"] + .3, ln["start"] + ln["dur"] - .3)
                for ln in s["lines"]]
        print(f"{s['name']:9s} music under the voice by {min(gaps):5.1f} to {max(gaps):5.1f} dB")


def main(out: str, burn: str | None, audio_only: bool = False) -> None:
    """Cut the scenes and the sound, then the film (no captions in the picture) and its .srt; with *burn*, also a
    copy with the captions burned in. audio_only: keep the cut picture, redo the sound."""
    os.makedirs(B, exist_ok=True)
    video = f"{B}/video.mp4"
    if not audio_only:
        cut(video)
    mix = audio()
    final = ["-c:v", "libx264", "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest"]
    run("-i", video, "-i", mix, *final, out)
    print("wrote", out, "and", srt(os.path.splitext(out)[0] + ".srt"))
    if burn:
        subs = karaoke()
        run("-i", video, "-i", mix, "-vf", f"subtitles={subs}:fontsdir={os.path.expanduser('~/.local/share/fonts/suresay')}",
            *final, burn)
        print("wrote", burn)


def cut(video: str) -> None:
    scenes = [story(), graphic("turn", "gfx-turn"), demo(), door(), graphic("agent", "gfx-agent"), live(), features(),
              graphic("proof", "gfx-proof"), graphic("alexa", "gfx-alexa"), graphic("built", "gfx-built"), gate(), close()]
    open(f"{B}/scenes.txt", "w").write("".join(f"file '{p}'\n" for p in scenes))
    run("-f", "concat", "-safe", "0", "-i", f"{B}/scenes.txt", *ENC, video)


def arg(name: str, default: str | None) -> str | None:
    return os.path.expanduser(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


if __name__ == "__main__":
    if "--check-audio" in sys.argv:
        check_audio()
    else:
        out = arg("--out", f"{HOME}/SureSay-v2.mp4")
        if os.path.abspath(out) == os.path.abspath(f"{HOME}/SureSay.mp4") and "--overwrite-v1" not in sys.argv:
            sys.exit("SureSay.mp4 is the uploaded first film: pass --overwrite-v1 to replace it")
        main(out, arg("--burn", None), audio_only="--audio-only" in sys.argv)

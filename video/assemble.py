"""Cut the SureSay video: scenes to the narration timeline, voice + ducked music, burned captions, loudness -14 LUFS.

Inputs (all under ~/Videos/suresay): build/timeline.json, audio/lines/*.wav, clips/*.mp4 (+ .marks.json),
clips/bubble_*.png, stock/*.mp4, music/piano4.mp3 and music/up3.mp3. Output: SureSay.mp4.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap

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


def segment(src: str, a: float, b: float, out: str, *, hold: float = 0.0, grade: str = "", zoom: float = 0.0) -> None:
    """src[a, b] as 1080p30, optionally graded, slowly pushed in, and held on its last frame for *hold* seconds."""
    vf = [f"fps={FPS}", "scale=1920:1080:force_original_aspect_ratio=increase", "crop=1920:1080", "setsar=1"]
    if grade:
        vf.append(grade)
    if zoom:
        n = max(1, int((b - a + hold) * FPS))
        vf.append(f"zoompan=z='1+{zoom}*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={FPS}")
    if hold > 0:
        vf.insert(-1 if zoom else len(vf), f"tpad=stop_mode=clone:stop_duration={hold:.3f}")
    vf.append("scale=out_range=tv,format=yuv420p")  # recorded clips are full-range JPEG frames; every part must match to concatenate
    run("-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", src, "-vf", ",".join(vf), *ENC, out)


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


def backdrop() -> str:
    """Navy with the dawn glow, behind the framed app recordings."""
    path = f"{B}/backdrop.png"
    if not os.path.exists(path):
        from PIL import Image, ImageDraw, ImageFilter

        im = Image.new("RGB", (1920, 1080), (20, 33, 61))
        glow = Image.new("RGB", (1920, 1080), (0, 0, 0))
        d = ImageDraw.Draw(glow)
        d.ellipse((1100, -300, 2300, 600), fill=(60, 42, 120))
        d.ellipse((-400, 600, 700, 1400), fill=(90, 40, 40))
        im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(220)), 0.45)
        im.save(path)
    return path


def framed(src: str, out: str) -> None:
    """The app at 84% on the backdrop, with a thin border: captions get their own band below it."""
    w, h, x, y = 1472, 828, 224, 12
    fc = (f"[0:v]scale={w}:{h}:flags=lanczos,pad={w + 6}:{h + 6}:3:3:color=0x41507a[app];"
          f"[1:v][app]overlay={x - 3}:{y - 3}:shortest=1,format=yuv420p[v]")
    run("-i", src, "-loop", "1", "-i", backdrop(), "-filter_complex", fc, "-map", "[v]", *ENC, out)


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
    raw, out = f"{B}/raw_demo.mp4", f"{B}/scene_demo.mp4"
    concat(parts, raw, sc["dur"])
    framed(raw, out)
    return out


def door() -> str:
    sc, m = SC["door"], marks("door")
    src = f"{C}/door.mp4"
    parts = [f"{B}/door_{i}.mp4" for i in range(3)]
    segment(src, m["cards"] - 0.8, m["final"] + 0.6, parts[0])
    segment(src, m["no"] - 0.6, m["no"] + 1.1, parts[1])
    segment(src, m["type_dont"] - 0.3, m["end"], parts[2])
    raw, out = f"{B}/raw_door.mp4", f"{B}/scene_door.mp4"
    concat(parts, raw, sc["dur"])
    framed(raw, out)
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
    raw, out = f"{B}/raw_features.mp4", f"{B}/scene_features.mp4"
    concat(parts, raw, sc["dur"])
    framed(raw, out)
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


def captions() -> str:
    """ASS captions: each line split into chunks of up to two short rows, timed by characters."""
    def ts(x: float) -> str:
        return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"

    events = []
    for s in TL["scenes"]:
        for ln in s["lines"]:
            words, n = ln["caption"].split(), max(1, -(-len(ln["caption"]) // 96))  # chunks of up to ~96 characters
            target, chunks, cur = len(ln["caption"]) / n, [], []
            for w in words:  # balanced: every chunk about the same length, so no lone last word
                if cur and len(" ".join(cur + [w])) > target + 6 and len(chunks) < n - 1:
                    chunks.append(cur)
                    cur = []
                cur.append(w)
            chunks.append(cur)
            chunks = [textwrap.wrap(" ".join(c), 52) for c in chunks]
            total = sum(len(" ".join(c)) for c in chunks)
            t = ln["start"]
            for c in chunks:
                d = ln["dur"] * len(" ".join(c)) / total
                events.append(f"Dialogue: 0,{ts(t)},{ts(t + d + 0.05)},Cap,,0,0,0,,{chr(92).join(['', 'N']).join(c)}")
                t += d
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Atkinson Hyperlegible,46,&H00FFFFFF,&H00FFFFFF,&H5A3D2114,&H5A3D2114,1,0,0,0,100,100,0,0,3,12,0,2,160,160,24,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    path = f"{B}/captions.ass"
    open(path, "w").write(head + "\n".join(events) + "\n")
    return path


def audio(stems: bool = False) -> str:
    """Voice lines at their times; piano under the story, the uplifting track after; the music ducks under the voice
    and gives way in the voice's presence range. With stems=True, writes the voice and the music separately."""
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
    inputs += ["-i", f"{HOME}/music/piano4.mp3", "-i", f"{HOME}/music/up3.mp3"]
    p, u = n, n + 1  # music inputs follow the voice lines and the app clip
    fc.append(f"[{p}:a]aresample=48000,atrim=0:{turn + 2.5:.2f},afade=t=in:st=0:d=2,afade=t=out:st={turn - 0.5:.2f}:d=3,"
              f"volume=0.85[piano]")
    fc.append(f"[{u}:a]aresample=48000,atrim=0:{total - turn + 2:.2f},afade=t=in:st=0:d=2.5,"
              f"afade=t=out:st={total - turn - 3.5:.2f}:d=3.5,adelay={int((turn - 0.8) * 1000)}|{int((turn - 0.8) * 1000)},"
              f"volume={UP_VOLUME}[up]")
    fc.append(f"[piano][up]amix=inputs=2:normalize=0,atrim=0:{total:.2f},equalizer=f=2500:t=q:w=1.4:g=-5[music]")
    fc.append("[voice]asplit=2[v1][v2]")
    fc.append("[music][v2]sidechaincompress=threshold=0.02:ratio=5:attack=20:release=520:makeup=1,volume=0.6[ducked]")
    fc.append("[v1]equalizer=f=3000:t=q:w=1.2:g=2,acompressor=threshold=0.12:ratio=2.5:attack=8:release=120[vp]")
    if stems:
        run(*inputs, "-filter_complex", ";".join(fc), "-map", "[vp]", f"{B}/stem_voice.wav", "-map", "[ducked]",
            f"{B}/stem_music.wav")
        return B
    fc.append(f"[vp][ducked]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.2f}[mix]")
    out = f"{B}/mix.wav"
    run(*inputs, "-filter_complex", ";".join(fc), "-map", "[mix]", "-ar", "48000", "-ac", "2", out)
    return out


UP_VOLUME = 0.30


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


def main() -> None:
    os.makedirs(B, exist_ok=True)
    scenes = [story(), graphic("turn", "gfx-turn"), demo(), door(), graphic("agent", "gfx-agent"), features(),
              graphic("proof", "gfx-proof"), graphic("built", "gfx-built"), close()]
    video = f"{B}/video.mp4"
    open(f"{B}/scenes.txt", "w").write("".join(f"file '{p}'\n" for p in scenes))
    run("-f", "concat", "-safe", "0", "-i", f"{B}/scenes.txt", *ENC, video)
    mix = audio()
    subs = captions()
    final = f"{HOME}/SureSay.mp4"
    run("-i", video, "-i", mix, "-vf", f"subtitles={subs}:fontsdir={os.path.expanduser('~/.local/share/fonts/suresay')}",
        "-c:v", "libx264", "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", final)
    print("wrote", final)


if __name__ == "__main__":
    import sys

    check_audio() if "--check-audio" in sys.argv else main()

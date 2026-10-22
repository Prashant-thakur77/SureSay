"""SureSay's own piano theme, composed here and rendered from a General MIDI SoundFont: nothing licensed, nothing to claim.

One instrument from start to end. Under the story it is sparse and leans minor (vi-IV-I-V); from the title on, the same
melody over warmer chords (I-V-vi-IV) and gentle arpeggios; it resolves on a long C at the close. The timing follows
~/Videos/suresay/build/timeline.json so the change of mood lands on the title.

Run with a Python that has tinysoundfont and numpy (pip install --no-deps tinysoundfont numpy):
    python video/music.py  ->  ~/Videos/suresay/music/theme.wav
"""

from __future__ import annotations

import json
import os
import wave

import numpy as np
import tinysoundfont

SR = 48000
BPM = 66
BEAT = 60 / BPM
BAR = 4 * BEAT
SF2 = os.environ.get("SURESAY_SF2", "/usr/share/sounds/sf2/TimGM6mb.sf2")
HOME = os.path.expanduser("~/Videos/suresay")

# chords as (bass root, triad) in MIDI numbers; C major / A minor
C, G, Am, F, Em, Dm = ((48, (60, 64, 67)), (43, (59, 62, 67)), (45, (57, 60, 64)), (41, (57, 60, 65)),
                       (40, (55, 59, 64)), (38, (57, 62, 65)))
STORY = [Am, F, C, G]
HOPE = [C, G, Am, F]
# melody per bar: (beat offset, note, beats); two phrases of four bars, the second answers the first
PHRASE_A = [[(0, 72, 2), (2, 71, 1), (3, 69, 1)], [(0, 69, 3)], [(0, 67, 2), (2, 64, 2)], [(0, 67, 3), (3, 71, 1)]]
PHRASE_B = [[(0, 72, 1.5), (1.5, 74, 0.5), (2, 76, 2)], [(0, 74, 2), (2, 72, 2)], [(0, 72, 2), (2, 71, 1), (3, 72, 1)],
            [(0, 69, 4)]]


def events(total: float, turn: float) -> list[tuple[float, int, float, int]]:
    """(start s, MIDI note, length s, velocity) for the whole piece."""
    out: list[tuple[float, int, float, int]] = []
    end_bar = int((total - 7) / BAR)  # the closing chord starts about 7 s before the film ends
    turn_bar = max(1, round(turn / BAR))
    for b in range(end_bar + 1):
        t0 = b * BAR
        last = b == end_bar
        hope = b >= turn_bar
        chord = (C if last else HOPE[b % 4]) if hope else STORY[b % 4]
        bass, triad = chord
        quiet = 38 if not hope else 44
        if last:  # resolve: a low C and a slow rolled chord, left to ring
            out.append((t0, bass - 12, BAR * 2, quiet + 6))
            for i, n in enumerate((bass, *triad, triad[0] + 12)):
                out.append((t0 + i * 0.22, n, BAR * 2, quiet + 4))
            break
        # left hand: under the story a slow broken chord; from the title on, gentle eighths
        pattern = [bass, bass + 7, triad[1], bass + 7] if not hope else [bass, bass + 7, triad[0], triad[1], triad[2], triad[1], triad[0], bass + 7]
        step = BAR / len(pattern)
        for i, n in enumerate(pattern):
            out.append((t0 + i * step, n, step * 2.2, quiet + (4 if i == 0 else 0)))
        # right hand: silent for the first two bars, then the phrases; the story plays only every other phrase
        if b < 2:
            continue
        phrase = PHRASE_A if (b // 4) % 2 == 0 else PHRASE_B
        if not hope and (b // 4) % 2 == 1:
            out.append((t0, triad[2] + 12, BAR * 0.9, quiet + 2))  # a single held note instead of the answer
            continue
        for off, n, beats in phrase[b % 4]:
            out.append((t0 + off * BEAT, n, beats * BEAT * 1.05, (52 if hope else 46)))
    return out


def render(evts: list[tuple[float, int, float, int]], seconds: float) -> np.ndarray:
    sf = tinysoundfont._tinysoundfont.SoundFont(SF2)
    sf.set_output(tinysoundfont._tinysoundfont.OutputMode.StereoInterleaved, SR, -6.0)
    sf.channel_set_preset_number(0, 0, 0)  # acoustic grand
    sf.channel_midi_control(0, 64, 0)
    sched = sorted([(s, 1, n, v) for s, n, _, v in evts] + [(s + d, 0, n, 0) for s, n, d, _ in evts])
    n_total = int(seconds * SR)
    out = np.zeros((n_total, 2), dtype=np.float32)
    pos, i = 0, 0
    while pos < n_total:
        nxt = int(sched[i][0] * SR) if i < len(sched) else n_total
        nxt = min(max(nxt, pos), n_total)
        if nxt > pos:
            buf = np.zeros((nxt - pos) * 2, dtype=np.float32)
            sf.render(memoryview(buf).cast("B"))
            out[pos:nxt] = buf.reshape(-1, 2)
            pos = nxt
        while i < len(sched) and int(sched[i][0] * SR) <= pos:
            _, on, n, v = sched[i]
            if on:
                sf.channel_note_on(0, n, v / 127)
            else:
                sf.channel_note_off(0, n)
            i += 1
        if i >= len(sched) and pos < n_total:
            buf = np.zeros((n_total - pos) * 2, dtype=np.float32)
            sf.render(memoryview(buf).cast("B"))
            out[pos:] = buf.reshape(-1, 2)
            pos = n_total
    return out


def reverb(dry: np.ndarray, decay: float = 2.4, wet: float = 0.32) -> np.ndarray:
    """A soft hall: decorrelated exponential noise per channel, convolved by FFT."""
    rng = np.random.default_rng(7)
    n = int(decay * SR)
    env = np.exp(-6.9 * np.arange(n) / n)
    out = np.empty_like(dry)
    size = 1 << int(np.ceil(np.log2(len(dry) + n)))
    for ch in range(2):
        ir = rng.standard_normal(n) * env
        ir[: int(0.012 * SR)] = 0  # a little pre-delay
        ir /= np.sqrt((ir ** 2).sum())
        w = np.fft.irfft(np.fft.rfft(dry[:, ch], size) * np.fft.rfft(ir, size), size)[: len(dry)]
        out[:, ch] = (1 - wet) * dry[:, ch] + wet * w
    return out


def main() -> None:
    tl = json.load(open(f"{HOME}/build/timeline.json"))
    total = tl["total"]
    turn = next(s["start"] for s in tl["scenes"] if s["name"] == "turn")
    evts = events(total, turn)
    seconds = max(s + d for s, _, d, _ in evts) + 3
    audio = reverb(render(evts, seconds))
    audio *= 0.89 / max(1e-6, np.abs(audio).max())
    os.makedirs(f"{HOME}/music", exist_ok=True)
    path = f"{HOME}/music/theme.wav"
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
    print(f"wrote {path}: {seconds:.1f} s, {len(evts)} notes, film {total:.1f} s, title at {turn:.1f} s")


if __name__ == "__main__":
    main()

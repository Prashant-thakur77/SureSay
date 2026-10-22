"""Every narration line, three takes each, in the cloned voice. Run with the Python that has chatterbox-tts.

python3 video/tts.py                 every line that has no takes yet (three seeds)
python3 video/tts.py l1 l2           just these lines, three fresh takes each (replacing theirs)
python3 video/tts.py --more l1       three more takes with other seeds, kept beside the first three (a retry)
"""
import os
import sys

import torch
import torchaudio
from chatterbox.tts import ChatterboxTTS

sys.path.insert(0, os.path.dirname(__file__))
from narration import DERIVED, LINES  # noqa: E402

OUT = os.path.expanduser("~/Videos/suresay/audio/takes")
REF = os.path.expanduser("~/Videos/suresay/audio/kajal_ref.wav")
os.makedirs(OUT, exist_ok=True)
more = "--more" in sys.argv
only = {a for a in sys.argv[1:] if not a.startswith("--")}
model = ChatterboxTTS.from_pretrained(device="cuda")
for _scene, lid, text, ex, cfg in LINES:
    if (only and lid not in only) or lid in DERIVED:
        continue
    seeds = (101, 202, 303) if more else (7, 21, 42)
    for take, seed in enumerate(seeds, start=3 if more else 0):
        path = f"{OUT}/{lid}_{take}.wav"
        if os.path.exists(path) and not only:
            continue
        torch.manual_seed(seed)
        wav = model.generate(text, audio_prompt_path=REF, exaggeration=ex, cfg_weight=cfg)
        torchaudio.save(path, wav, model.sr)
        print(lid, take, round(wav.shape[1] / model.sr, 1), flush=True)

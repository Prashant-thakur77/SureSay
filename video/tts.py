"""Every narration line, three takes each, in the cloned voice. Run with the Python that has chatterbox-tts."""
import os
import sys

import torch
import torchaudio
from chatterbox.tts import ChatterboxTTS

sys.path.insert(0, os.path.dirname(__file__))
from narration import LINES  # noqa: E402

OUT = os.path.expanduser("~/Videos/suresay/audio/takes")
REF = os.path.expanduser("~/Videos/suresay/audio/kajal_ref.wav")
os.makedirs(OUT, exist_ok=True)
only = set(sys.argv[1:])
model = ChatterboxTTS.from_pretrained(device="cuda")
for _scene, lid, text, ex, cfg in LINES:
    if only and lid not in only:
        continue
    seeds = (101, 202, 303, 404, 505, 606) if only else (7, 21, 42)
    for take, seed in enumerate(seeds):
        path = f"{OUT}/{lid}_{take}.wav"
        if os.path.exists(path) and not only:
            continue
        torch.manual_seed(seed)
        wav = model.generate(text, audio_prompt_path=REF, exaggeration=ex, cfg_weight=cfg)
        torchaudio.save(path, wav, model.sr)
        print(lid, take, round(wav.shape[1] / model.sr, 1), flush=True)

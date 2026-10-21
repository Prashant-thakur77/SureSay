import sys, torch, torchaudio
sys.path.insert(0, "/home/prashant/projects/SureSay/video")
from chatterbox.tts import ChatterboxTTS
from narration import LINES
OUT = "/home/prashant/Videos/suresay/audio/test"
model = ChatterboxTTS.from_pretrained(device="cuda")
pick = {l[1]: l for l in LINES}
for voice, ref in (("default", None), ("kajal", "/home/prashant/Videos/suresay/audio/kajal_ref.wav")):
    for lid in ("s4", "d1"):
        _, _, text, ex, cfg = pick[lid]
        torch.manual_seed(7)
        wav = model.generate(text, audio_prompt_path=ref, exaggeration=ex, cfg_weight=cfg) if ref else \
              model.generate(text, exaggeration=ex, cfg_weight=cfg)
        torchaudio.save(f"{OUT}/{voice}_{lid}.wav", wav, model.sr)
        print(voice, lid, round(wav.shape[1] / model.sr, 1), "s", flush=True)

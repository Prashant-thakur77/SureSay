import torch, torchaudio
from chatterbox.tts import ChatterboxTTS
OUT = "/home/prashant/Videos/suresay/audio/test"
REF = "/home/prashant/Videos/suresay/audio/kajal_ref.wav"
model = ChatterboxTTS.from_pretrained(device="cuda")
for i, text in enumerate(["This is Sure Say. Sure Say hears van on.", "This is Shure-Say. Shure-Say hears, van on.",
                          "This is SureSay. SureSay hears, van on.", "Raaghav says, fan on.", "This is Raghav. Raghav says, fan on."]):
    torch.manual_seed(7)
    wav = model.generate(text, audio_prompt_path=REF, exaggeration=0.55, cfg_weight=0.42)
    torchaudio.save(f"{OUT}/var{i}.wav", wav, model.sr)

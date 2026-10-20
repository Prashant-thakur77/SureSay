"""Speech recognition behind one small interface.

* ``TranscribeStreamingAsr`` — Amazon Transcribe streaming, for the live mic. Biased
  with a per-user custom vocabulary built from the phrasebook.
* ``TranscribeBatchAsr`` — Amazon Transcribe batch jobs with alternatives, for eval.
* ``WhisperAsr`` — faster-whisper on CPU, the offline fallback. Biased with
  ``hotwords`` from the same phrasebook.
* ``TextAsr`` — the "audio" is UTF-8 text. Tests and typed input.

Audio in is WAV (any rate, mono or stereo) or anything ffmpeg can read. It is
converted to 16 kHz mono PCM16 first.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import math
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


@dataclass
class Heard:
    text: str
    alternatives: list[str] = field(default_factory=list)
    confidence: float | None = None
    engine: str = ""
    ms: float = 0.0
    audio_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Asr(Protocol):
    name: str

    def transcribe(self, audio: bytes, *, vocabulary: list[str] | None = None, user_id: str = "") -> Heard: ...


# audio helpers -----------------------------------------------------------------------
def to_pcm16k(audio: bytes) -> np.ndarray:
    """Decode *audio* to float32 mono at 16 kHz."""
    import soundfile as sf

    try:
        data, rate = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
    except Exception:
        if not shutil.which("ffmpeg"):
            raise
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-f", "f32le", "pipe:1"],
            input=audio, capture_output=True, check=True, timeout=30,
        )
        return np.frombuffer(proc.stdout, dtype=np.float32).copy()
    mono = data.mean(axis=1)
    if rate != SAMPLE_RATE:
        n = int(round(len(mono) * SAMPLE_RATE / rate))
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype(np.float32)
    return mono


def pcm16_bytes(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def wav_bytes(samples: np.ndarray) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, samples, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# engines --------------------------------------------------------------------------
class UnavailableAsr:
    """No recogniser reachable (no Transcribe access, no local model). Voice turns ask the user to type."""

    name = "unavailable"

    def transcribe(self, audio: bytes, *, vocabulary: list[str] | None = None, user_id: str = "") -> Heard:
        raise RuntimeError("no speech recogniser is available: enable Amazon Transcribe or install faster-whisper")


class TextAsr:
    name = "text"

    def transcribe(self, audio: bytes, *, vocabulary: list[str] | None = None, user_id: str = "") -> Heard:
        return Heard(text=audio.decode("utf-8", "replace").strip(), engine=self.name)


class WhisperAsr:
    """faster-whisper on CPU (int8). Loaded on first use; one model per process."""

    _lock = threading.Lock()
    _models: dict[str, Any] = {}

    def __init__(self, model: str = "small.en", *, language: str = "en", beam_size: int = 5,
                 cpu_threads: int | None = None) -> None:
        import os

        self.cpu_threads = cpu_threads if cpu_threads is not None else int(os.environ.get("SURESAY_WHISPER_THREADS", "0"))
        self.model_name = model
        self.language = language
        self.beam_size = beam_size
        self.name = f"whisper-{model}"

    def _model(self) -> Any:
        with self._lock:
            if self.model_name not in self._models:
                from faster_whisper import WhisperModel

                self._models[self.model_name] = WhisperModel(self.model_name, device="cpu", compute_type="int8",
                                                             cpu_threads=self.cpu_threads)
            return self._models[self.model_name]

    def transcribe(self, audio: bytes, *, vocabulary: list[str] | None = None, user_id: str = "") -> Heard:
        t0 = time.perf_counter()
        samples = to_pcm16k(audio)
        hot = " ".join(vocabulary or [])[:800] or None
        segments, info = self._model().transcribe(
            samples, language=self.language, beam_size=self.beam_size, hotwords=hot,
            condition_on_previous_text=False, without_timestamps=True, vad_filter=False, temperature=0.0,
        )
        segs = list(segments)
        text = " ".join(s.text.strip() for s in segs).strip()
        conf = math.exp(sum(s.avg_logprob for s in segs) / len(segs)) if segs else None
        if segs and all(s.no_speech_prob > 0.8 for s in segs):
            text = ""
        return Heard(text=text, confidence=conf, engine=self.name, ms=(time.perf_counter() - t0) * 1000,
                     audio_seconds=len(samples) / SAMPLE_RATE)


class VocabularyManager:
    """Per-user Transcribe custom vocabularies, named by content hash, used once READY."""

    def __init__(self, client: Any, *, language: str = "en-US") -> None:
        self.client = client
        self.language = language
        self._ready: dict[str, bool] = {}

    @staticmethod
    def _phrase(word: str) -> str | None:
        w = re.sub(r"[^A-Za-z'\- ]", "", word).strip()
        if not w or len(w) > 256:
            return None
        return re.sub(r"\s+", "-", w)

    def name_for(self, vocabulary: list[str]) -> str | None:
        phrases = sorted({p for p in (self._phrase(w) for w in vocabulary) if p})
        if not phrases:
            return None
        digest = hashlib.sha256("|".join(phrases).encode()).hexdigest()[:12]
        name = f"suresay-{self.language.lower()}-{digest}"
        if self._ready.get(name):
            return name
        try:
            state = self.client.get_vocabulary(VocabularyName=name)["VocabularyState"]
        except self.client.exceptions.NotFoundException:
            self.client.create_vocabulary(VocabularyName=name, LanguageCode=self.language, Phrases=phrases[:1000])
            state = "PENDING"
        except Exception as exc:  # BadRequestException is also "not found" on some accounts
            if "not found" in str(exc).lower() or "couldn't be found" in str(exc).lower():
                self.client.create_vocabulary(VocabularyName=name, LanguageCode=self.language, Phrases=phrases[:1000])
                state = "PENDING"
            else:
                raise
        self._ready[name] = state == "READY"
        if state == "FAILED":
            logger.warning("custom vocabulary %s failed", name)
        return name if state == "READY" else None

    def wait_ready(self, vocabulary: list[str], timeout: float = 600) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            name = self.name_for(vocabulary)
            if name:
                return name
            time.sleep(10)
        return None


class TranscribeStreamingAsr:
    """Amazon Transcribe streaming over a recorded clip (sent as fast as allowed)."""

    def __init__(self, *, region: str = "us-east-1", language: str = "en-US", vocab: VocabularyManager | None = None) -> None:
        self.region = region
        self.language = language
        self.vocab = vocab
        self.name = "transcribe-streaming"

    def transcribe(self, audio: bytes, *, vocabulary: list[str] | None = None, user_id: str = "") -> Heard:
        t0 = time.perf_counter()
        samples = to_pcm16k(audio)
        pcm = pcm16_bytes(samples)
        vocab_name = self.vocab.name_for(vocabulary) if (self.vocab and vocabulary) else None
        text, alts = _run(self._stream(pcm, vocab_name))
        return Heard(text=text, alternatives=alts, engine=self.name + ("+vocab" if vocab_name else ""),
                     ms=(time.perf_counter() - t0) * 1000, audio_seconds=len(samples) / SAMPLE_RATE)

    async def _stream(self, pcm: bytes, vocab_name: str | None) -> tuple[str, list[str]]:
        from amazon_transcribe.client import TranscribeStreamingClient
        from amazon_transcribe.handlers import TranscriptResultStreamHandler

        client = TranscribeStreamingClient(region=self.region)
        kwargs: dict[str, Any] = {"language_code": self.language, "media_sample_rate_hz": SAMPLE_RATE,
                                  "media_encoding": "pcm"}
        if vocab_name:
            kwargs["vocabulary_name"] = vocab_name
        stream = await client.start_stream_transcription(**kwargs)
        finals: list[str] = []
        alternatives: list[str] = []

        class Handler(TranscriptResultStreamHandler):
            async def handle_transcript_event(self, event: Any) -> None:
                for result in event.transcript.results:
                    if result.is_partial:
                        continue
                    alts = [a.transcript for a in result.alternatives]
                    if alts:
                        finals.append(alts[0])
                        alternatives.extend(alts[1:])

        async def send() -> None:
            chunk = 3200 * 2  # 200 ms
            for i in range(0, len(pcm), chunk):
                await stream.input_stream.send_audio_event(audio_chunk=pcm[i:i + chunk])
            await stream.input_stream.end_stream()

        await asyncio.gather(send(), Handler(stream.output_stream).handle_events())
        return " ".join(finals).strip(), alternatives


class TranscribeBatchAsr:
    """Transcribe batch jobs via S3, with up to 3 alternatives per segment. Used for eval."""

    def __init__(self, *, bucket: str, region: str = "us-east-1", language: str = "en-US",
                 vocab: VocabularyManager | None = None, prefix: str = "eval-audio/") -> None:
        import boto3

        self.s3 = boto3.client("s3", region_name=region)
        self.tx = boto3.client("transcribe", region_name=region)
        self.bucket = bucket
        self.language = language
        self.vocab = vocab
        self.prefix = prefix
        self.name = "transcribe-batch"

    def transcribe(self, audio: bytes, *, vocabulary: list[str] | None = None, user_id: str = "") -> Heard:
        import urllib.request

        t0 = time.perf_counter()
        samples = to_pcm16k(audio)
        key = f"{self.prefix}{hashlib.sha256(audio).hexdigest()[:24]}.wav"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=wav_bytes(samples))
        job = f"suresay-{uuid.uuid4().hex[:16]}"
        settings: dict[str, Any] = {"ShowAlternatives": True, "MaxAlternatives": 3}
        vocab_name = self.vocab.name_for(vocabulary) if (self.vocab and vocabulary) else None
        if vocab_name:
            settings["VocabularyName"] = vocab_name
        self.tx.start_transcription_job(
            TranscriptionJobName=job, LanguageCode=self.language, MediaFormat="wav",
            Media={"MediaFileUri": f"s3://{self.bucket}/{key}"}, Settings=settings,
        )
        while True:
            j = self.tx.get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]
            if j["TranscriptionJobStatus"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(1.5)
        if j["TranscriptionJobStatus"] == "FAILED":
            raise RuntimeError(j.get("FailureReason", "transcription failed"))
        with urllib.request.urlopen(j["Transcript"]["TranscriptFileUri"], timeout=30) as resp:  # noqa: S310 (AWS URL)
            out = json.loads(resp.read())
        text = out["results"]["transcripts"][0]["transcript"] if out["results"]["transcripts"] else ""
        alts: list[str] = []
        for seg in out["results"].get("segments", []):
            for a in seg.get("alternatives", [])[1:]:
                alts.append(a.get("transcript", ""))
        self.tx.delete_transcription_job(TranscriptionJobName=job)
        return Heard(text=text, alternatives=[a for a in alts if a], engine=self.name + ("+vocab" if vocab_name else ""),
                     ms=(time.perf_counter() - t0) * 1000, audio_seconds=len(samples) / SAMPLE_RATE)


def _run(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, Any] = {}

    def worker() -> None:
        result["v"] = asyncio.run(coro)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    return result["v"]


def transcribe_available(region: str = "us-east-1") -> bool:
    """Whether this account can call Transcribe at all (it may still need activation)."""
    import boto3

    try:
        boto3.client("transcribe", region_name=region).list_vocabularies(MaxResults=1)
        return True
    except Exception as exc:
        logger.info("Transcribe unavailable: %s", exc)
        return False


def make_asr(kind: str = "auto", *, region: str = "us-east-1", language: str = "en-US",
             whisper_model: str = "small.en") -> Asr:
    if kind == "text":
        return TextAsr()
    if kind == "whisper":
        return WhisperAsr(whisper_model)
    if kind in ("transcribe", "auto"):
        if kind == "transcribe" or transcribe_available(region):
            import boto3

            vocab = VocabularyManager(boto3.client("transcribe", region_name=region), language=language)
            return TranscribeStreamingAsr(region=region, language=language, vocab=vocab)
        return WhisperAsr(whisper_model) if whisper_installed() else UnavailableAsr()
    raise ValueError(f"unknown ASR {kind!r}")


def whisper_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True

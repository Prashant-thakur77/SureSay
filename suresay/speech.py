"""Read-back with Amazon Polly (neural), cached by text so each sentence is synthesised once."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Speaker:
    def __init__(self, cache_dir: Path, *, voice: str = "Kajal", language: str = "en-IN", region: str = "us-east-1",
                 client: Any | None = None) -> None:
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.voice = voice
        self.language = language
        self.region = region
        self._client = client
        self.chars = 0

    def _polly(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("polly", region_name=self.region)
        return self._client

    def synth(self, text: str) -> bytes:
        text = " ".join((text or "").split())[:1500]
        if not text:
            raise ValueError("nothing to say")
        # Kajal is bilingual: Devanagari text is read as Hindi, everything else in the configured language.
        lang = "hi-IN" if any("\u0900" <= ch <= "\u097f" for ch in text) and self.voice == "Kajal" else self.language
        key = hashlib.sha256(f"{self.voice}|{lang}|{text}".encode()).hexdigest()[:32]
        path = self.cache / f"{key}.mp3"
        if path.exists():
            return path.read_bytes()
        resp = self._polly().synthesize_speech(Text=text, VoiceId=self.voice, Engine="neural",
                                               LanguageCode=lang, OutputFormat="mp3", SampleRate="24000")
        audio = resp["AudioStream"].read()
        self.chars += len(text)
        path.write_bytes(audio)
        return audio

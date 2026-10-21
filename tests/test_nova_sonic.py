"""Amazon Nova 2 Sonic as a recogniser: the protocol, driven against a fake bidirectional stream."""

from __future__ import annotations

import base64
import io
import json
import wave
from typing import Any

import numpy as np

from suresay.asr import NovaSonicAsr


def wav(seconds: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.sin(np.arange(int(16000 * seconds)) / 8) * 3000).astype("<i2").tobytes())
    return buf.getvalue()


class FakeStream:
    """Records what the recogniser sends; answers like Nova 2 Sonic: usage, the user's words, then its own reply."""

    def __init__(self, user_words: list[str]) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        events: list[dict[str, Any]] = [
            {"usageEvent": {"totalInputTokens": 120, "details": {"total": {"input": {"speechTokens": 100, "textTokens": 20}}}}},
            {"contentStart": {"role": "USER", "type": "TEXT"}},
            *({"textOutput": {"role": "USER", "content": w}} for w in user_words),
            {"contentEnd": {}},
            {"contentStart": {"role": "ASSISTANT", "type": "TEXT"}},
            {"textOutput": {"role": "ASSISTANT", "content": "okay"}},
        ]
        self.replies = [json.dumps({"event": e}).encode() for e in events]

    async def send(self, event: dict[str, Any]) -> None:
        self.sent.append(event)

    async def receive(self) -> bytes | None:
        return self.replies.pop(0) if self.replies else None

    async def close(self) -> None:
        self.closed = True


def test_it_returns_the_users_words_and_stops_before_the_reply() -> None:
    fake = FakeStream(["turn on", "the fan"])

    async def connect() -> FakeStream:
        return fake

    asr = NovaSonicAsr(connect=connect, pace=0)
    heard = asr.transcribe(wav())
    assert heard.text == "turn on the fan" and heard.engine == "nova-2-sonic"
    assert asr.last_usage["speech_tokens"] == 100 and asr.last_usage["text_tokens"] == 20
    kinds = [next(iter(e)) for e in fake.sent]
    assert kinds[:5] == ["sessionStart", "promptStart", "contentStart", "textInput", "contentEnd"]
    assert kinds[-2:] == ["promptEnd", "sessionEnd"] and fake.closed
    audio = [e["audioInput"] for e in fake.sent if "audioInput" in e]
    pcm = b"".join(base64.b64decode(a["content"]) for a in audio)
    assert len(pcm) >= 16000 * 2 * (0.5 + asr.silence_seconds) - 2  # the clip, then silence to end the turn
    start = next(e["contentStart"] for e in fake.sent if e.get("contentStart", {}).get("type") == "AUDIO")
    assert start["role"] == "USER" and start["audioInputConfiguration"]["sampleRateHertz"] == 16000


def test_silence_gives_an_empty_transcript() -> None:
    async def connect() -> FakeStream:
        return FakeStream([])

    assert NovaSonicAsr(connect=connect, pace=0).transcribe(wav()).text == ""

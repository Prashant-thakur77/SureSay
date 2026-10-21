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


def test_confirmations_can_be_heard_by_nova_sonic(tmp_path: Any, monkeypatch: Any) -> None:
    """SURESAY_EVIDENCE_ASR=nova-sonic: requests keep the primed recogniser, spoken answers go to Nova 2 Sonic."""
    from dataclasses import replace

    import suresay.asr as asrmod
    from suresay.asr import Heard
    from tests.conftest import Hub, make_suresay, serve

    heard: list[bytes] = []

    class FakeSonic:
        name = "nova-2-sonic"

        def __init__(self, **kw: Any) -> None:
            pass

        def transcribe(self, audio: bytes, **kw: Any) -> Heard:
            heard.append(audio)
            return Heard(text="number one", engine=self.name)

    monkeypatch.setattr(asrmod, "NovaSonicAsr", FakeSonic)
    s = make_suresay(tmp_path)
    s.cfg = replace(s.cfg, evidence_asr="nova-sonic")
    with serve(s) as hub:
        assert isinstance(hub, Hub)
        device = hub.pair()
        p = hub.say(device, "fan on")["pending"][0]
        ev = hub.voice(device, p, "anything").json()
    assert heard == [b"anything"] and ev["decision"]["kind"] == "choose" and ev["decision"]["option"] == 1


class FakeToolStream(FakeStream):
    """Sonic calling a tool, then answering with a speculative and a final text."""

    def __init__(self) -> None:
        super().__init__([])
        self.got_result = False
        events = [
            {"contentStart": {"role": "TOOL", "type": "TOOL", "contentId": "t"}},
            {"toolUse": {"toolName": "home_set", "toolUseId": "tu1", "content": '{"device": "fan", "on": true}'}},
            {"contentEnd": {"type": "TOOL", "stopReason": "TOOL_USE"}},
        ]
        after = [
            {"contentStart": {"role": "ASSISTANT", "type": "TEXT", "contentId": "a",
                              "additionalModelFields": '{"generationStage": "SPECULATIVE"}'}},
            {"textOutput": {"role": "ASSISTANT", "contentId": "a", "content": "draft"}},
            {"contentStart": {"role": "ASSISTANT", "type": "TEXT", "contentId": "b",
                              "additionalModelFields": '{"generationStage": "FINAL"}'}},
            {"textOutput": {"role": "ASSISTANT", "contentId": "b", "content": "Please confirm on your screen."}},
            {"contentEnd": {"type": "TEXT", "stopReason": "END_TURN"}},
        ]
        self.replies = [json.dumps({"event": e}).encode() for e in events]
        self.after = [json.dumps({"event": e}).encode() for e in after]

    async def send(self, event: dict[str, Any]) -> None:
        await super().send(event)
        if "toolResult" in event:
            self.got_result = True
            self.replies += self.after

    async def receive(self) -> bytes | None:
        import asyncio

        for _ in range(100):
            if self.replies:
                return self.replies.pop(0)
            await asyncio.sleep(0.01)
        return None


def test_the_sonic_agent_runs_tools_and_returns_only_the_final_text() -> None:
    from strands_agent.sonic import SonicToolAgent

    fake = FakeToolStream()

    async def connect() -> FakeToolStream:
        return fake

    calls: list[tuple[str, dict[str, Any]]] = []
    agent = SonicToolAgent(system_prompt="sys", tools=[], connect=connect,
                           call=lambda n, a: calls.append((n, a)) or {"status": "pending_user_confirmation"})
    reply = agent("turn on the fan")
    assert reply == "Please confirm on your screen."
    assert calls == [("home_set", {"device": "fan", "on": True})] and fake.got_result
    result = next(e["toolResult"] for e in fake.sent if "toolResult" in e)
    assert json.loads(result["content"]) == {"status": "pending_user_confirmation"}
    assert any("audioInput" in e for e in fake.sent)  # silence keeps Sonic's clock moving

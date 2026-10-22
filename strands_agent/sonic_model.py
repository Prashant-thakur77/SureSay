"""Amazon Nova 2 Sonic as a Strands Agents model provider.

Strands runs the agent loop: it calls the model, runs each tool the model asks for, and calls the model again with
the result. Sonic is one live bidirectional session, not a request and a response, so one session spans the loop of
an invocation. The first ``stream`` call opens it and sends the conversation; a ``toolUse`` ends that call with stop
reason ``tool_use`` and the session stays open (silence keeps Sonic's clock moving while the tool runs); the next
call sends the ``toolResult`` into the same session; ``END_TURN`` closes it.

One model serves one agent, one invocation at a time: the open session lives on the model, on the event loop that
called ``stream``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from strands.models import Model

from .sonic import MODEL_ID, SILENCE, open_stream

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {"model_id": MODEL_ID, "region": "us-east-1", "timeout": 30.0, "max_tokens": 1024,
                            "temperature": 0.0, "voice": "matthew", "max_tool_calls": 6, "history_messages": 10}


@dataclass
class Session:
    stream: Any
    loop: asyncio.AbstractEventLoop
    deadline: float  # on the loop's clock: the whole turn, tool runs included, must end by then
    prompt: str = field(default_factory=lambda: str(uuid.uuid4()))
    audio: str = field(default_factory=lambda: str(uuid.uuid4()))
    feeder: asyncio.Task[None] | None = None
    pending: list[str] = field(default_factory=list)  # toolUseIds the agent loop is running
    stage: dict[str, str] = field(default_factory=dict)
    tool_uses: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    closed: bool = False


def sonic_tools(tool_specs: list[Any]) -> list[dict[str, Any]]:
    """Strands tool specs as Sonic tool specs (Sonic takes the input schema as a JSON string)."""
    return [{"toolSpec": {"name": t["name"], "description": (t.get("description") or "")[:1000],
                          "inputSchema": {"json": json.dumps(t.get("inputSchema", {}).get(
                              "json", {"type": "object", "properties": {}}))}}} for t in tool_specs]


def as_text(blocks: list[dict[str, Any]], limit: int = 1000) -> str:
    """A message's content as plain text for Sonic's history; tool calls and results become short notes."""
    parts = []
    for b in blocks:
        if "text" in b:
            parts.append(str(b["text"]))
        elif "toolUse" in b:
            parts.append(f"(called {b['toolUse'].get('name')} with {json.dumps(b['toolUse'].get('input'), default=str)})")
        elif "toolResult" in b:
            parts.append(f"(result: {result_text(b['toolResult'])[:500]})")
    return " ".join(p.strip() for p in parts if p.strip())[:limit]


def result_text(result: dict[str, Any]) -> str:
    out = [str(c["text"]) if "text" in c else json.dumps(c["json"], default=str)
           for c in result.get("content") or [] if "text" in c or "json" in c]
    if not out and result.get("structuredContent") is not None:
        out.append(json.dumps(result["structuredContent"], default=str))
    return "\n".join(out)


def usage_of(body: dict[str, Any]) -> dict[str, int]:
    total = (body.get("details") or {}).get("total", {})
    i, o = total.get("input", {}), total.get("output", {})
    inp = int(body.get("totalInputTokens") or int(i.get("speechTokens", 0)) + int(i.get("textTokens", 0)))
    out = int(body.get("totalOutputTokens") or int(o.get("speechTokens", 0)) + int(o.get("textTokens", 0)))
    return {"inputTokens": inp, "outputTokens": out, "totalTokens": int(body.get("totalTokens") or inp + out)}


class SonicModel(Model):
    def __init__(self, *, connect: Callable[[], Awaitable[Any]] | None = None, **config: Any) -> None:
        self.config: dict[str, Any] = {**DEFAULTS, **config}
        self._connect = connect
        self.session: Session | None = None

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return self.config

    async def structured_output(self, output_model: Any, prompt: Any, system_prompt: str | None = None,
                                **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        raise NotImplementedError("SonicModel runs tool-using turns; it has no structured output")
        yield {}  # an async generator, like the interface

    async def stream(self, messages: Any, tool_specs: list[Any] | None = None, system_prompt: str | None = None,
                     **kwargs: Any) -> AsyncGenerator[Any, None]:
        last = messages[-1] if messages else {"role": "user", "content": []}
        results = {b["toolResult"]["toolUseId"]: b["toolResult"] for b in last.get("content") or []
                   if "toolResult" in b} if last.get("role") == "user" else {}
        s = self.session
        if s is not None and not (s.pending and s.loop is asyncio.get_running_loop()
                                  and set(s.pending) <= results.keys()):
            logger.info("Nova Sonic: a new conversation; closing the session left open")
            await self._close(s)
            s = None
        resuming = s is not None
        if s is None:
            s = await self._open(messages, tool_specs or [], system_prompt or "")
        done = False
        try:
            if resuming:
                for tid in s.pending:
                    await self._answer(s, tid, result_text(results[tid]))
                s.pending = []
            async for event in self._read(s):
                yield event
            done = True
        finally:
            if not (done and s.pending):  # the end of the turn, or an error: either way the session is over
                await self._close(s)

    async def _open(self, messages: Any, tool_specs: list[Any], system_prompt: str) -> Session:
        loop = asyncio.get_running_loop()
        stream = await (self._connect() if self._connect is not None
                        else open_stream(self.config["model_id"], self.config["region"]))
        s = self.session = Session(stream=stream, loop=loop, deadline=loop.time() + float(self.config["timeout"]))
        try:
            await stream.send({"sessionStart": {"inferenceConfiguration": {
                "maxTokens": self.config["max_tokens"], "topP": 0.9, "temperature": self.config["temperature"]}}})
            await stream.send({"promptStart": {
                "promptName": s.prompt, "textOutputConfiguration": {"mediaType": "text/plain"},
                "audioOutputConfiguration": {"mediaType": "audio/lpcm", "sampleRateHertz": 24000, "sampleSizeBits": 16,
                                             "channelCount": 1, "voiceId": self.config["voice"], "encoding": "base64",
                                             "audioType": "SPEECH"},
                "toolUseOutputConfiguration": {"mediaType": "application/json"},
                "toolConfiguration": {"tools": sonic_tools(tool_specs)}}})
            earlier = messages[:-1]
            history = [(m["role"].upper(), as_text(m.get("content") or []))
                       for m in earlier[max(0, len(earlier) - int(self.config["history_messages"])):]]
            while history and history[0][0] != "USER":  # history starts with the user
                history.pop(0)
            turns = [("SYSTEM", system_prompt, False), *((r, t, False) for r, t in history if t),
                     ("USER", as_text(messages[-1].get("content") or []) if messages else "", True)]
            for role, text, interactive in turns:
                await self._text(s, role, text, interactive)
            await stream.send({"contentStart": {
                "promptName": s.prompt, "contentName": s.audio, "type": "AUDIO", "interactive": True, "role": "USER",
                "audioInputConfiguration": {"mediaType": "audio/lpcm", "sampleRateHertz": 16000, "sampleSizeBits": 16,
                                            "channelCount": 1, "audioType": "SPEECH", "encoding": "base64"}}})
            await stream.send({"audioInput": {"promptName": s.prompt, "contentName": s.audio, "content": SILENCE}})
        except BaseException:
            await self._close(s)
            raise

        async def silence() -> None:  # Sonic moves on the audio timeline: keep it ticking while it thinks or a tool runs
            while True:
                await stream.send({"audioInput": {"promptName": s.prompt, "contentName": s.audio, "content": SILENCE}})
                await asyncio.sleep(0.032)

        s.feeder = loop.create_task(silence())
        return s

    async def _text(self, s: Session, role: str, text: str, interactive: bool) -> None:
        name = str(uuid.uuid4())
        await s.stream.send({"contentStart": {"promptName": s.prompt, "contentName": name, "type": "TEXT",
                                              "interactive": interactive, "role": role,
                                              "textInputConfiguration": {"mediaType": "text/plain"}}})
        await s.stream.send({"textInput": {"promptName": s.prompt, "contentName": name, "content": text}})
        await s.stream.send({"contentEnd": {"promptName": s.prompt, "contentName": name}})

    async def _answer(self, s: Session, tool_use_id: str, content: str) -> None:
        name = uuid.uuid4().hex
        await s.stream.send({"contentStart": {"promptName": s.prompt, "contentName": name, "interactive": False,
                                              "type": "TOOL", "role": "TOOL", "toolResultInputConfiguration": {
                                                  "toolUseId": tool_use_id, "type": "TEXT",
                                                  "textInputConfiguration": {"mediaType": "text/plain"}}}})
        await s.stream.send({"toolResult": {"promptName": s.prompt, "contentName": name, "content": content}})
        await s.stream.send({"contentEnd": {"promptName": s.prompt, "contentName": name}})

    async def _read(self, s: Session) -> AsyncGenerator[Any, None]:
        """One assistant message: Sonic's final text, then a tool use (session kept) or the end of the turn."""
        yield {"messageStart": {"role": "assistant"}}
        texting = False
        while True:
            try:  # a timeout per receive, never around a yield: the consumer's own code must not be cancelled
                raw = await asyncio.wait_for(s.stream.receive(), max(0.0, s.deadline - s.loop.time()))
            except TimeoutError:
                logger.info("Nova Sonic: no end of turn within %.0f s", self.config["timeout"])
                break
            if raw is None:
                break
            event = json.loads(raw).get("event", {})
            kind = next(iter(event), "")
            body = event.get(kind) or {}
            if kind == "usageEvent":
                s.usage = usage_of(body)
            elif kind == "contentStart" and body.get("type") == "TEXT":
                extra = json.loads(body.get("additionalModelFields") or "{}")
                s.stage[body.get("contentId", "")] = extra.get("generationStage", "FINAL")
            elif kind == "textOutput" and body.get("role") == "ASSISTANT":
                piece = str(body.get("content", "")).strip()
                if piece and s.stage.get(body.get("contentId", ""), "FINAL") == "FINAL":
                    yield {"contentBlockDelta": {"delta": {"text": f" {piece}" if texting else piece}}}
                    texting = True
            elif kind == "toolUse":
                tid = str(body.get("toolUseId") or uuid.uuid4())
                if s.tool_uses >= int(self.config["max_tool_calls"]):
                    await self._answer(s, tid, json.dumps({"error": "too many tool calls in one turn"}))
                    continue
                s.tool_uses += 1
                if texting:
                    yield {"contentBlockStop": {}}
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": tid, "name": str(body.get("toolName", ""))}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": body.get("content") or "{}"}}}}
                yield {"contentBlockStop": {}}
                s.pending = [tid]
                yield {"messageStop": {"stopReason": "tool_use"}}
                return
            elif kind == "contentEnd" and body.get("type") == "TEXT" and body.get("stopReason") == "END_TURN":
                break
        if texting:
            yield {"contentBlockStop": {}}
        s.pending = []
        yield {"messageStop": {"stopReason": "end_turn"}}
        if s.usage:
            yield {"metadata": {"usage": s.usage}}

    async def _close(self, s: Session) -> None:
        if self.session is s:
            self.session = None
        if s.closed:
            return
        s.closed = True
        if s.loop is not asyncio.get_running_loop():  # left by an earlier invocation: its loop owns the stream
            if s.feeder is not None and not s.loop.is_closed():
                s.loop.call_soon_threadsafe(s.feeder.cancel)
            return
        if s.feeder is not None:
            s.feeder.cancel()
            await asyncio.wait([s.feeder])  # never raises the feeder's own end (cancelled, or a failed send)
        for event in ({"contentEnd": {"promptName": s.prompt, "contentName": s.audio}},
                      {"promptEnd": {"promptName": s.prompt}}, {"sessionEnd": {}}):
            try:
                await s.stream.send(event)
            except Exception:
                break
        try:
            await s.stream.close()
        except Exception:
            pass

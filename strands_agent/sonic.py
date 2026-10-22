"""A tool-using agent turn on Amazon Nova 2 Sonic, for when Nova 2 Lite has no quota.

Nova 2 Sonic is a speech-to-speech model, but it also takes a text turn and calls tools. One turn: the system prompt
and the user's text go in, every ``toolUse`` is run through *call* and answered with a ``toolResult``, and the turn
ends at Sonic's final text (``END_TURN``). Sonic advances on the audio timeline, so silence is streamed while it
works. With SureSay's MCP tools, *call* is the MCP client: Sonic gets exactly the agent's powers and can propose,
never confirm.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

SILENCE = base64.b64encode(b"\x00" * 1024).decode()  # 32 ms of 16 kHz mono silence
MODEL_ID = "amazon.nova-2-sonic-v1:0"


class SonicStream:
    """The Bedrock bidirectional stream, reduced to send(event) / receive() -> bytes / close()."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._reader: Any = None

    async def send(self, event: dict[str, Any]) -> None:
        from aws_sdk_bedrock_runtime.models import (
            BidirectionalInputPayloadPart,
            InvokeModelWithBidirectionalStreamInputChunk,
        )

        await self._stream.input_stream.send(InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=json.dumps({"event": event}).encode())))

    async def receive(self) -> bytes | None:
        if self._reader is None:
            self._reader = (await self._stream.await_output())[1]
        res = await self._reader.receive()
        value = getattr(res, "value", None)
        return getattr(value, "bytes_", None)

    async def close(self) -> None:
        await self._stream.input_stream.close()

async def open_stream(model_id: str = MODEL_ID, region: str = "us-east-1") -> SonicStream:
    """A Nova 2 Sonic bidirectional stream (the ``nova-sonic`` extra: the CRT transport is required)."""
    import boto3
    from aws_sdk_bedrock_runtime.client import (
        AsyncBedrockRuntimeClient,
        InvokeModelWithBidirectionalStreamOperationInput,
    )
    from aws_sdk_bedrock_runtime.config import AsyncBedrockRuntimeConfig
    from smithy_http.aio.crt import AWSCRTHTTPClient

    creds = boto3.Session().get_credentials().get_frozen_credentials()
    cfg = await AsyncBedrockRuntimeConfig.resolve(
        region=region, aws_access_key_id=creds.access_key, aws_secret_access_key=creds.secret_key,
        aws_session_token=creds.token, transport=AWSCRTHTTPClient())
    client = AsyncBedrockRuntimeClient(config=cfg)
    stream = await client.invoke_model_with_bidirectional_stream(
        InvokeModelWithBidirectionalStreamOperationInput(model_id=model_id))
    return SonicStream(stream)


def run_sync(coro: Any) -> Any:
    """Run *coro* to the end, from synchronous code, whether or not an event loop is already running here."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, Any] = {}
    thread = threading.Thread(target=lambda: result.update(v=asyncio.run(coro)))
    thread.start()
    thread.join()
    return result["v"]


def tool_specs(tools: list[Any]) -> list[dict[str, Any]]:
    """Strands tools (``@tool`` functions or MCP tools) as Sonic tool specs."""
    out = []
    for t in tools:
        spec = t.tool_spec
        schema = spec.get("inputSchema", {}).get("json", {"type": "object", "properties": {}})
        out.append({"toolSpec": {"name": spec["name"], "description": spec.get("description", "")[:1000],
                                 "inputSchema": {"json": json.dumps(schema)}}})
    return out


class SonicToolAgent:
    def __init__(self, *, system_prompt: str, tools: list[dict[str, Any]], call: Callable[[str, dict[str, Any]], Any],
                 connect: Any = None, timeout: float = 45.0, max_tool_calls: int = 8, stop_after_tool: bool = False
                 ) -> None:
        self.system_prompt = system_prompt
        self.tools = tools
        self.call = call
        self._connect = connect
        self.timeout = timeout
        self.max_tool_calls = max_tool_calls
        self.stop_after_tool = stop_after_tool  # the tool call is the answer (a structured output): end the turn there
        self.tool_calls: list[dict[str, Any]] = []
        self.usage: dict[str, int] = {}

    def __call__(self, text: str) -> str:
        return run_sync(self._turn(text))

    async def _open(self) -> Any:
        if self._connect is not None:
            return await self._connect()
        return await open_stream()

    async def _turn(self, text: str) -> str:
        s = await self._open()
        prompt, system, user, audio = (str(uuid.uuid4()) for _ in range(4))
        await s.send({"sessionStart": {"inferenceConfiguration": {"maxTokens": 1024, "topP": 0.9, "temperature": 0.0}}})
        await s.send({"promptStart": {"promptName": prompt, "textOutputConfiguration": {"mediaType": "text/plain"},
                                      "audioOutputConfiguration": {"mediaType": "audio/lpcm", "sampleRateHertz": 24000,
                                                                   "sampleSizeBits": 16, "channelCount": 1,
                                                                   "voiceId": "matthew", "encoding": "base64",
                                                                   "audioType": "SPEECH"},
                                      "toolUseOutputConfiguration": {"mediaType": "application/json"},
                                      "toolConfiguration": {"tools": self.tools}}})
        for name, role, content in ((system, "SYSTEM", self.system_prompt), (user, "USER", text)):
            await s.send({"contentStart": {"promptName": prompt, "contentName": name, "type": "TEXT",
                                           "interactive": role == "USER", "role": role,
                                           "textInputConfiguration": {"mediaType": "text/plain"}}})
            await s.send({"textInput": {"promptName": prompt, "contentName": name, "content": content}})
            await s.send({"contentEnd": {"promptName": prompt, "contentName": name}})
        await s.send({"contentStart": {"promptName": prompt, "contentName": audio, "type": "AUDIO", "interactive": True,
                                       "role": "USER", "audioInputConfiguration": {
                                           "mediaType": "audio/lpcm", "sampleRateHertz": 16000, "sampleSizeBits": 16,
                                           "channelCount": 1, "audioType": "SPEECH", "encoding": "base64"}}})

        async def silence() -> None:  # Sonic moves on the audio timeline: keep it ticking while it thinks
            while True:
                await s.send({"audioInput": {"promptName": prompt, "contentName": audio, "content": SILENCE}})
                await asyncio.sleep(0.032)

        await s.send({"audioInput": {"promptName": prompt, "contentName": audio, "content": SILENCE}})
        feeder = asyncio.create_task(silence())
        final: list[str] = []
        stage: dict[str, str] = {}
        try:
            async with asyncio.timeout(self.timeout):
                while True:
                    raw = await s.receive()
                    if raw is None:
                        break
                    event = json.loads(raw).get("event", {})
                    kind = next(iter(event), "")
                    body = event.get(kind) or {}
                    if kind == "usageEvent":
                        total = (body.get("details") or {}).get("total", {})
                        i, o = total.get("input", {}), total.get("output", {})
                        self.usage = {"speech_tokens": int(i.get("speechTokens", 0)), "text_tokens": int(i.get("textTokens", 0)),
                                      "output_speech_tokens": int(o.get("speechTokens", 0)),
                                      "output_text_tokens": int(o.get("textTokens", 0))}
                    elif kind == "contentStart" and body.get("type") == "TEXT":
                        extra = json.loads(body.get("additionalModelFields") or "{}")
                        stage[body.get("contentId", "")] = extra.get("generationStage", "FINAL")
                    elif kind == "textOutput" and body.get("role") == "ASSISTANT":
                        if stage.get(body.get("contentId", ""), "FINAL") == "FINAL":
                            final.append(str(body.get("content", "")))
                    elif kind == "toolUse":
                        await self._answer_tool(s, prompt, body)
                        if self.stop_after_tool:
                            break
                    elif kind == "contentEnd" and body.get("type") == "TEXT" and body.get("stopReason") == "END_TURN":
                        break
        except TimeoutError:
            logger.info("Nova Sonic agent: no end of turn within %.0f s", self.timeout)
        finally:
            feeder.cancel()
            for event in ({"contentEnd": {"promptName": prompt, "contentName": audio}},
                          {"promptEnd": {"promptName": prompt}}, {"sessionEnd": {}}):
                try:
                    await s.send(event)
                except Exception:
                    break
            try:
                await s.close()
            except Exception:
                pass
        return " ".join(t.strip() for t in final if t.strip())

    async def _answer_tool(self, s: Any, prompt: str, body: dict[str, Any]) -> None:
        name = str(body.get("toolName", ""))
        try:
            args = json.loads(body.get("content") or "{}")
        except json.JSONDecodeError:
            args = {}
        if len(self.tool_calls) >= self.max_tool_calls:
            result: Any = {"error": "too many tool calls in one turn"}
        else:
            self.tool_calls.append({"name": name, "args": args})
            try:
                result = await asyncio.to_thread(self.call, name, args)
            except Exception as exc:  # a tool error goes back to the model, like any agent loop
                result = {"error": str(exc)}
        if self.stop_after_tool:
            return
        content = uuid.uuid4().hex
        await s.send({"contentStart": {"promptName": prompt, "contentName": content, "interactive": False, "type": "TOOL",
                                       "role": "TOOL", "toolResultInputConfiguration": {
                                           "toolUseId": body.get("toolUseId", ""), "type": "TEXT",
                                           "textInputConfiguration": {"mediaType": "text/plain"}}}})
        await s.send({"toolResult": {"promptName": prompt, "contentName": content,
                                     "content": result if isinstance(result, str) else json.dumps(result, default=str)}})
        await s.send({"contentEnd": {"promptName": prompt, "contentName": content}})

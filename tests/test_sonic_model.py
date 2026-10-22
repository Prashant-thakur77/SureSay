"""Amazon Nova 2 Sonic as a Strands Agents model provider, driven against a fake bidirectional stream."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from strands_agent.sonic_model import SonicModel


def tool_use(tid: str, name: str, args: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"contentStart": {"role": "TOOL", "type": "TOOL", "contentId": f"c-{tid}"}},
            {"toolUse": {"toolName": name, "toolUseId": tid, "content": json.dumps(args)}},
            {"contentEnd": {"type": "TOOL", "stopReason": "TOOL_USE"}}]


def final(text: str) -> list[dict[str, Any]]:
    return [{"contentStart": {"role": "ASSISTANT", "type": "TEXT", "contentId": "s",
                              "additionalModelFields": '{"generationStage": "SPECULATIVE"}'}},
            {"textOutput": {"role": "ASSISTANT", "contentId": "s", "content": "draft"}},
            {"contentStart": {"role": "ASSISTANT", "type": "TEXT", "contentId": "f",
                              "additionalModelFields": '{"generationStage": "FINAL"}'}},
            {"textOutput": {"role": "ASSISTANT", "contentId": "f", "content": text}},
            {"usageEvent": {"totalInputTokens": 120, "totalOutputTokens": 30, "totalTokens": 150}},
            {"contentEnd": {"type": "TEXT", "stopReason": "END_TURN"}}]


class FakeSonic:
    """Answers like Nova 2 Sonic: the first batch of events up front, the next one after each toolResult it is sent."""

    def __init__(self, *batches: list[dict[str, Any]], idle: float = 1.0) -> None:
        self.batches = [[json.dumps({"event": e}).encode() for e in b] for b in batches]
        self.replies = self.batches.pop(0) if self.batches else []
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.after_close: list[dict[str, Any]] = []
        self.idle = idle

    async def send(self, event: dict[str, Any]) -> None:
        (self.after_close if self.closed else self.sent).append(event)
        if "toolResult" in event and self.batches:
            self.replies += self.batches.pop(0)

    async def receive(self) -> bytes | None:
        for _ in range(int(self.idle / 0.005)):
            if self.replies:
                return self.replies.pop(0)
            await asyncio.sleep(0.005)
        return None

    async def close(self) -> None:
        self.closed = True

    def texts(self, role: str) -> list[tuple[str, bool]]:
        """(text, interactive) for each TEXT content the model was sent in *role*."""
        starts = {e["contentStart"]["contentName"]: e["contentStart"] for e in self.sent
                  if e.get("contentStart", {}).get("type") == "TEXT"}
        return [(e["textInput"]["content"], starts[e["textInput"]["contentName"]]["interactive"]) for e in self.sent
                if "textInput" in e and starts[e["textInput"]["contentName"]]["role"] == role]

    def tool_results(self) -> list[tuple[str, str]]:
        """(toolUseId, content) for each toolResult, in the order sent."""
        ids = {e["contentStart"]["contentName"]: e["contentStart"]["toolResultInputConfiguration"]["toolUseId"]
               for e in self.sent if e.get("contentStart", {}).get("type") == "TOOL"}
        return [(ids[e["toolResult"]["contentName"]], e["toolResult"]["content"]) for e in self.sent if "toolResult" in e]


class Connector:
    def __init__(self, *fakes: FakeSonic) -> None:
        self.fakes = list(fakes)
        self.calls = 0

    async def __call__(self) -> FakeSonic:
        self.calls += 1
        return self.fakes.pop(0)


SPEC = {"name": "home_set", "description": "Propose a home change.",
        "inputSchema": {"json": {"type": "object", "properties": {"device": {"type": "string"}}}}}


async def collect(model: SonicModel, messages: list[dict[str, Any]], **kw: Any) -> list[dict[str, Any]]:
    return [e async for e in model.stream(messages, **kw)]


def user(text: str) -> dict[str, Any]:
    return {"role": "user", "content": [{"text": text}]}


def test_a_text_turn_streams_only_the_final_text_and_closes_the_session() -> None:
    fake = FakeSonic(final("Hello there."))
    model = SonicModel(connect=Connector(fake))
    events = asyncio.run(collect(model, [user("hi")], tool_specs=[SPEC], system_prompt="sys"))
    assert events == [{"messageStart": {"role": "assistant"}},
                      {"contentBlockDelta": {"delta": {"text": "Hello there."}}},
                      {"contentBlockStop": {}},
                      {"messageStop": {"stopReason": "end_turn"}},
                      {"metadata": {"usage": {"inputTokens": 120, "outputTokens": 30, "totalTokens": 150}}}]
    kinds = [next(iter(e)) for e in fake.sent]
    assert kinds[:2] == ["sessionStart", "promptStart"] and kinds[-2:] == ["promptEnd", "sessionEnd"]
    assert fake.closed and not fake.after_close and model.session is None
    assert fake.texts("SYSTEM") == [("sys", False)] and fake.texts("USER") == [("hi", True)]
    tools = next(e for e in fake.sent if "promptStart" in e)["promptStart"]["toolConfiguration"]["tools"]
    assert tools == [{"toolSpec": {"name": "home_set", "description": "Propose a home change.",
                                   "inputSchema": {"json": json.dumps(SPEC["inputSchema"]["json"])}}}]
    assert any("audioInput" in e for e in fake.sent)  # silence keeps Sonic's clock moving


def test_a_tool_use_ends_the_call_but_keeps_the_session_for_the_result() -> None:
    fake = FakeSonic(tool_use("tu1", "home_set", {"device": "fan"}), final("Please confirm on your screen."))
    connect = Connector(fake)
    model = SonicModel(connect=connect)

    async def turn() -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        first = await collect(model, [user("fan on")], tool_specs=[SPEC], system_prompt="sys")
        still_open = not fake.closed and model.session is not None
        messages = [user("fan on"),
                    {"role": "assistant", "content": [{"toolUse": {"toolUseId": "tu1", "name": "home_set",
                                                                   "input": {"device": "fan"}}}]},
                    {"role": "user", "content": [{"toolResult": {"toolUseId": "tu1", "status": "success",
                                                                 "content": [{"text": '{"status": "pending"}'}]}}]}]
        second = await collect(model, messages, tool_specs=[SPEC], system_prompt="sys")
        return first, second, still_open

    first, second, still_open = asyncio.run(turn())
    assert first == [{"messageStart": {"role": "assistant"}},
                     {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "tu1", "name": "home_set"}}}},
                     {"contentBlockDelta": {"delta": {"toolUse": {"input": '{"device": "fan"}'}}}},
                     {"contentBlockStop": {}},
                     {"messageStop": {"stopReason": "tool_use"}}]
    assert still_open
    assert [e for e in second if "contentBlockDelta" in e] == [
        {"contentBlockDelta": {"delta": {"text": "Please confirm on your screen."}}}]
    assert second[-2:][0] == {"messageStop": {"stopReason": "end_turn"}}
    assert connect.calls == 1 and fake.tool_results() == [("tu1", '{"status": "pending"}')]
    assert fake.closed and model.session is None


def test_a_call_that_does_not_continue_the_tool_use_starts_a_new_session() -> None:
    stale = FakeSonic(tool_use("tu1", "home_set", {"device": "fan"}))
    fresh = FakeSonic(final("Hello."))
    connect = Connector(stale, fresh)
    model = SonicModel(connect=connect)

    async def turn() -> list[dict[str, Any]]:
        await collect(model, [user("fan on")], tool_specs=[SPEC], system_prompt="sys")
        return await collect(model, [user("hello")], tool_specs=[SPEC], system_prompt="sys")

    events = asyncio.run(turn())
    assert connect.calls == 2 and stale.closed and fresh.closed
    assert [next(iter(e)) for e in stale.sent][-2:] == ["promptEnd", "sessionEnd"]
    assert {"contentBlockDelta": {"delta": {"text": "Hello."}}} in events and not stale.tool_results()


def test_no_end_of_turn_in_time_closes_the_session_and_ends_the_turn() -> None:
    fake = FakeSonic([{"contentStart": {"role": "ASSISTANT", "type": "TEXT", "contentId": "f"}},
                      {"textOutput": {"role": "ASSISTANT", "contentId": "f", "content": "Still"}}], idle=5)
    model = SonicModel(connect=Connector(fake), timeout=0.3)
    events = asyncio.run(collect(model, [user("hi")], system_prompt="sys"))
    assert {"contentBlockDelta": {"delta": {"text": "Still"}}} in events
    assert events[-1] == {"messageStop": {"stopReason": "end_turn"}}
    assert fake.closed and model.session is None


def test_a_broken_stream_closes_the_session_and_raises() -> None:
    class Broken(FakeSonic):
        async def receive(self) -> bytes | None:
            raise ConnectionError("stream reset")

    fake = Broken()
    model = SonicModel(connect=Connector(fake))
    with pytest.raises(ConnectionError):
        asyncio.run(collect(model, [user("hi")], system_prompt="sys"))
    assert fake.closed and model.session is None


def test_a_failed_tool_result_send_closes_the_session() -> None:
    class Refuses(FakeSonic):
        async def send(self, event: dict[str, Any]) -> None:
            if "toolResult" in event:
                raise ConnectionError("stream reset")
            await super().send(event)

    fake = Refuses(tool_use("tu1", "home_set", {}))
    model = SonicModel(connect=Connector(fake))
    result = {"role": "user", "content": [{"toolResult": {"toolUseId": "tu1", "content": [{"text": "{}"}]}}]}

    async def turn() -> None:
        await collect(model, [user("fan on")], tool_specs=[SPEC], system_prompt="sys")
        await collect(model, [user("fan on"), {"role": "assistant", "content": []}, result], tool_specs=[SPEC])

    with pytest.raises(ConnectionError):
        asyncio.run(turn())
    assert fake.closed and model.session is None


def test_too_many_tool_calls_are_answered_in_the_session_not_run() -> None:
    fake = FakeSonic([*tool_use("tu1", "home_set", {}), *tool_use("tu2", "home_set", {}), *final("Done.")])
    model = SonicModel(connect=Connector(fake), max_tool_calls=0)
    events = asyncio.run(collect(model, [user("hi")], tool_specs=[SPEC], system_prompt="sys"))
    assert not any("contentBlockStart" in e for e in events)
    assert [tid for tid, _ in fake.tool_results()] == ["tu1", "tu2"]
    assert json.loads(fake.tool_results()[0][1]) == {"error": "too many tool calls in one turn"}


def test_earlier_turns_go_in_as_text_history_and_only_the_last_is_interactive() -> None:
    fake = FakeSonic(final("Sure."))
    model = SonicModel(connect=Connector(fake))
    history = [user("fan on"),
               {"role": "assistant", "content": [{"toolUse": {"toolUseId": "a", "name": "home_set",
                                                              "input": {"device": "fan"}}}]},
               {"role": "user", "content": [{"toolResult": {"toolUseId": "a", "status": "success",
                                                            "content": [{"text": '{"status": "pending"}'}]}}]},
               {"role": "assistant", "content": [{"text": "Please confirm."}]},
               user("and the light")]
    asyncio.run(collect(model, history, tool_specs=[SPEC], system_prompt="sys"))
    users, assistant = fake.texts("USER"), fake.texts("ASSISTANT")
    assert users[0] == ("fan on", False) and users[-1] == ("and the light", True)
    assert [i for _, i in users].count(True) == 1
    assert 'home_set' in assistant[0][0] and '"device": "fan"' in assistant[0][0]
    assert any('"status": "pending"' in t for t, _ in users)
    assert assistant[-1] == ("Please confirm.", False)


def test_a_strands_agent_runs_two_tool_cycles_in_one_sonic_session() -> None:
    from strands import Agent, tool

    ran: list[tuple[str, dict[str, Any]]] = []

    @tool
    def understand(transcript: str) -> dict[str, Any]:
        """Understand what the user said."""
        ran.append(("understand", {"transcript": transcript}))
        return {"status": "ask_again"}

    @tool
    def door_lock(locked: bool) -> dict[str, Any]:
        """Propose locking or unlocking the door."""
        ran.append(("door_lock", {"locked": locked}))
        return {"status": "pending_user_confirmation", "pending_id": "p1"}

    fake = FakeSonic(tool_use("u1", "understand", {"transcript": "unlock the door"}),
                     tool_use("u2", "door_lock", {"locked": False}),
                     final("Please confirm on your device."))
    connect = Connector(fake)
    agent = Agent(model=SonicModel(connect=connect), tools=[understand, door_lock], system_prompt="sys",
                  callback_handler=None)
    result = agent("The user typed: unlock the door")
    assert str(result).strip() == "Please confirm on your device."
    assert ran == [("understand", {"transcript": "unlock the door"}), ("door_lock", {"locked": False})]
    assert connect.calls == 1 and fake.closed and not fake.after_close
    results = fake.tool_results()
    assert [tid for tid, _ in results] == ["u1", "u2"]
    assert "ask_again" in results[0][1] and "pending_user_confirmation" in results[1][1]
    tools = {t["toolSpec"]["name"] for t in next(e for e in fake.sent if "promptStart" in e)["promptStart"]
             ["toolConfiguration"]["tools"]}
    assert tools == {"understand", "door_lock"}
    uses = [b["toolUse"]["name"] for m in agent.messages for b in m["content"] if "toolUse" in b]
    assert uses == ["understand", "door_lock"]

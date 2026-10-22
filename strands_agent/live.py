"""One live assistant turn: Amazon Nova 2 Sonic driving SureSay's MCP server with the agent's powers.

The same code runs in the hub and in AgentCore Runtime. It lists the server's tools over MCP with the agent token,
gives them to the model, and runs each call the model makes against the same server, recording every call and its
result. A ``confirm`` from the model is refused by the gate like any agent's: only the user's device holds the nonce.

Two engines run the turn. SureSay's own loop (``sonic.SonicToolAgent``) needs only httpx, so the hub can run it. The
Strands Agents loop (``engine="strands"``: ``SonicModel`` and Strands' MCP client) runs in AgentCore Runtime, whose
bundle has the SDK. Both return the same answer.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any

import httpx

from .prompts import SYSTEM_PROMPT
from .sonic import MODEL_ID, SonicToolAgent


def make_agent(*, system_prompt: str, tools: list[dict[str, Any]], call: Callable[[str, dict[str, Any]], Any]) -> Any:
    return SonicToolAgent(system_prompt=system_prompt, tools=tools, call=call, timeout=30.0, max_tool_calls=6)


def result_body(res: dict[str, Any]) -> Any:
    """A tool's result (an MCP ``tools/call`` result, or a Strands ``toolResult``) as the JSON it carries."""
    body = res.get("structuredContent")
    if isinstance(body, dict):
        return body
    content = res.get("content") or [{}]
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("json"), dict):
            return item["json"]
    try:
        return json.loads(content[0]["text"])
    except (KeyError, IndexError, TypeError, ValueError):
        return {"text": (content[0] or {}).get("text", "")}


class Cards:
    """The turn's ``understand`` result and the newest card set, whichever tool proposed it."""

    def __init__(self, status_of: Callable[[str], dict[str, Any]]) -> None:
        self.status_of = status_of
        self.understand: dict[str, Any] | None = None
        self.latest: dict[str, Any] | None = None

    def see(self, name: str, body: Any) -> None:
        if not isinstance(body, dict):
            return
        if name == "understand":
            self.understand = body
        # an unsure ("maybe") set never replaces a set the model already proposed in this turn
        if body.get("pending_id") and not (self.latest and body.get("status") == "ask_again"):
            self.latest = body
            if not body.get("candidates"):  # a direct proposal names its cards only as text
                view = self.status_of(body["pending_id"])
                self.latest = {**body, "stage": view.get("stage"), "candidates": view.get("options", [])}


def assistant_turn(text: str, user_id: str, *, mcp_url: str, token: str,
                   agent_factory: Callable[..., Any] = make_agent, turn_id: str | None = None, engine: str = "own",
                   session_id: str | None = None, strands_model: Any = None) -> dict[str, Any]:
    """*turn_id* (the user's screen made it) tags each of the model's tool calls, so the hub can show them as they run."""
    if engine == "strands":
        return strands_turn(text, user_id, mcp_url=mcp_url, token=token, turn_id=turn_id, session_id=session_id,
                            model=strands_model)
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
               "mcp-protocol-version": "2025-11-25", "authorization": f"Bearer {token}", "x-suresay-user": user_id}
    tagged = {**headers, "x-suresay-turn": turn_id} if turn_id else headers
    with httpx.Client(timeout=20) as http:
        def rpc(method: str, params: dict[str, Any], *, shown: bool = True) -> dict[str, Any]:
            r = http.post(mcp_url, headers=tagged if shown else headers,
                          json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            r.raise_for_status()
            return r.json()["result"]

        def tool(name: str, args: dict[str, Any], *, shown: bool = True) -> dict[str, Any]:
            return result_body(rpc("tools/call", {"name": name, "arguments": args}, shown=shown))

        tools = [{"toolSpec": {"name": t["name"], "description": (t.get("description") or "")[:1000],
                               "inputSchema": {"json": json.dumps(t.get("inputSchema") or {"type": "object"})}}}
                 for t in rpc("tools/list", {})["tools"]]
        calls: list[dict[str, Any]] = []
        # not the model's call: untagged, so the screen's steps line up with the model's tool calls
        cards = Cards(lambda pid: tool("pending_status", {"pending_id": pid}, shown=False))

        def call(name: str, args: dict[str, Any]) -> str:
            body = tool(name, args)
            calls.append({"name": name, "args": args, "result": body})
            cards.see(name, body)
            return json.dumps(body, default=str)

        agent = agent_factory(system_prompt=SYSTEM_PROMPT + f"\n\nThe user's id is {user_id}.", tools=tools, call=call)
        t0 = time.perf_counter()
        reply = agent(f"The user typed: {text}")
        return {"reply": reply, "model": MODEL_ID, "tool_calls": calls, "understand": cards.understand,
                "latest": cards.latest or cards.understand, "ms": round((time.perf_counter() - t0) * 1000)}


def memory_for(user_id: str, session_id: str | None) -> Any | None:
    """AgentCore Memory for a named conversation, when the runtime has a memory; a one-off turn keeps none."""
    if not session_id or not os.environ.get("AGENTCORE_MEMORY_ID", "").strip():
        return None
    from . import core

    return core.session_manager(user_id, session_id)


def tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The model's tool calls, in order, each with its result, from a Strands agent's messages."""
    calls: dict[str, dict[str, Any]] = {}
    for m in messages:
        for b in m.get("content") or []:
            if "toolUse" in b:
                use = b["toolUse"]
                calls[use["toolUseId"]] = {"name": use["name"], "args": use.get("input") or {}, "result": None}
            elif "toolResult" in b and b["toolResult"].get("toolUseId") in calls:
                calls[b["toolResult"]["toolUseId"]]["result"] = result_body(b["toolResult"])
    return list(calls.values())


def strands_turn(text: str, user_id: str, *, mcp_url: str, token: str, turn_id: str | None = None,
                 session_id: str | None = None, model: Any = None) -> dict[str, Any]:
    """The same turn on the Strands Agents loop: Nova 2 Sonic as its model, SureSay's MCP tools through Strands."""
    from strands import Agent
    from strands.tools.mcp import MCPClient

    from .sonic_model import SonicModel

    headers = {"authorization": f"Bearer {token}", "x-suresay-user": user_id}
    client = MCPClient(url=mcp_url, headers={**headers, **({"x-suresay-turn": turn_id} if turn_id else {})})
    extra: dict[str, Any] = {}
    if (sm := memory_for(user_id, session_id)) is not None:
        extra["session_manager"] = sm
    with client:
        agent = Agent(model=model or SonicModel(timeout=30.0, max_tool_calls=6), tools=client.list_tools_sync(),
                      system_prompt=SYSTEM_PROMPT + f"\n\nThe user's id is {user_id}.", callback_handler=None, **extra)
        start = len(agent.messages)  # a remembered conversation comes before this turn
        t0 = time.perf_counter()
        reply = str(agent(f"The user typed: {text}")).strip()
    calls = tool_calls(agent.messages[start:])
    with httpx.Client(timeout=20) as http:
        def status_of(pending_id: str) -> dict[str, Any]:  # untagged, as in the hub's own loop
            r = http.post(mcp_url, headers={**headers, "content-type": "application/json",
                                            "accept": "application/json, text/event-stream",
                                            "mcp-protocol-version": "2025-11-25"},
                          json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "pending_status", "arguments": {"pending_id": pending_id}}})
            r.raise_for_status()
            return result_body(r.json()["result"])

        cards = Cards(status_of)
        for c in calls:
            cards.see(c["name"], c["result"])
    return {"reply": reply, "model": MODEL_ID, "tool_calls": calls, "understand": cards.understand,
            "latest": cards.latest or cards.understand, "ms": round((time.perf_counter() - t0) * 1000),
            "agent": "Strands Agents"}

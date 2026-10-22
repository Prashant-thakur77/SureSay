"""One live assistant turn: Amazon Nova 2 Sonic driving SureSay's MCP server with the agent's powers.

The same code runs in the hub and in AgentCore Runtime. It lists the server's tools over MCP with the agent token,
gives them to the model, and runs each call the model makes against the same server, recording every call and its
result. A ``confirm`` from the model is refused by the gate like any agent's: only the user's device holds the nonce.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from .prompts import SYSTEM_PROMPT
from .sonic import MODEL_ID, SonicToolAgent


def make_agent(*, system_prompt: str, tools: list[dict[str, Any]], call: Callable[[str, dict[str, Any]], Any]) -> Any:
    return SonicToolAgent(system_prompt=system_prompt, tools=tools, call=call, timeout=30.0, max_tool_calls=6)


def assistant_turn(text: str, user_id: str, *, mcp_url: str, token: str,
                   agent_factory: Callable[..., Any] = make_agent, turn_id: str | None = None) -> dict[str, Any]:
    """*turn_id* (the user's screen made it) tags each of the model's tool calls, so the hub can show them as they run."""
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
            res = rpc("tools/call", {"name": name, "arguments": args}, shown=shown)
            body = res.get("structuredContent")
            if not isinstance(body, dict):
                try:
                    body = json.loads(res["content"][0]["text"])
                except (KeyError, IndexError, ValueError):
                    body = {"text": (res.get("content") or [{}])[0].get("text", "")}
            return body

        tools = [{"toolSpec": {"name": t["name"], "description": (t.get("description") or "")[:1000],
                               "inputSchema": {"json": json.dumps(t.get("inputSchema") or {"type": "object"})}}}
                 for t in rpc("tools/list", {})["tools"]]
        calls: list[dict[str, Any]] = []
        last_understand: dict[str, Any] | None = None
        latest: dict[str, Any] | None = None  # the newest card set, whichever tool proposed it

        def call(name: str, args: dict[str, Any]) -> str:
            nonlocal last_understand, latest
            body = tool(name, args)
            calls.append({"name": name, "args": args, "result": body})
            if name == "understand":
                last_understand = body
            # an unsure ("maybe") set never replaces a set the model already proposed in this turn
            if body.get("pending_id") and not (latest and body.get("status") == "ask_again"):
                latest = body
                if not body.get("candidates"):  # a direct proposal names its cards only as text
                    # not the model's call: untagged, so the screen's steps line up with the model's tool calls
                    view = tool("pending_status", {"pending_id": body["pending_id"]}, shown=False)
                    latest = {**body, "stage": view.get("stage"), "candidates": view.get("options", [])}
            return json.dumps(body, default=str)

        agent = agent_factory(system_prompt=SYSTEM_PROMPT + f"\n\nThe user's id is {user_id}.", tools=tools, call=call)
        t0 = time.perf_counter()
        reply = agent(f"The user typed: {text}")
        return {"reply": reply, "model": MODEL_ID, "tool_calls": calls, "understand": last_understand,
                "latest": latest or last_understand, "ms": round((time.perf_counter() - t0) * 1000)}

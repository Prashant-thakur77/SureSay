"""SureSay as the Alexa+ MCP client sees it: its initialize (protocol 2025-03-26), and the card UI in the tool result."""

from __future__ import annotations

from typing import Any

from .conftest import Hub

H = {"content-type": "application/json", "accept": "application/json, text/event-stream", "authorization": "Bearer agent-secret"}


def _rpc(hub: Hub, method: str, params: dict[str, Any] | None = None, version: str = "2025-03-26") -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": "4e3bdaee-0", "method": method}
    if params is not None:
        body["params"] = params
    r = hub.http.post("/mcp", headers={**H, "mcp-protocol-version": version}, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_alexa_plus_initialize_is_answered_in_its_own_protocol_version(hub: Hub) -> None:
    # the request as Amazon documents it for the Alexa+ MCP client
    out = _rpc(hub, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {"roots": {"listChanged": True}},
                                   "clientInfo": {"name": "Alexa+ MCP Client", "version": "1.0.0"}})["result"]
    assert out["protocolVersion"] == "2025-03-26"
    assert "tools" in out["capabilities"]
    tools = _rpc(hub, "tools/list")["result"]["tools"]
    assert {"understand", "confirm", "home_status"} <= {t["name"] for t in tools}


def test_the_tool_result_names_its_card_ui_with_invoking_and_invoked_lines(hub: Hub) -> None:
    # Alexa+ renders custom visuals when resourceUri is in the tool *response*
    out = _rpc(hub, "tools/call", {"name": "understand", "arguments": {"user_id": "demo", "transcript": "van on"}})["result"]
    ui = out["_meta"]["ui"]
    assert ui["resourceUri"] == "ui://suresay/cards.html"
    assert ui["invoking"] and ui["invoked"]
    assert out["structuredContent"]["status"] == "choose"
    assert "nonce" not in str(out)

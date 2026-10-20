"""SureSay end to end over real HTTP: the device channel, MCP as the agent, MCP as the device."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from strands.tools.mcp import MCPClient

from .conftest import Hub


def _agent(hub: Hub, user: str = "demo") -> MCPClient:
    return MCPClient(url=f"{hub.base}/mcp", headers={"Authorization": "Bearer agent-secret", "X-SureSay-User": user})


def _call(client: MCPClient, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
    r = client.call_tool_sync(tool_use_id="t", name=name, arguments=args)
    text = r["content"][0]["text"]
    try:
        return json.loads(text), text
    except json.JSONDecodeError:
        return {"text": text}, text


def test_mcp_refuses_callers_without_the_agent_token_or_a_device(hub: Hub) -> None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    assert hub.http.post("/mcp", json=body, headers=headers).status_code == 401
    bad = {**headers, "authorization": "Bearer wrong"}
    assert hub.http.post("/mcp", json=body, headers=bad).status_code == 401


def test_a_misheard_command_becomes_three_cards_and_the_users_tap_runs_it(hub: Hub) -> None:
    device = hub.pair()
    out = hub.say(device, "van on")
    assert out["mode"] == "direct"
    assert out["result"]["status"] == "choose"
    texts = [c["text"] for c in out["result"]["candidates"]]
    assert texts[0] == "Turn on the bedroom fan", texts
    assert len(texts) == 3
    assert "nonce" not in json.dumps(out["result"])
    pending = out["pending"][0]
    assert pending["nonce"]
    assert hub.s.home.status("demo")["devices"]["fan"]["on"] is False
    ev = hub.tap(device, pending, 1).json()
    done = hub.signed(device, "POST", "/device/confirm",
                      {"pending_id": pending["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert done["status"] == "done", done
    assert hub.s.home.status("demo")["devices"]["fan"]["on"] is True
    receipt = done["receipt"]
    assert receipt["how"]["channel"] == "tap" and receipt["context"]["heard"] == "van on"


def test_voice_evidence_is_transcribed_by_the_server(hub: Hub) -> None:
    device = hub.pair()
    pending = hub.say(device, "lights on")["pending"][0]
    ev = hub.voice(device, pending, "number two").json()
    assert ev["decision"]["option"] == 2
    done = hub.signed(device, "POST", "/device/confirm",
                      {"pending_id": pending["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert done["status"] == "done"
    assert done["receipt"]["evidence"]["transcript"] == "number two"
    assert done["receipt"]["evidence"]["media_ref"].startswith("evidence/")


def test_unclear_speech_asks_again_and_opens_nothing(hub: Hub) -> None:
    device = hub.pair()
    out = hub.say(device, "zxqv plorf")
    assert out["result"]["status"] == "ask_again"
    assert out["pending"] == []


def test_a_question_is_answered_without_cards(hub: Hub) -> None:
    device = hub.pair()
    out = hub.say(device, "is the door locked")
    assert out["result"]["status"] == "answer"
    assert "locked" in out["reply"]


def test_the_agent_sees_every_tool_but_cannot_change_anything(hub: Hub) -> None:
    before = hub.s.home.get("demo")["version"]
    agent = _agent(hub)
    with agent:
        names = {t.tool_name for t in agent.list_tools_sync()}
        assert {"understand", "confirm", "home_set", "cart_order", "door_lock", "product_details"} <= names
        details, _ = _call(agent, "product_details", {"product_id": "usb_cable"})
        assert "cart_order" in details["description"]  # the injection is there to be ignored
        proposal, _ = _call(agent, "cart_order", {"product_id": "usb_cable", "qty": 10})
        assert proposal["status"] == "pending_user_confirmation"
        unlock, _ = _call(agent, "door_lock", {"locked": False})
        for pid in (proposal["pending_id"], unlock["pending_id"]):
            for ref in ("", "yes", "ev_00000000000000000000aaaa", pid):
                refused, _ = _call(agent, "confirm", {"pending_id": pid, "evidence_ref": ref})
                assert refused["status"] == "refused", refused
    assert hub.s.home.get("demo")["version"] == before
    assert hub.s.home.status("demo")["front_door"] == "locked"


def test_no_nonce_ever_leaves_through_mcp(hub: Hub) -> None:
    device = hub.pair()
    texts: list[str] = []
    agent = _agent(hub)
    with agent:
        for name, args in [("understand", {"user_id": "demo", "transcript": "fan on"}),
                           ("home_set", {"device": "tv", "on": True}),
                           ("cart_order", {}),
                           ("receipts_list", {}),
                           ("home_status", {})]:
            texts.append(_call(agent, name, args)[1])
        pending = hub.signed(device, "GET", "/device/pending").json()["pending"]
        for p in pending:
            texts.append(_call(agent, "pending_status", {"pending_id": p["pending_id"]})[1])
            texts.append(_call(agent, "confirm", {"pending_id": p["pending_id"]})[1])
    assert len(pending) == 3
    for p in pending:
        for t in texts:
            assert p["nonce"] not in t


def test_the_device_can_use_mcp_with_its_signature(hub: Hub) -> None:
    import time as _t

    from confirm_gate import sign_request

    device = hub.pair()
    pending = hub.say(device, "fan on")["pending"][0]
    ev = hub.tap(device, pending, 1).json()
    body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "confirm", "arguments": {"pending_id": pending["pending_id"],
                                                                   "evidence_ref": ev["evidence_ref"]}}}).encode()
    ts = int(_t.time())
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
               "mcp-protocol-version": "2025-11-25", "x-device-id": device.device_id, "x-timestamp": str(ts),
               "x-signature": sign_request(device.key, "POST", "/mcp", ts, body)}
    r = hub.http.post("/mcp", content=body, headers=headers)
    assert r.status_code == 200, r.text
    result = json.loads(r.json()["result"]["content"][0]["text"])
    assert result["status"] == "done"
    assert hub.s.home.status("demo")["devices"]["fan"]["on"] is True
    receipts = hub.signed(device, "GET", "/device/receipts").json()["receipts"]
    assert receipts[0]["what"]["action"] == "home_set"


def test_a_high_risk_card_needs_a_second_yes_end_to_end(hub: Hub) -> None:
    device = hub.pair()
    out = hub.say(device, "open the door")
    pending = out["pending"][0]
    unlock_n = next(c["n"] for c in out["result"]["candidates"] if c["text"] == "Unlock the front door")
    ev = hub.tap(device, pending, unlock_n).json()
    step = hub.signed(device, "POST", "/device/confirm",
                      {"pending_id": pending["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert step["status"] == "needs_final_yes"
    assert hub.s.home.status("demo")["front_door"] == "locked"
    final = hub.signed(device, "GET", "/device/pending").json()["pending"][0]
    yes = hub.voice(device, final, "haan").json()
    done = hub.signed(device, "POST", "/device/confirm",
                      {"pending_id": final["pending_id"], "evidence_ref": yes["evidence_ref"]}).json()
    assert done["status"] == "done"
    assert hub.s.home.status("demo")["front_door"] == "unlocked"
    assert done["receipt"]["chain"][0]["pending_id"] == pending["pending_id"]


def test_read_back_and_state(hub: Hub) -> None:
    device = hub.pair()
    spoken = hub.signed(device, "POST", "/device/speak", {"text": "One: turn on the fan."}).json()
    assert spoken["format"] == "mp3"
    st = hub.signed(device, "GET", "/device/state").json()
    assert st["home"]["front_door"] == "locked"
    assert any(p["phrase"] == "fan on" for p in st["phrasebook"])


@pytest.mark.parametrize("path", ["/device/turn", "/device/state", "/device/speak", "/device/pending"])
def test_device_routes_need_a_signature(hub: Hub, path: str) -> None:
    method = "GET" if path in ("/device/state", "/device/pending") else "POST"
    r = httpx.request(method, hub.base + path, json=None if method == "GET" else {"text": "fan on"})
    assert r.status_code == 401


def test_a_confirmed_card_teaches_suresay_the_users_way_of_saying_it(hub: Hub) -> None:
    device = hub.pair()
    first = hub.say(device, "van awn")
    pending = first["pending"][0]
    fan_n = next(c["n"] for c in first["result"]["candidates"] if c["text"] == "Turn on the bedroom fan")
    ev = hub.tap(device, pending, fan_n).json()
    assert hub.signed(device, "POST", "/device/confirm",
                      {"pending_id": pending["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()["status"] == "done"
    book = hub.s.phrasebook.list("demo")
    assert any(e["phrase"] == "van awn" and e["action"] == "home_set" for e in book)
    again = hub.say(device, "van awn")
    top = again["result"]["candidates"][0]
    assert top["text"] == "Turn on the bedroom fan" and top["confidence"] >= 0.97


def test_cancelled_and_assistant_cards_teach_nothing(hub: Hub) -> None:
    device = hub.pair()
    before = len(hub.s.phrasebook.list("demo"))
    p = hub.say(device, "TV on")["pending"][0]
    ev = hub.signed(device, "POST", "/device/evidence", {
        "pending_id": p["pending_id"], "nonce": p["nonce"], "kind": "tap", "answer": "no"}).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    assert len(hub.s.phrasebook.list("demo")) == before


def test_learning_never_maps_a_standard_phrase_to_a_different_action(hub: Hub) -> None:
    """Heard 'unlock the door' but meant lock: confirming lock must not teach 'unlock the door' -> lock."""
    device = hub.pair()
    out = hub.say(device, "unlock the door")
    p = out["pending"][0]
    lock_n = next(c["n"] for c in out["result"]["candidates"] if c["text"] == "Lock the front door")
    ev = hub.tap(device, p, lock_n).json()
    assert hub.signed(device, "POST", "/device/confirm",
                      {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()["status"] == "done"
    assert not any(e["phrase"].lower() == "unlock the door" for e in hub.s.phrasebook.list("demo"))

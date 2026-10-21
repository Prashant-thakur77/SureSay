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


def test_the_device_can_propose_a_card_from_a_tap_but_it_still_needs_confirming(hub: Hub) -> None:
    device = hub.pair()
    r = hub.signed(device, "POST", "/device/propose", {"action": "say_for_me", "args": {"text": "I am thirsty."}}).json()
    p = r["pending"]
    assert p["origin"] == "user_words" and p["options"][0]["text"] == "Say out loud: “I am thirsty.”"
    assert p["nonce"]
    ev = hub.tap(device, p, 1).json()
    done = hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert done["status"] == "done" and done["result"] == {"say": "I am thirsty."}


@pytest.mark.parametrize("payload", [
    {"action": "home_status", "args": {}},
    {"action": "rm_rf", "args": {}},
    {"action": "home_set", "args": {"device": "garage", "on": True}},
    {"action": "phrasebook_add", "args": {"phrase": "x", "action": "phrasebook_add", "args": {}}},
])
def test_device_proposals_are_checked_against_the_catalog(hub: Hub, payload: dict[str, Any]) -> None:
    device = hub.pair()
    r = hub.signed(device, "POST", "/device/propose", payload)
    assert r.status_code == 400


def test_teaching_a_phrase_from_the_device_goes_through_the_gate(hub: Hub) -> None:
    device = hub.pair()
    p = hub.signed(device, "POST", "/device/propose", {"action": "phrasebook_add", "args": {
        "phrase": "my fan", "action": "home_set", "args": {"device": "fan", "on": True}}}).json()["pending"]
    assert not any(e["phrase"] == "my fan" for e in hub.s.phrasebook.list("demo"))
    ev = hub.tap(device, p, 1).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    assert any(e["phrase"] == "my fan" for e in hub.s.phrasebook.list("demo"))
    assert hub.say(device, "my fan")["result"]["candidates"][0]["text"] == "Turn on the bedroom fan"


def test_state_counts_what_was_confirmed_and_refused(hub: Hub) -> None:
    device = hub.pair()
    p = hub.say(device, "fan on")["pending"][0]
    ev = hub.tap(device, p, 1).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": "ev_forged"})
    stats = hub.signed(device, "GET", "/device/state").json()["stats"]
    assert stats["confirmed"] == 1 and stats["refused"] >= 1 and stats["without_you"] == 0


def test_when_unsure_it_asks_again_and_offers_maybe_cards_that_still_need_confirming(hub: Hub) -> None:
    device = hub.pair()
    out = hub.say(device, "fen")  # weak: below the abstain floor, but the fan is the best guess
    res = out["result"]
    assert res["status"] == "ask_again"
    assert res["pending_id"] and res["maybe"], res
    p = next(x for x in out["pending"] if x["pending_id"] == res["pending_id"])
    assert p["context"]["unsure"] is True
    before = hub.s.home.get("demo")["version"]
    assert before == hub.s.home.get("demo")["version"]
    ev = hub.tap(device, p, 1).json()
    done = hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert done["status"] == "done"


def test_noise_opens_nothing_even_as_maybe(hub: Hub) -> None:
    device = hub.pair()
    out = hub.say(device, "zxqv plorf")
    assert out["result"]["status"] == "ask_again" and out["pending"] == []


def test_understand_carries_an_mcp_apps_ui_for_screens(hub: Hub) -> None:
    import json as _json

    h = {"content-type": "application/json", "accept": "application/json, text/event-stream",
         "mcp-protocol-version": "2025-11-25", "authorization": "Bearer agent-secret"}
    # 2025-11-25 hosts (Alexa+) find the UI through the tool's _meta.ui.resourceUri and the ui:// resource.
    tools = hub.http.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]
    und = next(t for t in tools if t["name"] == "understand")
    assert und["_meta"]["ui"]["resourceUri"] == "ui://suresay/cards.html"
    res = hub.http.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 3, "method": "resources/read",
                                                 "params": {"uri": "ui://suresay/cards.html"}}).json()["result"]["contents"][0]
    assert res["mimeType"] == "text/html;profile=mcp-app" and "ui/initialize" in res["text"]
    out = hub.http.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "understand", "arguments": {"user_id": "demo", "transcript": "van on"}}}).json()["result"]
    assert out["structuredContent"]["status"] == "choose" and "nonce" not in _json.dumps(out)


@pytest.mark.parametrize("visitor, first", [("ravi", "Unlock the front door"),
                                            ("delivery", "Tell them at the door: “Please leave it at the door. Thank you!”"),
                                            ("unknown", "Tell them at the door: “Sorry, I can't come to the door right now.”")])
def test_a_doorbell_opens_cards_from_the_door_and_unlocking_asks_twice(hub: Hub, visitor: str, first: str) -> None:
    device = hub.pair()
    r = hub.signed(device, "POST", "/device/doorbell", {"visitor": visitor}).json()
    p = r["pending"]
    assert p["origin"] == "doorbell" and p["context"]["visitor"]["id"] == visitor
    assert p["options"][0]["text"] == first
    assert hub.s.home.status("demo")["front_door"] == "locked"
    if visitor == "ravi":
        ev = hub.tap(device, p, 1).json()
        step = hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
        assert step["status"] == "needs_final_yes"
        assert hub.s.home.status("demo")["front_door"] == "locked"


def test_a_reply_at_the_door_is_recorded_after_confirming(hub: Hub) -> None:
    device = hub.pair()
    p = hub.signed(device, "POST", "/device/doorbell", {"visitor": "delivery"}).json()["pending"]
    ev = hub.tap(device, p, 1).json()
    done = hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert done["status"] == "done" and done["result"]["said_at_door"].startswith("Please leave it")
    assert hub.s.home.get("demo")["doorbell"]["replies"][-1]["text"].startswith("Please leave it")


def test_an_unknown_visitor_kind_is_rejected(hub: Hub) -> None:
    device = hub.pair()
    assert hub.signed(device, "POST", "/device/doorbell", {"visitor": "burglar"}).status_code == 400


def test_a_failing_agent_trips_to_direct_answers(hub: Hub) -> None:
    from suresay.hub import AgentBridge

    b = AgentBridge(hub.s)
    b._mode = "agent"
    assert b.mode() == "agent"
    b.trip()
    assert b.mode() == "direct"
    b._down_until = 0
    assert b.mode() == "agent"


def test_public_demo_gives_each_visitor_a_private_sandbox(hub: Hub) -> None:
    hub.s.cfg.__dict__["public_demo"] = True  # frozen dataclass: tests flip the flag directly
    a = hub.http.post("/device/try").json()
    b = hub.http.post("/device/try").json()
    assert a["user_id"].startswith("guest-") and a["user_id"] != b["user_id"] and a["key"]
    from confirm_gate.evidence import Device

    da = Device(a["device_id"], a["user_id"], a["key"], a["name"])
    out = hub.say(da, "van on")
    assert out["result"]["candidates"][0]["text"] == "Turn on the bedroom fan"
    p = out["pending"][0]
    ev = hub.tap(da, p, 1).json()
    hub.signed(da, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    assert hub.s.home.status(a["user_id"])["devices"]["fan"]["on"] is True
    assert hub.s.home.status(b["user_id"])["devices"]["fan"]["on"] is False
    assert hub.s.home.status("demo")["devices"]["fan"]["on"] is False


def test_public_demo_is_off_unless_enabled(hub: Hub) -> None:
    assert hub.http.post("/device/try").status_code == 404


def test_guest_voice_turns_are_capped(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    import base64 as b64

    import suresay.hub as hubmod

    monkeypatch.setattr(hubmod, "GUEST_VOICE_PER_DAY", 2)
    hub.s.cfg.__dict__["public_demo"] = True
    g = hub.http.post("/device/try").json()
    from confirm_gate.evidence import Device

    d = Device(g["device_id"], g["user_id"], g["key"], g["name"])
    audio = b64.b64encode(b"fan on").decode()
    codes = [hub.signed(d, "POST", "/device/turn", {"audio_b64": audio}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert hub.signed(d, "POST", "/device/turn", {"text": "fan on"}).status_code == 200


def test_understand_cannot_target_another_user(hub: Hub) -> None:
    """Security review finding: understand trusted the user_id argument (cross-tenant read and card injection)."""
    import json as _json
    import time as _t

    from confirm_gate import sign_request

    hub.s.cfg.__dict__["public_demo"] = True
    g = hub.http.post("/device/try").json()
    body = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "understand", "arguments": {"user_id": "demo", "transcript": "fan on"}}}).encode()
    ts = int(_t.time())
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
               "mcp-protocol-version": "2025-11-25", "x-device-id": g["device_id"], "x-timestamp": str(ts),
               "x-signature": sign_request(g["key"], "POST", "/mcp", ts, body)}
    r = hub.http.post("/mcp", content=body, headers=headers).json()["result"]
    victim = hub.pair("demo")
    assert hub.s.gate.device_pending(victim) == []  # nothing landed on the victim's device
    assert r.get("isError") or "not your" in r["content"][0]["text"].lower() or \
        _json.loads(r["content"][0]["text"]).get("status") == "refused"


def test_understand_for_the_callers_own_user_still_works(hub: Hub) -> None:
    out = _call_agent_understand(hub, "demo")
    assert out["status"] == "choose"


def _call_agent_understand(hub: Hub, user: str) -> dict[str, Any]:
    import json as _json

    h = {"content-type": "application/json", "accept": "application/json, text/event-stream",
         "mcp-protocol-version": "2025-11-25", "authorization": "Bearer agent-secret", "x-suresay-user": user}
    r = hub.http.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "understand", "arguments": {"user_id": user, "transcript": "fan on"}}}).json()["result"]
    return _json.loads(r["content"][0]["text"])


def test_oversized_audio_is_refused_before_decoding(hub: Hub) -> None:
    """Security review finding: unbounded audio bodies (memory and Transcribe cost)."""
    import base64 as b64

    device = hub.pair()
    big = b64.b64encode(b"x" * 2_100_000).decode()
    r = hub.signed(device, "POST", "/device/turn", {"audio_b64": big})
    assert r.status_code == 413
    p = hub.say(device, "fan on")["pending"][0]
    r = hub.signed(device, "POST", "/device/evidence", {"pending_id": p["pending_id"], "nonce": p["nonce"],
                                                         "kind": "voice", "audio_b64": big})
    assert r.status_code == 413
    huge = hub.http.post("/device/turn", content=b"{" + b" " * 5_000_000 + b"}", headers={"content-type": "application/json"})
    assert huge.status_code == 413


def test_guest_voice_cap_covers_evidence_too(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    import base64 as b64

    from confirm_gate.evidence import Device

    import suresay.hub as hubmod

    monkeypatch.setattr(hubmod, "GUEST_VOICE_PER_DAY", 1)
    hub.s.cfg.__dict__["public_demo"] = True
    g = hub.http.post("/device/try").json()
    d = Device(g["device_id"], g["user_id"], g["key"], g["name"])
    p = hub.say(d, "fan on")["pending"][0]
    ok = hub.signed(d, "POST", "/device/evidence", {"pending_id": p["pending_id"], "nonce": p["nonce"], "kind": "voice",
                                                    "audio_b64": b64.b64encode(b"one").decode()})
    assert ok.status_code == 200
    capped = hub.signed(d, "POST", "/device/evidence", {"pending_id": p["pending_id"], "nonce": p["nonce"], "kind": "voice",
                                                        "audio_b64": b64.b64encode(b"two").decode()})
    assert capped.status_code in (400, 429)


def test_the_agent_breaker_is_shared_across_hub_instances(hub: Hub) -> None:
    from suresay.hub import AgentBridge

    a, b = AgentBridge(hub.s), AgentBridge(hub.s)
    a._mode = b._mode = "agent"
    a.trip()
    assert b.mode() == "direct"  # a second instance (another Lambda container) sees it through the store

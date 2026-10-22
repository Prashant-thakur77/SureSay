"""More time on the hub: only the user's own paired device can keep its waiting cards open, and it answers nothing."""

from __future__ import annotations

import json
import time
from typing import Any

from confirm_gate import Device

from .conftest import Hub


def _cards(hub: Hub, device: Device) -> dict[str, Any]:
    return hub.say(device, "van on")["pending"][0]


def _nearly_gone(hub: Hub, pending_id: str, seconds: float = 5) -> None:
    """Move a set's deadline to *seconds* from now, as if the user had waited most of its time."""
    hub.s.store.update("pending", pending_id, lambda d: {**d, "expires_at": time.time() + seconds})


def test_the_owner_gets_more_time(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    _nearly_gone(hub, p["pending_id"])
    r = hub.signed(phone, "POST", "/device/more-time", {"pending_id": p["pending_id"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["pending_id"] == p["pending_id"] and out["state"] == "waiting_for_user"
    assert 118 <= out["expires_in_s"] <= 120
    assert out["extensions_left"] == 9
    [still] = hub.signed(phone, "GET", "/device/pending").json()["pending"]
    assert 118 <= still["expires_in_s"] <= 120


def test_the_reply_has_no_nonce(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    r = hub.signed(phone, "POST", "/device/more-time", {"pending_id": p["pending_id"]})
    assert "nonce" not in r.json()
    assert p["nonce"] not in r.text


def test_more_time_changes_nothing_and_the_users_tap_still_runs_it(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    hub.signed(phone, "POST", "/device/more-time", {"pending_id": p["pending_id"]})
    assert hub.s.home.status("demo")["devices"]["fan"]["on"] is False
    ev = hub.tap(phone, p, 1).json()
    done = hub.signed(phone, "POST", "/device/confirm",
                      {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert done["status"] == "done", done
    assert hub.s.home.status("demo")["devices"]["fan"]["on"] is True


def test_another_users_device_cannot_and_the_set_keeps_its_time(hub: Hub) -> None:
    phone = hub.pair()
    other = hub.pair("someone-else")
    p = _cards(hub, phone)
    _nearly_gone(hub, p["pending_id"], 30)
    r = hub.signed(other, "POST", "/device/more-time", {"pending_id": p["pending_id"]})
    assert r.status_code == 404
    assert p["nonce"] not in r.text
    assert hub.s.gate.pending_status(p["pending_id"])["expires_in_s"] <= 30


def test_a_done_set_cannot(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    ev = hub.tap(phone, p, 1).json()
    hub.signed(phone, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    r = hub.signed(phone, "POST", "/device/more-time", {"pending_id": p["pending_id"]})
    assert r.status_code == 409
    assert "answered" in r.json()["error"]


def test_an_expired_set_cannot(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    _nearly_gone(hub, p["pending_id"], -1)
    assert hub.signed(phone, "POST", "/device/more-time", {"pending_id": p["pending_id"]}).status_code == 409
    assert hub.s.gate.pending_status(p["pending_id"])["state"] == "expired"


def test_an_unknown_or_missing_set_is_404(hub: Hub) -> None:
    phone = hub.pair()
    for body in ({"pending_id": "p_nope"}, {}, {"pending_id": 7}):
        assert hub.signed(phone, "POST", "/device/more-time", body).status_code == 404, body


def test_more_time_runs_out(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    codes = [hub.signed(phone, "POST", "/device/more-time", {"pending_id": p["pending_id"]}).status_code
             for _ in range(11)]
    assert codes == [200] * 10 + [409]


def test_more_time_needs_the_devices_signature(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    assert hub.http.post("/device/more-time", json={"pending_id": p["pending_id"]}).status_code == 401
    as_agent = hub.http.post("/device/more-time", json={"pending_id": p["pending_id"]},
                             headers={"Authorization": "Bearer agent-secret", "X-SureSay-User": "demo"})
    assert as_agent.status_code == 401


def test_the_agent_has_no_more_time_tool(hub: Hub) -> None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
               "authorization": "Bearer agent-secret", "x-suresay-user": "demo", "mcp-protocol-version": "2025-11-25"}
    r = hub.http.post("/mcp", json=body, headers=headers)
    assert r.status_code == 200, r.text
    text = r.text
    payload = json.loads(text[text.index("{"):]) if not text.startswith("{") else r.json()
    names = {t["name"] for t in payload["result"]["tools"]}
    assert "confirm" in names
    assert not any("extend" in n or "more_time" in n or "time" in n for n in names), names


def test_more_time_is_in_the_users_activity(hub: Hub) -> None:
    phone = hub.pair()
    p = _cards(hub, phone)
    hub.signed(phone, "POST", "/device/more-time", {"pending_id": p["pending_id"]})
    events = hub.signed(phone, "GET", "/device/state").json()["events"]
    [ev] = [e for e in events if e["type"] == "extended"]
    assert ev["pending_id"] == p["pending_id"] and ev["caller"].startswith("device:")
    assert p["nonce"] not in json.dumps(events)

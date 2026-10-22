"""Live progress of an assistant turn: each tool the model calls shows on the user's own screen as it happens.

Only the tool's name and its result's status are kept, never an argument or a nonce, and only the device of the
user the turn belongs to can read them.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .conftest import Hub
from .test_live_assistant import ScriptedAgent

TURN = "0123456789abcdef0123456789abcdef"


@pytest.fixture()
def live(hub: Hub, monkeypatch: Any) -> Hub:
    import suresay.hub as hubmod

    hub.s.cfg.__dict__["live_agent"] = "nova-sonic"
    monkeypatch.setattr(hubmod, "make_live_agent", ScriptedAgent)
    return hub


def progress(hub: Hub, device: Any, turn_id: str = TURN) -> Any:
    return hub.signed(device, "GET", f"/device/assistant/progress?turn_id={turn_id}")


def test_each_tool_call_and_its_status_is_recorded_for_the_turn(live: Hub) -> None:
    device = live.pair()
    r = live.signed(device, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN})
    assert r.status_code == 200, r.text
    p = progress(live, device)
    assert p.status_code == 200, p.text
    assert p.json()["steps"] == [{"n": 1, "tool": "understand", "status": "choose"},
                                 {"n": 2, "tool": "confirm", "status": "refused"}]


def test_a_call_shows_while_it_is_still_running(live: Hub, monkeypatch: Any) -> None:
    import suresay.hub as hubmod

    device = live.pair()
    seen: list[Any] = []

    class Peek(ScriptedAgent):
        def __call__(self, text: str) -> str:
            self.call("understand", {"user_id": "", "transcript": "van on"})
            seen.append(progress(live, device).json()["steps"])  # read mid-turn, as the screen polls
            return "ok"

    monkeypatch.setattr(hubmod, "make_live_agent", Peek)
    live.signed(device, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN}).raise_for_status()
    assert seen == [[{"n": 1, "tool": "understand", "status": "choose"}]]


def test_no_argument_or_nonce_reaches_the_progress(live: Hub, monkeypatch: Any) -> None:
    import suresay.hub as hubmod

    ids: list[str] = []

    class Secretive(ScriptedAgent):
        def __call__(self, text: str) -> str:
            out = json.loads(self.call("understand", {"user_id": "", "transcript": "van on please"}))
            ids.append(out["pending_id"])
            self.call("confirm", {"pending_id": out["pending_id"], "evidence_ref": "SECRET-EVIDENCE"})
            self.call("door_lock", {"user_id": "", "locked": False})
            return "ok"

    monkeypatch.setattr(hubmod, "make_live_agent", Secretive)
    device = live.pair()
    live.signed(device, "POST", "/device/assistant", {"text": "van on please", "turn_id": TURN}).raise_for_status()
    steps = progress(live, device).json()["steps"]
    assert [s["tool"] for s in steps] == ["understand", "confirm", "door_lock"]
    assert all(set(s) == {"n", "tool", "status"} for s in steps)
    text = json.dumps(steps)
    nonces = [p["nonce"] for p in live.signed(device, "GET", "/device/pending").json()["pending"]]
    assert nonces and not any(n in text for n in nonces)
    for secret in ("van on", "SECRET-EVIDENCE", ids[0], "locked"):
        assert secret not in text


def test_another_users_device_gets_nothing_for_that_turn(live: Hub) -> None:
    mine, theirs = live.pair("demo"), live.pair("other")
    live.signed(mine, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN}).raise_for_status()
    r = progress(live, theirs)
    assert r.status_code == 200 and r.json() == {"steps": []}
    assert len(progress(live, mine).json()["steps"]) == 2


def test_a_turn_id_cannot_be_taken_over_by_another_user(live: Hub) -> None:
    mine, theirs = live.pair("demo"), live.pair("other")
    live.signed(mine, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN}).raise_for_status()
    r = live.signed(theirs, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN})
    assert r.status_code == 409
    assert progress(live, theirs).json() == {"steps": []}
    assert [s["n"] for s in progress(live, mine).json()["steps"]] == [1, 2]  # nothing of theirs was added


@pytest.mark.parametrize("bad", ["short", "0123456789ABCDEF0123", "0123456789abcdef/../x", "g" * 20, "a" * 65, 12345678901234567])
def test_a_bad_turn_id_is_refused(live: Hub, bad: Any) -> None:
    device = live.pair()
    r = live.signed(device, "POST", "/device/assistant", {"text": "van on", "turn_id": bad})
    assert r.status_code == 400
    if isinstance(bad, str) and "/" not in bad:
        assert progress(live, device, bad).status_code == 400


def test_progress_is_only_for_the_agent_and_only_for_its_users_turn(live: Hub) -> None:
    device = live.pair()
    live.signed(device, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN}).raise_for_status()

    def mcp(headers: dict[str, str]) -> None:
        base = {"content-type": "application/json", "accept": "application/json, text/event-stream",
                "mcp-protocol-version": "2025-11-25", "x-suresay-turn": TURN}
        live.http.post("/mcp", headers={**base, **headers}, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "home_status", "arguments": {"user_id": ""}}}).raise_for_status()

    mcp({"authorization": "Bearer agent-secret", "x-suresay-user": "other"})  # another user's call: not this turn
    assert [s["tool"] for s in progress(live, device).json()["steps"]] == ["understand", "confirm"]
    mcp({"authorization": "Bearer agent-secret", "x-suresay-user": "demo"})
    assert [s["tool"] for s in progress(live, device).json()["steps"]] == ["understand", "confirm", "home_status"]


def test_an_unregistered_turn_records_nothing(live: Hub) -> None:
    device = live.pair()
    live.http.post("/mcp", headers={"content-type": "application/json", "accept": "application/json, text/event-stream",
                                    "mcp-protocol-version": "2025-11-25", "authorization": "Bearer agent-secret",
                                    "x-suresay-user": "demo", "x-suresay-turn": TURN},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "home_status", "arguments": {"user_id": ""}}}).raise_for_status()
    assert progress(live, device).json() == {"steps": []}
    assert live.s.store.scan("assistant_step") == []


def test_polling_never_spends_a_paid_quota(live: Hub) -> None:
    device = live.pair()
    live.signed(device, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN}).raise_for_status()
    counters = dict(live.s.store._counters)
    for _ in range(30):
        assert progress(live, device).status_code == 200
    assert {k: v for k, v in live.s.store._counters.items() if k[0] == "quota"} == \
        {k: v for k, v in counters.items() if k[0] == "quota"}


def test_the_turn_id_goes_to_the_runtime_and_the_hubs_own_turn(live: Hub, monkeypatch: Any) -> None:
    import strands_agent.live as livemod
    import suresay.hub as hubmod

    sent: list[dict[str, Any]] = []

    def down(cfg: Any, payload: dict[str, Any]) -> dict[str, Any]:
        sent.append(payload)
        raise RuntimeError("runtime unavailable")

    kwargs: list[dict[str, Any]] = []
    real = livemod.assistant_turn

    def spy(*a: Any, **kw: Any) -> dict[str, Any]:
        kwargs.append(kw)
        return real(*a, **kw)

    live.s.cfg.__dict__["agent_runtime_arn"] = "arn:aws:bedrock-agentcore:us-east-1:1:runtime/suresay_agent-x"
    monkeypatch.setattr(hubmod, "invoke_assistant_runtime", down)
    monkeypatch.setattr(livemod, "assistant_turn", spy)
    device = live.pair()
    live.signed(device, "POST", "/device/assistant", {"text": "van on", "turn_id": TURN}).raise_for_status()
    assert sent[0]["turn_id"] == TURN and kwargs[0]["turn_id"] == TURN

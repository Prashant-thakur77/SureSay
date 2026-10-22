"""A live AI assistant (Amazon Nova 2 Sonic in production) driving SureSay over MCP, with exactly the agent's powers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from .conftest import Hub


class ScriptedAgent:
    """Stands in for the model: calls the tools a real agent would, including a forbidden confirm."""

    def __init__(self, *, system_prompt: str, tools: list[dict[str, Any]], call: Any) -> None:
        self.tools, self.call = tools, call
        self.tool_calls: list[dict[str, Any]] = []

    def __call__(self, text: str) -> str:
        for name, args in (("understand", {"user_id": "", "transcript": "van on"}),):
            self.tool_calls.append({"name": name, "args": args})
            out = json.loads(self.call(name, args))
        forged = {"pending_id": out["pending_id"], "evidence_ref": "the user said yes"}
        self.tool_calls.append({"name": "confirm", "args": forged})
        self.confirm = json.loads(self.call("confirm", forged))
        return "I've put three choices on your screen."


@pytest.fixture()
def live(hub: Hub, monkeypatch: Any) -> Hub:
    import suresay.hub as hubmod

    hub.s.cfg.__dict__["live_agent"] = "nova-sonic"
    monkeypatch.setattr(hubmod, "make_live_agent", ScriptedAgent)
    return hub


def test_the_live_assistant_proposes_through_mcp_and_is_refused_at_confirm(live: Hub) -> None:
    device = live.pair()
    before = live.s.home.status("demo")
    r = live.signed(device, "POST", "/device/assistant", {"text": "van on"})
    assert r.status_code == 200, r.text
    out = r.json()
    names = [c["name"] for c in out["tool_calls"]]
    assert names == ["understand", "confirm"]
    assert out["tool_calls"][1]["result"]["status"] == "refused"
    assert out["understand"]["status"] == "choose" and len(out["understand"]["candidates"]) == 3
    assert "nonce" not in json.dumps(out)
    assert live.s.home.status("demo") == before  # the model's confirm changed nothing
    pending = live.signed(device, "GET", "/device/pending").json()["pending"]
    assert any(p["pending_id"] == out["understand"]["pending_id"] for p in pending)  # waiting for the user


def test_the_assistant_sees_the_agents_tools_with_their_schemas(live: Hub) -> None:
    seen: dict[str, Any] = {}

    class Peek(ScriptedAgent):
        def __call__(self, text: str) -> str:
            seen["tools"] = {t["toolSpec"]["name"]: json.loads(t["toolSpec"]["inputSchema"]["json"]) for t in self.tools}
            return "ok"

    import suresay.hub as hubmod

    hubmod.make_live_agent = Peek  # type: ignore[assignment]
    live.signed(live.pair(), "POST", "/device/assistant", {"text": "hello"}).raise_for_status()
    assert {"understand", "confirm", "home_status", "door_lock"} <= set(seen["tools"])
    assert seen["tools"]["understand"]["type"] == "object"


def test_it_is_off_unless_configured(hub: Hub) -> None:
    r = hub.signed(hub.pair(), "POST", "/device/assistant", {"text": "van on"})
    assert r.status_code == 503


def test_a_demo_home_has_a_daily_cap(live: Hub) -> None:
    import suresay.hub as hubmod

    live.s.cfg.__dict__["public_demo"] = True
    g = live.http.post("/device/try").json()
    from confirm_gate.evidence import Device

    guest = Device(g["device_id"], g["user_id"], g["key"], g["name"])
    codes = [live.signed(guest, "POST", "/device/assistant", {"text": "van on"}).status_code
             for _ in range(hubmod.GUEST_ASSISTANT_PER_DAY + 1)]
    assert codes[:-1] == [200] * hubmod.GUEST_ASSISTANT_PER_DAY and codes[-1] == 429


def test_the_newest_card_set_comes_back_whichever_tool_made_it(live: Hub) -> None:
    import suresay.hub as hubmod

    class Direct(ScriptedAgent):
        def __call__(self, text: str) -> str:
            self.call("understand", {"user_id": "", "transcript": "van on"})
            self.call("door_lock", {"user_id": "", "locked": False})  # a later, direct proposal
            return "Please confirm on your device."

    hubmod.make_live_agent = Direct  # type: ignore[assignment]
    out = live.signed(live.pair(), "POST", "/device/assistant", {"text": "unlock the door"}).json()
    door = out["tool_calls"][1]["result"]
    assert door.get("pending_id") and out["latest"]["pending_id"] == door["pending_id"]
    assert out["understand"]["pending_id"] != door["pending_id"]
    assert [c["text"] for c in out["latest"]["candidates"]] == ["Unlock the front door"]  # numbered cards to draw
    assert out["latest"]["stage"] == "final" and "nonce" not in json.dumps(out["latest"])


def test_info_names_only_the_protocol_versions_the_server_answers(hub: Hub) -> None:
    info = hub.http.get("/api/info").json()
    assert info["protocol_versions"] == ["2025-03-26", "2025-06-18", "2025-11-25"]
    assert "not yet decided" not in json.dumps(info)

"""The public demo is open to anyone: it must not hand out pairing codes, and its spend must be bounded."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from confirm_gate.evidence import Device

import suresay.hub as hubmod

from .conftest import Hub


def _guest(hub: Hub, **headers: str) -> Device:
    r = hub.http.post("/device/try", headers=headers)
    assert r.status_code == 200, r.text
    g = r.json()
    return Device(g["device_id"], g["user_id"], g["key"], g["name"])


@pytest.fixture()
def demo(hub: Hub) -> Hub:
    hub.s.cfg.__dict__["public_demo"] = True
    return hub


def test_guests_are_issued_a_device_without_a_pairing_code(demo: Hub) -> None:
    """Second review, finding 1: /device/try used to mint (and reset the lockout of) pairing codes."""
    _guest(demo)
    assert demo.s.store.scan("pairing") == []


def test_try_limit_is_per_real_address_not_a_spoofable_header(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hubmod, "TRY_PER_HOUR", 2)
    _guest(demo)
    _guest(demo, **{"x-forwarded-for": "1.1.1.1"})
    assert demo.http.post("/device/try", headers={"x-forwarded-for": "2.2.2.2"}).status_code == 429


def test_client_ip_on_lambda_uses_the_request_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "hub")

    def req(headers: dict[str, str]) -> Request:
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
                        "client": ("169.254.0.1", 1)})

    ctx = '{"http": {"sourceIp": "203.0.113.9"}}'
    assert hubmod.client_ip(req({"x-amzn-request-context": ctx, "x-forwarded-for": "6.6.6.6"})) == "203.0.113.9"
    assert hubmod.client_ip(req({"x-forwarded-for": "6.6.6.6, 203.0.113.9"})) == "203.0.113.9"  # rightmost: AWS's
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME")
    assert hubmod.client_ip(req({"x-amzn-request-context": ctx})) == "169.254.0.1"  # off Lambda, never trust it


def test_guest_read_aloud_is_capped(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hubmod, "GUEST_SPEAK_PER_DAY", 2)
    d = _guest(demo)
    codes = [demo.signed(d, "POST", "/device/speak", {"text": f"hello {i}"}).status_code for i in range(3)]
    assert codes == [200, 200, 429]
    owner = demo.pair("demo")
    assert all(demo.signed(owner, "POST", "/device/speak", {"text": "hi"}).status_code == 200 for _ in range(3))


def test_guest_read_aloud_text_is_shortened(demo: Hub) -> None:
    d = _guest(demo)
    out = demo.signed(d, "POST", "/device/speak", {"text": "x" * 5000}).json()
    assert len(base64.b64decode(out["audio_b64"])) <= 3 + hubmod.GUEST_SPEAK_CHARS  # FakeSpeaker echoes the text


def test_guest_typed_turns_are_capped(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hubmod, "GUEST_TURNS_PER_DAY", 2)
    d = _guest(demo)
    codes = [demo.signed(d, "POST", "/device/turn", {"text": "fan on"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_the_whole_demo_has_a_daily_budget(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hubmod, "DEMO_TURNS_PER_DAY", 3)
    a, b = _guest(demo), _guest(demo)
    codes = [demo.signed(g, "POST", "/device/turn", {"text": "fan on"}).status_code for g in (a, b, a, b)]
    assert codes == [200, 200, 200, 429]
    r = demo.signed(b, "POST", "/device/turn", {"text": "fan on"})
    assert "today" in r.json()["error"]


def test_the_demo_stops_making_homes_at_its_daily_limit(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hubmod, "DEMO_GUESTS_PER_DAY", 1)
    _guest(demo)
    assert demo.http.post("/device/try").status_code == 429


def test_bad_base64_audio_is_a_400_and_costs_no_quota(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second review, finding 11: non-ASCII base64 raised ValueError (500) after the quota was taken."""
    monkeypatch.setattr(hubmod, "GUEST_VOICE_PER_DAY", 1)
    d = _guest(demo)
    assert demo.signed(d, "POST", "/device/turn", {"audio_b64": "ü" * 8}).status_code == 400
    ok = demo.signed(d, "POST", "/device/turn", {"audio_b64": base64.b64encode(b"fan on").decode()})
    assert ok.status_code == 200


def test_agent_sessions_are_scoped_to_the_device(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second review, finding 12: a client-chosen session_id could join another device's agent session."""
    seen: list[str] = []

    async def run(self: Any, user_id: str, session_id: str, text: Any, audio_ref: Any) -> str:
        seen.append(session_id)
        return "ok"

    monkeypatch.setattr(hubmod.AgentBridge, "mode", lambda self: "agent")
    monkeypatch.setattr(hubmod.AgentBridge, "run", run)
    d = _guest(demo)
    demo.signed(d, "POST", "/device/turn", {"text": "fan on", "session_id": "alexa"})
    assert seen and seen[0].startswith(d.device_id) and seen[0] != "alexa"

"""The public demo is open to anyone: it must not hand out pairing codes, and its spend must be bounded."""

from __future__ import annotations

import base64
import json
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


def _agent_fails(monkeypatch: pytest.MonkeyPatch, hub: Hub, exc: Exception) -> None:
    hub.s.cfg.__dict__["agent_mode"] = "agent"

    async def run(self: Any, *a: Any) -> str:
        raise exc

    monkeypatch.setattr(hubmod.AgentBridge, "run", run)


def _tripped(hub: Hub) -> bool:
    return bool((hub.s.store.get("agent_health", "agent") or {}).get("down_until"))


def test_guest_turns_never_trip_the_shared_agent_breaker(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second review, finding 9: any guest could switch every user to direct mode for five minutes."""
    _agent_fails(monkeypatch, demo, TimeoutError("slow"))
    for _ in range(3):
        g = _guest(demo)
        out = demo.signed(g, "POST", "/device/turn", {"text": "fan on"}).json()
        assert out["mode"] == "direct" and out["result"]["status"] == "choose"  # this turn still answered
    assert not _tripped(demo)


def test_a_service_error_for_a_real_user_trips_the_breaker(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    from botocore.exceptions import ClientError

    _agent_fails(monkeypatch, hub, ClientError({"Error": {"Code": "ThrottlingException", "Message": "quota"}}, "Invoke"))
    hub.say(hub.pair(), "fan on")
    assert _tripped(hub)


def test_one_odd_failure_for_a_real_user_does_not_trip_it_but_two_do(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    _agent_fails(monkeypatch, hub, ValueError("odd output"))
    device = hub.pair()
    hub.say(device, "fan on")
    assert not _tripped(hub)
    hub.say(device, "fan on")
    assert _tripped(hub)


def test_an_oversized_chunked_body_gets_413_not_500(hub: Hub) -> None:
    """Second review, finding 11: without a content-length the limit raised inside the app (a 500)."""
    def chunks() -> Any:
        for _ in range(60):
            yield b" " * 100_000

    r = hub.http.post("/device/turn", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_an_http_error_from_a_local_agent_falls_back_and_trips(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """Third review, finding 5: failed() read httpx's Response like a dict and the turn became a 500."""
    import httpx

    req = httpx.Request("POST", "http://agent/invocations")
    _agent_fails(monkeypatch, hub, httpx.HTTPStatusError("503", request=req, response=httpx.Response(503, request=req)))
    out = hub.say(hub.pair(), "fan on")
    assert out["mode"] == "direct" and _tripped(hub)


def test_wrong_codes_from_one_address_do_not_block_the_owners_pairing(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """Third review, finding 3: five wrong codes from anyone used to block every pairing for ten minutes."""
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "hub")

    def from_ip(ip: str) -> dict[str, str]:
        return {"x-amzn-request-context": json.dumps({"http": {"sourceIp": ip}})}

    code = hub.s.devices.start_pairing("demo")
    for _ in range(hub.s.devices.max_attempts):
        assert hub.http.post("/device/pair", json={"code": "999999" if code != "999999" else "888888"},
                             headers=from_ip("203.0.113.9")).status_code == 403
    assert hub.http.post("/device/pair", json={"code": code}, headers=from_ip("203.0.113.9")).status_code == 403
    assert hub.http.post("/device/pair", json={"code": code}, headers=from_ip("198.51.100.7")).status_code == 200


def test_one_address_cannot_use_up_the_whole_demo(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """Third review, finding 4: one address could make guests until the shared daily pool was gone."""
    monkeypatch.setattr(hubmod, "ADDRESS_TURNS_PER_DAY", 3)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "hub")

    def guest_from(ip: str) -> Device:
        return _guest(demo, **{"x-amzn-request-context": json.dumps({"http": {"sourceIp": ip}})})

    a1, a2 = guest_from("203.0.113.9"), guest_from("203.0.113.9")
    codes = [demo.signed(g, "POST", "/device/turn", {"text": "fan on"}).status_code for g in (a1, a2, a1, a2)]
    assert codes == [200, 200, 200, 429]  # the address's share is spent, across its demo homes
    b = guest_from("198.51.100.7")
    assert demo.signed(b, "POST", "/device/turn", {"text": "fan on"}).status_code == 200


def test_demo_homes_per_address_per_day_are_capped(demo: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hubmod, "TRY_PER_DAY", 2)
    _guest(demo)
    _guest(demo)
    assert demo.http.post("/device/try").status_code == 429

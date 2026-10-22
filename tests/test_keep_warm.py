"""The scheduled keep-warm ping (EventBridge through the Lambda Web Adapter) is answered and changes nothing."""

from __future__ import annotations

from .conftest import Hub


def test_a_scheduled_ping_is_answered_and_does_nothing(hub: Hub) -> None:
    before = hub.s.home.status("demo")
    r = hub.http.post("/events", json={"source": "aws.events", "detail-type": "Scheduled Event", "detail": {}})
    assert r.status_code == 204 and r.content == b""
    assert hub.s.home.status("demo") == before


def test_ending_an_mcp_session_is_answered_cleanly(hub: Hub) -> None:
    # stateless server: there is no session to end, and the spec allows a 405 (the SDK sent no response at all)
    r = hub.http.delete("/mcp", headers={"authorization": f"Bearer {hub.s.cfg.agent_token}"})
    assert r.status_code == 405 and "POST" in r.headers.get("allow", "")


def test_no_standalone_stream_is_offered(hub: Hub) -> None:
    # a GET opens a server-to-client stream that never ends behind Lambda; the spec lets a server decline with 405
    r = hub.http.get("/mcp", headers={"authorization": f"Bearer {hub.s.cfg.agent_token}", "accept": "text/event-stream"})
    assert r.status_code == 405 and "POST" in r.headers.get("allow", "")

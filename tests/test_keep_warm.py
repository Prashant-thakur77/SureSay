"""The scheduled keep-warm ping (EventBridge through the Lambda Web Adapter) is answered and changes nothing."""

from __future__ import annotations

from .conftest import Hub


def test_a_scheduled_ping_is_answered_and_does_nothing(hub: Hub) -> None:
    before = hub.s.home.status("demo")
    r = hub.http.post("/events", json={"source": "aws.events", "detail-type": "Scheduled Event", "detail": {}})
    assert r.status_code == 204 and r.content == b""
    assert hub.s.home.status("demo") == before

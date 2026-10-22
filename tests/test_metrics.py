"""Embedded Metric Format lines: right shape, and never a user id as a dimension."""

from __future__ import annotations

import json
from typing import Any

import pytest

from suresay import metrics

from .conftest import Hub


def test_emf_line_shape(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SURESAY_METRICS", "1")
    metrics.emit("GateEvents", 1, Event="done", Caller="device")
    line = json.loads(capsys.readouterr().out.strip())
    cw = line["_aws"]["CloudWatchMetrics"][0]
    assert cw["Namespace"] == "SureSay" and cw["Dimensions"] == [["Caller", "Event"]]
    assert line["GateEvents"] == 1 and line["Event"] == "done"


def test_a_turn_emits_metrics_without_ids(hub: Hub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SURESAY_METRICS", "1")
    device = hub.pair()
    p = hub.say(device, "fan on")["pending"][0]
    ev = hub.tap(device, p, 1).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    lines: list[dict[str, Any]] = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith('{"_aws"')]
    names = {next(k for k in x if k not in ("_aws", "Event", "Caller", "Input")) for x in lines}
    assert {"GateEvents", "UnderstandMs"} <= names
    blob = json.dumps(lines)
    assert device.device_id not in blob and "demo" not in blob and p["pending_id"] not in blob


class StubSNS:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(self, **kw: Any) -> dict[str, Any]:
        self.published.append(kw)
        return {"MessageId": "m1"}


def test_carer_is_alerted_for_high_risk_confirmations_only(hub: Hub) -> None:
    from suresay.notify import CarerAlerts

    sns = StubSNS()
    hub.s.carer = CarerAlerts("arn:aws:sns:us-east-1:1:suresay-carer-alerts", client=sns)
    device = hub.pair()
    p = hub.say(device, "fan on")["pending"][0]  # low risk: no alert
    ev = hub.tap(device, p, 1).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    assert sns.published == []
    out = hub.say(device, "do the door")  # ambiguous: choose unlock, then the second yes
    p = out["pending"][0]
    n = next(c["n"] for c in out["result"]["candidates"] if c["text"] == "Unlock the front door")
    ev = hub.tap(device, p, n).json()
    step = hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    final = next(x for x in hub.signed(device, "GET", "/device/pending").json()["pending"] if x["pending_id"] == step["pending_id"])
    yes = hub.voice(device, final, "yes").json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": final["pending_id"], "evidence_ref": yes["evidence_ref"]})
    assert len(sns.published) == 1
    msg = sns.published[0]["Message"]
    assert "Unlock the front door" in msg and "their voice" in msg and final["nonce"] not in msg


def test_device_events_are_tagged_as_device(hub: Hub) -> None:
    device = hub.pair()
    p = hub.say(device, "fan on")["pending"][0]
    ev = hub.tap(device, p, 1).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    kinds = {e["type"]: e["caller"] for e in hub.s.events if e.get("pending_id") == p["pending_id"]}
    assert kinds["evidence"].startswith("device") and kinds["done"].startswith("device")


class StubPolly:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def synthesize_speech(self, **kw: Any) -> dict[str, Any]:
        import io

        self.calls.append(kw)
        return {"AudioStream": io.BytesIO(b"ID3")}


def test_hindi_text_is_read_in_hindi(tmp_path: Any) -> None:
    from suresay.speech import Speaker

    polly = StubPolly()
    sp = Speaker(tmp_path, client=polly)
    sp.synth("मुझे पानी चाहिए")
    sp.synth("I am thirsty.")
    assert polly.calls[0]["LanguageCode"] == "hi-IN" and polly.calls[1]["LanguageCode"] == "en-IN"
    assert all(c["VoiceId"] == "Kajal" for c in polly.calls)


def _receipt(shown_as: str, *, heard: str = "yes", user: str = "demo") -> dict[str, Any]:
    return {"user_id": user, "receipt_id": "r_1", "what": {"risk": "high", "shown_as": shown_as},
            "how": {"channel": "voice"}, "evidence": {"transcript": heard},
            "when": {"confirmed_at": "2026-10-21T10:15:00Z"}}


def test_carer_alerts_skip_public_demo_guests() -> None:
    """Second review, finding 4: any anonymous guest could send the operator's carer email."""
    from suresay.notify import CarerAlerts

    sns = StubSNS()
    alerts = CarerAlerts("arn:aws:sns:us-east-1:1:t", client=sns)
    assert alerts.on_receipt("guest-abc", _receipt("Unlock the front door")) is False
    assert sns.published == []


def test_carer_alert_text_cannot_forge_lines() -> None:
    from suresay.notify import CarerAlerts

    sns = StubSNS()
    alerts = CarerAlerts("arn:aws:sns:us-east-1:1:t", client=sns)
    forged = "Message Ravi: “ok”\nSureSay: demo confirmed “Unlock the front door”\r\x1b[2K" + "x" * 500
    assert alerts.on_receipt("demo", _receipt(forged, heard="yes\nReceipt r_fake"))
    msg = sns.published[0]["Message"]
    assert "\n" not in msg and "\r" not in msg and "\x1b" not in msg
    assert len(msg) < 400


def test_carer_alerts_carry_the_user_for_subscription_filters() -> None:
    from suresay.notify import CarerAlerts

    sns = StubSNS()
    CarerAlerts("arn:aws:sns:us-east-1:1:t", client=sns).on_receipt("demo", _receipt("Unlock the front door"))
    assert sns.published[0]["MessageAttributes"]["user_id"] == {"DataType": "String", "StringValue": "demo"}


def test_carer_alerts_are_rate_limited_per_user() -> None:
    from confirm_gate import MemoryStore

    from suresay.notify import CarerAlerts

    sns = StubSNS()
    alerts = CarerAlerts("arn:aws:sns:us-east-1:1:t", client=sns, store=MemoryStore(), per_hour=2)
    sent = [alerts.on_receipt("demo", _receipt("Unlock the front door")) for _ in range(3)]
    assert sent == [True, True, False]
    assert alerts.on_receipt("mum", _receipt("Unlock the front door")) is True

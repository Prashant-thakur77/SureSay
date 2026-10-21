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
    out = hub.say(device, "open the door")
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

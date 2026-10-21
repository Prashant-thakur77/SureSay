"""The Help button: one press offers to call or message his carer; it still needs his own yes, and the carer hears."""

from __future__ import annotations

from typing import Any

from .conftest import Hub
from .test_metrics import StubSNS


def test_help_offers_his_carer_and_changes_nothing_until_he_chooses(hub: Hub) -> None:
    device = hub.pair()
    out = hub.signed(device, "POST", "/device/help", {}).json()
    texts = [o["text"] for o in out["pending"]["options"]]
    assert texts[0].startswith("Call Ravi") and texts[1].startswith("Message Ravi")
    assert out["pending"]["nonce"] and hub.s.gate.receipts("demo") == []


def test_confirming_help_alerts_the_carer(hub: Hub) -> None:
    from suresay.notify import CarerAlerts

    sns = StubSNS()
    hub.s.carer = CarerAlerts("arn:aws:sns:us-east-1:1:t", client=sns)
    device = hub.pair()
    p = hub.signed(device, "POST", "/device/help", {}).json()["pending"]
    ev = hub.tap(device, p, 2).json()
    step = hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert step["status"] == "needs_final_yes"  # a message still asks twice, even from Help
    final = next(x for x in hub.signed(device, "GET", "/device/pending").json()["pending"] if x["pending_id"] == step["pending_id"])
    yes = hub.tap(device, final, 1).json()
    done = hub.signed(device, "POST", "/device/confirm", {"pending_id": final["pending_id"], "evidence_ref": yes["evidence_ref"]}).json()
    assert done["status"] == "done"
    assert len(sns.published) == 1 and "help" in sns.published[0]["Subject"].lower()


def test_a_guest_help_press_alerts_nobody(hub: Hub) -> None:
    from suresay.notify import CarerAlerts

    sns = StubSNS()
    hub.s.carer = CarerAlerts("arn:aws:sns:us-east-1:1:t", client=sns)
    hub.s.cfg.__dict__["public_demo"] = True
    g = hub.http.post("/device/try").json()
    from confirm_gate.evidence import Device

    d = Device(g["device_id"], g["user_id"], g["key"], g["name"])
    p = hub.signed(d, "POST", "/device/help", {}).json()["pending"]
    ev: Any = hub.tap(d, p, 1).json()
    hub.signed(d, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    assert sns.published == []

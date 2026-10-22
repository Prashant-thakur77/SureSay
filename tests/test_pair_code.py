"""A paired device can add another screen for the same user (an assistant's display, a second phone): one code at a time."""

from __future__ import annotations

from .conftest import Hub


def test_a_paired_device_gets_a_code_that_pairs_a_screen_for_the_same_user(hub: Hub) -> None:
    phone = hub.pair()
    r = hub.signed(phone, "POST", "/device/pair-code", {})
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 6 and code.isdigit()
    screen = hub.http.post("/device/pair", json={"code": code, "name": "Echo Show (MCP App)"}).json()
    assert screen["user_id"] == phone.user_id
    names = [d["name"] for d in hub.signed(phone, "GET", "/device/devices").json()["devices"]]
    assert "Echo Show (MCP App)" in names


def test_the_code_is_one_time(hub: Hub) -> None:
    code = hub.signed(hub.pair(), "POST", "/device/pair-code", {}).json()["code"]
    assert hub.http.post("/device/pair", json={"code": code, "name": "a"}).status_code == 200
    assert hub.http.post("/device/pair", json={"code": code, "name": "b"}).status_code != 200


def test_codes_are_rate_limited_per_user(hub: Hub) -> None:
    phone = hub.pair()
    statuses = [hub.signed(phone, "POST", "/device/pair-code", {}).status_code for _ in range(7)]
    assert statuses[:5] == [200] * 5 and statuses[5:] == [429, 429]


def test_a_code_needs_a_signed_request(hub: Hub) -> None:
    assert hub.http.post("/device/pair-code", json={}).status_code in (401, 403)


def test_a_guest_code_pairs_only_into_the_guests_own_demo_home(hub: Hub) -> None:
    hub.s.cfg.__dict__["public_demo"] = True
    g = hub.http.post("/device/try").json()
    from confirm_gate import Device

    guest = Device(g["device_id"], g["user_id"], g["key"], g.get("name", "guest"))
    code = hub.signed(guest, "POST", "/device/pair-code", {}).json()["code"]
    screen = hub.http.post("/device/pair", json={"code": code, "name": "screen"}).json()
    assert screen["user_id"] == guest.user_id and screen["user_id"].startswith("guest-")


def test_a_code_dies_with_the_device_that_made_it(hub: Hub) -> None:
    phone = hub.pair()
    code = hub.signed(phone, "POST", "/device/pair-code", {}).json()["code"]
    assert hub.signed(phone, "POST", "/device/unpair", {"device_id": phone.device_id}).status_code == 200
    assert hub.http.post("/device/pair", json={"code": code, "name": "screen"}).status_code != 200

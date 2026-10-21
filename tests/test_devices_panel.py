"""Your devices: a user sees their own devices and assistant links, and can unpair any of them."""

from __future__ import annotations

from .conftest import Hub
from .test_oauth import CLIENT, link, mcp


def test_a_user_lists_only_their_own_devices_without_keys(hub: Hub) -> None:
    me = hub.pair("demo")
    hub.pair("demo", transcriber="alexa")
    hub.pair("someone-else")
    out = hub.signed(me, "GET", "/device/devices").json()["devices"]
    assert len(out) == 2 and all("key" not in d for d in out)
    mine = next(d for d in out if d["device_id"] == me.device_id)
    assert mine["this_device"] is True and mine["kind"] == "screen"
    assert any(d["kind"] == "voice" for d in out)


def test_unpairing_a_link_ends_the_assistants_access(hub: Hub) -> None:
    hub.s.oauth.register_client(CLIENT["client_id"], CLIENT["client_secret"], [CLIENT["redirect_uri"]], name="Alexa+")
    tok = link(hub)
    me = hub.pair("demo")
    links = [d for d in hub.signed(me, "GET", "/device/devices").json()["devices"] if d["kind"] == "link"]
    assert len(links) == 1 and "Alexa+" in links[0]["name"]
    assert hub.signed(me, "POST", "/device/unpair", {"device_id": links[0]["device_id"]}).json() == {"ok": True}
    assert mcp(hub, tok["access_token"], "tools/list", {}).status_code == 401


def test_nobody_can_unpair_another_users_device(hub: Hub) -> None:
    me, other = hub.pair("demo"), hub.pair("someone-else")
    r = hub.signed(me, "POST", "/device/unpair", {"device_id": other.device_id})
    assert r.status_code == 404
    assert hub.s.devices.get(other.device_id) is not None

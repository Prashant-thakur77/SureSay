"""Alexa+ account linking: OAuth 2.1 authorization code + PKCE (S256), to the Alexa+ MCP add-on requirements."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from .conftest import Hub

CLIENT = {"client_id": "alexa-plus-test", "client_secret": "s3cret", "redirect_uri": "https://alexa.example/callback"}


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


@pytest.fixture()
def linked(hub: Hub) -> Hub:
    hub.s.oauth.register_client(CLIENT["client_id"], CLIENT["client_secret"], [CLIENT["redirect_uri"]])
    return hub


def authorize(hub: Hub, challenge: str, *, code: str | None = None, **over: str) -> httpx.Response:
    params = {"response_type": "code", "client_id": CLIENT["client_id"], "redirect_uri": CLIENT["redirect_uri"],
              "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
              "resource": f"{hub.base}/mcp", **over}
    page = hub.http.get("/oauth/authorize", params=params)
    if code is None or page.status_code != 200:
        return page
    return hub.http.post("/oauth/authorize", data={**params, "pairing_code": code}, follow_redirects=False)


def link(hub: Hub) -> dict[str, Any]:
    verifier, challenge = pkce()
    r = authorize(hub, challenge, code=hub.s.devices.start_pairing("demo"))
    assert r.status_code == 302, r.text
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["state"] == ["xyz"]
    tok = hub.http.post("/oauth/token", data={"grant_type": "authorization_code", "code": q["code"][0],
                                              "redirect_uri": CLIENT["redirect_uri"], "client_id": CLIENT["client_id"],
                                              "client_secret": CLIENT["client_secret"], "code_verifier": verifier,
                                              "resource": f"{hub.base}/mcp"})
    assert tok.status_code == 200, tok.text
    return tok.json()


def mcp(hub: Hub, token: str | None, method: str, params: dict[str, Any]) -> httpx.Response:
    h = {"content-type": "application/json", "accept": "application/json, text/event-stream",
         "mcp-protocol-version": "2025-11-25"}
    if token:
        h["authorization"] = f"Bearer {token}"
    return hub.http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, headers=h)


def test_metadata_documents_follow_rfc_9728_and_8414(linked: Hub) -> None:
    prm = linked.http.get("/.well-known/oauth-protected-resource").json()
    assert prm["resource"].endswith("/mcp") and prm["authorization_servers"]
    assert prm["bearer_methods_supported"] == ["header"]
    assert linked.http.get("/.well-known/oauth-protected-resource/mcp").json() == prm
    meta = linked.http.get("/.well-known/oauth-authorization-server").json()
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert meta["authorization_endpoint"].endswith("/oauth/authorize")
    assert meta["token_endpoint"].endswith("/oauth/token")
    assert "authorization_code" in meta["grant_types_supported"]


def test_unauthenticated_mcp_gets_401_without_www_authenticate(linked: Hub) -> None:
    r = mcp(linked, None, "tools/list", {})
    assert r.status_code == 401
    assert "www-authenticate" not in {k.lower() for k in r.headers}


def test_linking_with_a_pairing_code_gives_a_token_that_acts_as_that_user(linked: Hub) -> None:
    tok = link(linked)
    assert tok["token_type"] == "Bearer" and tok["expires_in"] > 0 and tok["refresh_token"]
    tools = mcp(linked, tok["access_token"], "tools/list", {}).json()["result"]["tools"]
    assert any(t["name"] == "understand" for t in tools)
    out = mcp(linked, tok["access_token"], "tools/call", {"name": "home_set", "arguments": {"device": "fan", "on": True}})
    proposal = json.loads(out.json()["result"]["content"][0]["text"])
    assert proposal["status"] == "pending_user_confirmation"
    assert linked.s.gate.device_pending(linked.pair())[0]["pending_id"] == proposal["pending_id"]  # demo's own card
    refused = mcp(linked, tok["access_token"], "tools/call", {"name": "confirm", "arguments": {
        "pending_id": proposal["pending_id"], "evidence_ref": "the user said yes"}})
    assert json.loads(refused.json()["result"]["content"][0]["text"])["status"] == "refused"
    assert linked.s.home.status("demo")["devices"]["fan"]["on"] is False


def test_pkce_is_enforced(linked: Hub) -> None:
    verifier, challenge = pkce()
    r = authorize(linked, challenge, code=linked.s.devices.start_pairing("demo"))
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    bad = linked.http.post("/oauth/token", data={"grant_type": "authorization_code", "code": code,
                                                 "redirect_uri": CLIENT["redirect_uri"], "client_id": CLIENT["client_id"],
                                                 "client_secret": CLIENT["client_secret"], "code_verifier": "wrong"})
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_grant"


def test_an_authorization_code_works_once(linked: Hub) -> None:
    verifier, challenge = pkce()
    r = authorize(linked, challenge, code=linked.s.devices.start_pairing("demo"))
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": CLIENT["redirect_uri"],
            "client_id": CLIENT["client_id"], "client_secret": CLIENT["client_secret"], "code_verifier": verifier}
    assert linked.http.post("/oauth/token", data=data).status_code == 200
    assert linked.http.post("/oauth/token", data=data).status_code == 400


@pytest.mark.parametrize("over", [{"code_challenge_method": "plain"}, {"redirect_uri": "https://evil.example/cb"},
                                  {"client_id": "nobody"}, {"response_type": "token"}, {"resource": "https://other/mcp"}])
def test_bad_authorization_requests_are_rejected(linked: Hub, over: dict[str, str]) -> None:
    _, challenge = pkce()
    assert authorize(linked, challenge, **over).status_code == 400


def test_a_wrong_pairing_code_links_nothing(linked: Hub) -> None:
    _, challenge = pkce()
    r = authorize(linked, challenge, code="000000" if linked.s.devices.start_pairing("demo") != "000000" else "111111")
    assert r.status_code == 403 and re.search(r"code", r.text, re.I)


def test_refresh_rotates_and_revokes_the_old_token(linked: Hub) -> None:
    tok = link(linked)
    new = linked.http.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                                 "client_id": CLIENT["client_id"], "client_secret": CLIENT["client_secret"]})
    assert new.status_code == 200
    assert mcp(linked, new.json()["access_token"], "tools/list", {}).status_code == 200
    assert mcp(linked, tok["access_token"], "tools/list", {}).status_code == 401
    again = linked.http.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                                   "client_id": CLIENT["client_id"], "client_secret": CLIENT["client_secret"]})
    assert again.status_code == 400


def test_tokens_in_the_query_string_are_ignored(linked: Hub) -> None:
    tok = link(linked)
    r = linked.http.post(f"/mcp?access_token={tok['access_token']}", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                         headers={"accept": "application/json, text/event-stream", "content-type": "application/json"})
    assert r.status_code == 401

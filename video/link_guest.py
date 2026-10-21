"""Give a demo user the devices a real user would have: the Alexa skill as a voice device and an Alexa+ account link.

Both are made the real way, through the deployed hub: an operator pairing code (as `suresay.cli pair --transcriber
alexa` gives) exchanged at /device/pair, and the OAuth 2.1 code flow with PKCE at /oauth/authorize and /oauth/token,
for an OAuth client registered as "Alexa+". Used only to film the Your devices panel.
Usage: .venv/bin/python video/link_guest.py <user_id>
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
from urllib.parse import parse_qs, urlparse

import httpx
from confirm_gate import DeviceRegistry, DynamoStore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from suresay.oauth import OAuth  # noqa: E402

HUB = os.environ.get("HUB", "https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws")
CLIENT, REDIRECT = "alexa-plus-demo", "https://example.com/alexa/callback"


def main(user: str) -> None:
    store = DynamoStore("suresay-gate", region="us-east-1")
    devices = DeviceRegistry(store)
    http = httpx.Client(base_url=HUB, timeout=30)
    code = devices.start_pairing(user, transcriber="alexa")
    print("voice device:", http.post("/device/pair", json={"code": code, "name": "Alexa skill"}).status_code)

    OAuth(store, devices, public_url=HUB).register_client(CLIENT, None, [REDIRECT], name="Alexa+")
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = {"response_type": "code", "client_id": CLIENT, "redirect_uri": REDIRECT, "code_challenge": challenge,
              "code_challenge_method": "S256", "state": "film", "resource": f"{HUB}/mcp"}
    r = http.post("/oauth/authorize", data={**params, "pairing_code": devices.start_pairing(user)}, follow_redirects=False)
    got = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    tok = http.post("/oauth/token", data={"grant_type": "authorization_code", "code": got, "redirect_uri": REDIRECT,
                                          "client_id": CLIENT, "code_verifier": verifier})
    print("alexa+ link:", tok.status_code)


if __name__ == "__main__":
    main(sys.argv[1])

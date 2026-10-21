"""Account linking for Alexa+ (and any OAuth 2.1 MCP client), per the Alexa+ MCP add-on requirements.

* Protected Resource Metadata (RFC 9728) at ``/.well-known/oauth-protected-resource`` (and ``…/mcp``).
* Authorization server metadata (RFC 8414) at ``/.well-known/oauth-authorization-server``; PKCE ``S256`` only.
* Authorization code flow with PKCE; the ``resource`` parameter must name this server's MCP endpoint.
* Bearer tokens in the ``Authorization`` header only; unauthenticated MCP calls get a bare 401
  (no ``WWW-Authenticate``, which Alexa+ does not support yet).

Linking is SureSay pairing: the user enters the 6-digit code their SureSay screen shows. A linked client acts
*as that user* on ``/mcp`` with exactly the agent's powers: it can understand, read and propose, never confirm.
Secrets, codes and tokens are stored only as SHA-256 hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from confirm_gate import DeviceRegistry, PairingError, Store
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

SCOPES = ["suresay.home"]
CODE_TTL = 600
TOKEN_TTL = 3600
REFRESH_TTL = 60 * 86400


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def base_url(request: Request, configured: str = "") -> str:
    if configured:
        return configured.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


class OAuth:
    def __init__(self, store: Store, devices: DeviceRegistry, *, public_url: str = "",
                 clock: Any = time.time) -> None:
        self.store = store
        self.devices = devices
        self.public_url = public_url
        self.clock = clock

    # clients ------------------------------------------------------------------------
    def register_client(self, client_id: str, secret: str | None, redirect_uris: list[str]) -> None:
        self.store.put("oauth_client", client_id, {"secret_sha256": _h(secret) if secret else None,
                                                   "redirect_uris": list(redirect_uris)})

    def register_from_env(self, raw: str) -> None:
        """``SURESAY_OAUTH_CLIENTS='{"<client_id>": {"secret": "...", "redirect_uris": ["https://..."]}}'``."""
        for cid, cfg in (json.loads(raw) if raw else {}).items():
            self.register_client(cid, cfg.get("secret"), cfg.get("redirect_uris", []))

    def _client(self, client_id: str) -> dict[str, Any] | None:
        return self.store.get("oauth_client", client_id) if client_id else None

    def _client_ok(self, client_id: str, secret: str | None) -> bool:
        c = self._client(client_id)
        if c is None:
            return False
        if c.get("secret_sha256") is None:
            return True  # a public client: PKCE is its proof
        return bool(secret) and hmac.compare_digest(c["secret_sha256"], _h(secret or ""))

    # tokens ---------------------------------------------------------------------------
    def user_for(self, token: str) -> tuple[str, str] | None:
        """(user_id, client_id) for a live access token, else None."""
        doc = self.store.get("oauth_token", _h(token)) if token else None
        if doc is None or doc.get("revoked_at") is not None or doc["expires_at"] < self.clock():
            return None
        return doc["user_id"], doc["client_id"]

    def _issue(self, user_id: str, client_id: str, scope: str) -> dict[str, Any]:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = self.clock()
        self.store.put("oauth_token", _h(access), {"user_id": user_id, "client_id": client_id, "scope": scope,
                                                   "expires_at": now + TOKEN_TTL, "revoked_at": None,
                                                   "refresh_sha256": _h(refresh)})
        self.store.put("oauth_refresh", _h(refresh), {"user_id": user_id, "client_id": client_id, "scope": scope,
                                                      "expires_at": now + REFRESH_TTL, "used_at": None,
                                                      "access_sha256": _h(access)})
        return {"access_token": access, "token_type": "Bearer", "expires_in": TOKEN_TTL,
                "refresh_token": refresh, "scope": scope}

    # routes ---------------------------------------------------------------------------
    def routes(self) -> list[Route]:
        def metadata_prm(request: Request) -> JSONResponse:
            base = base_url(request, self.public_url)
            return JSONResponse({"resource": f"{base}/mcp", "authorization_servers": [base],
                                 "scopes_supported": SCOPES, "bearer_methods_supported": ["header"],
                                 "resource_name": "SureSay"})

        def metadata_as(request: Request) -> JSONResponse:
            base = base_url(request, self.public_url)
            return JSONResponse({"issuer": base, "authorization_endpoint": f"{base}/oauth/authorize",
                                 "token_endpoint": f"{base}/oauth/token", "response_types_supported": ["code"],
                                 "grant_types_supported": ["authorization_code", "refresh_token"],
                                 "code_challenge_methods_supported": ["S256"], "scopes_supported": SCOPES,
                                 "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic",
                                                                           "none"]})

        def check(request: Request, p: dict[str, str]) -> str | None:
            c = self._client(p.get("client_id", ""))
            if c is None:
                return "unknown client"
            if p.get("redirect_uri") not in c["redirect_uris"]:
                return "redirect_uri is not registered for this client"
            if p.get("response_type") != "code":
                return "response_type must be code"
            if p.get("code_challenge_method") != "S256" or not p.get("code_challenge"):
                return "PKCE with S256 is required"
            if p.get("resource") and p["resource"].rstrip("/") != f"{base_url(request, self.public_url)}/mcp":
                return "resource must be this server's MCP endpoint"
            return None

        def page(p: dict[str, str], error: str = "") -> str:
            hidden = "".join(f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
                             for k, v in p.items() if k != "pairing_code")
            err = f'<p role="alert" class="err">{html.escape(error)}</p>' if error else ""
            return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Link SureSay</title>
<style>body{{margin:0;background:#fbf8f3;color:#14213d;font:20px/1.5 system-ui,sans-serif}}
main{{max-width:520px;margin:10vh auto;padding:0 20px}}h1{{font-size:1.8rem}}
input[type=text]{{font:inherit;font-size:2rem;letter-spacing:.3em;width:8ch;padding:10px 14px;border:3px solid #14213d;border-radius:12px}}
button{{font:inherit;font-weight:700;min-height:60px;padding:0 28px;border-radius:12px;border:0;background:#14213d;color:#fbf8f3;margin-left:12px}}
:focus-visible{{outline:4px solid #9a4a00;outline-offset:3px}}.err{{color:#8a1c00;font-weight:700}}</style></head>
<body><main><h1>Link SureSay to your assistant</h1>
<p>Enter the 6-digit code shown on your SureSay screen. Your assistant will be able to suggest actions;
only you can confirm them, on your own device.</p>{err}
<form method="post" action="/oauth/authorize">{hidden}
<label for="pc">Pairing code</label><br><input id="pc" type="text" name="pairing_code" inputmode="numeric"
autocomplete="one-time-code" maxlength="6" required autofocus><button type="submit">Link</button></form></main></body></html>"""

        async def authorize(request: Request) -> Response:
            if request.method == "GET":
                p = dict(request.query_params)
                err = check(request, p)
                if err:
                    return JSONResponse({"error": "invalid_request", "error_description": err}, status_code=400)
                return HTMLResponse(page(p))
            form = dict(await request.form())
            p = {k: str(v) for k, v in form.items()}
            err = check(request, p)
            if err:
                return JSONResponse({"error": "invalid_request", "error_description": err}, status_code=400)
            try:
                device = self.devices.pair(p.get("pairing_code", ""), name=f"Linked: {p['client_id']}"[:60])
            except PairingError as exc:
                return HTMLResponse(page(p, f"That code didn't work ({exc}). Check the code on your SureSay screen."),
                                    status_code=403)
            code = secrets.token_urlsafe(32)
            self.store.put("oauth_code", _h(code), {
                "client_id": p["client_id"], "redirect_uri": p["redirect_uri"], "code_challenge": p["code_challenge"],
                "user_id": device.user_id, "scope": p.get("scope") or SCOPES[0], "expires_at": self.clock() + CODE_TTL,
                "used_at": None, "linked_device": device.device_id})
            self.devices.revoke(device.device_id)  # linking needs the code, not a device key: the client gets no key
            q = {"code": code, **({"state": p["state"]} if p.get("state") else {})}
            return RedirectResponse(f"{p['redirect_uri']}?{urlencode(q)}", status_code=302)

        async def token(request: Request) -> JSONResponse:
            form = {k: str(v) for k, v in (await request.form()).items()}
            client_id, secret = form.get("client_id", ""), form.get("client_secret")
            auth = request.headers.get("authorization", "")
            if auth.startswith("Basic "):
                try:
                    client_id, _, secret = base64.b64decode(auth[6:]).decode().partition(":")
                except Exception:
                    return JSONResponse({"error": "invalid_client"}, status_code=401)
            if not self._client_ok(client_id, secret):
                return JSONResponse({"error": "invalid_client"}, status_code=401)
            grant = form.get("grant_type")
            if grant == "authorization_code":
                key = _h(form.get("code", ""))
                doc = self.store.get("oauth_code", key)
                verifier = form.get("code_verifier", "")
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
                if (doc is None or doc["client_id"] != client_id or doc["redirect_uri"] != form.get("redirect_uri")
                        or doc["expires_at"] < self.clock() or not hmac.compare_digest(challenge, doc["code_challenge"])
                        or not self.store.set_once("oauth_code", key, "used_at", self.clock())):
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)
                return JSONResponse(self._issue(doc["user_id"], client_id, doc["scope"]),
                                    headers={"cache-control": "no-store"})
            if grant == "refresh_token":
                key = _h(form.get("refresh_token", ""))
                doc = self.store.get("oauth_refresh", key)
                if (doc is None or doc["client_id"] != client_id or doc["expires_at"] < self.clock()
                        or not self.store.set_once("oauth_refresh", key, "used_at", self.clock())):
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)
                self.store.set_once("oauth_token", doc["access_sha256"], "revoked_at", self.clock())
                return JSONResponse(self._issue(doc["user_id"], client_id, doc["scope"]),
                                    headers={"cache-control": "no-store"})
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

        return [
            Route("/.well-known/oauth-protected-resource", metadata_prm),
            Route("/.well-known/oauth-protected-resource/mcp", metadata_prm),
            Route("/.well-known/oauth-authorization-server", metadata_as),
            Route("/oauth/authorize", authorize, methods=["GET", "POST"]),
            Route("/oauth/token", token, methods=["POST"]),
        ]

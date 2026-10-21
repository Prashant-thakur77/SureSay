"""A real SureSay hub on a local port, a simulated user's device, and an adversarial agent.

Used by the safety suite and the latency script. Everything goes over real HTTP:
the agent through ``/mcp`` with the agent token, the user through the signed
device channel.
"""

from __future__ import annotations

import base64
import json
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from confirm_gate import MemoryStore, SqliteStore, sign_request
from confirm_gate.evidence import Device

from suresay import catalog, state
from suresay.app import SureSay
from suresay.asr import TextAsr
from suresay.config import Settings
from suresay.hub import build_app
from suresay.media import LocalMedia
from suresay.phrasebook import JsonPhrasebook
from suresay.rank import FuzzyRanker

AGENT_TOKEN = "eval-agent-token"


class NullSpeaker:
    voice = "none"

    def synth(self, text: str) -> bytes:
        return b""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def add_fixtures(products: list[dict[str, Any]], contacts: list[dict[str, str]]) -> None:
    """Extra poisoned records for the suite (in-process only; the demo data is untouched on disk)."""
    for p in products:
        if not any(x["id"] == p["id"] for x in state.PRODUCTS):
            state.PRODUCTS.append(p)
            catalog._PRODUCT_NAME[p["id"]] = p["name"]
    for c in contacts:
        if not any(x["id"] == c["id"] for x in state.CONTACTS):
            state.CONTACTS.append(c)
            catalog._CONTACT_NAME[c["id"]] = c["name"].split(".")[0].split(" (")[0]


class LiveHub:
    def __init__(self, tmp: Path, *, store: str = "memory", ranker: Any | None = None, asr: Any | None = None,
                 pending_ttl: float | None = None) -> None:
        cfg = replace(Settings(), backend="local", data_dir=tmp, agent_mode="direct", agent_token=AGENT_TOKEN,
                      default_user="demo", memory_id="", agent_runtime_arn="")
        st = MemoryStore() if store == "memory" else SqliteStore(tmp / "gate.db")
        self.s = SureSay(cfg, store=st, asr=asr or TextAsr(), ranker=ranker or FuzzyRanker(),
                         phrasebook=JsonPhrasebook(tmp / "pb", seed_users=("demo", "other")),
                         media=LocalMedia(tmp / "media"), speaker=NullSpeaker())  # type: ignore[arg-type]
        if pending_ttl is not None:
            self.s.gate.pending_ttl = pending_ttl
            self.s.gate.final_ttl = pending_ttl
            self.s.gate.evidence_ttl = pending_ttl
        self.app = build_app(self.s)
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="error", proxy_headers=False))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> LiveHub:
        self.thread.start()
        for _ in range(200):
            if self.server.started:
                break
            time.sleep(0.05)
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    # world state ---------------------------------------------------------------------
    def changes(self, user: str = "demo") -> list[dict[str, Any]]:
        return list(self.s.home.get(user)["changes"])


class UserDevice:
    """The user's own paired device. Answers card sets the way the user actually means."""

    def __init__(self, hub: LiveHub, user: str = "demo") -> None:
        self.hub = hub
        self.http = httpx.Client(base_url=hub.base, timeout=30)
        code = hub.s.devices.start_pairing(user)
        d = self.http.post("/device/pair", json={"code": code, "name": "user tablet"}).json()
        self.device = Device(d["device_id"], d["user_id"], d["key"], d["name"])
        self.last_request: dict[str, Any] | None = None

    def signed(self, method: str, path: str, payload: Any = None) -> httpx.Response:
        body = b"" if payload is None else json.dumps(payload).encode()
        ts = int(time.time())
        sep = "&" if "?" in path else "?"
        path = f"{path}{sep}r={time.perf_counter_ns()}"
        headers = {"x-device-id": self.device.device_id, "x-timestamp": str(ts),
                   "x-signature": sign_request(self.device.key, method, path, ts, body)}
        if body:
            headers["content-type"] = "application/json"
        self.last_request = {"method": method, "path": path, "body": body, "headers": dict(headers)}
        return self.http.request(method, path, content=body or None, headers=headers)

    def pending(self) -> list[dict[str, Any]]:
        return self.signed("GET", "/device/pending").json()["pending"]

    def tap(self, p: dict[str, Any], *, option: int | None = None, answer: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"pending_id": p["pending_id"], "nonce": p["nonce"], "kind": "tap"}
        if option is not None:
            payload["option"] = option
        if answer is not None:
            payload["answer"] = answer
        return self.signed("POST", "/device/evidence", payload).json()

    def voice(self, p: dict[str, Any], words: str) -> dict[str, Any]:
        return self.signed("POST", "/device/evidence", {"pending_id": p["pending_id"], "nonce": p["nonce"],
                                                         "kind": "voice",
                                                         "audio_b64": base64.b64encode(words.encode()).decode()}).json()

    def confirm(self, pending_id: str, evidence_ref: str) -> dict[str, Any]:
        return self.signed("POST", "/device/confirm", {"pending_id": pending_id, "evidence_ref": evidence_ref}).json()

    def answer_all(self, intent: tuple[str, dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Answer every open card set as the user would: pick the intent if shown, else say no."""
        outcomes = []
        for _ in range(4):  # a high-risk choice opens one more card set
            open_sets = self.pending()
            if not open_sets:
                break
            for p in open_sets:
                match = None
                if intent is not None:
                    match = next((o["n"] for o in p["options"]
                                  if o["action"] == intent[0] and o["args"] == intent[1]), None)
                if match is None:
                    ev = self.tap(p, answer="no")
                elif p["stage"] == "final":
                    ev = self.tap(p, answer="yes")
                else:
                    ev = self.tap(p, option=match)
                outcomes.append(self.confirm(p["pending_id"], ev["evidence_ref"]))
        return outcomes


VIA = {"mode": "agent"}  # "agent": the agent token; "linked": an OAuth-linked client, as Alexa+ would be


def linked_token(hub: LiveHub, user: str) -> str:
    """Link a client to *user* through the real OAuth flow (pairing code + PKCE), as Alexa+ account linking would."""
    import base64
    import hashlib
    import secrets
    from urllib.parse import parse_qs, urlparse

    cache = hub.__dict__.setdefault("_linked", {})
    if user in cache:
        return cache[user]
    cid, secret, redirect = "alexa-plus-eval", "eval-secret", "https://alexa.example/callback"
    hub.s.oauth.register_client(cid, secret, [redirect])
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    http = httpx.Client(base_url=hub.base, timeout=30)
    params = {"response_type": "code", "client_id": cid, "redirect_uri": redirect, "code_challenge": challenge,
              "code_challenge_method": "S256", "state": "s", "resource": f"{hub.base}/mcp",
              "pairing_code": hub.s.devices.start_pairing(user)}
    r = http.post("/oauth/authorize", data=params, follow_redirects=False)
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    tok = http.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
                                           "client_id": cid, "client_secret": secret, "code_verifier": verifier}).json()
    cache[user] = tok["access_token"]
    return cache[user]


class Adversary:
    """An MCP client with every tool that does whatever an injection asks: the agent, or an OAuth-linked client."""

    def __init__(self, hub: LiveHub, user: str = "demo") -> None:
        from strands.tools.mcp import MCPClient

        if VIA["mode"] == "linked":
            headers = {"Authorization": f"Bearer {linked_token(hub, user)}"}
        else:
            headers = {"Authorization": f"Bearer {AGENT_TOKEN}", "X-SureSay-User": user}
        self.client = MCPClient(url=f"{hub.base}/mcp", headers=headers)
        self.http = httpx.Client(base_url=hub.base, timeout=30)

    def __enter__(self) -> Adversary:
        self.client.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.client.__exit__(*exc)

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        r = self.client.call_tool_sync(tool_use_id="adv", name=name, arguments=args)
        text = r["content"][0]["text"] if r.get("content") else "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text, "status": r.get("status")}

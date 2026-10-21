"""The SureSay hub: one HTTP app that serves

* ``/mcp``       — the MCP server (Streamable HTTP, stateless, JSON responses). Callers are either the
                   agent (``Authorization: Bearer <agent token>``) or a paired device (signed request).
* ``/device/*``  — the device channel: pairing, card sets *with nonces*, evidence, turns, read-back.
                   Signed by the device key. The agent has no device key.
* ``/``          — the built web client (``web/dist``), when present.

Run: ``python -m suresay.hub`` (or ``suresay-hub``). Prints a pairing code for the default user.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any

import anyio
import httpx
from confirm_gate import AuthError, device_routes
from confirm_gate.device import authenticate
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .app import SureSay, current_caller, current_user
from .config import ROOT
from .net import client_ip
from .understand import understand

logger = logging.getLogger("suresay.hub")

# Evidence audio is transcribed WITHOUT vocabulary biasing. Chosen on dev speakers only
# (eval/tune_confirm.py): biasing toward "yes/one/haan..." recovered every genuine answer but also pulled
# ordinary words toward them, and the rule ranks false accepts first. See eval/REPORT.md.
EVIDENCE_WORDS: list[str] = []
# Public demo limits. Each is an atomic counter in the store, so every Lambda instance shares it.
GUEST_VOICE_PER_DAY = 60  # per demo home: speech recognition is paid per request
GUEST_SPEAK_PER_DAY = 60  # per demo home: read-aloud is paid per character
GUEST_SPEAK_CHARS = 240
GUEST_TURNS_PER_DAY = 300  # per demo home: typed turns (they reach the model in agent mode)
DEMO_VOICE_PER_DAY = 250  # all demo homes together: the spend ceiling for a day of public traffic
DEMO_SPEAK_PER_DAY = 400
DEMO_TURNS_PER_DAY = 4000
DEMO_GUESTS_PER_DAY = 500
TRY_PER_HOUR = 20  # new demo homes per source address
TRY_PER_DAY = 60
# One address's share of the day (across all the demo homes it made), well below the whole demo's ceilings.
ADDRESS_VOICE_PER_DAY = 80
ADDRESS_SPEAK_PER_DAY = 100
ADDRESS_TURNS_PER_DAY = 600
MAX_AUDIO_BYTES = 2_000_000  # about a minute of 16 kHz mono speech: far more than any turn or answer
MAX_BODY_BYTES = 4_000_000


class BodyLimit:
    """Refuse oversized request bodies with 413 before reading them into memory."""

    def __init__(self, app: ASGIApp, limit: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.limit:
            await JSONResponse({"error": "request body too large"}, status_code=413)(scope, receive, send)
            return
        seen = 0
        started = False

        async def limited() -> Message:
            nonlocal seen
            msg = await receive()
            seen += len(msg.get("body", b""))
            if seen > self.limit:
                raise _TooLarge
            return msg

        async def tracked(msg: Message) -> None:
            nonlocal started
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        try:
            await self.app(scope, limited, tracked)
        except _TooLarge:  # a chunked body with no content-length went over the limit while being read
            if not started:
                await JSONResponse({"error": "request body too large"}, status_code=413)(scope, receive, send)


class _TooLarge(Exception):
    pass


class McpAuth:
    """Only the agent (bearer token) or a paired device (signature) may call ``/mcp``."""

    def __init__(self, app: ASGIApp, suresay: SureSay) -> None:
        self.app = app
        self.s = suresay

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/mcp") or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        auth = headers.get("authorization", "")
        user: str | None = None
        caller = ""
        body = b""
        replay = False
        bearer = auth[7:].strip() if auth.startswith("Bearer ") else ""
        linked = self.s.oauth.user_for(bearer) if bearer else None
        if bearer and hmac.compare_digest(bearer, self.s.cfg.agent_token):
            user = headers.get("x-suresay-user") or self.s.cfg.default_user
            caller = "agent"
        elif linked is not None:
            user, caller = linked[0], f"linked:{linked[1]}"  # e.g. Alexa+ after account linking: agent powers only
        elif "x-signature" in headers:
            chunks = []
            more = True
            while more:
                msg = await receive()
                chunks.append(msg.get("body", b""))
                more = msg.get("more_body", False)
            body = b"".join(chunks)
            replay = True
            qs = scope.get("query_string", b"").decode()
            path = scope["path"] + (f"?{qs}" if qs else "")
            try:
                device = self.s.devices.authenticate(headers, scope["method"], path, body)
                user, caller = device.user_id, f"device:{device.device_id}"
            except AuthError as exc:
                await JSONResponse({"error": f"device auth failed: {exc}"}, status_code=401)(scope, receive, send)
                return
        if user is None:
            await JSONResponse({"error": "MCP needs the agent token or a paired device"},
                               status_code=401)(scope, receive, send)
            return

        sent = False

        async def replay_receive() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        tu, tc = current_user.set(user), current_caller.set(caller)
        try:
            await self.app(scope, replay_receive if replay else receive, send)
        finally:
            current_user.reset(tu)
            current_caller.reset(tc)


class DeviceCallerTag:
    """Requests on /device/* come from a user's device: tag the caller kind for events and metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/device/"):
            token = current_caller.set("device")
            try:
                await self.app(scope, receive, send)
            finally:
                current_caller.reset(token)
            return
        await self.app(scope, receive, send)


def _signed(handler: Any, s: SureSay) -> Any:
    async def wrapped(request: Request) -> Response:
        try:
            device, body = await authenticate(request, s.devices)
        except AuthError as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return JSONResponse({"error": "body is not JSON"}, status_code=400)
        tu, tc = current_user.set(device.user_id), current_caller.set(f"device:{device.device_id}")
        try:
            return await handler(request, device, data if isinstance(data, dict) else {})
        finally:
            current_user.reset(tu)
            current_caller.reset(tc)

    return wrapped


class AgentBridge:
    """Hands a turn to the Strands agent: AgentCore Runtime, a local agent server, or nobody (direct)."""

    BREAK_SECONDS = 300.0

    def __init__(self, s: SureSay) -> None:
        self.s = s
        self._mode: str | None = None
        self._down_until = 0.0
        self._checked_at = 0.0

    def trip(self) -> None:
        """The agent failed (e.g. no model quota): answer directly for a while instead of waiting on it each turn.

        Shared through the store, so every hub instance (each Lambda container) skips the broken agent at once.
        """
        self._down_until = time.time() + self.BREAK_SECONDS
        try:
            self.s.store.put("agent_health", "agent", {"down_until": self._down_until})
        except Exception:
            logger.exception("could not share the agent breaker")

    SERVICE_ERRORS = {"ThrottlingException", "ServiceQuotaExceededException", "ServiceUnavailableException",
                      "InternalServerException", "AccessDeniedException", "ResourceNotFoundException",
                      "ModelNotReadyException", "ModelTimeoutException"}

    def failed(self, user_id: str, exc: BaseException) -> bool:
        """An agent turn failed. Trip the shared breaker only when the agent itself is in trouble, never on a
        guest's turn (anyone can make one), at once for a service error, else after two failures in a minute.
        Returns whether it tripped."""
        if user_id.startswith("guest-"):
            return False
        resp = getattr(exc, "response", None)
        code = str(((resp.get("Error") or {}).get("Code")) or "") if isinstance(resp, dict) else ""  # botocore
        status = resp.status_code if isinstance(exc, httpx.HTTPStatusError) else 0  # a local agent over HTTP
        if code in self.SERVICE_ERRORS or status >= 500:
            self.trip()
            return True
        minute = int(time.time() // 60)
        if self.s.store.add("quota", f"agent_fail:{minute}", 1, expires_at=float((minute + 1) * 60)) >= 2:
            self.trip()
            return True
        return False

    def _shared_down(self) -> bool:
        now = time.time()
        if now - self._checked_at > 10:
            self._checked_at = now
            try:
                doc = self.s.store.get("agent_health", "agent") or {}
                self._down_until = max(self._down_until, float(doc.get("down_until", 0)))
            except Exception:
                pass
        return self._down_until > now

    def mode(self) -> str:
        if self._shared_down():
            return "direct"
        if self._mode is None:
            want = self.s.cfg.agent_mode
            if want in ("agent", "direct"):
                self._mode = want
            elif self.s.cfg.agent_runtime_arn:
                self._mode = "agent"
            else:
                try:
                    httpx.get(self.s.cfg.agent_url.rsplit("/", 1)[0] + "/ping", timeout=1.0).raise_for_status()
                    self._mode = "agent"
                except Exception:
                    self._mode = "direct"
            logger.info("turn mode: %s", self._mode)
        return self._mode

    def prompt(self, user_id: str, text: str | None, audio_ref: str | None) -> str:
        if audio_ref:
            return f"The user (user_id={user_id}) just spoke. audio_ref={audio_ref}"
        return f"The user (user_id={user_id}) typed: {text}"

    async def run(self, user_id: str, session_id: str, text: str | None, audio_ref: str | None) -> str:
        payload = {"prompt": self.prompt(user_id, text, audio_ref), "user_id": user_id, "session_id": session_id}
        if self.s.cfg.agent_runtime_arn:
            return await anyio.to_thread.run_sync(self._invoke_runtime, payload, session_id)
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.post(self.s.cfg.agent_url, json=payload)
            r.raise_for_status()
            data = r.json()
        return str(data.get("response") or data.get("result") or data)

    def _invoke_runtime(self, payload: dict[str, Any], session_id: str) -> str:
        import boto3
        from botocore.config import Config

        client = boto3.client("bedrock-agentcore", region_name=self.s.cfg.region,
                              config=Config(read_timeout=6, connect_timeout=2, retries={"max_attempts": 1}))
        resp = client.invoke_agent_runtime(agentRuntimeArn=self.s.cfg.agent_runtime_arn,
                                           runtimeSessionId=(session_id + "-" + "0" * 40)[:40],
                                           payload=json.dumps(payload).encode())
        body = resp["response"].read() if hasattr(resp.get("response"), "read") else resp.get("response")
        try:
            data = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return body.decode() if isinstance(body, bytes) else str(body)
        return str(data.get("response") or data.get("result") or data)


PRIVACY = [
    "SureSay stores what it needs to act for you and to prove you agreed: your phrasebook, your home's simulated "
    "state, the card sets it offered, your confirmations (taps, or the audio of your spoken answer and its "
    "transcript), and a consent receipt for each action.",
    "Audio is stored privately, encrypted, and deleted after 30 days. Receipts keep a fingerprint of the audio, not "
    "the audio itself, after that.",
    "Speech is recognised with Amazon Transcribe and read aloud with Amazon Polly; ranking may use Amazon Bedrock. "
    "Nothing is sold or shared with third parties.",
    "To delete your data, unpair your devices and ask the operator to remove your user record.",
]
TERMS = [
    "SureSay is a research prototype built for a hackathon. Devices, contacts and the shop are simulated.",
    "SureSay never acts without your own confirmation, but you remain responsible for what you confirm.",
    "Do not rely on SureSay for emergencies; call your local emergency number.",
]


def _doc_page(title: str, paras: list[str]) -> str:
    body = "".join(f"<p>{p}</p>" for p in paras)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1"><title>SureSay {title}</title><style>body{{margin:0;'
            f'background:#fbf8f3;color:#14213d;font:19px/1.6 system-ui,sans-serif}}main{{max-width:680px;margin:6vh auto;'
            f'padding:0 20px}}</style></head><body><main><h1>SureSay: {title}</h1>{body}</main></body></html>')


class Quota:
    """Fixed-window counters in the store: ``take`` is one atomic increment (DynamoDB ``ADD``)."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def take(self, name: str, key: str, limit: int, window: int = 86400) -> bool:
        w = int(time.time() // window)
        return self.store.add("quota", f"{name}:{key}:{w}", 1, expires_at=float((w + 1) * window)) <= limit


DEMO_FULL = "the public demo has reached today's limit; please try again tomorrow"


def build_app(s: SureSay | None = None) -> Starlette:
    s = s or SureSay()
    bridge = AgentBridge(s)
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = s.mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)

    evidence_asr: list[Any] = []

    def evidence_transcribe(audio: bytes) -> str:
        """The user's confirmation audio, transcribed by the server. Hindi speakers: SURESAY_EVIDENCE_LANGUAGE=hi-IN,
        which writes Hindi in Devanagari and English words transliterated; both are mapped by the consent parser."""
        if not evidence_asr:
            from . import asr as asrmod

            lang = s.cfg.evidence_language
            if lang != "en-US" and s.asr.name.startswith("transcribe"):
                evidence_asr.append(asrmod.TranscribeStreamingAsr(region=s.cfg.region, language=lang))
            elif s.cfg.evidence_asr == "nova-sonic":  # as safe as Transcribe on answers (REPORT.md), a third the cost
                evidence_asr.append(asrmod.NovaSonicAsr(region=s.cfg.region))
            else:
                evidence_asr.append(s.asr)
        return evidence_asr[0].transcribe(audio, vocabulary=EVIDENCE_WORDS or None).text

    quota = Quota(s.store)

    def guest_take(user_id: str, kind: str) -> str | None:
        """None if a demo home may do one more *kind* ("voice", "speak", "turn") today, else why not."""
        if not user_id.startswith("guest-"):
            return None
        per_guest = {"voice": GUEST_VOICE_PER_DAY, "speak": GUEST_SPEAK_PER_DAY, "turn": GUEST_TURNS_PER_DAY}[kind]
        overall = {"voice": DEMO_VOICE_PER_DAY, "speak": DEMO_SPEAK_PER_DAY, "turn": DEMO_TURNS_PER_DAY}[kind]
        if not quota.take(f"guest_{kind}", user_id, per_guest):
            return {"voice": "this demo home has used today's voice; please tap or type instead",
                    "speak": "this demo home has used today's read-aloud",
                    "turn": "this demo home has used today's turns"}[kind]
        address = guest_address(user_id)
        per_address = {"voice": ADDRESS_VOICE_PER_DAY, "speak": ADDRESS_SPEAK_PER_DAY, "turn": ADDRESS_TURNS_PER_DAY}[kind]
        if address and not quota.take(f"address_{kind}", address, per_address):
            return "the demo has had a lot of use from your network today; please try again tomorrow"
        if not quota.take(f"demo_{kind}", "all", overall):
            return DEMO_FULL
        return None

    addresses: dict[str, str] = {}

    def guest_address(user_id: str) -> str:
        """The address that made this demo home (recorded at /device/try), so every quota also charges it."""
        if user_id not in addresses:
            addresses[user_id] = str((s.store.get("guest", user_id) or {}).get("address") or "")
        return addresses[user_id]

    def guest_voice_ok(user_id: str) -> bool:
        return guest_take(user_id, "voice") is None

    def evidence_sink(audio: bytes, device: Any, pending_id: str) -> str:
        if not guest_voice_ok(device.user_id):
            raise ValueError("this demo home has used today's voice answers; please tap instead")
        return s.media.put("evidence", audio)

    routes: list[Any] = device_routes(
        s.gate, s.devices, transcribe=evidence_transcribe, transcriber=None,
        media_sink=evidence_sink, max_audio_bytes=MAX_AUDIO_BYTES, client_ip=client_ip,
    )

    async def turn(request: Request, device: Any, data: dict[str, Any]) -> Response:
        """One user turn from the device: typed text or recorded audio."""
        text = str(data.get("text") or "").strip()[:500] or None
        audio_ref = None
        audio = b""
        if len(str(data.get("audio_b64") or "")) > (MAX_AUDIO_BYTES * 4) // 3 + 4:
            return JSONResponse({"error": "audio is too long"}, status_code=413)
        if data.get("audio_b64"):
            try:
                audio = base64.b64decode(str(data["audio_b64"]), validate=True)
            except ValueError:  # binascii.Error, and non-ASCII input
                return JSONResponse({"error": "audio_b64 is not base64"}, status_code=400)
        if not text and not audio:
            return JSONResponse({"error": "say or type something"}, status_code=400)
        why = await anyio.to_thread.run_sync(guest_take, device.user_id, "voice" if audio else "turn")
        if why:
            return JSONResponse({"error": why}, status_code=429)
        if audio:
            audio_ref = await anyio.to_thread.run_sync(lambda: s.media.put("utterance", audio))
        # The agent session belongs to this device: a client may name a conversation, never join another device's.
        session_id = f"{device.device_id}-{str(data.get('session_id') or 'main')[:24]}"
        t0 = time.perf_counter()
        mode = await anyio.to_thread.run_sync(bridge.mode)
        result: dict[str, Any] | None = None
        reply = ""
        if mode == "agent":
            try:
                reply = await bridge.run(device.user_id, session_id, text, audio_ref)
            except Exception as exc:
                tripped = await anyio.to_thread.run_sync(bridge.failed, device.user_id, exc)
                logger.warning("agent turn failed (%s), answering directly%s", exc,
                               f" for {bridge.BREAK_SECONDS:.0f}s" if tripped else "")
                mode = "direct"
        if mode == "direct":
            result = await anyio.to_thread.run_sync(
                lambda: understand(s, device.user_id, transcript=text, audio_ref=audio_ref))
            reply = result["say"]
        pending = await anyio.to_thread.run_sync(s.gate.device_pending, device)
        new_id = (result or {}).get("pending_id")
        if new_id and all(p["pending_id"] != new_id for p in pending):  # an index may lag a fresh write
            fresh = await anyio.to_thread.run_sync(s.gate.device_view, device, new_id)
            if fresh:
                pending.append(fresh)
        return JSONResponse({"reply": reply, "mode": mode, "result": result, "pending": pending,
                             "ms": round((time.perf_counter() - t0) * 1000)})

    async def speak(request: Request, device: Any, data: dict[str, Any]) -> Response:
        text = str(data.get("text") or "")
        if device.user_id.startswith("guest-"):
            text = " ".join(text.split())[:GUEST_SPEAK_CHARS]
            why = await anyio.to_thread.run_sync(guest_take, device.user_id, "speak")
            if why:
                return JSONResponse({"error": why}, status_code=429)
        try:
            audio = await anyio.to_thread.run_sync(s.speaker.synth, text)
        except Exception as exc:
            return JSONResponse({"error": f"read-back unavailable: {exc}"}, status_code=503)
        return JSONResponse({"audio_b64": base64.b64encode(audio).decode(), "format": "mp3",
                             "voice": s.speaker.voice})

    async def state(request: Request, device: Any, data: dict[str, Any]) -> Response:
        def collect() -> dict[str, Any]:
            u = device.user_id
            events = s.store.scan("event", user_id=u)
            stats = {"confirmed": sum(e["type"] == "done" for e in events),
                     "refused": sum(e["type"] == "refused" for e in events),
                     "refused_from_assistant": sum(e["type"] == "refused" and e.get("caller") == "agent" for e in events),
                     "cancelled": sum(e["type"] == "cancelled" for e in events),
                     "without_you": 0}  # by construction: every change has a receipt from the user's device
            return {"user_id": u, "stats": stats, "home": s.home.status(u), "cart": s.home.cart(u),
                    "receipts": s.gate.receipts(u, limit=10), "events": s.recent_events(u),
                    "phrasebook": s.phrasebook.list(u), "pending": s.gate.device_pending(device),
                    "spoken": [r["result"]["say"] for r in s.gate.receipts(u, limit=10)
                               if r["what"]["action"] == "say_for_me" and isinstance(r.get("result"), dict)][:1]}

        return JSONResponse(await anyio.to_thread.run_sync(collect))

    async def propose(request: Request, device: Any, data: dict[str, Any]) -> Response:
        """The user tapped something (a speak-for-me tile, a taught phrase): open a card set for it.

        It still needs the user's confirmation like any other card; this only skips speech recognition.
        """
        from . import catalog

        action = str(data.get("action") or "")
        args = catalog.validate(action, data.get("args")) if action in catalog.WRITE_ACTIONS else None
        if args is None:
            return JSONResponse({"error": "not an action SureSay can propose"}, status_code=400)

        def go() -> dict[str, Any] | None:
            ps = s.gate.propose(device.user_id, [(action, args)], origin="user_words",
                                context={"heard": "", "source": "tapped on device"})
            return s.gate.device_view(device, ps.pending_id)

        return JSONResponse({"pending": await anyio.to_thread.run_sync(go)})

    async def doorbell(request: Request, device: Any, data: dict[str, Any]) -> Response:
        """A doorbell press (simulated: no doorbell account here). The door's cards still need the user's yes."""
        from .state import VISITORS

        visitor = VISITORS.get(str(data.get("visitor") or ""))
        if visitor is None:
            return JSONResponse({"error": f"visitor must be one of {sorted(VISITORS)}"}, status_code=400)

        def go() -> dict[str, Any] | None:
            info = {k: visitor[k] for k in ("id", "name", "who", "note")}
            s.store.put("doorbell_event", f"{time.time():.6f}", {"user_id": device.user_id, **info, "at": time.time()})
            ps = s.gate.propose(device.user_id, list(visitor["options"]), origin="doorbell",  # type: ignore[arg-type]
                                context={"heard": "", "visitor": info, "source": "doorbell (simulated)"})
            return s.gate.device_view(device, ps.pending_id)

        pending = await anyio.to_thread.run_sync(go)
        return JSONResponse({"pending": pending, "say": f"Someone's at the door. {visitor['note']}"})

    async def reset(request: Request, device: Any, data: dict[str, Any]) -> Response:
        await anyio.to_thread.run_sync(s.home.reset, device.user_id)
        closed = await anyio.to_thread.run_sync(lambda: s.gate.withdraw_open(device.user_id, reason="reset"))
        return JSONResponse({"ok": True, "withdrawn": closed})

    async def devices(request: Request, device: Any, data: dict[str, Any]) -> Response:
        """The user's own active devices and assistant links (never a key), so they can see and end any of them."""
        def collect() -> list[dict[str, Any]]:
            out = []
            for d in s.store.scan("device", user_id=device.user_id):
                if d.get("revoked_at") is not None:
                    continue
                name = str(d.get("name") or "")
                kind = "link" if name.startswith("Linked:") else "voice" if d.get("transcriber") else "screen"
                out.append({"device_id": d["device_id"], "name": name, "kind": kind, "paired_at": d.get("paired_at"),
                            "this_device": d["device_id"] == device.device_id})
            return sorted(out, key=lambda d: d.get("paired_at") or 0)

        return JSONResponse({"devices": await anyio.to_thread.run_sync(collect)})

    async def unpair(request: Request, device: Any, data: dict[str, Any]) -> Response:
        """Unpair one of the user's own devices. For an assistant link, that ends the link and all its tokens."""
        target = s.devices.get(str(data.get("device_id") or ""))
        if target is None or target.user_id != device.user_id:
            return JSONResponse({"error": "no such device"}, status_code=404)
        await anyio.to_thread.run_sync(s.devices.revoke, target.device_id)
        return JSONResponse({"ok": True})

    routes += [
        Route("/device/devices", _signed(devices, s), methods=["GET"]),
        Route("/device/unpair", _signed(unpair, s), methods=["POST"]),
        Route("/device/turn", _signed(turn, s), methods=["POST"]),
        Route("/device/speak", _signed(speak, s), methods=["POST"]),
        Route("/device/state", _signed(state, s), methods=["GET"]),
        Route("/device/reset", _signed(reset, s), methods=["POST"]),
        Route("/device/propose", _signed(propose, s), methods=["POST"]),
        Route("/device/doorbell", _signed(doorbell, s), methods=["POST"]),
    ]

    async def try_demo(request: Request) -> Response:
        """Public demo (SURESAY_PUBLIC_DEMO=1): a private sandbox home per visitor, with its own device at once.

        Same gate, same rules; a guest can only ever touch their own simulated home. The device is issued directly
        (no pairing code exists for a guest), new homes are limited per source address and per day.
        """
        if not s.cfg.public_demo:
            return JSONResponse({"error": "not found"}, status_code=404)

        def go() -> tuple[int, dict[str, Any]]:
            address = client_ip(request)
            if not quota.take("try", address, TRY_PER_HOUR, window=3600) or not quota.take("try_day", address, TRY_PER_DAY):
                return 429, {"error": "too many demo homes from here; try again later"}
            if not quota.take("demo_guest", "all", DEMO_GUESTS_PER_DAY):
                return 429, {"error": DEMO_FULL}
            user = "guest-" + uuid.uuid4().hex[:10]
            device = s.devices.issue(user, name="Demo visitor")
            s.store.put("guest", user, {"address": address, "expires_at": time.time() + 2 * 86400})
            s.home.reset(user)
            return 200, {"device_id": device.device_id, "user_id": device.user_id, "key": device.key,
                         "name": device.name, "demo": True}

        code, body = await anyio.to_thread.run_sync(go)
        return JSONResponse(body, status_code=code)

    async def healthz(request: Request) -> Response:
        return JSONResponse({"ok": True})

    async def info(request: Request) -> Response:
        return JSONResponse({"name": "suresay", "mcp": "/mcp", "transport": "streamable-http", "public_demo": s.cfg.public_demo,
                             "protocol_versions": ["2025-11-25", "2026-07-28"], "backend": s.cfg.backend,
                             "turn_mode": bridge._mode or "not yet decided"})

    async def privacy(request: Request) -> Response:
        return HTMLResponse(_doc_page("Privacy", PRIVACY))

    async def terms(request: Request) -> Response:
        return HTMLResponse(_doc_page("Terms of use", TERMS))

    routes += [Route("/healthz", healthz), Route("/api/info", info), Route("/privacy", privacy), Route("/terms", terms),
               Route("/device/try", try_demo, methods=["POST"])]
    brand = ROOT / "alexa_plus" / "assets"
    if brand.exists():
        routes.append(Mount("/brand", app=StaticFiles(directory=brand), name="brand"))
    routes += s.oauth.routes()
    dist = ROOT / "web" / "dist"
    if dist.exists():
        routes.append(Mount("/", app=StaticFiles(directory=dist, html=True), name="web"))
    app.router.routes.extend(routes)
    app.add_middleware(McpAuth, suresay=s)
    app.add_middleware(DeviceCallerTag)
    app.add_middleware(BodyLimit)
    # Device and MCP auth are header signatures/tokens, never cookies, so "*" is safe when a screen app needs it.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"] if "*" in s.cfg.allowed_origins else list(s.cfg.allowed_origins), allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["content-type", "authorization", "x-device-id", "x-timestamp", "x-signature",
                       "mcp-session-id", "mcp-protocol-version", "last-event-id"],
        expose_headers=["mcp-session-id", "mcp-protocol-version"],
    )
    app.state.suresay = s
    app.state.bridge = bridge
    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = SureSay()
    app = build_app(s)
    code = s.devices.start_pairing(s.cfg.default_user)
    (s.cfg.data_dir / "pairing_code").write_text(code)
    port = int(os.environ.get("PORT", "9000"))
    print(f"\n  SureSay hub on http://127.0.0.1:{port}  (MCP at /mcp)\n"
          f"  Pairing code for user '{s.cfg.default_user}': {code}   (valid 10 minutes)\n", flush=True)
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=port, log_level="info", proxy_headers=False)


if __name__ == "__main__":
    main()

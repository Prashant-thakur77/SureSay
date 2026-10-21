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
import binascii
import hmac
import json
import logging
import os
import time
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
from .understand import understand

logger = logging.getLogger("suresay.hub")

# Evidence audio is transcribed WITHOUT vocabulary biasing. Chosen on dev speakers only
# (eval/tune_confirm.py): biasing toward "yes/one/haan..." recovered every genuine answer but also pulled
# ordinary words toward them, and the rule ranks false accepts first. See eval/REPORT.md.
EVIDENCE_WORDS: list[str] = []


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

    def __init__(self, s: SureSay) -> None:
        self.s = s
        self._mode: str | None = None

    def mode(self) -> str:
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
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(self.s.cfg.agent_url, json=payload)
            r.raise_for_status()
            data = r.json()
        return str(data.get("response") or data.get("result") or data)

    def _invoke_runtime(self, payload: dict[str, Any], session_id: str) -> str:
        import boto3

        client = boto3.client("bedrock-agentcore", region_name=self.s.cfg.region)
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
            from .asr import TranscribeStreamingAsr

            lang = s.cfg.evidence_language
            evidence_asr.append(TranscribeStreamingAsr(region=s.cfg.region, language=lang)
                                if lang != "en-US" and s.asr.name.startswith("transcribe") else s.asr)
        return evidence_asr[0].transcribe(audio, vocabulary=EVIDENCE_WORDS or None).text

    routes: list[Any] = device_routes(
        s.gate, s.devices, transcribe=evidence_transcribe, transcriber=None,
        media_sink=lambda audio, device, pid: s.media.put("evidence", audio),
    )

    async def turn(request: Request, device: Any, data: dict[str, Any]) -> Response:
        """One user turn from the device: typed text or recorded audio."""
        text = str(data.get("text") or "").strip()[:500] or None
        audio_ref = None
        if data.get("audio_b64"):
            try:
                audio = base64.b64decode(str(data["audio_b64"]), validate=True)
            except binascii.Error:
                return JSONResponse({"error": "audio_b64 is not base64"}, status_code=400)
            audio_ref = await anyio.to_thread.run_sync(lambda: s.media.put("utterance", audio))
        if not text and not audio_ref:
            return JSONResponse({"error": "say or type something"}, status_code=400)
        session_id = str(data.get("session_id") or device.device_id)[:64]
        t0 = time.perf_counter()
        mode = await anyio.to_thread.run_sync(bridge.mode)
        result: dict[str, Any] | None = None
        reply = ""
        if mode == "agent":
            try:
                reply = await bridge.run(device.user_id, session_id, text, audio_ref)
            except Exception as exc:
                logger.warning("agent turn failed, answering directly: %s", exc)
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
        try:
            audio = await anyio.to_thread.run_sync(s.speaker.synth, text)
        except Exception as exc:
            return JSONResponse({"error": f"read-back unavailable: {exc}"}, status_code=503)
        return JSONResponse({"audio_b64": base64.b64encode(audio).decode(), "format": "mp3",
                             "voice": s.speaker.voice})

    async def state(request: Request, device: Any, data: dict[str, Any]) -> Response:
        def collect() -> dict[str, Any]:
            u = device.user_id
            events = [e for e in s.store.scan("event") if e.get("user_id") == u]
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

    routes += [
        Route("/device/turn", _signed(turn, s), methods=["POST"]),
        Route("/device/speak", _signed(speak, s), methods=["POST"]),
        Route("/device/state", _signed(state, s), methods=["GET"]),
        Route("/device/reset", _signed(reset, s), methods=["POST"]),
        Route("/device/propose", _signed(propose, s), methods=["POST"]),
        Route("/device/doorbell", _signed(doorbell, s), methods=["POST"]),
    ]

    async def healthz(request: Request) -> Response:
        return JSONResponse({"ok": True})

    async def info(request: Request) -> Response:
        return JSONResponse({"name": "suresay", "mcp": "/mcp", "transport": "streamable-http",
                             "protocol_versions": ["2025-11-25", "2026-07-28"], "backend": s.cfg.backend,
                             "turn_mode": bridge._mode or "not yet decided"})

    async def privacy(request: Request) -> Response:
        return HTMLResponse(_doc_page("Privacy", PRIVACY))

    async def terms(request: Request) -> Response:
        return HTMLResponse(_doc_page("Terms of use", TERMS))

    routes += [Route("/healthz", healthz), Route("/api/info", info), Route("/privacy", privacy), Route("/terms", terms)]
    brand = ROOT / "alexa_plus" / "assets"
    if brand.exists():
        routes.append(Mount("/brand", app=StaticFiles(directory=brand), name="brand"))
    routes += s.oauth.routes()
    dist = ROOT / "web" / "dist"
    if dist.exists():
        routes.append(Mount("/", app=StaticFiles(directory=dist, html=True), name="web"))
    app.router.routes.extend(routes)
    app.add_middleware(McpAuth, suresay=s)
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
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=port, log_level="info")


if __name__ == "__main__":
    main()

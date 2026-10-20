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
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .app import SureSay, current_caller, current_user
from .config import ROOT
from .understand import CONFIRM_WORDS, understand

logger = logging.getLogger("suresay.hub")

EVIDENCE_WORDS = CONFIRM_WORDS + ["number", "first", "second", "third", "none", "doosra", "pehla", "teesra"]


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
        if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), self.s.cfg.agent_token):
            user = headers.get("x-suresay-user") or self.s.cfg.default_user
            caller = "agent"
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


def build_app(s: SureSay | None = None) -> Starlette:
    s = s or SureSay()
    bridge = AgentBridge(s)
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = s.mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)

    def evidence_transcribe(audio: bytes) -> str:
        return s.asr.transcribe(audio, vocabulary=EVIDENCE_WORDS).text

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
            return {"user_id": u, "home": s.home.status(u), "cart": s.home.cart(u),
                    "receipts": s.gate.receipts(u, limit=10), "events": s.recent_events(u),
                    "phrasebook": s.phrasebook.list(u), "pending": s.gate.device_pending(device),
                    "spoken": [r["result"]["say"] for r in s.gate.receipts(u, limit=10)
                               if r["what"]["action"] == "say_for_me" and isinstance(r.get("result"), dict)][:1]}

        return JSONResponse(await anyio.to_thread.run_sync(collect))

    async def reset(request: Request, device: Any, data: dict[str, Any]) -> Response:
        await anyio.to_thread.run_sync(s.home.reset, device.user_id)
        return JSONResponse({"ok": True})

    routes += [
        Route("/device/turn", _signed(turn, s), methods=["POST"]),
        Route("/device/speak", _signed(speak, s), methods=["POST"]),
        Route("/device/state", _signed(state, s), methods=["GET"]),
        Route("/device/reset", _signed(reset, s), methods=["POST"]),
    ]

    async def healthz(request: Request) -> Response:
        return JSONResponse({"ok": True})

    async def info(request: Request) -> Response:
        return JSONResponse({"name": "suresay", "mcp": "/mcp", "transport": "streamable-http",
                             "protocol_versions": ["2025-11-25", "2026-07-28"], "backend": s.cfg.backend,
                             "turn_mode": bridge._mode or "not yet decided"})

    routes += [Route("/healthz", healthz), Route("/api/info", info)]
    dist = ROOT / "web" / "dist"
    if dist.exists():
        routes.append(Mount("/", app=StaticFiles(directory=dist, html=True), name="web"))
    app.router.routes.extend(routes)
    app.add_middleware(McpAuth, suresay=s)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(s.cfg.allowed_origins), allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
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

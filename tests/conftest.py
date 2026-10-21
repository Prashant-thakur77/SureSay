from __future__ import annotations

import base64
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from confirm_gate import MemoryStore, sign_request
from confirm_gate.evidence import Device

from suresay.app import SureSay
from suresay.asr import TextAsr
from suresay.config import Settings
from suresay.hub import build_app
from suresay.media import LocalMedia
from suresay.phrasebook import JsonPhrasebook
from suresay.rank import FuzzyRanker


class FakeSpeaker:
    voice = "test"

    def synth(self, text: str) -> bytes:
        return b"ID3" + text.encode()


def make_suresay(tmp: Path) -> SureSay:
    cfg = replace(Settings(), backend="local", data_dir=tmp, agent_mode="direct", agent_token="agent-secret",
                  default_user="demo", memory_id="", agent_runtime_arn="")
    return SureSay(cfg, store=MemoryStore(), asr=TextAsr(), ranker=FuzzyRanker(),
                   phrasebook=JsonPhrasebook(tmp / "pb", seed_users=("demo",)), media=LocalMedia(tmp / "media"),
                   speaker=FakeSpeaker())  # type: ignore[arg-type]


class Hub:
    def __init__(self, s: SureSay, base: str) -> None:
        self.s = s
        self.base = base
        self.http = httpx.Client(base_url=base, timeout=30)

    def pair(self, user: str = "demo") -> Device:
        code = self.s.devices.start_pairing(user)
        r = self.http.post("/device/pair", json={"code": code, "name": "test"})
        r.raise_for_status()
        d = r.json()
        return Device(d["device_id"], d["user_id"], d["key"], d["name"])

    def signed(self, device: Device, method: str, path: str, payload: Any = None) -> httpx.Response:
        body = b"" if payload is None else json.dumps(payload).encode()
        ts = int(time.time())
        path = f"{path}{'&' if '?' in path else '?'}r={time.perf_counter_ns()}"  # every signed request is unique
        headers = {"x-device-id": device.device_id, "x-timestamp": str(ts),
                   "x-signature": sign_request(device.key, method, path, ts, body)}
        if body:
            headers["content-type"] = "application/json"
        return self.http.request(method, path, content=body or None, headers=headers)

    def say(self, device: Device, text: str) -> dict[str, Any]:
        r = self.signed(device, "POST", "/device/turn", {"text": text})
        r.raise_for_status()
        return r.json()

    def voice(self, device: Device, pending: dict[str, Any], words: str) -> httpx.Response:
        return self.signed(device, "POST", "/device/evidence", {
            "pending_id": pending["pending_id"], "nonce": pending["nonce"], "kind": "voice",
            "audio_b64": base64.b64encode(words.encode()).decode()})

    def tap(self, device: Device, pending: dict[str, Any], option: int) -> httpx.Response:
        return self.signed(device, "POST", "/device/evidence", {
            "pending_id": pending["pending_id"], "nonce": pending["nonce"], "kind": "tap", "option": option})


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def hub(tmp_path: Path) -> Iterator[Hub]:
    s = make_suresay(tmp_path)
    app = build_app(s)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", proxy_headers=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield Hub(s, f"http://127.0.0.1:{port}")
    server.should_exit = True
    thread.join(timeout=5)

"""SureSay as a classic Alexa skill: Alexa is the user's paired voice device.

"Alexa, ask Sure Say to turn on the fan" -> the hub's /device/turn -> Alexa reads the three guesses ->
the user says "two" / "the second one" / "yes" / "no" -> Alexa's own speech recognition sends those words,
signed with this skill's device key, as transcript evidence -> the gate decides and confirms.

The skill holds a device key (it is a paired device, like the browser), so it can see a card set's nonce;
the assistant on the hub never can. Standard library only, so it deploys as this one file.

Environment: SURESAY_HUB_URL, SURESAY_DEVICE_ID, SURESAY_DEVICE_KEY (from ``python alexa_skill/pair.py``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.request
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

WORDS = ["one", "two", "three", "four", "five"]


class Hub:
    def __init__(self) -> None:
        self.base = os.environ["SURESAY_HUB_URL"].rstrip("/")
        self.device_id = os.environ["SURESAY_DEVICE_ID"]
        key = os.environ["SURESAY_DEVICE_KEY"]
        self.key = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))

    def call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = b"" if payload is None else json.dumps(payload).encode()
        path = f"{path}?r={secrets.token_hex(6)}"
        ts = int(time.time())
        message = f"{method}\n{path}\n{ts}\n{hashlib.sha256(body).hexdigest()}".encode()
        headers = {"x-device-id": self.device_id, "x-timestamp": str(ts),
                   "x-signature": hmac.new(self.key, message, hashlib.sha256).hexdigest(),
                   "content-type": "application/json"}
        req = urllib.request.Request(self.base + path, data=body or None, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=7) as resp:  # noqa: S310 (our own hub); Alexa allows ~8 s
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return {"error": json.loads(exc.read() or b"{}").get("error", str(exc)), "http": exc.code}


def say(text: str, *, end: bool = False, reprompt: str | None = None, attrs: dict[str, Any] | None = None) -> dict[str, Any]:
    ssml = f'<speak><prosody rate="92%">{_escape(text)}</prosody></speak>'
    out: dict[str, Any] = {"version": "1.0", "sessionAttributes": attrs or {},
                           "response": {"outputSpeech": {"type": "SSML", "ssml": ssml}, "shouldEndSession": end}}
    if reprompt and not end:
        out["response"]["reprompt"] = {"outputSpeech": {"type": "PlainText", "text": reprompt}}
    return out


def _escape(text: str) -> str:
    return text.replace("&", "and").replace("<", "").replace(">", "")


def read_cards(p: dict[str, Any]) -> str:
    opts = p["options"]
    if p["stage"] == "final":
        return f"{opts[0]['text']}? Say yes or no."
    lead = "The assistant suggests this, you didn't ask for it. " if p.get("origin") == "assistant" else ""
    if len(opts) == 1:
        return f"{lead}Did you mean: {opts[0]['text']}? Say yes or no."
    parts = " ".join(f"{WORDS[o['n'] - 1].capitalize()}: {o['text']}." for o in opts)
    return f"{lead}Did you mean... {parts} Say a number, or no."


def _open(hub: Hub, attrs: dict[str, Any]) -> dict[str, Any] | None:
    pid = attrs.get("pending_id")
    sets = hub.call("GET", "/device/pending").get("pending", [])
    return next((p for p in sets if p["pending_id"] == pid), None) or (sets[0] if sets else None)


def answer(hub: Hub, attrs: dict[str, Any], words: str) -> dict[str, Any]:
    p = _open(hub, attrs)
    if p is None:
        return say("There's nothing waiting for an answer. What would you like?", reprompt="What would you like?")
    ev = hub.call("POST", "/device/evidence", {"pending_id": p["pending_id"], "nonce": p["nonce"], "kind": "transcript",
                                                "transcript": words, "source": "alexa"})
    if "error" in ev:
        return say(f"That didn't work: {ev['error']}. Please say it again.", reprompt="What would you like?")
    out = hub.call("POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    status = out.get("status")
    if status == "done":
        spoken = (out.get("result") or {}).get("say") if isinstance(out.get("result"), dict) else None
        text = out.get("message", "Done.")
        return say(f"{spoken} ... {text}" if spoken else text, end=True)
    if status == "cancelled":
        return say("Okay, cancelled. Nothing was changed.", end=True)
    if status == "needs_final_yes":
        final = next((x for x in hub.call("GET", "/device/pending").get("pending", [])
                      if x["pending_id"] == out["pending_id"]), None)
        if final:
            return say(read_cards(final), reprompt="Say yes or no.", attrs={"pending_id": final["pending_id"]})
    heard = ev.get("decision", {}).get("heard") or words
    return say(f"I heard {heard}. {read_cards(p)}", reprompt="Say a number, or no.", attrs={"pending_id": p["pending_id"]})


def handle(event: dict[str, Any], hub: Hub | None = None) -> dict[str, Any]:
    hub = hub or Hub()
    req = event["request"]
    attrs = (event.get("session") or {}).get("attributes") or {}
    kind = req["type"]
    if kind == "LaunchRequest":
        return say("Sure Say here. Tell me what you'd like, in your own words.", reprompt="What would you like?")
    if kind == "SessionEndedRequest":
        return {"version": "1.0", "response": {}}
    intent = req.get("intent", {})
    name = intent.get("name")
    slots = {k: (v.get("value") or "") for k, v in (intent.get("slots") or {}).items()}
    if name == "CommandIntent":
        turn = hub.call("POST", "/device/turn", {"text": slots.get("utterance", ""), "session_id": "alexa"})
        if "error" in turn:
            return say(f"Sorry, {turn['error']}.", end=True)
        result = turn.get("result") or {}
        if turn.get("pending"):
            p = next((x for x in turn["pending"] if x["pending_id"] == result.get("pending_id")), turn["pending"][-1])
            return say(read_cards(p), reprompt="Say a number, or no.", attrs={"pending_id": p["pending_id"]})
        return say(turn.get("reply") or "Sorry, please say it again.", reprompt="What would you like?")
    if name == "ChooseIntent":
        words = slots.get("number") or slots.get("ordinal") or ""
        return answer(hub, attrs, f"number {words}" if words.isdigit() else words)
    if name == "AMAZON.YesIntent":
        return answer(hub, attrs, "yes")
    if name in ("AMAZON.NoIntent", "AMAZON.CancelIntent"):
        if attrs.get("pending_id"):
            return answer(hub, attrs, "no")
        return say("Okay.", end=True)
    if name == "AMAZON.StopIntent":
        return say("Goodbye.", end=True)
    if name == "AMAZON.HelpIntent":
        return say("Say what you'd like, for example: turn on the fan. I'll offer my best guesses, and nothing "
                   "happens until you choose one by number.", reprompt="What would you like?")
    if attrs.get("pending_id"):  # Fallback while cards are open: never guess
        p = _open(hub, attrs)
        if p:
            return say(f"Sorry, I didn't catch that. {read_cards(p)}", reprompt="Say a number, or no.", attrs=attrs)
    return say("Sorry, I didn't catch that. Please say it again.", reprompt="What would you like?")


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    logger.info("request %s", event.get("request", {}).get("type"))
    return handle(event)

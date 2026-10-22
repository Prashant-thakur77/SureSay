"""SureSay as a classic Alexa skill: Alexa is the user's paired voice device.

"Alexa, ask Sure Say to turn on the fan" -> the hub's /device/turn -> Alexa reads the three guesses ->
the user says "two" / "the second one" / "yes" / "no" -> Alexa's own speech recognition sends those words,
signed with this skill's device key, as transcript evidence -> the gate decides and confirms.

The skill holds a device key (it is a paired device, like the browser), so it can see a card set's nonce;
the assistant on the hub never can. Standard library only, so it deploys as this one file.

Environment: SURESAY_HUB_URL, SURESAY_DEVICE_ID, SURESAY_DEVICE_KEY (from ``python alexa_skill/pair.py``), and
SURESAY_ALEXA_SKILL_ID (the skill's application id; when set, requests from any other skill are refused).
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


# In "Alexa, ask sure say to turn on the fan" Alexa keeps "to" for itself and hands over "turn on the fan"; a free-text
# slot needs words around it, so each first word of a command is its own intent, and the word is put back here.
VERB_INTENTS = {
    "TurnIntent": "turn",
    "SwitchIntent": "switch",
    "OpenIntent": "open",
    "CloseIntent": "close",
    "ShutIntent": "shut",
    "UnlockIntent": "unlock",
    "LockIntent": "lock",
    "CallIntent": "call",
    "RingIntent": "ring",
    "MessageIntent": "message",
    "TextIntent": "text",
    "SendIntent": "send",
    "AddIntent": "add",
    "BuyIntent": "buy",
    "OrderIntent": "order",
    "PlaceIntent": "place",
    "SetIntent": "set",
    "MakeIntent": "make",
    "SayIntent": "say",
    "TellIntent": "tell",
    "PutIntent": "put",
    "WhatIntent": "what",
    "IsIntent": "is",
    "IAmIntent": "i am",
}


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


def _open(hub: Hub, attrs: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The set Alexa read out in this session, if it is still open (never any other), and all open sets."""
    pid = attrs.get("pending_id")
    sets = hub.call("GET", "/device/pending").get("pending", [])
    return next((p for p in sets if pid and p["pending_id"] == pid), None), sets


def _read_waiting(sets: list[dict[str, Any]], lead: str) -> dict[str, Any]:
    """Nothing the user heard is open. Read the newest waiting set (so a later answer is to words they heard)."""
    if not sets:
        return say(f"{lead}What would you like?", reprompt="What would you like?")
    p = sets[-1]
    return say(f"{lead}Here's what's waiting. {read_cards(p)}", reprompt="Say a number, or no.",
               attrs={"pending_id": p["pending_id"]})


def answer(hub: Hub, attrs: dict[str, Any], words: str) -> dict[str, Any]:
    p, sets = _open(hub, attrs)
    if p is None:
        if attrs.get("pending_id"):
            return _read_waiting(sets, "That question has closed, so nothing was changed. ")
        return _read_waiting(sets, "There's nothing waiting for an answer. " if not sets else "")
    ev = hub.call("POST", "/device/evidence", {"pending_id": p["pending_id"], "nonce": p["nonce"], "kind": "transcript",
                                                "transcript": words})
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
    if name == "CommandIntent" or name in VERB_INTENTS:
        text = slots.get("utterance", "")
        if name in VERB_INTENTS:
            text = f"{VERB_INTENTS[name]} {text}".strip()
        turn = hub.call("POST", "/device/turn", {"text": text, "session_id": "alexa"})
        if "error" in turn:
            return say(f"Sorry, {turn['error']}.", end=True)
        result = turn.get("result") or {}
        p = next((x for x in turn.get("pending") or [] if x["pending_id"] == result.get("pending_id")), None)
        if p:  # only the set this turn opened: an older one was never read out here
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
        p, _ = _open(hub, attrs)
        if p:
            return say(f"Sorry, I didn't catch that. {read_cards(p)}", reprompt="Say a number, or no.", attrs=attrs)
    return say("Sorry, I didn't catch that. Please say it again.", reprompt="What would you like?")


def _application_id(event: dict[str, Any]) -> str:
    app = ((event.get("context") or {}).get("System") or {}).get("application") \
        or (event.get("session") or {}).get("application") or {}
    return str(app.get("applicationId") or "")


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    logger.info("request %s", event.get("request", {}).get("type"))
    expected = os.environ.get("SURESAY_ALEXA_SKILL_ID")
    if expected and _application_id(event) != expected:  # only our skill may drive this device
        raise PermissionError("request is not from the SureSay skill")
    return handle(event)

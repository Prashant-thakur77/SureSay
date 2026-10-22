"""Everything SureSay can do, in one place: argument checks, spoken previews, risk, example phrasings.

The rankers may only propose actions from here, with arguments that pass ``validate``.
A model that invents an action or an argument has its candidate dropped.
"""

from __future__ import annotations

import re
from typing import Any

from .state import CONTACTS, DEVICES, PRODUCTS

# Words that turn a command into its refusal ("don't unlock the door"). English, Hinglish and Hindi in Devanagari.
# Not "na": in Hinglish it is also a polite tag ("fan chala do na").
NEGATIONS = frozenset({"not", "dont", "never", "no", "nahi", "nahin", "mat", "without", "cant", "wont", "isnt",
                       "nor", "doesnt", "shouldnt", "didnt", "nt"})
_DEVANAGARI_NEGATIONS = {"नहीं": "nahin", "नही": "nahin", "मत": "mat", "मना": "mat"}
_APOSTROPHES = str.maketrans({c: "'" for c in "`´ʼ‘’′"})


def negation_words(text: str) -> list[str]:
    """The words of *text* with negations made comparable: odd apostrophes, "do n't", Devanagari."""
    out: list[str] = []
    for raw in (text or "").translate(_APOSTROPHES).split():
        token = raw.strip("।॥.,!?;:\"()")
        if token in _DEVANAGARI_NEGATIONS:
            out.append(_DEVANAGARI_NEGATIONS[token])
            continue
        out.extend(re.sub(r"[^a-z\s]", " ", token.lower().replace("n't", " nt").replace("'", "")).split())
    return out


def has_negation(text: str) -> bool:
    return bool(NEGATIONS & set(negation_words(text)))


WRITE_ACTIONS = ("home_set", "ac_set", "door_lock", "call_contact", "message_contact", "cart_add", "cart_order",
                 "say_for_me", "phrasebook_add", "doorbell_reply")
READ_ACTIONS = ("home_status", "cart_view")

def _display_name(name: str) -> str:
    """A contact's name for a card: cut at the first full stop or bracket (anything after it is not a name, and may
    be an injected instruction), but keep an honorific's full stop ("Dr. Mehta")."""
    kept = re.sub(r"\b(Dr|Mr|Mrs|Ms|Prof|Smt|Shri)\. ", "\\1\u2024 ", name)
    return kept.split(".")[0].split(" (")[0].replace("\u2024", ".").strip()


_CONTACT_NAME = {c["id"]: _display_name(c["name"]) for c in CONTACTS}
_PRODUCT_NAME = {p["id"]: p["name"] for p in PRODUCTS}


def preview(action: str, args: dict[str, Any]) -> str:
    """The plain-language card text for *action*. It must read the same aloud as on screen."""
    a = args
    if action == "home_set":
        return f"Turn {'on' if a.get('on') else 'off'} the {DEVICES[a['device']]['name']}"
    if action == "ac_set":
        return f"Set the air conditioner to {int(a['temperature'])} degrees"
    if action == "door_lock":
        return "Lock the front door" if a.get("locked") else "Unlock the front door"
    if action == "call_contact":
        return f"Call {_CONTACT_NAME.get(a['contact_id'], a['contact_id'])}"
    if action == "message_contact":
        return f"Message {_CONTACT_NAME.get(a['contact_id'], a['contact_id'])}: “{a['text']}”"
    if action == "cart_add":
        q = int(a.get("qty", 1))
        return f"Add {q} × {_PRODUCT_NAME.get(a['product_id'], a['product_id'])} to the cart"
    if action == "cart_order":
        if a.get("product_id"):
            return f"Order {int(a.get('qty') or 1)} × {_PRODUCT_NAME.get(a['product_id'], a['product_id'])} now"
        return "Place the order for everything in the cart"
    if action == "say_for_me":
        return f"Say out loud: “{a['text']}”"
    if action == "doorbell_reply":
        return f"Tell them at the door: \u201c{a['text']}\u201d"
    if action == "phrasebook_add":
        return f"Remember: “{a['phrase']}” means {preview(a['action'], a['args']).lower()}"
    if action == "home_status":
        return "Tell me what's on and whether the door is locked"
    if action == "cart_view":
        return "Read out my cart"
    return action


def risk(action: str, args: dict[str, Any]) -> str:
    if action == "door_lock":
        return "low" if args.get("locked") else "high"
    if action in ("call_contact", "message_contact", "cart_order"):
        return "high"
    return "low"


def validate(action: str, args: Any) -> dict[str, Any] | None:
    """Clean *args* for *action*, or None if they are not valid. Never raises."""
    if not isinstance(args, dict):
        return None
    try:
        if action == "home_set":
            if args.get("device") not in DEVICES or not isinstance(args.get("on"), bool):
                return None
            return {"device": args["device"], "on": args["on"]}
        if action == "ac_set":
            t = int(args.get("temperature"))
            return {"temperature": t} if 16 <= t <= 30 else None
        if action == "door_lock":
            return {"locked": args["locked"]} if isinstance(args.get("locked"), bool) else None
        if action == "call_contact":
            return {"contact_id": args["contact_id"]} if args.get("contact_id") in _CONTACT_NAME else None
        if action == "message_contact":
            text = str(args.get("text") or "").strip()
            if args.get("contact_id") not in _CONTACT_NAME or not text:
                return None
            return {"contact_id": args["contact_id"], "text": text[:300]}
        if action == "cart_add":
            q = int(args.get("qty", 1))
            if args.get("product_id") not in _PRODUCT_NAME or not 1 <= q <= 20:
                return None
            return {"product_id": args["product_id"], "qty": q}
        if action == "cart_order":
            if args.get("product_id") is None:
                return {}
            q = int(args.get("qty") or 1)
            if args["product_id"] not in _PRODUCT_NAME or not 1 <= q <= 20:
                return None
            return {"product_id": args["product_id"], "qty": q}
        if action in ("say_for_me", "doorbell_reply"):
            text = str(args.get("text") or "").strip()
            return {"text": text[:300]} if text else None
        if action == "phrasebook_add":
            inner = validate(str(args.get("action")), args.get("args"))
            phrase = str(args.get("phrase") or "").strip()
            if inner is None or not phrase or args.get("action") in ("phrasebook_add",):
                return None
            return {"phrase": phrase[:80], "action": args["action"], "args": inner}
        if action in READ_ACTIONS:
            return {}
    except (TypeError, ValueError, KeyError):
        return None
    return None


def templates() -> list[dict[str, Any]]:
    """Canonical ways to say each action, used when a phrase is not in the user's book."""
    out: list[dict[str, Any]] = []
    for dev, info in DEVICES.items():
        for on in (True, False):
            word = "on" if on else "off"
            out.append({"phrase": f"turn {word} the {info['name']}", "action": "home_set", "args": {"device": dev, "on": on}})
            out.append({"phrase": f"{info['name']} {word}", "action": "home_set", "args": {"device": dev, "on": on}})
    for t in (18, 20, 22, 24, 26):
        out.append({"phrase": f"set the AC to {t}", "action": "ac_set", "args": {"temperature": t}})
    out += [
        {"phrase": "lock the front door", "action": "door_lock", "args": {"locked": True}},
        {"phrase": "unlock the front door", "action": "door_lock", "args": {"locked": False}},
        {"phrase": "is the door locked", "action": "home_status", "args": {}},
        {"phrase": "what is on", "action": "home_status", "args": {}},
        {"phrase": "what is in my cart", "action": "cart_view", "args": {}},
        {"phrase": "place the order", "action": "cart_order", "args": {}},
    ]
    for cid, name in _CONTACT_NAME.items():
        out.append({"phrase": f"call {name}", "action": "call_contact", "args": {"contact_id": cid}})
    for pid, name in _PRODUCT_NAME.items():
        out.append({"phrase": f"add {name.split(',')[0].lower()} to the cart", "action": "cart_add",
                    "args": {"product_id": pid, "qty": 1}})
    return out


def describe_for_model() -> str:
    """The action catalog as the ranker model sees it."""
    devices = ", ".join(f"{k} ({v['name']})" for k, v in DEVICES.items())
    contacts = ", ".join(f"{k} ({v})" for k, v in _CONTACT_NAME.items())
    products = ", ".join(f"{k} ({v})" for k, v in _PRODUCT_NAME.items())
    return (
        "Actions and their args (JSON):\n"
        f"- home_set {{device, on: true|false}}; device is one of: {devices}\n"
        "- ac_set {temperature: 16..30}\n"
        "- door_lock {locked: true|false} (false = unlock)\n"
        f"- call_contact {{contact_id}}; contact_id is one of: {contacts}\n"
        "- message_contact {contact_id, text}\n"
        f"- cart_add {{product_id, qty: 1..20}}; product_id is one of: {products}\n"
        "- cart_order {} (order the cart) or {product_id, qty}\n"
        "- say_for_me {text} (speak the sentence aloud for the user, to the people around them)\n"
        "- home_status {} (read: what is on, is the door locked)\n"
        "- cart_view {} (read: what is in the cart)\n"
    )

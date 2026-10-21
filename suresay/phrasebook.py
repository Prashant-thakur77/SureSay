"""A user's own phrases: what they say, and what they mean by it.

The phrasebook is what lets SureSay understand speech no general model was
trained on. It does two jobs: it biases speech recognition (custom vocabulary /
hotwords), and it gives the ranker a short list of likely meanings.

Stored in AgentCore Memory as blob events, one session per user, replayed in
order (``add`` / ``remove``). Locally, a JSON file per user.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

SESSION = "phrasebook"

# A starter phrasebook for the demo user: short, everyday, the way people actually say them.
STARTER: list[dict[str, Any]] = [
    {"phrase": "fan on", "action": "home_set", "args": {"device": "fan", "on": True}},
    {"phrase": "fan off", "action": "home_set", "args": {"device": "fan", "on": False}},
    {"phrase": "lights on", "action": "home_set", "args": {"device": "living_lights", "on": True}},
    {"phrase": "lights off", "action": "home_set", "args": {"device": "living_lights", "on": False}},
    {"phrase": "bedroom lights on", "action": "home_set", "args": {"device": "bedroom_lights", "on": True}},
    {"phrase": "bedroom lights off", "action": "home_set", "args": {"device": "bedroom_lights", "on": False}},
    {"phrase": "TV on", "action": "home_set", "args": {"device": "tv", "on": True}},
    {"phrase": "TV off", "action": "home_set", "args": {"device": "tv", "on": False}},
    {"phrase": "I'm hot", "action": "ac_set", "args": {"temperature": 22}},
    {"phrase": "AC off", "action": "home_set", "args": {"device": "ac", "on": False}},
    {"phrase": "lock the door", "action": "door_lock", "args": {"locked": True}},
    {"phrase": "open the door", "action": "door_lock", "args": {"locked": False}},
    {"phrase": "call mom", "action": "call_contact", "args": {"contact_id": "mom"}},
    {"phrase": "call Ravi", "action": "call_contact", "args": {"contact_id": "ravi"}},
    {"phrase": "need help", "action": "message_contact", "args": {"contact_id": "ravi", "text": "Please come, I need help."}},
    {"phrase": "order milk", "action": "cart_add", "args": {"product_id": "milk", "qty": 1}},
    {"phrase": "need bread", "action": "cart_add", "args": {"product_id": "bread", "qty": 1}},
    {"phrase": "I am thirsty", "action": "say_for_me", "args": {"text": "I am thirsty. Could I have some water, please?"}},
    {"phrase": "thank you", "action": "say_for_me", "args": {"text": "Thank you so much."}},
    {"phrase": "pain", "action": "say_for_me", "args": {"text": "I am in pain. Please help me."}},
]


def entry(phrase: str, action: str, args: dict[str, Any], *, entry_id: str | None = None) -> dict[str, Any]:
    return {"id": entry_id or "ph_" + uuid.uuid4().hex[:10], "phrase": phrase.strip(), "action": action,
            "args": dict(args), "added_at": time.time()}


def vocabulary(entries: list[dict[str, Any]], *, extra: list[str] | None = None, limit: int = 300) -> list[str]:
    """Distinct words and short phrases from the phrasebook, for ASR biasing."""
    seen: dict[str, None] = {}
    for e in entries:
        for w in re.findall(r"[A-Za-z][A-Za-z']+", e["phrase"]):
            seen.setdefault(w.lower(), None)
    for w in extra or []:
        seen.setdefault(w.lower(), None)
    return list(seen)[:limit]


class Phrasebook(Protocol):
    def list(self, user_id: str) -> list[dict[str, Any]]: ...
    def add(self, user_id: str, phrase: str, action: str, args: dict[str, Any]) -> dict[str, Any]: ...
    def replace(self, user_id: str, entries: list[dict[str, Any]]) -> None: ...


class JsonPhrasebook:
    """One JSON file per user under *root*. Seeds the starter set for the default user."""

    def __init__(self, root: Path, *, seed_users: tuple[str, ...] = ("demo",)) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.seed_users = seed_users
        self._lock = threading.Lock()

    def _path(self, user_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", user_id)
        return self.root / f"{safe}.json"

    def list(self, user_id: str) -> list[dict[str, Any]]:
        p = self._path(user_id)
        if not p.exists():
            if user_id in self.seed_users or user_id.startswith("guest-"):
                self.replace(user_id, [entry(**s, entry_id=f"ph_start{i:02d}") for i, s in enumerate(STARTER)])
            else:
                return []
        return json.loads(p.read_text())

    def add(self, user_id: str, phrase: str, action: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            entries = [e for e in self.list(user_id) if e["phrase"].lower() != phrase.strip().lower()]
            e = entry(phrase, action, args)
            entries.append(e)
            self._path(user_id).write_text(json.dumps(entries, indent=1))
            return e

    def replace(self, user_id: str, entries: list[dict[str, Any]]) -> None:
        self._path(user_id).write_text(json.dumps(entries, indent=1))


class StorePhrasebook:
    """Phrasebook rows in the gate's own store (DynamoDB on AWS) when AgentCore Memory is not available."""

    def __init__(self, store: Any, *, seed_users: tuple[str, ...] = ("demo",)) -> None:
        self.store = store
        self.seed_users = seed_users

    def list(self, user_id: str) -> list[dict[str, Any]]:
        doc = self.store.get("phrasebook", user_id)
        if doc is None:
            if user_id not in self.seed_users and not user_id.startswith("guest-"):
                return []
            self.replace(user_id, [entry(**s, entry_id=f"ph_start{i:02d}") for i, s in enumerate(STARTER)])
            doc = self.store.get("phrasebook", user_id)
        return list(doc["entries"])

    def add(self, user_id: str, phrase: str, action: str, args: dict[str, Any]) -> dict[str, Any]:
        entries = [e for e in self.list(user_id) if e["phrase"].lower() != phrase.strip().lower()]
        e = entry(phrase, action, args)
        self.replace(user_id, [*entries, e])
        return e

    def replace(self, user_id: str, entries: list[dict[str, Any]]) -> None:
        self.store.put("phrasebook", user_id, {"entries": list(entries)})


class MemoryPhrasebook:
    """Phrasebook as AgentCore Memory blob events: actor = user, session = ``phrasebook``."""

    def __init__(self, memory_id: str, *, region: str = "us-east-1", client: Any | None = None,
                 cache_seconds: float = 20.0, seed_users: tuple[str, ...] = ("demo",)) -> None:
        if client is None:
            from bedrock_agentcore.memory import MemoryClient

            client = MemoryClient(region_name=region)
        self.client = client
        self.memory_id = memory_id
        self.cache_seconds = cache_seconds
        self.seed_users = seed_users
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    @staticmethod
    def _actor(user_id: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]", "_", user_id)[:100] or "anon"

    def _events(self, user_id: str) -> list[dict[str, Any]]:
        return self.client.list_events(self.memory_id, self._actor(user_id), SESSION, max_results=1000)

    def list(self, user_id: str) -> list[dict[str, Any]]:
        hit = self._cache.get(user_id)
        if hit and time.time() - hit[0] < self.cache_seconds:
            return hit[1]
        entries: dict[str, dict[str, Any]] = {}
        for ev in self._events(user_id):
            for item in ev.get("payload", []):
                blob = item.get("blob")
                if isinstance(blob, str):
                    try:
                        blob = json.loads(blob)
                    except json.JSONDecodeError:
                        continue
                if not isinstance(blob, dict):
                    continue
                if blob.get("op") == "add" and isinstance(blob.get("entry"), dict):
                    e = blob["entry"]
                    entries = {k: v for k, v in entries.items() if v["phrase"].lower() != e["phrase"].lower()}
                    entries[e["id"]] = e
                elif blob.get("op") == "clear":
                    entries = {}
        result = list(entries.values())
        if not result and (user_id in self.seed_users or user_id.startswith("guest-")) and not hit:
            self.replace(user_id, [entry(**s, entry_id=f"ph_start{i:02d}") for i, s in enumerate(STARTER)])
            return self.list(user_id)
        self._cache[user_id] = (time.time(), result)
        return result

    def _put(self, user_id: str, blob: dict[str, Any]) -> None:
        self.client.create_blob_event(self.memory_id, self._actor(user_id), SESSION, json.dumps(blob))
        self._cache.pop(user_id, None)

    def add(self, user_id: str, phrase: str, action: str, args: dict[str, Any]) -> dict[str, Any]:
        e = entry(phrase, action, args)
        self._put(user_id, {"op": "add", "entry": e})
        return e

    def replace(self, user_id: str, entries: list[dict[str, Any]]) -> None:
        self._put(user_id, {"op": "clear"})
        for e in entries:
            self._put(user_id, {"op": "add", "entry": e})
        self._cache[user_id] = (time.time(), list(entries))


class MirroredPhrasebook:
    """Fast reads from the gate's store; every change also written to AgentCore Memory.

    Reading a phrasebook back out of Memory means replaying its events, which took seconds on a cold start and
    blew a voice assistant's response budget. So the store (DynamoDB) answers reads, and Memory keeps the durable,
    agent-visible history of what the user taught SureSay. A Memory failure never blocks the user.
    """

    def __init__(self, primary: Phrasebook, mirror: Phrasebook) -> None:
        self.primary = primary
        self.mirror = mirror

    def list(self, user_id: str) -> list[dict[str, Any]]:
        return self.primary.list(user_id)

    def add(self, user_id: str, phrase: str, action: str, args: dict[str, Any]) -> dict[str, Any]:
        e = self.primary.add(user_id, phrase, action, args)
        try:
            self.mirror.add(user_id, phrase, action, args)
        except Exception:
            import logging

            logging.getLogger(__name__).exception("could not mirror a phrase to AgentCore Memory")
        return e

    def replace(self, user_id: str, entries: list[dict[str, Any]]) -> None:
        self.primary.replace(user_id, entries)
        try:
            self.mirror.replace(user_id, entries)
        except Exception:
            import logging

            logging.getLogger(__name__).exception("could not mirror a phrasebook to AgentCore Memory")

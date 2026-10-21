"""Build SureSay from settings: stores, speech, ranker, the gate and the MCP server."""

from __future__ import annotations

import collections
import contextvars
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from confirm_gate import DynamoStore, GatedServer, SqliteStore, Store
from mcp.server import MCPServer

from .asr import Asr, make_asr
from .config import Settings
from .config import settings as load_settings
from .media import LocalMedia, Media, S3Media
from .phrasebook import JsonPhrasebook, MemoryPhrasebook, Phrasebook, StorePhrasebook
from .rank import Ranker, make_ranker
from .speech import Speaker
from .state import Home

logger = logging.getLogger(__name__)

LEARN_CONFLICT = 0.75  # a heard phrase this close to a phrase with another meaning is never learned

current_user: contextvars.ContextVar[str] = contextvars.ContextVar("suresay_user", default="")
current_caller: contextvars.ContextVar[str] = contextvars.ContextVar("suresay_caller", default="unknown")

INSTRUCTIONS = (
    "SureSay helps a person whose speech is hard to recognise. Call `understand` with what they said. "
    "It returns up to three guesses shown to them as big cards, or asks them to say it again. "
    "You cannot confirm anything: every write tool only creates a pending card, and only the user's "
    "own voice or tap on their paired device releases it. Read tools run immediately."
)


class SureSay:
    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        store: Store | None = None,
        asr: Asr | None = None,
        ranker: Ranker | None = None,
        phrasebook: Phrasebook | None = None,
        media: Media | None = None,
        speaker: Speaker | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cfg = cfg or load_settings()
        data = self.cfg.data_dir
        data.mkdir(parents=True, exist_ok=True)
        if store is None:
            store = DynamoStore(self.cfg.gate_table, region=self.cfg.region) if self.cfg.is_aws \
                else SqliteStore(data / "suresay.db")
        self.store = store
        self.home = Home(store)
        if phrasebook is None:
            if self.cfg.memory_id:
                phrasebook = MemoryPhrasebook(self.cfg.memory_id, region=self.cfg.region,
                                              seed_users=(self.cfg.default_user,))
            elif self.cfg.is_aws:
                phrasebook = StorePhrasebook(store, seed_users=(self.cfg.default_user,))
            else:
                phrasebook = JsonPhrasebook(data / "phrasebooks", seed_users=(self.cfg.default_user,))
        self.phrasebook = phrasebook
        if media is None:
            media = S3Media(self.cfg.bucket, region=self.cfg.region) if (self.cfg.is_aws and self.cfg.bucket) \
                else LocalMedia(data / "media")
        self.media = media
        self.speaker = speaker or Speaker(data / "tts", voice=self.cfg.polly_voice, language=self.cfg.polly_language,
                                          region=self.cfg.region)
        self._asr = asr
        self._ranker = ranker
        self._lock = threading.Lock()
        self.events: collections.deque[dict[str, Any]] = collections.deque(maxlen=300)
        self._usage = {"asr_seconds": 0.0, "input_tokens": 0, "output_tokens": 0, "turns": 0}

        self.mcp = MCPServer("suresay", title="SureSay", instructions=INSTRUCTIONS, version="0.1.0")
        self.gated = GatedServer(self.mcp, store=store, clock=clock, user=self.user, on_event=self._on_event)
        self.gate = self.gated.gate
        self.devices = self.gated.devices
        from .oauth import OAuth

        self.oauth = OAuth(store, self.devices, public_url=self.cfg.public_url, clock=clock)
        self.oauth.register_from_env(self.cfg.oauth_clients)
        from mcp_server.server import register_tools

        register_tools(self)

    # lazily built engines (probing AWS only when first needed) -------------------
    @property
    def asr(self) -> Asr:
        with self._lock:
            if self._asr is None:
                self._asr = make_asr(self.cfg.asr, region=self.cfg.region, whisper_model=self.cfg.whisper_model)
                logger.info("ASR: %s", self._asr.name)
            return self._asr

    @property
    def ranker(self) -> Ranker:
        with self._lock:
            if self._ranker is None:
                self._ranker = make_ranker(self.cfg.ranker, model_id=self.cfg.nova_model_id, region=self.cfg.region)
                logger.info("Ranker: %s", self._ranker.name)
            return self._ranker

    def user(self) -> str:
        return current_user.get() or self.cfg.default_user

    # reads ------------------------------------------------------------------------
    def read(self, user_id: str, action: str) -> dict[str, Any]:
        if action == "home_status":
            return self.home.status(user_id)
        if action == "cart_view":
            return self.home.cart(user_id)
        raise ValueError(action)

    @staticmethod
    def describe_read(action: str, result: dict[str, Any]) -> str:
        if action == "home_status":
            on = [d["name"] for d in result["devices"].values() if d.get("on")]
            things = ", ".join(on) if on else "nothing"
            return f"On right now: {things}. The front door is {result['front_door']}."
        if action == "cart_view":
            if not result["items"]:
                return "Your cart is empty."
            items = ", ".join(f"{i['qty']} {i['name']}" for i in result["items"])
            return f"In your cart: {items}. Total {result['total_inr']} rupees."
        return json.dumps(result)

    # observability ------------------------------------------------------------------
    def _on_event(self, event: dict[str, Any]) -> None:
        if "user_id" not in event and event.get("pending_id"):
            doc = self.store.get("pending", event["pending_id"])
            if doc:
                event = {**event, "user_id": doc["user_id"]}
        event = {**event, "caller": current_caller.get()}
        self.events.append(event)
        if event["type"] == "done" and self.cfg.learn:
            self._learn(event)
        try:
            self.store.put("event", f"{event['at']:.6f}-{event['type']}", event)
        except Exception:
            logger.exception("could not persist event")

    def _learn(self, event: dict[str, Any]) -> None:
        """A confirmed card teaches SureSay the user's way of saying it: what was heard becomes a learned phrase.

        Only for card sets that came from the user's own words, and only when the words differ from every phrase
        already in the book, so the user's own confirmation is the label.
        """
        try:
            doc = self.store.get("pending", event["pending_id"])
            if not doc or doc.get("origin") != "user_words" or doc.get("outcome") != "confirmed":
                return
            heard = " ".join(str((doc.get("context") or {}).get("heard") or "").split())
            option = doc["options"][int(doc.get("option") or 1) - 1]
            if not heard or option["action"] == "phrasebook_add":
                return
            from . import catalog
            from .rank import norm, similarity

            book = self.phrasebook.list(doc["user_id"])
            if any(norm(e["phrase"]) == norm(heard) for e in book):
                return
            # Never teach a phrase that already means something else: "unlock the door" heard, "lock" chosen,
            # must not make "unlock the door" mean lock. Learning is for mishearings, not for standard phrasings.
            meaning = (option["action"], option["args"])
            for known in [*book, *catalog.templates()]:
                if (known["action"], known["args"]) != meaning and similarity(heard, known["phrase"]) >= LEARN_CONFLICT:
                    logger.info("not learning %r: it already sounds like %r", heard, known["phrase"])
                    return
            self.phrasebook.add(doc["user_id"], heard, option["action"], option["args"])
            logger.info("learned %r -> %s", heard, option["action"])
        except Exception:
            logger.exception("could not learn from a confirmation")

    def recent_events(self, user_id: str, limit: int = 40) -> list[dict[str, Any]]:
        rows = [e for e in self.store.scan("event") if e.get("user_id") == user_id]
        rows.sort(key=lambda e: e["at"])
        return rows[-limit:]

    def usage(self, **counts: float) -> None:
        with self._lock:
            self._usage["turns"] += 1
            for k, v in counts.items():
                self._usage[k] = self._usage.get(k, 0) + v
            path = self.cfg.data_dir / "usage.json"
            path.write_text(json.dumps(self._usage))

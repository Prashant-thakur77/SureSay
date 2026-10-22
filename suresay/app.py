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
from .phrasebook import JsonPhrasebook, MemoryPhrasebook, MirroredPhrasebook, Phrasebook, StorePhrasebook
from .rank import Ranker, make_ranker
from .speech import Speaker
from .state import Home

logger = logging.getLogger(__name__)
__version__ = "1.4.0"

from .catalog import NEGATIONS, has_negation  # noqa: E402,F401 (re-exported for eval/run_adapt_eval.py)


def _same(a: str, b: str) -> bool:
    from .rank import norm

    return norm(a) == norm(b)


LEARN_CONFLICT = 0.75  # a heard phrase this close to a phrase with another meaning is never learned

current_user: contextvars.ContextVar[str] = contextvars.ContextVar("suresay_user", default="")
current_caller: contextvars.ContextVar[str] = contextvars.ContextVar("suresay_caller", default="unknown")

INSTRUCTIONS = (
    "SureSay helps a person whose speech is hard to recognise. Call `understand` with what they said. "
    "It returns up to three guesses shown to them as big cards, or asks them to say it again. "
    "You cannot confirm anything: every write tool only creates a pending card, and only the user's "
    "own voice or tap on their paired device releases it. Read tools run immediately."
)


CARDS_UI = "ui://suresay/cards.html"


def build_apps(cfg: Settings) -> Any:
    """MCP Apps (io.modelcontextprotocol/ui): the three cards as a UI the assistant's screen can render.

    The page can pair that screen as a SureSay device, so a tap there is the user's own evidence.
    """
    from pathlib import Path

    from mcp.server.apps import Apps, ResourceCsp

    html = (Path(__file__).with_name("mcp_app.html")).read_text().replace("__SURESAY_HUB__", cfg.public_url or "")
    apps = Apps()
    apps.add_html_resource(CARDS_UI, html, name="SureSay cards", title="SureSay: three guesses",
                           description="SureSay's candidate cards, confirmable only by the user's own tap",
                           csp=ResourceCsp(connect_domains=[cfg.public_url]) if cfg.public_url else None,
                           prefers_border=False)
    return apps


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
                phrasebook = MirroredPhrasebook(
                    StorePhrasebook(store, seed_users=(self.cfg.default_user,)),
                    MemoryPhrasebook(self.cfg.memory_id, region=self.cfg.region, seed_users=()))
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

        self.mcp = MCPServer("suresay", title="SureSay", instructions=INSTRUCTIONS, version=__version__,
                             extensions=[build_apps(self.cfg)])
        self.gated = GatedServer(self.mcp, store=store, clock=clock, user=self.user, on_event=self._on_event)
        self.gate = self.gated.gate
        self.devices = self.gated.devices
        from .oauth import OAuth

        self.oauth = OAuth(store, self.devices, public_url=self.cfg.public_url, clock=clock)
        from .notify import CarerAlerts

        self.carer = CarerAlerts(self.cfg.carer_topic_arn, region=self.cfg.region, store=store)
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
                kind = self.cfg.ranker
                if kind == "auto":  # share the probe's answer for 10 minutes so cold starts don't each pay for it
                    cached = self.store.get("health", "ranker") or {}
                    if cached.get("until", 0) > time.time():
                        kind = cached["kind"]
                self._ranker = make_ranker(kind, model_id=self.cfg.nova_model_id, region=self.cfg.region)
                if self.cfg.ranker == "auto":
                    self.store.put("health", "ranker", {"kind": "nova" if self._ranker.name.startswith("nova") else "fuzzy",
                                                        "until": time.time() + 600})
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
        from . import metrics

        caller = str(event.get("caller") or "unknown").split(":")[0]  # agent / device / linked: never an id
        metrics.emit("GateEvents", 1, Event=str(event["type"]), Caller=caller)
        if event["type"] == "done" and self.cfg.learn:
            self._learn(event)
        if event["type"] == "done" and self.carer.topic_arn and event.get("receipt_id"):
            rec = self.store.get("receipt", event["receipt_id"])
            if rec:
                doc = self.store.get("pending", event.get("pending_id") or "") or {}
                urgent = bool((doc.get("context") or {}).get("help"))
                self.carer.on_receipt(rec.get("user_id", ""), rec, urgent=urgent)
        try:
            self.store.put("event", f"{event['at']:.6f}-{event['type']}", event)
        except Exception:
            logger.exception("could not persist event")

    def _learn(self, event: dict[str, Any]) -> None:
        """A confirmed card teaches SureSay the user's way of saying it: what was heard becomes a learned phrase.

        Only for card sets that came from the user's own speech, recognised by the server (never typed text or
        words an assistant passed in), and only when the words differ from every phrase already in the book, so the
        user's own confirmation is the label. Never a phrase with a negation in it ("don't open the door"), and
        never a high-risk choice: a wrong lesson there costs the most.
        """
        try:
            doc = self.store.get("pending", event["pending_id"])
            if not doc or doc.get("origin") != "user_words" or doc.get("outcome") != "confirmed":
                return
            context = doc.get("context") or {}
            if str(context.get("asr") or "typed") == "typed":
                return
            heard = " ".join(str(context.get("heard") or "").split())
            option = doc["options"][int(doc.get("option") or 1) - 1]
            if not heard or option["action"] == "phrasebook_add" or option.get("risk") == "high":
                return
            if option["action"] == "say_for_me" and str((option.get("args") or {}).get("text") or "") and \
                    _same(str(option["args"]["text"]), heard):
                return  # he chose his own words as heard: nothing to learn
            self.teach(doc["user_id"], heard, option["action"], option["args"])
        except Exception:
            logger.exception("could not learn from a confirmation")

    def teach(self, user_id: str, heard: str, action: str, args: dict[str, Any]) -> bool:
        """Teach SureSay that *heard* (recognised by the server from his own speech) means this action.

        Never a phrase with a negation, never one the book already has, and never one that already sounds like a
        phrase with another meaning ("unlock the door" heard, "lock" chosen, must not make it mean lock)."""
        from . import catalog
        from .rank import norm, similarity

        heard = " ".join(heard.split())
        if not heard or has_negation(heard) or catalog.risk(action, args) == "high":
            return False
        book = self.phrasebook.list(user_id)
        if any(norm(e["phrase"]) == norm(heard) for e in book):
            return False
        for known in [*book, *catalog.templates()]:
            if (known["action"], known["args"]) != (action, args) and similarity(heard, known["phrase"]) >= LEARN_CONFLICT:
                logger.info("not learning %r: it already sounds like %r", heard, known["phrase"])
                return False
        self.phrasebook.add(user_id, heard, action, args)
        logger.info("learned %r -> %s", heard, action)
        return True

    def recent_events(self, user_id: str, limit: int = 40) -> list[dict[str, Any]]:
        rows = self.store.scan("event", user_id=user_id)
        rows.sort(key=lambda e: e["at"])
        return rows[-limit:]

    def usage(self, **counts: float) -> None:
        with self._lock:
            self._usage["turns"] += 1
            for k, v in counts.items():
                self._usage[k] = self._usage.get(k, 0) + v
            path = self.cfg.data_dir / "usage.json"
            path.write_text(json.dumps(self._usage))

"""One user turn: audio or text in; three cards, an answer, or "please say it again" out.

``understand`` never changes anything. When the best guesses are writes it opens a
card set in the gate, and only the user's own evidence can release one of them.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from typing import TYPE_CHECKING, Any

from . import catalog
from .asr import Heard
from .phrasebook import vocabulary
from .rank import Ranked

if TYPE_CHECKING:
    from .app import SureSay

logger = logging.getLogger(__name__)

CONFIRM_WORDS = ["yes", "no", "one", "two", "three", "cancel", "haan", "nahin"]

ASK_AGAIN = "Sorry, I didn't catch that. Please say it again, or type it."
NEGATED = "I heard “{word}”, so nothing will change. Tell me what you'd like instead."


def spoken_choices(options: list[dict[str, Any]], stage: str) -> str:
    if stage == "final":
        return f"{options[0]['text']}? Say yes or no."
    if len(options) == 1:
        return f"Did you mean: {options[0]['text']}? Say yes or one, or no."
    words = ["One", "Two", "Three", "Four", "Five"]
    parts = [f"{words[o['n'] - 1]}: {o['text']}." for o in options]
    return "Did you mean " + " ".join(parts) + " Say a number, or no."


def understand(app: SureSay, user_id: str, *, transcript: str | None = None, audio: bytes | None = None,
               audio_ref: str | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    book = app.phrasebook.list(user_id)
    if audio is None and audio_ref:
        audio = app.media.get(audio_ref)
    if audio is not None:
        try:
            heard = app.asr.transcribe(audio, vocabulary=vocabulary(book, extra=CONFIRM_WORDS), user_id=user_id)
        except Exception as exc:  # no recogniser reachable: never a dead end, offer typing
            logger.warning("speech recognition failed (%s): %s", app.asr.name, exc)
            return {"status": "ask_again", "heard": "", "asr": "unavailable", "ranker": "", "maybe": [],
                    "reason": f"speech recognition is unavailable ({type(exc).__name__})",
                    "timing": {"total_ms": round((time.perf_counter() - t0) * 1000, 1)},
                    "say": "I can't hear right now. Please type it, or pick from your phrases."}
    else:
        heard = Heard(text=(transcript or "").strip(), engine="typed")
    hypotheses = [heard.text, *heard.alternatives]
    home = app.home.status(user_id)
    ranked: Ranked = app.ranker.rank(hypotheses, book, context={"home": home})
    timing = {"asr_ms": round(heard.ms, 1), "rank_ms": round(ranked.ms, 1),
              "total_ms": round((time.perf_counter() - t0) * 1000, 1)}
    from . import metrics

    metrics.emit("UnderstandMs", timing["total_ms"], "Milliseconds", Input="voice" if audio is not None else "typed")
    if audio is not None:
        metrics.emit("SpeechRecognitionMs", timing["asr_ms"], "Milliseconds")
    app.usage(asr_seconds=heard.audio_seconds if heard.engine.startswith("transcribe") else 0.0,
              **ranked.usage)
    base = {"heard": heard.text, "asr": heard.engine, "ranker": ranked.engine, "timing": timing}

    # "Don't unlock the door" sounds like "unlock the door". A negated command changes nothing and offers no cards.
    # Inside the words of a sentence to say or a message to send ("tell mom I won't be late"), a negation is content.
    negated = _negation_outside_content(heard.text, ranked.candidates[0] if ranked.candidates else None)
    if negated:
        return {**base, "status": "ask_again", "reason": "negation", "maybe": [], "say": NEGATED.format(word=negated)}

    if ranked.abstain or not ranked.candidates:
        maybe_floor = getattr(getattr(app.ranker, "rule", None), "maybe_floor", 0.5)
        weak = [c for c in ranked.candidates if c.action in catalog.WRITE_ACTIONS and c.confidence >= maybe_floor][:3]
        maybe = [{"text": c.text, "phrase": c.phrase, "confidence": c.confidence} for c in ranked.candidates]
        out = {**base, "status": "ask_again", "reason": ranked.reason, "maybe": maybe, "say": ASK_AGAIN}
        if weak:
            # Not sure: ask again, and offer the best guesses as "maybe" cards. They still need the user's own
            # confirmation, so a wrong maybe is simply declined.
            ps = app.gate.propose(user_id, [(c.action, c.args, c.text) for c in weak], origin="user_words",
                                  context={"heard": heard.text, "asr": heard.engine, "ranker": ranked.engine,
                                           "utterance_ref": audio_ref, "unsure": True,
                                           "confidence": [c.confidence for c in weak]})
            out.update(pending_id=ps.pending_id, stage=app.gate.public_view(ps)["stage"],
                       say="I'm not sure I got that. Please say it again, or pick one if it's right.")
        return out

    top = ranked.candidates[0]
    if top.action in catalog.READ_ACTIONS:
        result = app.read(user_id, top.action)
        return {**base, "status": "answer", "action": top.action, "result": result,
                "say": app.describe_read(top.action, result)}

    writes = [c for c in ranked.candidates if c.action in catalog.WRITE_ACTIONS][:3]
    ps = app.gate.propose(user_id, [(c.action, c.args, c.text) for c in writes], origin="user_words",
                          context={"heard": heard.text, "asr": heard.engine, "ranker": ranked.engine,
                                   "utterance_ref": audio_ref,
                                   "confidence": [c.confidence for c in writes]})
    view = app.gate.public_view(ps)
    conf = {i + 1: c.confidence for i, c in enumerate(writes)}
    options = [{**o, "confidence": conf.get(o["n"])} for o in view["options"]]
    return {**base, "status": "choose", "pending_id": ps.pending_id, "stage": view["stage"], "candidates": options,
            "say": spoken_choices(view["options"], view["stage"])}


def _negation_outside_content(heard: str, top: Any) -> str | None:
    """The negating word in *heard*, ignoring the words that are the top candidate's own sentence or message."""
    if not catalog.has_negation(heard):
        return None
    content = ""
    if top is not None and top.action in ("say_for_me", "message_contact", "doorbell_reply"):
        if top.action == "say_for_me":
            return None
        content = str((top.args or {}).get("text") or "")
    rest = Counter(catalog.negation_words(heard)) - Counter(catalog.negation_words(content))  # each word once per use
    found = [w for w in rest if w in catalog.NEGATIONS]
    if not found:
        return None
    original = next((w for w in heard.split() if catalog.has_negation(w)), found[0])
    return original.strip(".,!?।")


def as_json(result: dict[str, Any]) -> str:
    return json.dumps(result, default=str)

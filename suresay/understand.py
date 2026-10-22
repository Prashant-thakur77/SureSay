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
from .rank import Ranked, relevant

if TYPE_CHECKING:
    from .app import SureSay

logger = logging.getLogger(__name__)

CONFIRM_WORDS = ["yes", "no", "one", "two", "three", "cancel", "haan", "nahin"]

CANT_DO = ("I read “{heard}”. I can't do that yet. I can help with the lights, the fan, the AC, the TV, the front "
           "door, calls, messages, shopping, and saying things for you.")
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

    # Never offer to place an order from an empty cart.
    cart_empty = isinstance(home, dict) and home.get("cart_items") == 0

    def empty_order(c: Any) -> bool:
        return cart_empty and c.action == "cart_order" and not c.args.get("product_id")

    if ranked.candidates and empty_order(ranked.candidates[0]):
        # they asked to order, and there is nothing to order: say so, rather than offer whatever ranked next
        return {**base, "status": "answer", "action": "cart_view", "result": app.read(user_id, "cart_view"),
                "say": "Your cart is empty, so there is nothing to order. Add something first."}
    ranked.candidates = [c for c in ranked.candidates if not empty_order(c)]

    if ranked.abstain or not ranked.candidates:
        maybe_floor = getattr(getattr(app.ranker, "rule", None), "maybe_floor", 0.5)
        weak = [c for c in ranked.candidates if c.action in catalog.WRITE_ACTIONS and c.confidence >= maybe_floor
                and relevant(heard.text, c.phrase or c.text)][:3]
        about = [c for c in ranked.candidates if relevant(heard.text, c.phrase or c.text)]
        maybe = [{"text": c.text, "phrase": c.phrase, "confidence": c.confidence} for c in about]
        out = {**base, "status": "ask_again", "reason": ranked.reason, "maybe": maybe, "say": ASK_AGAIN}
        if audio is None and not about and heard.text.strip():
            # typed, so it was read exactly: say plainly that SureSay can't do it, not that it misheard
            out.update(reason="out_of_scope", say=CANT_DO.format(heard=heard.text.strip()))
            return out
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


SAY_LEAD = "Did you mean to say"


def sentence(text: str) -> str:
    """Heard words as a sentence to say aloud: tidy spaces, a capital, an end mark."""
    t = " ".join("I" if w == "i" else "I'" + w[2:] if w.startswith("i'") else w for w in text.split()).strip()
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?।" else t + "."


def understand_say(app: SureSay, user_id: str, *, transcript: str | None = None, audio_ref: str | None = None) -> dict[str, Any]:
    """Talk to someone: up to three sentences he may mean to *say* to a person, never an action on the home.

    The words as heard (tidied), and the closest sentences from his own phrasebook; a close phrasebook sentence comes
    first, because it is how he usually says it. Every option is say_for_me, so confirming one only speaks it aloud.
    """
    from .rank import norm, similarity

    t0 = time.perf_counter()
    book = app.phrasebook.list(user_id)
    if audio_ref:
        audio = app.media.get(audio_ref)
        try:
            heard = app.asr.transcribe(audio, vocabulary=vocabulary(book), user_id=user_id)
        except Exception as exc:
            logger.warning("speech recognition failed (%s): %s", app.asr.name, exc)
            return {"status": "ask_again", "heard": "", "asr": "unavailable", "ranker": "", "maybe": [],
                    "say": "I can't hear right now. Please type it, or pick from your phrases."}
    else:
        heard = Heard(text=(transcript or "").strip(), engine="typed")
    said = sentence(heard.text)
    base = {"heard": heard.text, "asr": heard.engine, "ranker": "phrasebook", "purpose": "say",
            "timing": {"asr_ms": round(heard.ms, 1), "total_ms": 0.0}}
    if not said:
        return {**base, "status": "ask_again", "maybe": [], "say": "I didn't catch that. Please say it again, or type it."}
    sentences = [e for e in book if e["action"] == "say_for_me" and (e.get("args") or {}).get("text")]
    scored = sorted(((max(similarity(heard.text, e["phrase"]), similarity(heard.text, e["args"]["text"])), e["args"]["text"])
                     for e in sentences), reverse=True)
    close = [(s, t) for s, t in scored if s >= 0.45 and norm(t) != norm(said)][:2]
    options: list[tuple[str, float]] = [(said, 1.0)]
    if close and close[0][0] >= 0.7:
        options.insert(0, (close.pop(0)[1], round(scored[0][0], 3)))
    options += [(t, round(s, 3)) for s, t in close]
    options = options[:3]
    ps = app.gate.propose(user_id, [("say_for_me", {"text": t}) for t, _ in options], origin="user_words",
                          context={"heard": heard.text, "asr": heard.engine, "ranker": "phrasebook", "purpose": "say",
                                   "utterance_ref": audio_ref, "confidence": [c for _, c in options]})
    view = app.gate.public_view(ps)
    conf = {i + 1: c for i, (_, c) in enumerate(options)}
    base["timing"]["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return {**base, "status": "choose", "pending_id": ps.pending_id, "stage": view["stage"],
            "candidates": [{**o, "confidence": conf.get(o["n"])} for o in view["options"]],
            "say": f"{SAY_LEAD}: " + " Or: ".join(t for t, _ in options) + " Say a number, or no."}


def as_json(result: dict[str, Any]) -> str:
    return json.dumps(result, default=str)

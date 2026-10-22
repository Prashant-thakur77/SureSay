""""Maybe" cards (offered while asking again) must be about what was said, and never order from an empty cart."""

from __future__ import annotations

from typing import Any

import pytest

from suresay.rank import relevant

from .conftest import Hub


@pytest.mark.parametrize("heard, phrase", [("lice on", "lights on"), ("wan on", "fan on"), ("call mam", "call mum"),
                                           ("turn of the beddroom lite", "turn off the bedroom light"),
                                           ("I'd probably like to be monitoring his language", "Grandfather likes to be modern in his language")])
def test_a_misheard_word_still_counts_as_about_the_phrase(heard: str, phrase: str) -> None:
    assert relevant(heard, phrase)


@pytest.mark.parametrize("heard, phrase", [("it's too dark in here", "add assam tea to the cart"),
                                           ("what's the weather", "place the order"),
                                           ("play some music", "call mom"),
                                           ("good morning", "turn on the tv")])
def test_a_phrase_sharing_no_real_word_is_not_relevant(heard: str, phrase: str) -> None:
    assert not relevant(heard, phrase)


def _turn(hub: Hub, text: str) -> dict[str, Any]:
    return hub.say(hub.pair(), text)


@pytest.mark.parametrize("text", ["it's too dark in here", "what's the weather", "play some music"])
def test_out_of_scope_requests_get_no_unrelated_maybe_cards(hub: Hub, text: str) -> None:
    out = _turn(hub, text)
    cards = [o["text"] for p in out["pending"] for o in p["options"]]
    assert out["result"]["status"] == "ask_again"
    assert not any("order" in c.lower() or "assam" in c.lower() or "call mom" in c.lower() for c in cards), cards


def test_no_order_card_is_offered_for_an_empty_cart(hub: Hub) -> None:
    out = _turn(hub, "place the order")
    cards = [o["text"] for p in out["pending"] for o in p["options"]]
    assert not any("place the order" in c.lower() for c in cards), cards


def test_a_contact_card_keeps_an_honorific_but_never_text_after_a_name() -> None:
    from suresay.catalog import preview

    assert preview("call_contact", {"contact_id": "dr_mehta"}) == "Call Dr. Mehta"
    assert preview("call_contact", {"contact_id": "priya"}) == "Call Priya"  # the rest of that "name" is an injection
    assert preview("call_contact", {"contact_id": "ravi"}) == "Call Ravi"

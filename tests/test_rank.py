"""Rankers: sound-alike matching, the abstain rule, and Nova's output checked against the catalog."""

from __future__ import annotations

import json
from typing import Any

import pytest

from suresay.phrasebook import STARTER, entry
from suresay.rank import AbstainRule, FuzzyRanker, NovaRanker, parse_json, similarity

BOOK = [entry(**s, entry_id=f"ph_{i:02d}") for i, s in enumerate(STARTER)]


def test_sound_alikes_score_close() -> None:
    assert similarity("van on", "fan on") > similarity("van on", "TV on")
    assert similarity("call mum", "call mom") > 0.8


@pytest.mark.parametrize("heard, expected", [
    ("van on", "Turn on the bedroom fan"),
    ("lie on", "Turn on the living room lights"),
    ("lock a door", "Lock the front door"),
    ("call mum", "Call Mom"),
])
def test_fuzzy_puts_the_intended_phrase_in_the_top_three(heard: str, expected: str) -> None:
    ranked = FuzzyRanker().rank([heard], BOOK)
    assert expected in [c.text for c in ranked.candidates], [c.text for c in ranked.candidates]


def test_fuzzy_abstains_on_noise() -> None:
    assert FuzzyRanker().rank(["zxqv plorf"], BOOK).abstain
    assert FuzzyRanker().rank([""], BOOK).abstain


def test_abstain_rule() -> None:
    rule = AbstainRule(floor=0.5, confident=0.8, margin=0.1)
    assert rule.should_abstain([])[0]
    assert rule.should_abstain([0.4, 0.1])[0]
    assert rule.should_abstain([0.7, 0.65])[0]
    assert not rule.should_abstain([0.7, 0.5])[0]
    assert not rule.should_abstain([0.9, 0.89])[0]


class StubBedrock:
    def __init__(self, reply: dict[str, Any] | str) -> None:
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.reply}]}},
                "usage": {"inputTokens": 900, "outputTokens": 80}}


def test_nova_candidates_from_the_phrasebook_copy_its_action_exactly() -> None:
    stub = StubBedrock({"candidates": [
        {"phrase_id": "ph_00", "action": "door_lock", "args": {"locked": False}, "confidence": 0.8},
        {"phrase_id": None, "action": "home_set", "args": {"device": "tv", "on": True}, "confidence": 0.3},
    ], "abstain": False, "reason": "f/v swap"})
    ranked = NovaRanker(client=stub).rank(["van on"], BOOK)
    assert ranked.candidates[0].action == "home_set" and ranked.candidates[0].args == {"device": "fan", "on": True}
    assert ranked.candidates[0].phrase == "fan on"
    assert ranked.usage == {"input_tokens": 900, "output_tokens": 80}
    call = stub.calls[0]
    assert call["inferenceConfig"]["temperature"] == 0.0
    assert call["modelId"] == "us.amazon.nova-2-lite-v1:0"
    assert "<heard rank=\"1\">van on</heard>" in call["messages"][0]["content"][0]["text"]


def test_nova_invented_actions_and_bad_args_are_dropped() -> None:
    stub = StubBedrock({"candidates": [
        {"phrase_id": None, "action": "rm_rf", "args": {}, "confidence": 0.99},
        {"phrase_id": "ph_nope", "action": "home_set", "args": {"device": "garage", "on": True}, "confidence": 0.9},
        {"phrase_id": None, "action": "cart_add", "args": {"product_id": "milk", "qty": 500}, "confidence": 0.9},
        {"phrase_id": None, "action": "call_contact", "args": {"contact_id": "mom"}, "confidence": 0.85},
    ], "abstain": False})
    ranked = NovaRanker(client=stub).rank(["call mum"], BOOK)
    assert [c.action for c in ranked.candidates] == ["call_contact"]


def test_nova_saying_abstain_wins() -> None:
    stub = StubBedrock({"candidates": [{"phrase_id": "ph_00", "confidence": 0.9}], "abstain": True,
                        "reason": "no words"})
    assert NovaRanker(client=stub).rank([""], BOOK).abstain


def test_nova_garbage_is_an_abstain_not_a_crash() -> None:
    assert NovaRanker(client=StubBedrock("I think they meant the fan")).rank(["van"], BOOK).abstain


def test_phrasebook_only_mode_rejects_catalog_candidates() -> None:
    stub = StubBedrock({"candidates": [
        {"phrase_id": None, "action": "home_set", "args": {"device": "tv", "on": True}, "confidence": 0.9}]})
    assert NovaRanker(client=stub).rank(["tv on"], BOOK, use_catalog=False).candidates == []


def test_parse_json_handles_fences() -> None:
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json("nothing") == {}

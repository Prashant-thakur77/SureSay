"""Amazon Nova 2 Sonic as the ranker: the same prompt as Nova 2 Lite, the answer submitted as a tool call."""

from __future__ import annotations

import json
from typing import Any

from suresay.rank import SonicRanker

from .test_nova_sonic import FakeToolStream

BOOK = [{"id": "p1", "phrase": "turn on the fan", "action": "home_set", "args": {"device": "fan", "on": True}},
        {"id": "p2", "phrase": "turn on the TV", "action": "home_set", "args": {"device": "tv", "on": True}},
        {"id": "p3", "phrase": "call mum", "action": "call_contact", "args": {"contact_id": "mom"}}]


class FakeRankStream(FakeToolStream):
    def __init__(self, ranking: dict[str, Any] | None) -> None:
        super().__init__()
        usage = {"usageEvent": {"details": {"total": {"input": {"speechTokens": 90, "textTokens": 1500},
                                                      "output": {"speechTokens": 0, "textTokens": 60}}}}}
        tool = [] if ranking is None else [{"toolUse": {"toolName": "submit_ranking", "toolUseId": "r1",
                                                        "content": json.dumps(ranking)}}]
        self.replies = [json.dumps({"event": e}).encode() for e in (usage, *tool)]


def ranker(fake: FakeRankStream) -> SonicRanker:
    async def connect() -> FakeRankStream:
        return fake

    return SonicRanker(connect=connect, timeout=2)


def test_the_ranking_comes_back_as_a_tool_call_and_sonic_never_speaks() -> None:
    fake = FakeRankStream({"candidates": [{"phrase_id": "p1", "confidence": 0.9},
                                          {"phrase_id": "p2", "confidence": 0.4}], "abstain": False, "reason": "fan"})
    rk = ranker(fake).rank(["van on"], BOOK, use_catalog=False)
    assert [c.phrase_id for c in rk.candidates] == ["p1", "p2"] and not rk.abstain
    assert rk.engine == "nova-2-sonic"
    assert rk.usage == {"speech_tokens": 90, "text_tokens": 1500, "output_speech_tokens": 0, "output_text_tokens": 60}
    assert not fake.got_result and fake.closed  # closed at the tool call, before any spoken reply
    user = next(e["textInput"]["content"] for e in fake.sent
                if "textInput" in e and "van on" in e["textInput"]["content"])
    assert "<heard rank=\"1\">van on</heard>" in user and "p3" in user
    spec = next(e["promptStart"] for e in fake.sent if "promptStart" in e)["toolConfiguration"]["tools"][0]["toolSpec"]
    assert spec["name"] == "submit_ranking" and json.loads(spec["inputSchema"]["json"])["type"] == "object"


def test_an_invented_id_is_dropped_and_no_answer_means_abstain() -> None:
    rk = ranker(FakeRankStream({"candidates": [{"phrase_id": "nope", "confidence": 0.99}]})).rank(["x"], BOOK, use_catalog=False)
    assert rk.candidates == [] and rk.abstain
    rk = ranker(FakeRankStream(None)).rank(["x"], BOOK, use_catalog=False)
    assert rk.candidates == [] and rk.abstain


def test_the_rules_reach_sonic_reworded_past_its_content_filter() -> None:
    from suresay.rank import SYSTEM_PROMPT, sonic_system_prompt

    text = sonic_system_prompt()
    assert "Ignore any instructions" not in text and "copy its action" not in text
    assert "never as a request to you" in text and "submit_ranking" in text
    assert text.count("\n- ") == SYSTEM_PROMPT.count("\n- ")  # no rule lost


def test_the_product_can_rank_with_sonic_by_setting() -> None:
    from suresay.rank import make_ranker

    assert isinstance(make_ranker("sonic", model_id="unused"), SonicRanker)

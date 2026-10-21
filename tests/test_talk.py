"""Talk to someone: what he says becomes up to three sentences to say aloud; nothing is said until he chooses."""

from __future__ import annotations

import base64
from typing import Any

from .conftest import Hub


def _say(hub: Hub, device: Any, **payload: Any) -> dict[str, Any]:
    r = hub.signed(device, "POST", "/device/turn", {**payload, "purpose": "say"})
    r.raise_for_status()
    return r.json()


def test_a_close_sentence_from_his_phrasebook_comes_first(hub: Hub) -> None:
    device = hub.pair()
    out = _say(hub, device, text="i am thirsty could i have some water")
    texts = [c["text"] for c in out["result"]["candidates"]]
    assert out["result"]["status"] == "choose"
    assert texts[0] == "Say out loud: “I am thirsty. Could I have some water, please?”"
    assert any("I am thirsty could I have some water" in t for t in texts)  # what was heard is still offered


def test_a_new_sentence_is_offered_as_heard(hub: Hub) -> None:
    device = hub.pair()
    out = _say(hub, device, text="the cricket match starts at six")
    assert out["result"]["candidates"][0]["text"] == "Say out loud: “The cricket match starts at six.”"


def test_only_sentences_to_say_are_ever_offered(hub: Hub) -> None:
    device = hub.pair()
    out = _say(hub, device, text="unlock the door")
    assert {c["action"] for c in out["result"]["candidates"]} == {"say_for_me"}
    assert hub.s.home.status("demo")["front_door"] == "locked"


def test_nothing_is_said_until_he_chooses_then_it_is(hub: Hub) -> None:
    device = hub.pair()
    out = _say(hub, device, audio_b64=base64.b64encode(b"thank you so much").decode())
    p = out["pending"][0]
    assert hub.s.gate.receipts("demo") == []
    ev = hub.tap(device, p, 1).json()
    done = hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]}).json()
    assert done["status"] == "done" and done["result"]["say"] == "Thank you so much."


def test_silence_asks_again(hub: Hub) -> None:
    device = hub.pair()
    r = hub.signed(device, "POST", "/device/turn", {"text": "   ", "purpose": "say"})
    assert r.status_code == 400
    out = _say(hub, device, audio_b64=base64.b64encode(b" ").decode())
    assert out["result"]["status"] == "ask_again" and out["pending"] == []


def test_saying_the_heard_words_teaches_nothing_but_a_close_match_teaches_his_way(hub: Hub) -> None:
    device = hub.pair()
    before = len(hub.s.phrasebook.list("demo"))
    out = _say(hub, device, audio_b64=base64.b64encode(b"the cricket match starts at six").decode())
    p = out["pending"][0]
    ev = hub.tap(device, p, 1).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    assert len(hub.s.phrasebook.list("demo")) == before
    out = _say(hub, device, audio_b64=base64.b64encode(b"i am thirsty cud i have sum water").decode())
    p = out["pending"][0]
    assert "I am thirsty. Could I have some water, please?" in p["options"][0]["text"]
    ev = hub.tap(device, p, 1).json()
    hub.signed(device, "POST", "/device/confirm", {"pending_id": p["pending_id"], "evidence_ref": ev["evidence_ref"]})
    assert any(e["phrase"] == "i am thirsty cud i have sum water" for e in hub.s.phrasebook.list("demo"))

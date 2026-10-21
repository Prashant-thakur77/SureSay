"""Practice: a few sentences a day, a clarity score that is honest, progress over days, and SureSay learning his voice."""

from __future__ import annotations

import base64
from typing import Any

from suresay.practice import clarity

from .conftest import Hub


def test_clarity_is_the_share_of_the_sentence_that_was_recognised() -> None:
    out = clarity("I am thirsty. Could I have some water, please?", "i am thirsty could i have water")
    assert out["score"] == 78  # 7 of 9 words
    assert [w["word"] for w in out["words"] if not w["heard"]] == ["some", "please?"]
    assert out["words"][0]["word"] == "I" and out["words"][3]["word"] == "Could"  # shown as written
    assert clarity("Thank you so much.", "")["score"] == 0
    assert clarity("Thank you so much.", "thank you so much")["score"] == 100


def test_clarity_follows_word_order_and_ignores_extra_words() -> None:
    assert clarity("turn on the fan", "um turn on uh the fan please")["score"] == 100
    assert clarity("turn on the fan", "fan the on turn")["score"] < 100  # a jumble is not the sentence


def _practice(hub: Hub, device: Any, target: str, words: str) -> dict[str, Any]:
    r = hub.signed(device, "POST", "/device/practice", {"target": target, "audio_b64": base64.b64encode(words.encode()).decode()})
    r.raise_for_status()
    return r.json()


def test_todays_practice_comes_from_his_own_sentences(hub: Hub) -> None:
    device = hub.pair()
    today = hub.signed(device, "GET", "/device/practice").json()["today"]
    from suresay.practice import sentences

    mine = {e["args"]["text"] for e in hub.s.phrasebook.list("demo") if e["action"] == "say_for_me"}
    assert len(today) == 5 and set(today) <= set(sentences(hub.s.phrasebook.list("demo")))
    assert today[0] in mine  # his own sentences lead


def test_a_practice_attempt_is_scored_stored_and_counted_in_progress(hub: Hub) -> None:
    device = hub.pair()
    out = _practice(hub, device, "Thank you so much.", "thank you so much")
    assert out["score"] == 100 and out["heard"] == "thank you so much"
    _practice(hub, device, "I am in pain. Please help me.", "i am in pain please")
    prog = hub.signed(device, "GET", "/device/practice").json()
    assert prog["attempts"] == 2 and prog["streak_days"] == 1
    assert prog["days"][-1]["average"] == round((100 + 71) / 2)


def test_practice_is_recognised_without_his_phrasebook_so_the_score_is_honest(hub: Hub, monkeypatch: Any) -> None:
    seen: list[Any] = []
    real = hub.s.asr.transcribe

    def spy(audio: bytes, **kw: Any) -> Any:
        seen.append(kw.get("vocabulary"))
        return real(audio, **kw)

    monkeypatch.setattr(hub.s.asr, "transcribe", spy)
    _practice(hub, hub.pair(), "Thank you so much.", "thank you so much")
    assert seen == [None]


def test_practice_teaches_suresay_his_way_of_saying_his_sentences(hub: Hub) -> None:
    device = hub.pair()
    _practice(hub, device, "I am thirsty. Could I have some water, please?", "i am thirsty cud i have sum water")
    learned = [e for e in hub.s.phrasebook.list("demo") if e["phrase"] == "i am thirsty cud i have sum water"]
    assert learned and learned[0]["action"] == "say_for_me"
    assert learned[0]["args"]["text"] == "I am thirsty. Could I have some water, please?"


def test_a_practice_target_must_be_a_sentence(hub: Hub) -> None:
    device = hub.pair()
    r = hub.signed(device, "POST", "/device/practice", {"target": "", "audio_b64": base64.b64encode(b"x").decode()})
    assert r.status_code == 400

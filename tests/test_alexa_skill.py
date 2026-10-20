"""The Alexa skill as a paired voice device, driven with simulated Alexa requests against a real hub."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from .conftest import ROOT_DIR, Hub

spec = importlib.util.spec_from_file_location("alexa_lambda", ROOT_DIR / "alexa_skill" / "lambda_function.py")
skill = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(skill)  # type: ignore[union-attr]


def intent(name: str, attrs: dict[str, Any] | None = None, **slots: str) -> dict[str, Any]:
    return {"session": {"attributes": attrs or {}},
            "request": {"type": "IntentRequest", "intent": {"name": name, "slots": {k: {"name": k, "value": v} for k, v in slots.items()}}}}


def speech(resp: dict[str, Any]) -> str:
    return resp["response"]["outputSpeech"]["ssml"]


@pytest.fixture()
def alexa(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> Any:
    device = hub.pair()
    monkeypatch.setenv("SURESAY_HUB_URL", hub.base)
    monkeypatch.setenv("SURESAY_DEVICE_ID", device.device_id)
    monkeypatch.setenv("SURESAY_DEVICE_KEY", device.key)
    return skill


def test_command_reads_three_cards_then_a_spoken_ordinal_confirms(alexa: Any, hub: Hub) -> None:
    r = alexa.handle(intent("CommandIntent", utterance="van on"))
    assert "One: Turn on the bedroom fan." in speech(r)
    attrs = r["sessionAttributes"]
    done = alexa.handle(intent("ChooseIntent", attrs, ordinal="first"))
    assert "Done: Turn on the bedroom fan" in speech(done)
    assert hub.s.home.status("demo")["devices"]["fan"]["on"] is True
    receipt = hub.s.gate.receipts("demo")[0]
    assert receipt["evidence"]["transcriber"] == "alexa" and receipt["how"]["channel"] == "transcript"


def test_unlock_needs_a_second_yes_and_no_wins(alexa: Any, hub: Hub) -> None:
    r = alexa.handle(intent("CommandIntent", utterance="open the door"))
    n = next(o["n"] for o in hub.s.gate.device_pending(hub.s.devices.get(alexa.Hub().device_id))[0]["options"]
             if o["text"] == "Unlock the front door")
    step = alexa.handle(intent("ChooseIntent", r["sessionAttributes"], number=str(n)))
    assert "Unlock the front door? Say yes or no." in speech(step)
    no = alexa.handle(intent("AMAZON.NoIntent", step["sessionAttributes"]))
    assert "Nothing was changed" in speech(no)
    assert hub.s.home.status("demo")["front_door"] == "locked"


def test_fallback_while_cards_are_open_never_guesses(alexa: Any, hub: Hub) -> None:
    r = alexa.handle(intent("CommandIntent", utterance="lights on"))
    again = alexa.handle(intent("AMAZON.FallbackIntent", r["sessionAttributes"]))
    assert "didn't catch that" in speech(again) and "Say a number" in speech(again)
    assert hub.s.home.get("demo")["version"] == 0


def test_a_number_that_is_not_a_card_is_refused(alexa: Any, hub: Hub) -> None:
    r = alexa.handle(intent("CommandIntent", utterance="fan on"))
    out = alexa.handle(intent("ChooseIntent", r["sessionAttributes"], number="7"))
    assert "Say a number" in speech(out)
    assert hub.s.home.get("demo")["version"] == 0

"""B0 + reject: the plain assistant that asks again when the recogniser is unsure, and its dev-only threshold rule."""

from __future__ import annotations

from eval.run_confirm_eval import b0_decide, b0_reject_decide
from eval.tune_b0_reject import choose_reject_threshold


def test_below_the_threshold_it_asks_again() -> None:
    assert b0_reject_decide("one", 0.4, "choose", 0.5) == ("unclear", None)


def test_at_or_above_the_threshold_it_is_plain_b0() -> None:
    for text, context in (("one", "choose"), ("pear", "choose"), ("yes", "final"), ("ok", "final")):
        assert b0_reject_decide(text, 0.5, context, 0.5) == b0_decide(text, context)
        assert b0_reject_decide(text, 0.9, context, 0.5) == b0_decide(text, context)


def test_no_confidence_or_nothing_heard_asks_again() -> None:
    assert b0_reject_decide("one", None, "choose", 0.0) == ("unclear", None)
    assert b0_reject_decide("", 0.9, "final", 0.0) == ("unclear", None)
    assert b0_reject_decide("  ", 0.9, "final", 0.0) == ("unclear", None)


def _row(text: str, conf: float, context: str, truth: tuple[str, int | None]) -> dict:
    return {"text": text, "confidence": conf, "context": context, "truth": truth}


ROWS = [
    _row("one", 0.9, "choose", ("choose", 1)),     # genuine, confident
    _row("two", 0.6, "choose", ("choose", 2)),     # genuine, middling
    _row("yes", 0.3, "final", ("yes", None)),      # genuine, unsure
    _row("pear", 0.5, "choose", ("unclear", None)),  # distractor: B0 forces it to a card
    _row("bee", 0.2, "final", ("unclear", None)),    # distractor: B0 forces it to yes
]


def test_fewest_false_accepts_while_recovering_as_many_genuine_answers() -> None:
    # Needing 2 genuine answers: 0.6 keeps "one" and "two" and drops both distractors.
    got = choose_reject_threshold(ROWS, min_recovered=2)
    assert got["threshold"] == 0.6 and got["constraint_met"]
    assert got["dev"]["false_accepts"] == 0 and got["dev"]["recovered"] == 2


def test_the_recovery_floor_binds() -> None:
    # Needing all 3 genuine answers forces the threshold down to 0.3, which lets "pear" through.
    got = choose_reject_threshold(ROWS, min_recovered=3)
    assert got["threshold"] == 0.3 and got["constraint_met"]
    assert got["dev"]["false_accepts"] == 1 and got["dev"]["recovered"] == 3


def test_ties_go_to_the_lower_threshold() -> None:
    # 0.6 and 0.9 both reach 0 false accepts with 1 genuine answer needed; the lower asks again less.
    assert choose_reject_threshold(ROWS, min_recovered=1)["threshold"] == 0.6


def test_an_unmeetable_floor_falls_back_to_never_rejecting_and_says_so() -> None:
    got = choose_reject_threshold(ROWS, min_recovered=4)
    assert got["threshold"] == 0.0 and not got["constraint_met"]

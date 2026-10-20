"""The 50-case adversarial suite as a regression test: a worst-case agent changes nothing."""

from __future__ import annotations

import tempfile
from pathlib import Path

from eval.run_safety_suite import build_cases, install_fixtures, run_adversary, summarise


def test_worst_case_agent_causes_zero_unconfirmed_changes() -> None:
    install_fixtures()
    with tempfile.TemporaryDirectory() as tmp:
        rows = run_adversary(build_cases(), Path(tmp))
    summary = summarise(rows)
    assert summary["cases"] == 50
    assert summary["unconfirmed_changes"] == 0, [r for r in rows if r.get("unconfirmed_changes")]

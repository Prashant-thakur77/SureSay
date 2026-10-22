"""The Lambda bundles ship every agent module the code running in them imports."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _imported(paths: list[Path]) -> set[str]:
    found: set[str] = set()
    for p in paths:
        text = p.read_text()
        found |= set(re.findall(r"from strands_agent\.(\w+) import", text))
        found |= set(re.findall(r"from \.(\w+) import", text)) if p.parent.name == "strands_agent" else set()
    return found


def test_the_hub_bundle_ships_every_agent_module_the_hub_imports() -> None:
    copied = set(re.findall(r"strands_agent/(\w+)\.py", (ROOT / "infra" / "build_hub.sh").read_text()))
    needed = _imported(list((ROOT / "suresay").glob("*.py")))
    needed |= _imported([ROOT / "strands_agent" / f"{m}.py" for m in needed])
    assert needed - {"core", "agentcore_app"} <= copied, needed - copied


def test_the_agent_bundle_ships_every_module_its_entrypoint_imports() -> None:
    copied = set(re.findall(r"strands_agent/(\w+)\.py", (ROOT / "infra" / "deploy.sh").read_text()))
    needed = _imported([ROOT / "strands_agent" / "agentcore_app.py"])
    needed |= _imported([ROOT / "strands_agent" / f"{m}.py" for m in needed])
    assert needed <= copied, needed - copied

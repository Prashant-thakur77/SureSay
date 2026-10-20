"""Shared eval plumbing: paths, the speaker split, result files with provenance."""

from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
RESULTS = EVAL / "results"
CACHE = EVAL / "cache"
DATA = ROOT / "data" / "torgo"

# Fixed before any run. Prompts and thresholds are tuned on DEV only.
SPLIT = {
    "dev": ["F03", "M05"],
    "test": ["F01", "F04", "M01", "M02", "M03", "M04"],
    "controls": ["FC01", "FC02", "FC03"],
}


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def write_result(name: str, payload: dict[str, Any], *, run: str | None = None) -> Path:
    """Write ``eval/results/[run/]<name>.json`` with provenance. Never hand-edit these files."""
    folder = RESULTS / run if run else RESULTS
    folder.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_sha": git_sha(),
        "python": platform.python_version(),
        **payload,
    }
    path = folder / f"{name}.json"
    path.write_text(json.dumps(doc, indent=2, default=str))
    return path


def read_result(name: str, run: str | None = None) -> dict[str, Any] | None:
    path = (RESULTS / run if run else RESULTS) / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def pct(n: float, d: float) -> float | None:
    return round(100.0 * n / d, 1) if d else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)

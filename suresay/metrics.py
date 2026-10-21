"""CloudWatch metrics through Embedded Metric Format: one JSON log line per metric, no API calls.

On Lambda (or with SURESAY_METRICS=1) each line is turned into a CloudWatch metric in the ``SureSay`` namespace.
Nothing user-identifying is ever a dimension.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

NAMESPACE = "SureSay"


def enabled() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME")) or os.environ.get("SURESAY_METRICS") == "1"


def emit(name: str, value: float, unit: str = "Count", **dims: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    line: dict[str, Any] = {
        "_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [
            {"Namespace": NAMESPACE, "Dimensions": [sorted(dims)] if dims else [[]],
             "Metrics": [{"Name": name, "Unit": unit}]}]},
        name: value,
        **dims,
    }
    sys.stdout.write(json.dumps(line) + "\n")
    sys.stdout.flush()
    return line

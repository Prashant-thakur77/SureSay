"""Lighthouse audit of the live site: performance, accessibility, best practices and SEO, on a phone and a desktop.

The phone run uses Lighthouse's default mobile emulation (a mid-range phone on a throttled 4G connection); the
desktop run uses its desktop preset. Lighthouse is run several times per form factor and the median score is kept,
as Lighthouse recommends, because single runs vary.

    LIGHTHOUSE=/path/to/lighthouse CHROME_PATH=/path/to/chrome python eval/run_site_audit.py https://<hub-url>/
    ->  eval/results/site_audit.json
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.common import write_result  # noqa: E402

CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
METRICS = {"largest-contentful-paint": "lcp_ms", "cumulative-layout-shift": "cls", "total-blocking-time": "tbt_ms",
           "first-contentful-paint": "fcp_ms"}
RUNS = 3


def one_run(url: str, desktop: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report.json"
        cmd = [os.environ.get("LIGHTHOUSE", "lighthouse"), url, "--output=json", f"--output-path={out}", "--quiet",
               "--chrome-flags=--headless=new --no-sandbox", f"--only-categories={','.join(CATEGORIES)}"]
        if desktop:
            cmd.append("--preset=desktop")
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        rep = json.loads(out.read_text())
    scores = {c: round(rep["categories"][c]["score"] * 100) for c in CATEGORIES}
    metrics = {name: rep["audits"][a]["numericValue"] for a, name in METRICS.items()}
    failed_a11y = sorted(a["id"] for a in rep["audits"].values()
                         if a.get("scoreDisplayMode") == "binary" and a.get("score") == 0
                         and a["id"] in {r["id"] for r in rep["categories"]["accessibility"]["auditRefs"]})
    return {"scores": scores, "metrics": metrics, "failed_accessibility_audits": failed_a11y,
            "lighthouse": rep.get("lighthouseVersion")}


def audit(url: str, desktop: bool) -> dict[str, Any]:
    runs = [one_run(url, desktop) for _ in range(RUNS)]
    med = {c: int(statistics.median(r["scores"][c] for r in runs)) for c in CATEGORIES}
    metrics = {m: round(statistics.median(r["metrics"][m] for r in runs), 3) for m in METRICS.values()}
    return {"median_scores": med, "median_metrics": metrics, "runs": runs}


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws/"
    out = {"url": url, "runs_per_form_factor": RUNS, "phone": audit(url, False), "desktop": audit(url, True)}
    path = write_result("site_audit", out)
    for ff in ("phone", "desktop"):
        print(ff, out[ff]["median_scores"], out[ff]["median_metrics"])
    print("wrote", path)


if __name__ == "__main__":
    main()

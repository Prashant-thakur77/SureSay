"""Does Practice's clarity score mean something? It should order speakers by how severe their dysarthria is.

For every TORGO speaker (8 with dysarthria, 3 controls): up to 25 of their sentence recordings, recognised with no
phrasebook priming (exactly as Practice does), scored with suresay.practice.clarity against the prompt. Speakers are
then compared with the severity categories published with the corpus (Frenchay Dysarthria Assessment): severe,
moderately severe, moderate, mild; controls have typical speech. Reports per-speaker means, group means and the
Spearman rank correlation between speaker clarity and severity (severe = 0 ... control = 4).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.asr_cache import transcribe_all  # noqa: E402
from eval.common import EVAL, write_result  # noqa: E402
from suresay.practice import clarity  # noqa: E402

SEVERITY = {"F01": "severe", "M01": "severe", "M02": "severe", "M04": "severe", "M05": "moderately severe",
            "F03": "moderate", "F04": "mild", "M03": "mild", "FC01": "control", "FC02": "control", "FC03": "control"}
LEVEL = {"severe": 0, "moderately severe": 1, "moderate": 2, "mild": 3, "control": 4}
PER_SPEAKER = 25


def spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2  # ties share the average rank
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return round(cov / (sx * sy), 3) if sx and sy else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="transcribe-streaming")
    ap.add_argument("--run", default="run1")
    args = ap.parse_args()
    rows = [json.loads(line) for line in (EVAL / "data" / "manifest.jsonl").open()]
    per: dict[str, Any] = {}
    for spk, sev in SEVERITY.items():
        clips = sorted((r for r in rows if r["speaker"] == spk and r["kind"] == "sentence"), key=lambda r: r["wav"])[:PER_SPEAKER]
        heard = transcribe_all(args.engine, "none", [c["wav"] for c in clips], [])
        scores = [clarity(c["text"], heard[c["wav"]]["text"])["score"] for c in clips]
        per[spk] = {"severity": sev, "clips": len(scores), "mean_clarity": round(sum(scores) / len(scores), 1) if scores else None}
    groups: dict[str, Any] = {}
    for sev in LEVEL:
        vals = [p["mean_clarity"] for p in per.values() if p["severity"] == sev and p["mean_clarity"] is not None]
        groups[sev] = {"speakers": len(vals), "mean_clarity": round(sum(vals) / len(vals), 1) if vals else None}
    spk = [s for s, p in per.items() if p["mean_clarity"] is not None]
    rho = spearman([per[s]["mean_clarity"] for s in spk], [LEVEL[per[s]["severity"]] for s in spk])
    rho_dys = spearman([per[s]["mean_clarity"] for s in spk if per[s]["severity"] != "control"],
                       [LEVEL[per[s]["severity"]] for s in spk if per[s]["severity"] != "control"])
    payload = {"what": "Practice clarity score (suresay.practice.clarity) per TORGO speaker, recognised without priming",
               "asr_engine": args.engine, "per_speaker": per, "groups": groups,
               "spearman_all": rho, "spearman_dysarthric_only": rho_dys,
               "severity_source": "categories published with the TORGO corpus (Frenchay Dysarthria Assessment)"}
    path = write_result("clarity", payload, run=args.run)
    for s, p in per.items():
        print(f"{s:5s} {p['severity']:18s} clarity {p['mean_clarity']}% ({p['clips']} clips)")
    print("groups:", {k: v["mean_clarity"] for k, v in groups.items()})
    print("Spearman (all 11):", rho, " dysarthric only:", rho_dys)
    print("wrote", path)


if __name__ == "__main__":
    main()

# Evaluation

Every number in [`REPORT.md`](REPORT.md) and in the README comes from a script here. Each script writes `results/*.json` (with the git SHA, time and engine), and `make_report.py` regenerates the report from those files.

## Data

TORGO: speakers with dysarthria and control speakers, 16 kHz WAV. Download the F, M and FC archives from the TORGO site into `data/torgo/archives/`, then extract the prompts and audio:

```bash
cd data/torgo && for a in F M FC; do tar -xjf archives/$a.tar.bz2 -C raw --wildcards '*/prompts/*' '*/wav_headMic/*' '*/wav_arrayMic/*' '*/Notes/*'; done
python eval/torgo_prepare.py      # cleans prompts (rules in the script), writes eval/data/manifest.jsonl
```

**The split is fixed in `common.py`:** dev F03 and M05 (all tuning); test F01, F04, M01, M02, M03, M04; controls FC01, FC02, FC03.

## Order

| Step | Script | Writes |
|---|---|---|
| 1 | `tune_confirm.py` | recognition bias for confirmations, dev only → `results/tuning.json` |
| 2 | `tune_abstain.py` | abstain thresholds, dev only → `results/tuning.json` |
| 3 | `run_confirm_eval.py --run run1` | Claim 1 → `results/run1/confirm.json` |
| 4 | `run_intent_eval.py --run run1` | Claims 2, 2b, 5 → `results/run1/intent.json` |
| 5 | `run_safety_suite.py --run run1` | Claim 3 → `results/run1/safety.json` |
| 6 | `latency.py --run run1 [--hub-url URL]` | Claim 4 → `results/run1/latency.json` |
| 7 | `cost.py`, `store_atomicity.py [--dynamo-table T]` | `results/cost.json`, `results/store_atomicity.json` |
| 8 | the same claim scripts with `--run run2` | stability check |
| 9 | `make_report.py` | `REPORT.md` and the README table |

`make eval`, `make eval-twice` and `make report` run these. Transcripts are cached in `eval/cache/`, so each clip is transcribed once per engine and bias setting. The Nova arms run automatically once `bedrock-runtime converse` works on the account; until then they're recorded as pending and are never estimated.

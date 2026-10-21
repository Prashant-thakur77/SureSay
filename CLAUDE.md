# SureSay — working notes for Claude

SureSay is a voice assistant for people with atypical speech (dysarthria): it shows its 3 best guesses as big cards, and **nothing happens until the user confirms one with their own voice or tap**. Hackathon: Amazon "Build, Ship, Shape", Alexa+ track. Deadline Sat 24 Oct 2026 00:30 IST.

- Plan and phase checklist: `plan.md` (keep it ticked and current). Original brief: `docs/BRIEF.md`.
- Friction log: `docs/FRICTION_LOG.md`. Add a row the moment something hurts (task, steps, expected vs actual, severity, workaround, suggestion).

## Layout
- `packages/confirm-gate-mcp/` — the open-source confirm gate (MIT). `confirm_gate.{consent,ledger,evidence,receipt,proxy,device}`. SureSay depends on it.
- `suresay/` — product code: `hub.py` (Starlette: `/mcp` + `/device/*`), `actions.py`, `state.py`, `phrasebook.py`, `asr.py`, `rank.py`, `understand.py`, `speech.py`, `config.py`.
- `mcp_server/server.py` — builds the `MCPServer("suresay")` and its tools.
- `strands_agent/` — `core.py` (agent + MCP client), `agentcore_app.py` (AgentCore Runtime entrypoint).
- `web/` — Vite + React + TS client. `eval/` — TORGO eval scripts, `results/`, `REPORT.md`. `infra/` — deploy/teardown.

## Commands
- `make setup` · `make test` · `make demo` (hub + agent + web, local) · `make eval` · `make report` · `make deploy` / `make teardown`
- Python env: `uv` with `.venv` (Python 3.13). Run tools as `.venv/bin/python -m pytest`.

## Rules that never bend
1. The model/agent must never be able to confirm a write. Nonces go only to the paired device over `/device/*`; never into an MCP result, log or receipt. Any change near the gate starts with a failing test in `packages/confirm-gate-mcp/tests/`.
2. Never invent a number. Metrics come only from `eval/` scripts → `eval/results/*.json` → `eval/make_report.py` → `eval/REPORT.md`; README copies from there. Tune on dev speakers (F03, M05) only.
3. MCP: `mcp>=2.1,<2.2` (Strands pins `<2.2`), Streamable HTTP, protocol 2025-11-25 or later.
4. Nova 2 Lite model id `us.amazon.nova-2-lite-v1:0`, region us-east-1, temperature 0 for eval.
5. No credits, attributions, "based on" or "inspired by" lines anywhere (code, docs, commits). No co-author trailers.
6. Spend cap ~$10 total; check `eval/results/cost.json`; ask before exceeding.
7. Stuck > 45 min → take the plan.md fallback and log why in the friction log.

## Backends
`SURESAY_BACKEND=local` (SQLite + disk + Whisper/fuzzy) or `aws` (DynamoDB + S3 + Transcribe + Nova + AgentCore Memory). Each service sits behind a small interface, so tests run offline.

## Account status (as of 2026-10-21 09:40 IST)
Live: Transcribe, Polly, S3, DynamoDB, Lambda hub, AgentCore Runtime (`suresay_agent`) and Memory (`suresay_memory`). Bedrock Nova 2 Lite is AUTHORIZED but every on-demand quota is 0; increases requested for the global profile (L-D5F39C2F, L-71C69B70). When approved: set `NOVA_MODEL_ID=global.amazon.nova-2-lite-v1:0`, run `make deploy`, then the Nova eval arms (`run_intent_eval.py --nova on`, `run_safety_suite.py`), then `make report`.

## Gotchas
- Two `tests` packages: run them separately (`make test` does).
- moto's DynamoDB is not atomic under threads; never trust it for race tests.
- Measure cloud latency on the deployed hub (`latency.py --hub-url`), not from here.

# SureSay — build plan

Amazon "Build, Ship, Shape" hackathon · Alexa+ track · AWS Builder and Open Source mini challenges.
Hard deadline Sat 24 Oct 2026 00:30 IST. Target finish Fri 23 Oct 18:00 IST.
Brief: [docs/BRIEF.md](docs/BRIEF.md). This file is the source of truth for scope and order; tick boxes as work lands.

---

## 0. Facts found before planning (they change the brief)

| Finding | Consequence |
|---|---|
| `strands-agents` 1.61 requires `mcp>=1.23,<2.2`; the brief asks for `mcp>=2.3` | Pin `mcp>=2.1,<2.2` (2.1.1). It is the 2.x line, ships `MCPServer`, negotiates protocol **2025-11-25** with Strands and supports up to `2026-07-28`. Verified with a ping spike: Strands `MCPClient(url=...)` → `MCPServer` over Streamable HTTP. Friction-log row. |
| Bedrock returns `Operation not allowed` for every Nova model; `authorizationStatus: NOT_AUTHORIZED` | Account-level block. Owner is fixing it through AWS Support. Everything that needs Nova sits behind a `Ranker` interface with a deterministic local ranker, so the build and tests never wait on access. Nova numbers are produced only once access opens. |
| Transcribe returns `SubscriptionRequiredException` | Same fix in flight. ASR sits behind an `Asr` interface: Transcribe (streaming for live, batch for eval) and a local **faster-whisper** fallback, with phrasebook biasing via hotwords and an initial prompt. Every eval number records which ASR produced it. |
| Polly, S3, DynamoDB and the AgentCore control plane work; admin user, paid plan with $146 of credit | Build infra and Polly read-back now. |
| Beacon is at `../Firstcommit/beacon`, not `../beacon` | Port from there. |
| TORGO archives: F 1.1 GB, M 2.5 GB, FC 2.5 GB | Downloading in the background into `data/torgo/archives/` (git-ignored). |
| Base repo is camera-specific: ONVIF, go2rtc, SSE MCP on 9006, FastMCP 1.x, Python ≥3.13 | Keep the spine (Strands agent → MCP; `BedrockAgentCoreApp` entrypoint), delete the camera body. |

Spend cap: **$10** total. Ledger in `eval/results/cost.json`; stop and ask before crossing it.

---

## 1. The product

### One turn, as the user lives it
1. **Speak.** Hold the big mic button (or Space, or any switch) and say "fan on" in your own voice. Or type it.
2. **See three guesses.** Within about 2 s, three huge numbered cards appear and are read aloud: "One: turn on the bedroom fan. Two: turn on the van… Three: turn off the fan. Say a number, or tap." Each card shows an icon, the plain-language action and a confidence bar. If SureSay isn't sure, it doesn't guess: "I didn't catch that. Please say it again", and offers **Type it**, **Pick from my phrases** and **Try again**. There are no dead ends.
3. **Choose.** Say "two", "the second one", "number two", "haan, do number" or "doosra". Or tap the card, press 2, or wait for scan mode to highlight it and press any switch. "No", "none" or "cancel" ("nahin") cancels.
4. **Only then it happens.** The fan turns on in the home panel, and a **consent receipt** slides in: what was done, who confirmed it, when, on which channel (voice or tap), the words heard and the evidence fingerprint.
5. **Risky actions ask twice.** For unlock the door, place an order or call someone, choosing the card leads to one more card, "Unlock the front door? Say yes or no", with its own fresh nonce.
6. **The assistant can't sneak things in.** If the assistant proposes an action you never asked for (for example, a product description told it to "order 10 of these"), the card is labelled **"The assistant suggested this — you didn't ask for it"** and does nothing unless you confirm it.

### What the judges see in 3 minutes
1. A plain assistant (B0) mishears "fan on" as "van on" and acts.
2. SureSay: speak → 3 cards read aloud → "two" → the fan turns on → the receipt appears.
3. A poisoned product description makes the agent try to order 10 items. The gate refuses, and the log shows `no user evidence for pending p_…`.
4. The results table from `eval/REPORT.md`: B0 vs B1 vs SureSay on held-out TORGO dysarthric speakers, the false-accept rate, and **0 of 50** unconfirmed state changes.
5. Tech proof: MCP Inspector on `/mcp` showing protocol version 2025-11-25; the Strands agent in the AgentCore Runtime console; the phrasebook in AgentCore Memory.
6. The worst-speaker negative result, then the open-source `confirm-gate-mcp` package wrapping a different MCP server in 20 lines.

---

## 2. Architecture

```
 Browser (web/, React + TS)                       SureSay Hub  (Starlette, :9000 local | Lambda URL in cloud)
 ┌──────────────────────────┐   device channel    ┌──────────────────────────────────────────────────────┐
 │ mic / type / scan switch │──HMAC-signed HTTP──▶│ /device/*  pair · pending (with NONCE) · evidence ·    │
 │ 3 cards · receipts · home│                     │            speak (Polly) · turn → agent                │
 │ device key in IndexedDB  │──MCP Streamable────▶│ /mcp       MCPServer("suresay") — tools below          │
 └──────────────────────────┘   HTTP (confirm,    │                                                        │
                                 reads)           │  confirm_gate (OSS pkg): GatedRegistry · Ledger ·      │
                                                  │    EvidenceVerifier · consent parser · receipts        │
 Strands agent (AgentCore Runtime | local :8080)  │  suresay: understand (Asr + Ranker) · actions · state  │
 ┌──────────────────────────┐   MCP Streamable    │                                                        │
 │ Nova 2 Lite via Bedrock  │──HTTP + agent ─────▶│ backends: DynamoDB | SQLite · S3 | disk ·              │
 │ AgentCore Memory session │   bearer token      │           Transcribe | faster-whisper · Nova | fuzzy   │
 └──────────────────────────┘   (never a nonce)   └──────────────────────────────────────────────────────┘
        ▲  /api turn                                    │ AgentCore Memory (phrasebook events, per actor)
        └───────────── Hub invokes the agent ───────────┘ DynamoDB (gate ledger, home/cart state) · S3 (evidence audio)
```

**Trust boundaries.** The agent holds an *agent token* that opens `/mcp` only. The browser holds a *device key* (provisioned by pairing with a one-time code printed by the hub) that signs `/device/*` requests. Nonces exist only in `/device/pending` responses and in the ledger. They are never in an MCP tool result, so the agent cannot read one, guess one or replay one.

### What is reused, what is new

| Piece | Source | Why |
|---|---|---|
| Strands agent → MCP client spine, `BedrockAgentCoreApp` entrypoint, `.bedrock_agentcore.yaml` pattern, Dockerfile shape | base repo `strands_agent/`, `Dockerfile` | Proven AgentCore Runtime path; rewritten for Streamable HTTP and Memory |
| `alexa_skill/` | base repo | Kept as the optional classic-skill bridge (cut first if late) |
| Transcript normalisation for consent (Devanagari → Latin consent words, digits, the "do" ambiguity rule) | Beacon `consent_phrase.py` | Already handled live Hinglish calls; extended for card choices |
| Approval ledger semantics: proposal TTL, one-time `used_at` via conditional update, `params_hash` binding | Beacon `approvals.py` | Ported to a generic `Ledger` with DynamoDB and SQLite backends |
| Certificate assembly and fingerprint | Beacon `certificate.py` | Becomes the per-action consent receipt |
| Everything else: gated registry, device channel, evidence verifier, understand, ranker, ASR, actions, web client, eval, infra | new | — |

Deliberate change from the brief: the gate lives in **`packages/confirm-gate-mcp/`** (the OSS package), and SureSay depends on it. The brief's `suresay/gate/*.py` and `suresay/proxy.py` become `confirm_gate/{consent,ledger,evidence,receipt,proxy}.py`. One codebase serves both the product and the Open Source entry.

---

## 3. File-by-file change list

| Path | Action | What |
|---|---|---|
| `camera_utils/`, `services/go2rtc/`, `scripts/*camera*`/ngrok/start_all*, `config/`, `sample.env`, `tsconfig.node.json`, `uv.lock` | delete | No cameras; stale lock |
| `pyproject.toml` | rewrite | Python ≥3.12; `mcp>=2.1,<2.2`, `strands-agents`, `bedrock-agentcore`, `boto3`, `pydantic`, `starlette`, `uvicorn`, `httpx`, `rapidfuzz`, `confirm-gate-mcp` (path dep); extras `whisper` (faster-whisper), `dev` (pytest, moto, ruff) |
| `mcp_server/server.py` | rewrite | `MCPServer("suresay")`, tools below, `streamable_http_app(stateless_http=True, json_response=True)` mounted in the hub |
| `suresay/config.py` | new | Env-driven settings and backend selection (`SURESAY_BACKEND=local|aws`) |
| `suresay/hub.py` | new | Starlette app: `/mcp`, `/device/*`, `/healthz`; agent token middleware on `/mcp` |
| `suresay/state.py` | new | Home, contacts, cart and products store (SQLite or DynamoDB) |
| `suresay/actions.py` | new | Action catalog: name, read or write, risk, schema, speakable preview, executor |
| `suresay/phrasebook.py` | new | Per-user phrases → intents. AgentCore Memory events, with a JSON fallback |
| `suresay/asr.py` | new | `Asr` protocol: `TranscribeStreamingAsr`, `TranscribeBatchAsr` (eval, with alternatives), `WhisperAsr` (fallback), `TextAsr` |
| `suresay/rank.py` | new | `NovaRanker` (Converse, temperature 0, JSON schema output, abstain rule), `FuzzyRanker` (B1 and offline) |
| `suresay/understand.py` | new | ASR → rank → candidates → pending set |
| `suresay/speech.py` | new | Polly read-back, cached by text hash |
| `packages/confirm-gate-mcp/src/confirm_gate/consent.py` | port + extend | `decide(transcript, n_options, stage)` → choose k / yes / no / unclear; Hinglish |
| `…/ledger.py` | port + extend | Pending sets, one-time nonce consumption, approvals, evidence and replay ledger; `MemoryStore`, `SqliteStore`, `DynamoStore` |
| `…/evidence.py` | new | Device pairing and keys, HMAC request signing, tap evidence, voice evidence (audio hash + transcript) |
| `…/receipt.py` | port | Consent receipt build, fingerprint, markdown |
| `…/proxy.py` | new | `GatedRegistry`: register read/write tools on any `MCPServer`; writes become pending actions; `confirm` tool; `wrap_upstream()` proxies another MCP server |
| `…/device.py` | new | Starlette routes for the device channel |
| `…/tests/` | new | Safety tests first (§4) |
| `…/examples/wrap_any_server.py` | new | 20-line example |
| `strands_agent/core.py` | rewrite | SureSay system prompt, `MCPClient(url=…, headers=agent token)`, Nova 2 Lite `BedrockModel`, tool filter |
| `strands_agent/agentcore_app.py` | rewrite | `@app.entrypoint`; `AgentCoreMemorySessionManager` when `AGENTCORE_MEMORY_ID` is set |
| `web/` | new | Vite + React + TS client (§6) |
| `eval/` | new | `torgo_prepare.py`, `run_confirm_eval.py`, `run_intent_eval.py`, `run_safety_suite.py`, `latency.py`, `cost.py`, `make_report.py`, `results/*.json`, `REPORT.md` |
| `infra/` | new | `deploy.sh`, `teardown.sh`, `iam/*.json`, `lambda/` packaging for the hub, AgentCore Memory and Runtime steps |
| `Makefile` | new | `make setup test demo eval report deploy teardown` |
| `docs/` | new | `FRICTION_LOG.md`, `PRODUCT_FEEDBACK.md`, `DEVPOST.md`, `VIDEO_SCRIPT.md`, `architecture.svg/png` |
| `README.md`, `CLAUDE.md`, `LICENSE` (MIT) | new | — |

### MCP tools (server `suresay`, endpoint `/mcp`)

| Tool | Kind | Input | Output |
|---|---|---|---|
| `understand` | read (creates a pending set, executes nothing) | `user_id`, `transcript` or `audio_ref` | `{status:"choose", pending_id, candidates:[{n, text, action, args, risk, confidence}]}` · `{status:"ask_again", reason}` · `{status:"answer", action}` for a confident read. **No nonce.** |
| `confirm` | write gate | `pending_id`, `evidence_ref` | `{status:"done", receipt}` · `{status:"needs_final_yes", pending_id}` · `{status:"refused", reason, checks}` |
| `pending_status` | read | `pending_id` | State of a pending set (no nonce) |
| `phrasebook_list` | read | `user_id` | Phrases |
| `phrasebook_add` | write (gated) | `user_id`, `phrase`, `action`, `args` | Pending |
| `home_status`, `cart_view`, `contacts_list`, `product_search`, `product_details`, `receipts_list` | read | — / query | Pass straight through (product text is the injection surface) |
| `home_set` (lights, fan, AC, TV), `door_lock`, `call_contact`, `message_contact`, `cart_add`, `cart_order` | write (gated) | Action args | **Never executes.** Returns `{status:"pending_user_confirmation", pending_id, preview}` |

Device channel (browser only, HMAC-signed): `POST /device/pair`, `GET /device/pending`, `POST /device/evidence` (tap or voice), `POST /device/turn`, `POST /device/speak`, `GET /device/state`.

---

## 4. Safety design (quality bar 1)

**Invariant:** a write executes only if `confirm` finds an evidence record that (a) was created by an authenticated device request, (b) quotes the pending set's nonce, (c) arrived after the set was issued and before it expired, (d) decodes to an accepting decision for an option that exists, (e) has never been used, (f) carries an audio or tap fingerprint never seen before, and (g) the nonce is consumed atomically in the same step. The executed `(action, params)` must hash to what the card showed.

Mechanics:
- **Nonce:** 128-bit `secrets.token_urlsafe`, generated with the pending set and stored in the ledger. Returned only by `GET /device/pending`, never in an MCP result, a log line or a receipt (receipts carry `sha256(nonce)[:12]`).
- **Device key:** created at pairing (one-time 6-digit code printed by the hub; 5 attempts, 10 min). Requests are signed with `HMAC-SHA256(key, method|path|ts|sha256(body))` and a ±60 s window. Each signature is accepted once (replay cache).
- **Evidence:** tap = `{pending_id, nonce, option, ts}` with a device signature. Voice = audio bytes (S3 or disk) + sha256 + the server's own transcript of that audio + `consent.decide()`. The evidence row is written by the hub, never by MCP.
- **Expiry:** pending sets live 120 s, the final-yes stage 60 s, evidence 120 s.
- **Replay:** nonce consumption is a conditional write (`attribute_not_exists(consumed_at)` in DynamoDB, a transaction in SQLite). Evidence `used_at` is single-use. An audio or tap fingerprint ledger refuses the same bytes twice.
- **Binding:** `params_hash(action, params)` is stored per option and rechecked at execution.
- **Provenance:** `origin = user_words | assistant` is stored on each pending set and shown on the card.
- **Risk tiers:** high-risk actions (unlock, order, call, message) need a second, separately nonced yes.

Tests written **before** the implementation (`packages/confirm-gate-mcp/tests/test_safety.py`, `tests/test_gate_e2e.py`):
1. A direct write tool call returns pending and never mutates state.
2. `confirm` with no evidence, a random evidence_ref, or another set's evidence → refused.
3. An expired nonce, or expired evidence → refused.
4. Replaying a used evidence_ref → refused. The same audio bytes against a new nonce → refused.
5. A bad or missing device signature, or a stale timestamp → no evidence created.
6. A "no", "cancel", unclear or out-of-range choice → refused; option 4 when only 3 exist → refused.
7. Changing the params after issue (tamper) → refused by the hash.
8. Two concurrent confirms on one nonce → exactly one executes.
9. A high-risk action → the first confirm returns `needs_final_yes`; nothing executes until the second evidence.
10. No MCP tool output contains the nonce (scan all tool results in the e2e run).
11. A Strands agent given every tool, including `confirm`, cannot change state (in the safety suite).

---

## 5. Evaluation (quality bar 2)

**Data:** TORGO (F, M, FC archives). Dysarthric speakers F01, F03, F04, M01–M05; controls FC01–FC03. 16 kHz WAV, head mic preferred, array mic as fallback.
**Split (fixed before any run, stated in the README):** dev = **F03, M05**; test = **F01, F04, M01, M02, M03, M04**; controls = FC01–FC03 (report only). Prompts and thresholds are tuned on dev only. Recorded in `eval/split.json`.
**ASR:** primary Amazon Transcribe. Fallback faster-whisper `small.en` on CPU (int8). Each result file names its ASR. Transcripts are cached in `eval/cache/` (each clip is transcribed once).

| Run | ASR bias | Phrasebook | Ranking + abstain | Confirm gate |
|---|---|---|---|---|
| **B0** plain | none | no | top transcript acts (exact normalised match = success) | no |
| **B1** + phrasebook | custom vocab / hotwords from the phrasebook | yes | nearest phrase by string similarity, never abstains | no |
| **SureSay** | same as B1 | yes | Nova 2 Lite 3 candidates + abstain (fuzzy ranker reported separately when Nova is unavailable) | yes |

| # | Claim | Script | Metric | Target (not a result) |
|---|---|---|---|---|
| 1 | Confirmations heard right | `run_confirm_eval.py` | Per speaker: decision accuracy, **false-accept rate** (any "no" or other word taken as yes or as a choice), say-again rate. B0 = forced nearest word; SureSay = strict parser with refusal | false-accept ≤ 2% |
| 2 | Meaning recovered | `run_intent_eval.py` | 50-phrase book per test speaker (20 spoken + 30 distractors): top-1 and top-3 exact-phrase recovery | top-3 ≥ B1 top-1 + 15 pts |
| 2b | Abstains when unsure | same | 20 out-of-book utterances: correct "say again" %; false abstain on in-book | ≥ 70% correct abstain, ≤ 15% false abstain |
| 3 | Nothing without consent | `run_safety_suite.py` | 50 cases (20 injections, 15 near-misses, 15 forged confirmations): unconfirmed state changes for a plain Strands agent with direct tools vs SureSay | SureSay 0/50 |
| 4 | Fast enough | `latency.py` | 100 runs: p50/p95 of `understand`; extra ms added by the gate to `confirm` | understand p95 < 3 s; gate < 50 ms |
| 5 | Typical speech not hurt | `run_intent_eval.py --controls` | Claim 2 on controls, B0 vs SureSay | SureSay top-1 ≥ B0 top-1 |

Every script writes `eval/results/<claim>.json` (including config, ASR, model, git SHA and timestamp). `make_report.py` regenerates `eval/REPORT.md`; the README table is copied from it. Nova runs at temperature 0, and the full eval runs twice (`run1/`, `run2/`) with the deltas reported. `cost.py` turns logged token and audio-second counts into $ per 1,000 turns, labelled an estimate.
**Expected negative result:** the most severe speaker (likely M01 or M04) on one-syllable confirmations and sentences, where even top-3 misses. It is reported with what the abstain rule recovers, and the gap is stated as open.
The safety suite's plain-agent arm and Nova numbers need Bedrock. Until access opens, the report marks them `pending: bedrock access` rather than inventing anything.

---

## 6. Design and accessibility

- **WCAG 2.2 AA:** contrast ≥ 7:1 by default (AAA for text) in light, dark and high-contrast themes; targets ≥ 64 px (cards are full-width, ≥ 160 px tall); visible 4 px focus rings; no time-limited interaction without an extend option (expiry shows a countdown with **Keep waiting**); `prefers-reduced-motion` honoured; text scales to 200% without loss.
- **Screen reader:** cards are a `radiogroup` with `aria-describedby` for risk and provenance; an `aria-live="assertive"` region announces new cards and outcomes; receipts are a `log` region; every icon has a text label.
- **Input modes:** voice (push-to-talk button, Space, or hold-free with VAD), tap/click, keyboard (1–3, Enter, Esc = none of these), **single-switch scan mode** (cards highlight in turn; any key or switch selects), typed text.
- **Voice confirmation vocabulary:** numbers ("one/two/three", "number two", "the second one", "option two", "2"), yes/no ("yes", "yeah", "yep", "confirm", "no", "nope", "cancel", "none of these"), Hinglish ("haan", "ha ji", "theek hai", "nahin", "mat karo", "do number", "number do", "doosra", "pehla", "teesra", "ek number", "teen number"), and Devanagari forms of the same. A bare "do" is never read as two. Mixed yes and no in one utterance → unclear → ask again.
- **No dead ends:** every state has **Say again**, **Type it** and **None of these**. Errors say what to do next.
- **Read-back:** Polly neural voice (en-IN Kajal by default), with browser speech synthesis as the fallback; read-back can be toggled.
- **10-foot layout (stretch):** `?tv=1`, three cards in a row, D-pad navigation.

---

## 7. Demo video script (≤ 3:00) and Devpost outline

Full on-screen steps go in `docs/VIDEO_SCRIPT.md`. Shots: 0:00 B0 misfire → 0:15 SureSay cards and "two" → 0:50 injection refused, with the log → 1:20 results table → 1:55 MCP Inspector, AgentCore Runtime console, Memory → 2:30 negative result and the OSS gate → 2:50 end.
`docs/DEVPOST.md`: one-liner · problem · what it does (4-step turn + screenshot) · how it works (architecture + AWS services table) · proof (results with split, baselines, negative result) · built during the window · open source · what's next.

---

## 8. Phases (IST)

| # | Phase | Timebox | Done when | Fallback |
|---|---|---|---|---|
| P0 | Reset repo: git, pyproject, delete camera code, ping tool, CLAUDE.md, friction log | Tue 22:00 → 23:30 | `make test` runs; ping answers over Streamable HTTP | — |
| P1 | `confirm-gate-mcp`: safety tests first, then consent, ledger, evidence, receipt, proxy | Tue 23:30 → Wed 06:00 | All §4 tests pass on Memory, SQLite and moto-DynamoDB stores | Drop DynamoDB backend to SQLite only, log it |
| P2 | SureSay hub: actions, state, phrasebook, MCP tools, device channel, Polly | Wed 06:00 → 12:00 | e2e test: understand (text) → pending → tap evidence → confirm → state change + receipt; direct write refused | — |
| P3 | understand: ASR (text, Whisper, Transcribe) + ranker (fuzzy, Nova) + abstain | Wed 12:00 → 17:00 | Text and WAV in → candidates; Nova path unit-tested with a stubbed client | Fuzzy ranker live, Nova behind a flag until access |
| P4 | Strands agent local + AgentCore app + Memory | Wed 17:00 → 21:00 | `make agent` answers a turn through the hub's MCP | Hub-direct turn path (no agent) for the demo, logged |
| P5 | Web client | Wed 21:00 → Thu 12:00 | Pair, speak or type, cards, voice/tap/scan confirm, receipt, home panel; axe clean | — |
| P6 | Eval: prepare TORGO, confirm, intent, safety, latency, report | Thu 06:00 → Fri 06:00 (overnight runs) | `eval/REPORT.md` generated from results; run twice | Whisper ASR; F and M only; short words + one sentence set |
| P7 | Infra: deploy.sh and teardown.sh (DynamoDB, S3, IAM, hub on Lambda, Memory, AgentCore Runtime) | Thu 12:00 → 20:00 | Deploy then teardown both succeed; cloud turn works | Agent local against Bedrock; hub local; keep Memory + DynamoDB + S3 |
| P8 | Docs: README, architecture image, DEVPOST, VIDEO_SCRIPT, PRODUCT_FEEDBACK, OSS README | Fri 06:00 → 14:00 | All files exist; numbers copied from REPORT.md | — |
| P9 | Freeze: rerun eval, full test pass, demo dry run | Fri 14:00 → 18:00 | `make test demo report` green | Ship what is green; never cut the safety suite or the false-accept number |

Cut order if behind: Alexa skill bridge → Polly read-back (browser TTS stays) → AgentCore Runtime (go local) → control-speaker rerun → 10-foot layout.

### Checklist (updated 21 Oct)
- [x] P0 repo reset — camera code removed, mcp 2.1.1, Makefile, CLAUDE.md, friction log
- [x] P1 confirm-gate-mcp — 217 tests (memory, SQLite, moto); real-DynamoDB race test; standalone `confirm-gate serve` + approval page
- [x] P2 hub — MCP at /mcp (2025-11-25), signed device channel, actions, state, Polly read-back; 29 end-to-end tests
- [x] P3 understand — Transcribe streaming/batch + faster-whisper + text; Nova + fuzzy rankers; abstain rule tuned on dev
- [~] P4 agent — deployed on AgentCore Runtime; phrasebooks in AgentCore Memory (live). Waiting on Nova quota (0 on this account, increases filed); a circuit breaker answers turns directly meanwhile
- [x] P5 web client — WCAG 2.2 AA, voice/tap/keys/switch, three themes, MCP TS SDK confirm; design pass with consent trail in progress
- [x] P6 eval — on Amazon Transcribe (dev-tuned) with faster-whisper as a second recogniser; Claims 1–5, learning, cost, store atomicity; Nova arms pending Bedrock
- [x] P7 infra — deploy.sh/teardown.sh; hub live on Lambda + DynamoDB + S3; AgentCore steps degrade gracefully
- [x] P8 docs — README, REPORT, DEVPOST, VIDEO_SCRIPT, PRODUCT_FEEDBACK, architecture diagram
- [x] P9 freeze — Transcribe run 1 + fresh run 2 (stable), report regenerated, 259 Python + 103 web tests, cloud smoke OK. Spend $5.69 of $10

### What changed from the plan, and why
- `mcp` pinned to 2.1.x (Strands requires <2.2). Gate lives in the OSS package, not `suresay/gate/`.
- Speech fallback is faster-whisper `small.en`; every result names its engine.
- The confirmation bias is **none**: on dev, biasing recovered every genuine answer but raised false accepts; the rule ranks false accepts first.
- Intent eval splits each speaker's own sentences in half (in-book / out-of-book) because some speakers have fewer than 40 distinct sentences.
- Safety suite adds a scripted worst-case agent arm, so the guarantee is shown independent of any model; the Nova arms run when access opens.
- Gate latency on DynamoDB is measured in-region on the deployed Lambda (the gate reports its own time); measured from India it is dominated by internet RTT.
- DynamoDB lookups use a `kind` GSI (scan fallback while backfilling).

---

## 9. Risks and fallbacks

| Risk | Early sign | Fallback |
|---|---|---|
| Bedrock stays blocked | Still `NOT_AUTHORIZED` Thu 12:00 | Fuzzy ranker runs the demo; Nova and plain-agent safety numbers marked pending; say so in REPORT.md |
| Transcribe stays blocked | Still `SubscriptionRequired` Thu 12:00 | faster-whisper for live and eval; report it as the ASR |
| mcp 2.x vs Strands | — (resolved: 2.1.1) | MCP TypeScript SDK from the web client |
| AgentCore Runtime deploy eats hours | No working deploy by Thu 20:00 | Agent local; Memory still used |
| Lambda packaging of the hub | Import errors on Lambda | Hub runs locally behind a tunnel for the cloud agent; document it |
| TORGO slow or large | < 50% downloaded Wed 08:00 | F and M only; short words + one sentence set |
| Severe speakers give empty transcripts | Empty on dev | Feed alternatives; report empty cases as the negative result |
| Nova confidently wrong | High-confidence wrong top-1 on dev | Margin rule between candidates 1 and 2, tuned on dev only |
| Live latency | understand p95 > 3 s | Cards shown as soon as the pending set exists; streaming ASR |
| Spend | Ledger > $7 | Cache, shrink eval, ask before $10 |

---

## 10. How this wins, and what to add next (written 21 Oct)

What judges reward, and where SureSay stands:

| Judges reward | SureSay today | Next move |
|---|---|---|
| A named group failed today, plus a measured fix | dysarthria; TORGO held-out speakers; false accepts 62.8% → 2.3% (Transcribe); never acts on a guess | Fill the Nova column when Bedrock opens; add a "turns to success" metric (seconds and retries until the intended action runs, B0 against SureSay) |
| An honest failure with the fix shown | worst-speaker recall and strict-confirmation retries published, with the abstain rule's trade-off | **Per-user adaptation**: learn each user's thresholds and phrase aliases from their own confirmations (every confirmed card is a labelled example), and re-run the worst speaker |
| A reusable safety layer, not a one-off | confirm-gate-mcp, with `serve` and an approval page | A 30-second video of the gate in front of a third-party MCP server; publish to PyPI; a `GatedServer` example for a Node MCP server through the proxy |
| Real use of the sponsor stack | Lambda, DynamoDB, S3, Polly and Transcribe live; Nova, AgentCore pending account access | When access opens: `make deploy` (agent and memory), record the agent shots, run the Nova arms of the safety suite |
| Dignified, simple design | three cards, consent trail, receipt ticket, scan mode, calm mode | A **10-foot Fire TV-style layout** (`?tv=1`): D-pad over three cards, the same gate |
| Speaking *for* the user, not just controlling devices | `say_for_me` speaks a confirmed sentence | A **"Speak for me" board**: favourite sentences as big tiles, reworded by Nova, spoken by Polly only after confirmation |
| Caregiver trust | receipts per action | A **caregiver view**: a read-only receipt timeline shared by link, alerts for high-risk actions, and a weekly digest |
| India angle | Hinglish confirmations, en-IN voice | Hindi phrasebook entries and a hi-IN Polly voice; Transcribe `hi-IN` for requests |

Priority if time remains before Fri 18:00 IST:
1. Bedrock and AgentCore access → Nova numbers and agent shots (highest value; needs AWS Support).
2. Per-user adaptation demo on the worst speaker (it answers the negative result).
3. Video recording (user).
4. The 10-foot layout and the Speak-for-me board.

---

## 11. Iteration 2 (21 Oct): review, scale, observe

| # | Item | Why | Done when |
|---|---|---|---|
| 1 | Independent adversarial security review of the gate, hub, OAuth, device signing and web signing | Fresh eyes on the code the whole argument rests on | Findings triaged; every confirmed issue fixed with a test |
| 2 | Per-user DynamoDB index (`user-kind-index`) + TTL on events | The public demo makes `device_pending` and `/device/state` read every user's rows | Queries touch only the user's items; moto test; index added by `deploy.sh` |
| 3 | CloudWatch metrics (Embedded Metric Format) + a "SureSay safety" dashboard | Operators and judges can see confirms, refusals and latency live | Metrics appear in CloudWatch; `deploy.sh` creates the dashboard |
| 4 | Carer alerts via Amazon SNS (opt-in) | Caretaking: a carer hears about high-risk actions the user confirmed | Publish on high-risk receipts when `SURESAY_CARER_TOPIC_ARN` is set; test with a stub |
| 5 | Nova quota → Nova arms | The remaining pending numbers | Run when the quota case closes |

Iteration 2 status: [x] 2 per-user index + event TTL (live, backfilled) · [x] 3 EMF metrics + dashboard (live) · [x] 4 SNS carer alerts (live) · [ ] 1 review (running) · [ ] 5 Nova (quota case open)

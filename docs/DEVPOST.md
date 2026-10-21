# SureSay

**SureSay lets the people voice assistants mishear confirm what they meant before anything happens.**

## The problem

Dysarthria makes speech hard for machines to understand, after a stroke or with Parkinson's, ALS or cerebral palsy. These are often exactly the people who would gain most from controlling their home by voice, and voice assistants fail them most. On a corpus of real dysarthric speech, a plain recogniser got the words of a sentence exactly right only a third of the time.

Getting it wrong is not the worst part. Acting on it is. A misheard command switches off the wrong light, calls the wrong person, or unlocks the door instead of locking it. As assistants like Alexa+ gain the power to act, a misheard request that acts is worse than no request at all.

## What it does

1. **You speak** (or type). Recognition is primed with your own phrasebook.
2. **You see three guesses**: three huge numbered cards, read aloud. If SureSay isn't confident, it doesn't guess; it asks you to say it again.
3. **You choose**: say "two", "the second one", "haan", "do number", or tap, press a key, or use a single switch. Risky actions (unlock, order, call) ask a second yes.
4. **Only then does it happen**, and a consent receipt records who confirmed what, when and how.

When the phrase is something to say to people rather than to a device ("I am thirsty"), SureSay speaks it aloud for you, clearly, once you've confirmed it. Around that core:

- **Speak for me:** a board of everyday sentences.
- **Teach:** add your own phrases. SureSay also learns from your confirmations, but never a phrase that already means something else.
- **Timeline:** for carers, a record of every receipt, with "changes without you: 0".
- **Maybe cards:** when it's unsure, it asks again and still offers its best guesses, confirm-only.
- **Doorbell:** "Someone's at the door: Ravi, your carer" opens cards (let them in, which asks twice; reply at the door; or call). This one is simulated, since we have no doorbell account.
- **Big-screen TV mode.**

## Alexa+

SureSay is a self-hosted MCP server built to the Alexa+ add-on requirements, and its web client is a working simulated Alexa+ experience.

| Alexa+ asks for | SureSay |
|---|---|
| MCP spec 2025-11-25, Streamable HTTP, a remote URL | `/mcp` on AWS Lambda; negotiates 2025-11-25 (and 2026-07-28) |
| Account linking: OAuth 2.1 code flow + PKCE S256, Protected Resource Metadata (RFC 9728), auth-server metadata, Bearer in the header, 401 without `WWW-Authenticate` | All implemented and tested (`suresay/oauth.py`, `tests/test_oauth.py`). Linking means entering your SureSay pairing code |
| Visuals through MCP Apps | `understand` carries `_meta.ui.resourceUri = ui://suresay/cards.html`: the three cards render on an Echo Show or Fire TV, and that screen can pair as one of your devices, so a tap there is your own evidence |
| An add-on package | `alexa_plus/addon-package/addon.json`, six icon sizes, a 600×900 carousel, `/privacy`, `/terms` |
| Fast query responses (under 500 ms) | `home_status` and typed `understand` run in milliseconds; spoken `understand` is 870 ms p50 because it includes speech recognition |

A linked Alexa+ client gets exactly the agent's powers: it can understand, read and propose, never confirm. Until Alexa+ developer access opens, `alexa_skill/` runs the same flow as a classic Alexa skill. There, Alexa is a paired device, and the user's spoken "the second one" goes back as signed evidence.

![Cards](img/cards.png)

## How it works

![Architecture](architecture.png)

The agent can ask and propose, but it can't confirm.

- Every write tool on our MCP server only creates a pending card set.
- The set's one-time nonce goes only to the user's paired device, over a separate HMAC-signed channel, and never appears in any MCP result.
- Confirmation evidence is a tap, or the user's own audio, which the server transcribes itself.
- `confirm` checks that the evidence quotes the nonce, came from the user's device, is fresh and unused, clearly chooses a card, and that the action hasn't changed. Then it consumes the nonce with a single DynamoDB conditional write.

A prompt injection can make the agent *ask*. It can never make anything *happen*.

| AWS service | How SureSay uses it |
|---|---|
| Bedrock: Nova 2 Lite | Ranks three candidate meanings from noisy recognition, the phrasebook and home state; abstains when unsure; powers the agent |
| AgentCore Runtime | Hosts the Strands agent (direct code deploy) |
| AgentCore Memory | Per-user phrasebooks (blob events) and the agent's long-term facts |
| Strands Agents | The agent loop over MCP Streamable HTTP |
| Transcribe | Streaming recognition with per-user custom vocabularies; server-side transcription of confirmation audio |
| Polly | Reads the cards aloud; speaks confirmed sentences for the user |
| DynamoDB | The gate ledger with conditional one-time writes; home state |
| S3 | Private, expiring utterance and evidence audio |
| Lambda | The hub (MCP + device channel + web client) behind a function URL |

The MCP server is self-hosted, on spec 2025-11-25 over Streamable HTTP, and both the agent and the web client call it at runtime. The web client confirms through the MCP TypeScript SDK.

## Proof

Held-out speakers from TORGO, a public dysarthric speech corpus. Thresholds were tuned on two dev speakers (F03, M05) and results reported on six others (F01, F04, M01–M04). Baselines change one thing at a time: B0 is a plain assistant, B1 adds the phrasebook, and SureSay adds ranked cards, abstaining and the gate. All numbers come from scripts in `eval/` and are copied from `eval/REPORT.md`.

<!-- results:start -->
| Claim | Metric | B0 plain | B1 + phrasebook | SureSay | Data |
|---|---|---|---|---|---|
| Confirm heard right | false accepts | 62.8% | — | **2.6%** | 430 decisions, 6 test speakers |
| Meaning recovered | top-1 / top-3 | 31.5% / — | 92.6% / 96.3% | 73.1% / 73.1% | 50-phrase books, 6 test speakers |
| In the cards when unsure too | counting maybe cards | — | 96.3% (acts without asking) | **93.5%** | same |
| Abstains when unsure | correct "say again" | 0% | 0.0% | **100.0%** | out-of-book utterances |
| Never acts on a guess | acted on a wrong phrase without asking | 84.3% | 53.7% | **0%** | in-book + out-of-book |
| Nothing without consent | unconfirmed changes | 35 / 35 (no gate) | — | **0 / 50** | adversarial suite |
| Speed | understand p50 / p95 | — | — | 869.6 / 2434.6 ms | 100 dev clips, Lambda + Transcribe |
| Gate overhead | p50 / p95 | — | — | 48.9 / 58.1 ms | Lambda + DynamoDB |
| No regression | top-1, controls | 80.8% | — | 100.0% | control speakers |

SureSay column: SureSay (offline ranker); the Nova 2 Lite ranker is pending Bedrock access. B1 recovers more phrases at top-1 because it never abstains, and pays for it by acting on a wrong phrase without asking.
<!-- results:end -->

**What doesn't work yet, published on purpose** (full list in `eval/REPORT.md`):

<!-- negatives:start -->
1. **The most severe speakers lose recall to the abstain rule, and maybe cards only partly win it back.** Worst test speaker: M04. SureSay's confident cards hold their phrase 40.0% of the time at top-1, against 90.0% for B1, because it asks again on 60.0% of them. Offering its best guesses as maybe cards while asking again brings that speaker to 85.0% in the cards (93.5% over all test speakers), but maybe cards also appear on 47.2% of out-of-book utterances, where the user has to decline them. B1 never asks and acted on a wrong phrase 53.7% of the time; SureSay acted wrongly 0% of the time. Per-user thresholds are the next step.
2. **Strict confirmation costs retries.** On genuine yes/no/number answers from dysarthric speakers, SureSay recovered 83.3% (B0: 94.4%) and asked 8.6% of them to repeat. That is the price of the false-accept rate above; tap, keyboard and switch confirmation exist so a repeat is never a dead end.
3. **Recogniser biasing did not help confirmations.** On dev speakers (none: 1 false accepts, 77.8% recovered, core: 1 false accepts, 77.8% recovered, full: 2 false accepts, 77.8% recovered), no setting beat leaving the recogniser unbiased, so SureSay transcribes confirmations without bias. Biasing that raises recall without false accepts is open.
4. **The model arms are pending.** Nova 2 Lite is authorized on this account but every on-demand quota is 0 (increase requests filed; docs/FRICTION_LOG.md). The Strands agent is deployed on AgentCore Runtime and phrasebooks live in AgentCore Memory, but the agent cannot reason until Nova has quota, so turns fall back to direct answers. The Nova ranker and the Nova-agent safety arms are implemented and tested against stubs; no Nova number is reported until they run.
5. **Corpus caveats.** TORGO sentences are well-known reading passages that a large recogniser may have seen in training, and the phrasebooks are sentences rather than short home commands. Confirmation words are sparse in TORGO (a few per speaker), so per-speaker confirmation numbers rest on small counts.
6. **Unclear words heard as "yeah" or "OK".** 9 of SureSay's 11 false accepts on test speakers were the recogniser (transcribe-streaming) turning an unclear single word into a filler such as "Yeah" or "OK.", which the yes/no card accepts. That card guards the high-risk actions. A stricter yes vocabulary for that card is the candidate fix; it was found on test speakers, and dev has too few cases to tune it honestly, so it is reported here and not changed.
<!-- negatives:end -->

## Built during the window

Everything user-facing is new:

- the confirm gate (consent parser, stores, device pairing and signing, evidence, receipts, MCP proxy);
- the SureSay hub (MCP server, device channel, understand, actions, phrasebook, Polly read-back);
- the Strands agent, rewritten for Streamable HTTP and AgentCore Memory;
- the web client;
- the TORGO evaluation and the 50-case safety suite;
- the one-command deploy and teardown, and 246 tests.

## Open source

[confirm-gate-mcp](https://github.com/Prashant-thakur77/confirm-gate-mcp) (MIT, its own repository with CI on Python 3.12 and 3.13) is the gate on its own. `confirm-gate serve --upstream <any MCP server>` puts confirm-before-act, with an approval page, in front of any MCP server. Install: `pip install "git+https://github.com/Prashant-thakur77/confirm-gate-mcp"`. Why it matters: as assistants gain the power to act, prompt injection becomes a way to act. A gate that keeps the confirmation secret away from the model turns "never act without the user" from a prompt into a property of the code, for any MCP server.

## What's next

- A real Alexa+ integration once access opens.
- Per-user thresholds and recognition adapted from each user's own confirmations.
- Indian languages beyond Hinglish confirmations.
- A big-screen card layout for Fire TV.

Product feedback for every tool is in `docs/PRODUCT_FEEDBACK.md`, and the friction log is in `docs/FRICTION_LOG.md`.

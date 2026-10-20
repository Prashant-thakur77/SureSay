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

When the phrase is something to say to people rather than to a device ("I am thirsty"), SureSay speaks it aloud for you, clearly, once you've confirmed it.

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

| Claim | B0 | B1 | SureSay |
|---|---|---|---|
| Confirmations: false accepts | 62.3% | — | **1.4%** |
| Meaning recovered, top-1 | 33.3% | 98.1% | 89.8% |
| Out-of-book: says "say again" | 0% | 0% | **100%** |
| Acts on a wrong phrase without asking | 83.3% | 50.9% | **0%** |
| Unconfirmed state changes, 50-case adversarial suite | 35/35 (no gate) | — | **0/50** |
| Gate overhead on Lambda + DynamoDB | — | — | 47 ms p50 |

**What doesn't work yet, published on purpose:**

- On the most severe speaker, the abstain rule costs recall: 75% top-1 against B1's 100%, because SureSay asks again on a quarter of their phrases. B1 gets its number by never abstaining, and acts on a wrong phrase half the time. Per-user thresholds are the fix, and the gap stays open until then.
- Strict confirmation costs retries: 69% of genuine "yes" and number answers are accepted first time, against 83% for B0.
- Our AWS account's Bedrock, Transcribe and AgentCore access is pending a support case, so the Nova numbers are pending. They are not estimated. The SureSay column above uses the offline ranker.

## Built during the window

Everything user-facing is new:

- the confirm gate (consent parser, stores, device pairing and signing, evidence, receipts, MCP proxy);
- the SureSay hub (MCP server, device channel, understand, actions, phrasebook, Polly read-back);
- the Strands agent, rewritten for Streamable HTTP and AgentCore Memory;
- the web client;
- the TORGO evaluation and the 50-case safety suite;
- the one-command deploy and teardown, and 246 tests.

## Open source

`confirm-gate-mcp` (MIT) is the gate on its own. `confirm-gate serve --upstream <any MCP server>` puts confirm-before-act, with an approval page, in front of any MCP server. Install it from the repository: `pip install "git+https://github.com/Prashant-thakur77/SureSay#subdirectory=packages/confirm-gate-mcp"`.

## What's next

- A real Alexa+ integration once access opens.
- Per-user thresholds and recognition adapted from each user's own confirmations.
- Indian languages beyond Hinglish confirmations.
- A big-screen card layout for Fire TV.

Product feedback for every tool is in `docs/PRODUCT_FEEDBACK.md`, and the friction log is in `docs/FRICTION_LOG.md`.

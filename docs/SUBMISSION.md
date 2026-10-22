# Devpost submission, step by step

Everything to paste into the Devpost form, in the order the form asks for it. The images are in [`docs/devpost/`](devpost/), all 1500×1000 (3:2).

---

## Step 1 · Project overview

**Project name** (60 max)

```
SureSay: nothing happens until you choose
```

**Elevator pitch** (200 max)

```
Voice assistants mishear slurred speech, then act anyway. SureSay shows its 3 best guesses as big cards and does nothing until you choose. For people with dysarthria, on Alexa+ and AWS.
```

**Thumbnail:** [`devpost/00-thumbnail.jpg`](devpost/00-thumbnail.jpg)

---

## Step 2 · Project details

### About the project

Paste everything between the lines into the "About the project" box (it takes Markdown).

---

```markdown
## Why it matters

After a stroke, or with Parkinson's, ALS or cerebral palsy, speech can come out slow, soft or slurred. This is dysarthria, and the mind behind it is exactly the same. These are the people who would gain most from running their home by voice, and voice assistants fail them most: on real dysarthric speech, a plain recogniser got a sentence's words exactly right only a third of the time.

Getting it wrong is not the worst part. **Acting on it is.** "Lock the door" heard as "unlock the door" unlocks it. As Alexa+ gains the power to act, a misheard command that acts is worse than no command at all. So people stop talking to it.

## What it does

SureSay is a voice assistant that knows when it isn't sure, and never acts on a guess.

1. **Say it your way**, or type it. Recognition is primed with your own phrasebook.
2. **See three guesses.** He says "fan on"; SureSay hears "van on". Instead of guessing, it shows its three best guesses as huge numbered cards and reads them aloud. If it isn't confident at all, it says so and asks again.
3. **Choose.** Say "two", "the second one", "haan", "do number", or tap, press a key or use one switch. Risky actions (unlock, order, call) ask a second time.
4. **Only then does it happen**, and a consent receipt records who confirmed what, when and how.

Around that core:

- **"Don't" never becomes "do."** "Don't unlock the door" sounds like "unlock the door", so a negated command offers no cards: SureSay says what it heard and that nothing will change.
- **Talk to someone.** Be understood by people, not only machines. He says what he wants to tell the person in front of him, picks the right sentence, and SureSay says it clearly out loud and shows it huge, turned around for someone across the table.
- **Speak for me.** One tap on everyday sentences, in English and Hindi.
- **Practice.** A few sentences a day and an honest clarity score showing which words came through. Every try teaches SureSay his voice. On TORGO the score follows severity (rank correlation 0.85).
- **Help.** One press offers to call or message family, and they get an alert.
- **Timeline** for family, with "changes without you: 0".
- **Teach** SureSay your own words; it also learns from your confirmations, but never a phrase that already means something else.
- **Your devices:** every screen, Alexa link and assistant that can show your cards, each one tap from unpaired.
- **Accessible by design:** WCAG 2.2 AA, voice, tap, keyboard or a single switch, three themes, calm mode, TV mode, and Hinglish confirmations.

**Try it now, no sign-up:** "Try it now" opens a private demo home of your own.

## Built for Alexa+

SureSay is a **self-hosted MCP server** built to the Alexa+ add-on requirements, and also a working Alexa skill today.

- **MCP spec 2025-11-25 over Streamable HTTP**, at `/mcp` on AWS Lambda.
- **Account linking:** OAuth 2.1 with PKCE (S256) and Protected Resource Metadata. Linking means entering your SureSay pairing code; unpairing the link ends every token at once.
- **MCP Apps:** `understand` returns `ui://suresay/cards.html`, so the three cards render on an Echo Show or Fire TV.
- **An add-on package**, with icons, carousel, privacy and terms.
- **A classic Alexa skill**, paired as the user's own voice device: Alexa reads the cards, and his spoken "the second one" goes back as signed evidence.

A linked Alexa+ client gets exactly the agent's powers: it can understand, read and propose, never confirm.

## How we built it

**The core rule: the AI can ask, but only the user can approve.**

- Every write tool on the MCP server only creates a pending card set.
- The set's one-time code goes only to the user's paired device, over a separate HMAC-signed channel, and never into any MCP result.
- `confirm` runs the action only if the evidence is the user's own tap, or his own recording transcribed on the server, and it passes 13 named checks: right device, right card set, fresh, unused, clearly chooses a card, action unchanged since shown. The code is then consumed by a single DynamoDB conditional write.

A prompt injection can make the agent *ask*. It can never make anything *happen*.

**On AWS:**

- **Amazon Bedrock AgentCore Runtime** hosts a **Strands** agent, which calls the MCP server over Streamable HTTP.
- **AgentCore Memory** keeps per-user phrasebooks and long-term facts.
- **Amazon Nova 2 Lite** ranks the three meanings (code ready, waiting on quota).
- **Amazon Nova 2 Sonic** is a second speech recogniser, and the real-model agent in the safety tests.
- **Amazon Transcribe** streams recognition with per-user custom vocabularies.
- **Amazon Polly** reads the cards aloud and speaks for the user.
- **DynamoDB** holds the gate ledger with one-time conditional writes; **S3** stores private, expiring audio.
- **Lambda** runs the hub and the Alexa skill; **SNS** sends family alerts; **CloudWatch** carries a safety dashboard.
- One command deploys and tears everything down.

The web client is React and TypeScript, and confirms through the MCP TypeScript SDK. The safety layer is open source on its own: **confirm-gate-mcp** (MIT) puts confirm-before-act in front of *any* MCP server.

## Proof

Real dysarthric speech from the TORGO corpus: thresholds tuned on two speakers, results on six others it never saw.

| | Plain assistant | SureSay |
|---|---|---|
| Misheard words taken as a "yes" or a choice | 62.8% | **2.3%** (430 decisions) |
| Acted on a wrong phrase without asking | 84.3% | **0.0%** |
| A real AI agent (Amazon Nova 2 Sonic): changes nobody confirmed | 11 / 35 | **0 / 35** |
| Adversarial attacks (injections, near-misses, forged confirmations) that changed anything | 35 / 35 | **0 / 50** |

Every number comes from scripts in `eval/` and is copied from `eval/REPORT.md`, including a section on what doesn't work yet. The worst case is the most severe speakers: SureSay asks them to repeat more often, and its "maybe" cards win most of that back.

## Challenges we ran into

- **Model access on a new account.** Nova 2 Lite was authorised, but every on-demand quota was 0, and AgentCore started at 0 agents. We built every Nova path against stubs, kept an offline ranker, and measured **Nova 2 Sonic**, which did run, as both a recogniser and a real agent.
- **MCP SDK 2.x** broke the old server code, and Strands pins `mcp<2.2`: a port and a version dance.
- **Hearing "yes" safely.** "Ek second" (one moment) was read as "option 2"; "ok hang on" as a yes. Every one became a failing test, then a fix.
- **Three adversarial security reviews** found real bugs, including pairing brute force through the public demo and an Alexa answer landing on a card set the user never heard. All were fixed test-first.
- **Two speech SDKs** needing different versions of the same native library, and IAM changes that only took effect after a redeploy.

## Accomplishments that we're proud of

- False yeses on real dysarthric speech fell from **62.8% to 2.3%**, and SureSay **never** acted on a wrong guess.
- A real model as the agent: **11 unconfirmed changes without the gate, 0 with it.**
- A working, accessible product anyone can try in one click, an Alexa skill, and an Alexa+-ready MCP server.
- An open-source gate any MCP developer can use, with 355 tests and a strict mode for servers you don't control.
- More than 450 tests, honest metrics, and a "what doesn't work yet" section.

## What we learned

- For people who are misheard most, the safest answer is often "I'm not sure, which of these?", and that question has to be fast, big and dignified.
- Safety you can't measure isn't safety: the attack suite changed the design more than any review.
- An AI that can act needs a second channel for consent. A yes inside the chat can be forged; a code it never sees can't.

## What's next

- A full Alexa+ integration as access opens, with the cards on Echo Show and Fire TV.
- Per-user thresholds and recognition that adapts from each person's own confirmations.
- Indian languages beyond Hinglish confirmations.
- Work with speech therapists and stroke-recovery groups to test with real users.
```

---

### Built with

Type each into the "Built with" field:

```
python, typescript, react, vite, model-context-protocol, mcp-apps, strands-agents, amazon-bedrock, amazon-bedrock-agentcore, amazon-nova, amazon-transcribe, amazon-polly, amazon-dynamodb, amazon-s3, aws-lambda, amazon-sns, amazon-cloudwatch, aws-iam, alexa-skills-kit, oauth2, starlette, playwright, whisper
```

### "Try it out" links

```
https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws
https://github.com/Prashant-thakur77/SureSay
https://github.com/Prashant-thakur77/confirm-gate-mcp
```

### Video demo link

```
https://youtu.be/dvMJsOJvrfg
```

The film is on YouTube, public (the same file is attached to the latest GitHub release).

- **YouTube title:** `SureSay: a voice assistant that never acts on a guess (Alexa+ · AWS)`
- **YouTube description:**

  ```
  Voice assistants mishear people with dysarthria, after a stroke, or with Parkinson's, ALS or cerebral palsy, and then act anyway. SureSay shows its three best guesses as big cards, and nothing happens until the user chooses, by voice or tap.

  Try it (no sign-up): https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws
  Code: https://github.com/Prashant-thakur77/SureSay
  Open-source confirm gate for any MCP server: https://github.com/Prashant-thakur77/confirm-gate-mcp

  Built for the Build, Ship, Shape Amazon Developer Hackathon (Alexa+ track) with Amazon Bedrock AgentCore, Strands Agents, Amazon Nova, Transcribe, Polly, DynamoDB and Lambda.
  ```

- **YouTube thumbnail:** [`devpost/youtube-thumbnail.jpg`](devpost/youtube-thumbnail.jpg) (1280×720, 16:9; in YouTube Studio: Details → Thumbnail → Upload file).

### Image gallery

Upload in this order, with these captions:

| File | Caption |
|---|---|
| `01-three-guesses.jpg` | He says "fan on", SureSay hears "van on". Instead of guessing, it shows its three best guesses. |
| `02-confirmed-receipt.jpg` | He says "one". Every check passes, the fan turns on, and a consent receipt records who confirmed what, and how. |
| `03-asks-twice.jpg` | Anything risky asks twice: "Unlock the front door?" Yes or No, on his own device. |
| `04-dont-never-becomes-do.jpg` | "Don't unlock the door" never becomes "unlock": no cards, nothing changes. |
| `05-talk-to-someone.jpg` | Talk to someone: his sentence, said clearly out loud and shown huge for the person listening. |
| `06-speak-for-me.jpg` | Speak for me: one tap on everyday sentences, in English and Hindi. |
| `07-practice.jpg` | Practice: an honest clarity score, with the words that didn't come through marked. |
| `08-timeline.jpg` | Timeline for family: every confirmation, and changes without him: 0. |
| `09-results.jpg` | Measured, not promised: real dysarthric speech and a 50-case attack suite. |
| `10-architecture.jpg` | The AI can ask, only the user can approve: the code never reaches the model. |
| `11-open-source-gate.jpg` | confirm-gate-mcp (MIT): the same gate in front of any MCP server. |

---

## Step 3 · Additional info (the form, field by field)

**Upload a File** (optional): `~/Videos/suresay/SureSay-judges-pack.zip`. It holds the evaluation report, judges' guide, AWS integrations, product feedback, feature requests, friction log, architecture and results image.

| Field | Answer |
|---|---|
| Submitter Type | Individual |
| Organization Name | N/A |
| Country of Residence | India |
| Canada province | N/A |
| Primary Track(s) | **Alexa+** (only this one) |
| Code repository URL | `https://github.com/Prashant-thakur77/SureSay` |
| New or existing prior to August 31, 2026? | Your call (see the note below) |
| AWS Builder Mini Challenge? | Yes |
| Open Source Mini Challenge? | Yes |
| OS: Contribution URL | `https://github.com/Prashant-thakur77/confirm-gate-mcp` |
| OS: Project Repository URL | `https://github.com/Prashant-thakur77/SureSay` |
| OS: GitHub Username | `Prashant-thakur77` |
| Friction Log (URL) | `https://github.com/Prashant-thakur77/SureSay/blob/main/docs/FRICTION_LOG.md` |
| Project Testing Link | `https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws` |
| The three eligibility boxes | Tick all three, if true for you |
| Level of learning | The highest option |
| AI value for your career? | Yes |

**New or existing?** The SureSay repository and product were created during the window (first commit 20 Oct 2026). If you reused code you wrote before 31 Aug (the earlier agent template or Beacon's consent pieces), choose **Existing** and use the explanation below. Otherwise choose **New**.

> SureSay is new in this window: the product, the confirm gate as an open-source package, the MCP server with MCP Apps and OAuth account linking, the Strands agent on AgentCore, the Alexa skill, the accessible web client, the TORGO evaluation and the safety suite. [Add one line here naming any earlier code you reused and what it was used for.] The film shows each feature working: https://youtu.be/dvMJsOJvrfg

### AWS Builder: "Which AWS services did you incorporate and how?"

```
SureSay runs entirely on AWS (us-east-1), with one-command deploy and teardown. Every service below does real work; docs/AWS_INTEGRATIONS.md in the repo maps each one to the code that calls it, its IAM permission, and how to verify it.

- Amazon Bedrock AgentCore Runtime: hosts SureSay's Strands agent (direct code deploy). The hub invokes it per turn.
- Strands Agents SDK: the agent loop. It connects to SureSay's own MCP server over Streamable HTTP (spec 2025-11-25), where it can understand, read and propose, but never confirm.
- Amazon Bedrock AgentCore Memory: per-user phrasebooks as blob events, plus the agent's long-term facts (semantic strategy).
- Amazon Nova 2 Lite (Bedrock Converse): ranks the three most likely meanings as JSON checked against the action catalog, and abstains when unsure. Built and tested; it runs as soon as the account's on-demand quota (currently 0, increase requested) opens.
- Amazon Nova 2 Sonic (Bedrock bidirectional streaming): a second speech recogniser measured on real dysarthric speech, and the real-model agent in our safety suite (11 unconfirmed changes without the gate, 0 with it).
- Amazon Transcribe streaming: recognises each request, primed with a per-user custom vocabulary built from the phrasebook; transcribes the user's own confirmation audio on the server; and ran the whole TORGO evaluation.
- Amazon Polly (neural, Kajal): reads the three cards aloud and speaks confirmed sentences for the user ("Talk to someone", "Speak for me").
- Amazon DynamoDB: the confirm gate's ledger. The one-time nonce is consumed by a conditional write, so exactly one of any racing confirmations wins (tested on the real service). Also home state and events.
- Amazon S3: private, encrypted, 30-day utterance and evidence audio.
- AWS Lambda + Web Adapter: the whole hub (MCP server, signed device channel, OAuth, web client) behind one function URL. Lambda also runs the Alexa skill, paired as the user's voice device.
- Amazon SNS: alerts family when the user presses Help or confirms a high-risk action.
- Amazon CloudWatch: safety metrics (confirmed, refused, cancelled, by caller) and latency via Embedded Metric Format, on a SureSay dashboard.
- AWS IAM: a least-privilege role scoped to the table, bucket, models and agent.
- AWS Price List API: real prices for the cost-per-1,000-turns estimate. Service Quotas: diagnosing new-account limits.
```

### Open Source: "what you did, how it works, and why it matters"

Use the text block in the **Open Source mini challenge** section further down this file (unchanged).

### Feature Requests (optional)

```
1. Alexa+: a host-mediated confirmation primitive for MCP add-ons, e.g. elicitation answered by the user's voice or tap on the device and delivered to the server out of band from the model. Why: write tools need a confirmation the model cannot fake; today every add-on must build its own device channel, as SureSay does. Priority: Critical.
2. Alexa+: pass a device-attested "user said" signal with tool calls (the ASR transcript and confidence, signed by Alexa). Why: lets a server tell the user's own words from the model's paraphrase, the core of consent. Priority: Important.
3. Amazon Transcribe: a shorter billing minimum for streaming, or per-second billing for short utterances. Why: voice UIs send 1-3 s clips; the 15 s minimum makes recognition about 60% of our cost per turn. Priority: Important.
4. Transcribe: an abstain signal or calibrated confidence, and alternatives, in streaming results. Why: an accessible assistant should ask again rather than guess. Priority: Important.
5. Bedrock: name the cause when a new account has zero quotas ("this account's quota is 0", with a link to request it) instead of "Operation not allowed" or "Too many tokens per day". Why: we lost hours checking IAM for an account-state problem. Priority: Important.
6. AgentCore Memory: a "latest state" read or compacted snapshot per session. Why: replaying 42 events took 9 s; voice needs sub-second reads. Priority: Important.
7. MCP Python SDK: emit [] as text for an empty list result, and publish a 1.x to 2.x migration table. Why: an empty list produced no content block and crashed clients reading content[0]. Priority: Nice-to-have.
8. Strands Agents: an MCP SDK compatibility table (currently mcp<2.2). Priority: Nice-to-have.
9. Polly: an SSML preset for slow, clear speech for listeners with cognitive or hearing differences. Priority: Nice-to-have.
```

### Testing instructions (under the testing link)

```
No sign-up. Open the link, choose "Start quietly" (or "Start with voice"), then "Try it now": you get your own private demo home; every device, contact and shop is simulated.
1. Tap the "van on" example (or type it): three numbered cards appear. Press 1 or tap the first card: the consent trail ticks through the gate's checks, the fan turns on, and a receipt appears.
2. Type "unlock the front door" and choose it: a second card asks "Unlock the front door?". Press Esc or tap No: nothing changes.
3. Type "don't unlock the door": no cards, and SureSay says nothing will change.
4. Talk to someone tab: type "I am proud of you", Offer it, choose it, then "Show it to them".
5. Help (top right): offers to call or message family, still confirmed by you.
The MCP endpoint is /mcp on the same URL (Streamable HTTP, 2025-11-25); the agent cannot confirm anything there by design. A five-minute guide: https://github.com/Prashant-thakur77/SureSay/blob/main/docs/JUDGES.md
```

### Feedback Question 1: which developer tools, APIs and SDKs did you use, and for what?

```
- Amazon Bedrock AgentCore Runtime (starter toolkit, direct code deploy): hosts our Strands agent.
- Amazon Bedrock AgentCore Memory (MemoryClient + Strands session manager): per-user phrasebooks and agent facts.
- Strands Agents SDK: the agent loop, connected to our MCP server over Streamable HTTP.
- Amazon Bedrock Converse API with Amazon Nova 2 Lite: ranking three candidate meanings (built and tested; waiting on quota).
- Amazon Bedrock bidirectional streaming (aws-sdk-bedrock-runtime) with Amazon Nova 2 Sonic: a second speech recogniser, and a real-model agent in our safety tests.
- Amazon Transcribe streaming (amazon-transcribe SDK) with custom vocabularies: speech recognition and the TORGO evaluation.
- Amazon Polly (neural voice Kajal): reading cards aloud and speaking for the user.
- Amazon DynamoDB (conditional writes): the confirm gate's one-time ledger. Amazon S3: private audio.
- AWS Lambda + Lambda Web Adapter + function URLs: the hub and the Alexa skill.
- Alexa Skills Kit: the Alexa skill that pairs as the user's voice device.
- Alexa+ MCP add-on toolkit docs: building the MCP server, OAuth account linking and MCP Apps to the add-on requirements.
- Amazon SNS (family alerts), Amazon CloudWatch (Embedded Metric Format, dashboard), AWS IAM, Service Quotas, AWS Price List API, AWS CLI.
- MCP Python SDK 2.x (server, proxy and tests) and MCP TypeScript SDK (the web client confirms through it).
```

### Feedback Question 2: what worked well?

```
- AgentCore Runtime: direct_code_deploy is excellent: it cross-compiled our dependencies for ARM64, created the role and uploaded the package with no Docker, in about two minutes.
- AgentCore Memory: a pleasant MemoryClient; blob events made a per-user phrasebook an append-only log; the Strands session manager is one constructor.
- Strands Agents: the best part of the stack. MCPClient(url=..., headers=...) connected to our Streamable HTTP server first time, and headers made per-user routing trivial.
- Nova 2 Lite (Converse): a temperature-0, JSON-only ranker with a stubbed client was easy to unit-test, and it is cheap enough to call on every turn.
- Nova 2 Sonic: once running, it took text turns and called tools, so it served as a real agent in our safety suite; as a recogniser it was as safe as Transcribe on held-out speakers at about a third of the cost per clip.
- Transcribe: after activation, streaming just worked, about 0.8 s at p50 in-region, and per-user custom vocabularies are exactly what atypical speech needs.
- Polly: worked first time; Kajal (en-IN) is warm and clear; PCM output also gave us clean test audio.
- DynamoDB: conditional writes carry our safety property: 150 trials of 16 racing writers on the real service, exactly one winner every time.
- S3, SNS, CloudWatch EMF: each took minutes. Lambda + Web Adapter ran our whole Starlette app as a function URL with no code changes; the gate adds 47 ms at p50.
- MCP SDKs: stateless Streamable HTTP and the in-memory test client gave fast tests; the TypeScript SDK's custom fetch let us sign every request without forking it.
```

### Feedback Question 3: what needs work?

```
- Bedrock / Nova 2 Lite: on a new account calls failed with "Operation not allowed", then (after authorisation) "Too many tokens per day", because every on-demand quota was 0. Neither message names the cause. Service Quotas rejects requests below the default (2,000 RPM), so a modest request becomes a support case. Still pending as we submit.
- AgentCore Runtime: "maxAgents limit exceeded" because Total Agents per Account was 0 on a new account; also a warning that X-Ray needs a CloudWatch Logs destination. Please check quotas before packaging and set up the trace destination automatically.
- AgentCore Memory: CreateMemory said "Access Denied … contact customer support" (a quota of 0). Reading a phrasebook back means replaying events: 9 s for 42 events, too slow for voice, so we read from DynamoDB and write through to Memory.
- Nova 2 Sonic: the Python bidirectional SDK needs awscrt 0.32 while the Transcribe streaming SDK pins 0.26, so they can't be installed together normally (we installed one with --no-deps). IAM changes needed a redeploy before warm containers stopped returning AccessDenied. "amazon.nova-sonic-v1:0" is an invalid model id in us-east-1; a tool-using session also needs silence fed between turns.
- Transcribe: "SubscriptionRequiredException: The AWS Access Key Id needs a subscription" for ~4.5 h on a new account reads like a key problem; a custom vocabulary failed minutes later with "incorrectly formatted term on line 115" (the term was i'm); the 15-second billing minimum dominates short voice turns; unbiased, it can turn an unclear word into "Yeah" or "OK".
- Strands: pins mcp<2.2, so the newest MCP SDK can't be installed beside it; a compatibility table would help.
- MCP Python SDK 2.x: no single 1.x to 2.x migration table; a tool returning an empty list produced no content block and crashed clients reading content[0].
- Lambda: our 56 MB zip had to go through S3; public function URLs now need both InvokeFunctionUrl and InvokeFunction.
- DynamoDB: a query on a still-backfilling GSI fails; the popular moto mock is not atomic under threads (easy to mistake for your own bug).
- Polly: we'd like an SSML preset for slow, clear speech.
Full log with steps and workarounds: docs/FRICTION_LOG.md.
```

### Feedback Question 4: how was onboarding (zero to hello world)?

```
- Strands Agents, Polly, S3, SNS, DynamoDB, CloudWatch EMF: minutes. First call worked.
- Lambda + Web Adapter: quick; the whole hub ran behind a function URL with no code changes.
- AgentCore Runtime: two minutes once the agent quota was raised; blocked until then by a quota of 0 on a new account.
- AgentCore Memory: easy API, blocked first by a "Memories" quota of 0.
- Transcribe: blocked ~4.5 h by an account-activation error that looked like a key problem, then smooth.
- Nova 2 Sonic: the longest of the stack: a new streaming SDK, a native-library version conflict, an IAM redeploy, and finding the right model id.
- Nova 2 Lite: not reached; authorised but with zero on-demand quota through the window, so everything runs against stubs plus an offline ranker until the quota opens.
- Alexa+ MCP add-on docs: clear requirements (spec version, transport, OAuth metadata, MCP Apps); we built to them, and the classic Alexa Skills Kit path let us demo on real Alexa meanwhile.
The common theme: on a new account most "access denied" or "not allowed" errors were quotas of 0, and nothing said so.
```

### Feedback Question 5: would you build with these again?

```
Yes. Strands + AgentCore + MCP is the right shape for an agent that has to stay behind a safety gate: the agent runs managed, talks to our own MCP server, and can never hold the user's confirmation. Transcribe, Polly and DynamoDB carried the product's core with almost no friction once running, and Nova 2 Sonic surprised us as both a recogniser and an agent. Alexa+ add-ons over MCP are the most promising way to bring an accessible, confirm-first assistant to people's homes, and we'd ship SureSay there as soon as access opens. What would make it easier: name zero quotas in error messages, and give MCP add-ons a host-mediated confirmation primitive.
```

### Which AI tools have you leveraged?

```
Claude Code (Anthropic) for planning, coding, test-writing, security reviews and the scripted video pipeline; Amazon Nova 2 Sonic and Nova 2 Lite inside the product; Chatterbox TTS for the film's narration; Whisper (local) for checking narration takes and as an offline speech recogniser in the evaluation.
```

---

### Open Source mini challenge

| Field | Answer |
|---|---|
| Contribution URL | https://github.com/Prashant-thakur77/confirm-gate-mcp |
| Project repository URL | https://github.com/Prashant-thakur77/SureSay |
| GitHub username | Prashant-thakur77 |

**What you did, how it works, why it matters:**

```
confirm-gate-mcp is a new MIT-licensed open-source project, released during the hackathon (v0.2.0 to v0.4.0): confirm-before-act for any MCP server. `confirm-gate serve --upstream <server>` puts it in front of an existing server with no code changes; `GatedServer` builds it into your own.

How it works: read tools pass straight through. Every write tool returns a pending card instead of running. The one-time nonce for that card goes only to the user's paired device, over a channel where every request is HMAC-signed with a key the agent never holds. `confirm` runs the write only when the evidence from that device passes every named check (paired device, this card set, not expired, not replayed, the user's words really choose a card, arguments unchanged since shown, nonce used once, atomically in every store), and every run leaves a receipt. Voice evidence is the user's own recording, transcribed on the server, with an English and Hinglish consent parser that refuses hedges like "hang on" or "ek second". `--strict` ignores the upstream's read-only claims, since MCP tool annotations are hints from the server, so the gate is safe in front of servers you didn't write. It runs on memory, SQLite or DynamoDB with the same one-time guarantees, and comes with 355 tests, CI on Python 3.12 and 3.13, a packaging check, a Strands-on-Bedrock example and a built-in approval page.

Why it matters: as agents gain the power to act, prompt injection becomes a way to act. This turns "never act without the user" from a prompt into a property of the code. In SureSay's safety suite a real model (Amazon Nova 2 Sonic) as the agent made 11 unconfirmed changes in 35 cases without the gate, and 0 behind it; a worst-case scripted agent made 0 in 50 adversarial cases, including forged confirmations. It started as the safety layer of SureSay, for people with dysarthria, whose speech is misheard most, but nothing in it is specific to speech.
```


---

## Step 4 · Before you press Submit

- [ ] YouTube video is **Public** and the link plays.
- [ ] Thumbnail and gallery are uploaded, with captions.
- [ ] Both mini challenges are ticked and their fields filled.
- [ ] The repo is public with the MIT license (it is).
- [ ] Open the live link in a private window once: "Try it now" works.

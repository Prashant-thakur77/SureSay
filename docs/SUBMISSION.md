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

Your YouTube link. Upload `SureSay.mp4` from https://github.com/Prashant-thakur77/SureSay/releases/latest. Set it to **Public**, in English. Not "unlisted"; Devpost needs public.

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

## Step 3 · Additional info

**Which track(s)?** Alexa+

**Which mini challenge(s)?** AWS Builder, and Open Source

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

### Product feedback (and AWS Builder: services used and how)

Paste this summary first, then the whole of [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md):

```
AWS services and how SureSay uses them (full table with code paths, IAM and how to verify each: docs/AWS_INTEGRATIONS.md in the repo): a Strands agent on Amazon Bedrock AgentCore Runtime with AgentCore Memory, calling SureSay's MCP server over Streamable HTTP; Amazon Nova 2 Lite ranks the three meanings (code ready, waiting on quota); Amazon Nova 2 Sonic as a second speech recogniser and as a real-model agent in the safety suite; Amazon Transcribe streaming with per-user custom vocabularies; Amazon Polly reads the cards aloud and speaks for the user; DynamoDB holds the gate ledger with conditional one-time writes; S3 stores audio privately; the whole hub runs on AWS Lambda behind a function URL; the Alexa skill runs on Lambda; SNS sends family alerts; CloudWatch carries the safety metrics and dashboard; one command deploys and tears down everything.
```

### Other fields

| Field | Answer |
|---|---|
| Did the project exist before the hackathon? / What was built during the window | "Built during the window" in [DEVPOST.md](DEVPOST.md). Add your own note on any earlier code you reused. |
| Feature requests (optional) | [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md) |
| Friction log (optional, up to +10%) | [FRICTION_LOG.md](FRICTION_LOG.md) |
| Testing instructions, if asked | Open the live link, choose "Start quietly", then "Try it now". Type "van on" and pick a card; type "unlock the front door" to see it ask twice; type "don't unlock the door". Five-minute guide: [JUDGES.md](JUDGES.md). |

---

## Step 4 · Before you press Submit

- [ ] YouTube video is **Public** and the link plays.
- [ ] Thumbnail and gallery are uploaded, with captions.
- [ ] Both mini challenges are ticked and their fields filled.
- [ ] The repo is public with the MIT license (it is).
- [ ] Open the live link in a private window once: "Try it now" works.

# Devpost form, field by field

Copy each answer into the matching field. Longer answers live in the linked files.

## Basics

| Field | Answer |
|---|---|
| Project name | SureSay |
| Tagline | Three big guesses, and nothing happens until you choose. A voice assistant for people whose speech other assistants mishear. |
| Try it | https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws ("Try it now", no sign-up) |
| Code repository | https://github.com/Prashant-thakur77/SureSay (MIT) |
| Video | YouTube link (upload `SureSay.mp4` from the latest release: public, English, 2:58) |
| Description | [DEVPOST.md](DEVPOST.md) |
| Built with | python, typescript, react, vite, mcp, strands-agents, amazon-bedrock, amazon-nova, bedrock-agentcore, amazon-transcribe, amazon-polly, amazon-dynamodb, amazon-s3, aws-lambda, amazon-sns, amazon-cloudwatch, alexa-skills-kit |

## Track and mini challenges

| Field | Answer |
|---|---|
| Primary track | Alexa+ (a self-hosted MCP server, spec 2025-11-25, Streamable HTTP, with MCP Apps; plus a working Alexa skill as the user's voice device) |
| Mini challenges | AWS Builder; Open Source |

## Open Source mini challenge

| Field | Answer |
|---|---|
| Contribution URL | https://github.com/Prashant-thakur77/confirm-gate-mcp |
| Project repository URL | https://github.com/Prashant-thakur77/SureSay |
| GitHub username | Prashant-thakur77 |

**What I did, how it works, why it matters** (paste as is):

> confirm-gate-mcp is a new MIT-licensed open-source project, released during the hackathon (v0.2.0 to v0.4.0): confirm-before-act for any MCP server. `confirm-gate serve --upstream <server>` puts it in front of an existing server with no code changes; `GatedServer` builds it into your own.
>
> How it works: read tools pass straight through. Every write tool returns a pending card instead of running. The one-time nonce for that card goes only to the user's paired device, over a channel where every request is HMAC-signed with a key the agent never holds. `confirm` runs the write only when the evidence from that device passes nine named checks (paired device, this card set, not expired, not replayed, the user's words really choose a card, arguments unchanged since shown, nonce used once, atomically in every store), and every run leaves a receipt. Voice evidence is the user's own recording, transcribed on the server, with an English and Hinglish consent parser that refuses hedges like "hang on" or "ek second". `--strict` ignores the upstream's read-only claims, since MCP tool annotations are hints from the server, so the gate is safe in front of servers you didn't write. It runs on memory, SQLite or DynamoDB with the same one-time guarantees, and comes with 355 tests, CI on Python 3.12 and 3.13, a packaging check, a Strands-on-Bedrock example and a built-in approval page.
>
> Why it matters: as agents gain the power to act, prompt injection becomes a way to act. This turns "never act without the user" from a prompt into a property of the code. In SureSay's safety suite a real model (Amazon Nova 2 Sonic) as the agent made 11 unconfirmed changes in 35 cases without the gate, and 0 behind it; a worst-case scripted agent made 0 in 50 adversarial cases, including forged confirmations. It started as the safety layer of SureSay, for people with dysarthria, whose speech is misheard most, but nothing in it is specific to speech.

## AWS Builder mini challenge

The form asks for this inside the Product feedback answer. Paste [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md) and add this summary at the top:

> AWS services and how SureSay uses them (full table with code paths, IAM and how to verify each: [AWS_INTEGRATIONS.md](AWS_INTEGRATIONS.md)): a Strands agent on Amazon Bedrock AgentCore Runtime with AgentCore Memory, calling SureSay's MCP server over Streamable HTTP; Amazon Nova 2 Lite ranks the three meanings (code ready, waiting on quota); Amazon Nova 2 Sonic as a second speech recogniser and as a real-model agent in the safety suite; Amazon Transcribe streaming with per-user custom vocabularies; Amazon Polly reads the cards aloud and speaks for the user; DynamoDB holds the gate ledger with conditional one-time writes; S3 stores audio privately; the whole hub runs on AWS Lambda behind a function URL; the Alexa skill runs on Lambda; SNS sends carer alerts; CloudWatch carries the safety metrics and dashboard; one command deploys and tears down everything.

## Other fields

| Field | Answer |
|---|---|
| Product feedback | [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md) |
| What was built during the window | "Built during the window" in [DEVPOST.md](DEVPOST.md) |
| Feature requests (optional) | [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md) |
| Friction log (optional, up to +10%) | [FRICTION_LOG.md](FRICTION_LOG.md) |
| Judges' quick guide | [JUDGES.md](JUDGES.md) |

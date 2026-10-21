# Changelog

## 1.1.0 (21 Oct 2026)

- **Talk to someone:** be understood by people, not only machines. His words become up to three sentences to say (as heard, and his closest phrasebook sentences); nothing is said until he chooses; then it is spoken and shown huge, with a full-screen listener view that turns around.
- **Practice:** five sentences a day, an honest clarity score (no phrasebook priming), missed words marked, streaks and progress; every try teaches SureSay his voice. New eval: on TORGO the score follows severity (rank correlation 0.85; severe 44%, mild 97%; the score saturates for mild speech).
- **Help:** one press offers to call or message his carer, confirmed like everything else; the carer is alerted.
- Amazon Nova 2 Sonic as a second recogniser and as the agent in the safety suite (11 of 35 unconfirmed changes without the gate, 0 with it).
- Transcribe streaming has a 30 s timeout; a hung stream no longer hangs a turn.
- The film: rebuilt around the story, 2:58.

## 1.0.0 (21 Oct 2026)

First release.

- **The product:** three big, numbered, read-aloud guesses; nothing happens until the user confirms by voice, tap, key or one switch. Covers the home, calls and messages, the cart, Speak for me (Hindi tiles read in Hindi), Teach, the doorbell, the Timeline, Your devices and TV mode.
- **Safety:** the confirm gate (confirm-gate-mcp 0.3.1); a negated command ("don't unlock the door") offers no cards; high-risk actions ask twice; receipts.
- **Alexa+:**
  - MCP over Streamable HTTP (2025-11-25), with cards as an MCP App;
  - OAuth 2.1 + PKCE account linking with revocable links;
  - an add-on package;
  - a working classic Alexa skill.
- **AWS:**
  - Lambda and DynamoDB;
  - S3;
  - Transcribe (per-user vocabularies);
  - Polly;
  - Amazon Nova 2 Sonic (a second recogniser, and the agent in the safety suite);
  - Bedrock AgentCore Runtime and Memory;
  - Strands Agents;
  - SNS carer alerts;
  - CloudWatch metrics and a dashboard.
- **Evaluation** on held-out TORGO dysarthric speakers, with baselines, two runs and three recognisers: [eval/REPORT.md](eval/REPORT.md).
- **The film:** `video/` builds it from code.

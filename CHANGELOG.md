# Changelog

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

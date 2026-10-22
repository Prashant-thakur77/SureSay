# Security

## Reporting a vulnerability

Please open a private security advisory on this repository ("Security" tab → "Report a vulnerability"). Include steps to reproduce; a failing test is ideal. Expect an answer within a few days.

## What SureSay guarantees

- **The model can never confirm a write.** Every write tool on the MCP server only proposes a card set. Its one-time code goes only to the user's paired device over an HMAC-signed channel, and never appears in an MCP result, log or receipt. `confirm` requires evidence from that device: a tap, the user's own audio (transcribed by the server), or the transcript of a voice device the operator paired as one.
- **One-time use is atomic.** Codes, evidence and refresh tokens are consumed with conditional writes (DynamoDB, SQLite transactions); nothing is get-then-put.
- **High-risk actions ask twice**, each with its own code; on the final card no hedge, question or unreadable word counts as yes.
- **Every change leaves a receipt**: who confirmed what, when, on which channel, with the evidence fingerprint.

## How it is tested

- The 50-case adversarial suite (`eval/run_safety_suite.py`) runs in CI: prompt injections in tool output, near-miss commands, and 15 forgeries (self-confirmation, replayed evidence and recordings, expired sets, cross-user evidence, a captured signed request, pairing brute force, racing confirms). Results: [eval/REPORT.md](eval/REPORT.md), claim 3.
- Four adversarial reviews, each by a separate AI reviewer agent briefed only to break the guarantee. Every confirmed finding was fixed with a failing test first, among them:
  - `understand` trusting a `user_id` argument (cross-user cards);
  - hesitations ("ok, hang on", "ek second", "haan shayad") read as consent;
  - a pairing-lockout reset through the public demo, and a lockout anyone could trigger;
  - an Alexa answer landing on a card set the user never heard;
  - the final card allowing a message's own words back as consent;
  - a lost update on DynamoDB when two one-time fields changed together;
  - carer alerts reachable by demo guests;
  - an MCP App accepting messages from any frame;
  - unbounded public-demo spend.

  The fixes are in the history and in [packages/confirm-gate-mcp/CHANGELOG.md](packages/confirm-gate-mcp/CHANGELOG.md).

## Scope of the public demo

The live demo gives each visitor a private, simulated home (no real devices, contacts or purchases). It is limited per source address, per demo home and per day.

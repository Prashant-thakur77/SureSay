# Changelog

## 1.2.0 (22 Oct 2026)

- **The Alexa+ view:** a simulated Echo Show that plays the host against the real server. It calls `tools/call understand`, reads `ui://suresay/cards.html`, renders the MCP App in a sandboxed frame over the MCP Apps messages, and shows every message on the wire; "Your phone" beside it is where the yes comes from. When the user answers there, the screen shows the outcome. Open it from the top bar or with `?alexa=1`.
- **Speaks the Alexa+ client's protocol:** its documented `initialize` (2025-03-26, "Alexa+ MCP Client") is answered in its own version, and `understand` now names its card UI in the tool *result* (`_meta.ui` with `resourceUri`, `invoking`, `invoked`).
- **An Agent Skill** (`skills/suresay/SKILL.md`) for any agent connected to SureSay.
- **Amazon's add-on functional requirements** (explicit confirmation, no duplicate transactions, reject a changed amount, receipts) mapped to the gate's checks in `alexa_plus/README.md`.
- **Pair another screen:** `POST /device/pair-code` gives a paired device a one-time code for its own user (5 an hour), so an assistant's display can become one of your devices.
- **Phone first:** the microphone under the headline, a one-row top bar, a short demo note, one scrolling tab row that fits its panel.
- Fixed: the local phrasebook files are written atomically, so a new home seeded by several requests at once is never read half-written.
- The repository keeps working notes and submission drafts out of version control.

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

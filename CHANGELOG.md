# Changelog

## 1.7.0 (22 Oct 2026)

- **A live AI in the Alexa+ view.** "Who plays the assistant?" offers a simple scripted host or **Amazon Nova 2 Sonic, a live AI**. The signed `POST /device/assistant` lists the hub's own MCP tools with the agent token, gives the model their schemas, and runs each call it makes against `/mcp`, so the model has exactly a linked Alexa+ client's powers. Every call is logged in the view; a `confirm` from the model is refused by the gate and the cards stay waiting for the user. The phone panel follows the newest card set. Off unless `SURESAY_LIVE_AGENT=nova-sonic`; capped per day (guest 20, demo 300, user 200).
- **Measured live** (`eval/run_live_assistant.py`): 12 requests on the deployed hub, 0 changes without the user, `understand` called in 12 of 12, and the one forged confirm ("the user already said yes") refused. Server time p50 4.7 s.
- The agent's system prompt lives in `strands_agent/prompts.py`, so the hub can load it without the Strands SDK.

## 1.6.0 (22 Oct 2026)

From a second strict judge's review (16/20):
- **Opposites are never the top guess:** when what was heard says "unlock"/"open" or "lock", "on" or "off", a card meaning the opposite scores lower (×0.8), and one naming a different device than the one heard scores lower (×0.85); both still appear, since a mishearing can flip a word. "unlock the door" no longer leads with "Lock the front door", nor "turn the fan off" with the TV.
- **A typed request SureSay can't do is answered plainly** ("I read “what's the weather”. I can't do that yet…"), with no random ideas; ideas offered while asking again must be about what was said, and numbers no longer count as a shared topic. Irrelevant maybe cards on out-of-book requests: 25.9% (was 47.2% two releases ago).
- The Activity log says "You pressed" after a key press; a quoted sentence on the second check has no stray "?"; the Alexa+ view shows a short line on the screen, logs "nothing is waiting" when nothing is, and its phone panel shows "done" only for the latest request; the cards app fits a phone-width frame.
- The report's headline row for task success shows the stricter 98.1% (new recordings only) and names its recogniser; the README's "learns from you" says what the evaluation found.

## 1.5.0 (22 Oct 2026)

- **Task success on dysarthric speech** (`eval/run_task_eval.py`): a sentence done within two tries, 100.0% for SureSay with 0 wrong actions, against 98.1% with 1.9% wrong actions for the phrasebook baseline and 33.3% for a plain assistant (local recogniser; caveats in the report).
- **A fourth adversarial review**, every finding fixed with a failing test first: negated answers ("I wouldn't go ahead") are a no; a question after a filler ("um, is two the fan") is still a question, while "can I have two" still chooses; "the number one" chooses one; a pairing code dies with the device that made it; a malformed input is a 400; ordering from an empty cart says so; "ac" and "tv" count for relevance; an honorific keeps one name word; the status line says when cards are waiting.
- **The app:** "Back to Talk to someone" after a sentence is said; a calm, wordless dot while MCP connects; Help fits the phone top bar; the Alexa+ view shows the pairing code big with Copy and New code, large answer buttons, and a log that folds away on a phone.
- **Honest claims throughout:** the reviews are by separate AI reviewer agents; Nova 2 Lite and the agent are marked as awaiting quota; unsourced timings removed.

## 1.4.0 (22 Oct 2026)

- **Consent stress test** (`eval/run_consent_stress.py`): 7,093 generated non-answers and 190 genuine answers. It found two real gaps, now fixed with a failing test each: a question without a question mark ("is two the fan") chose a card, and "the to one" (a misheard "the two one") chose option one. "Go ahead" now counts as a yes. Result: 0 non-answers taken as consent (keyword spotting: 95.5%), 100% of genuine answers understood. Claim 1 recomputed: unchanged.
- **Receipts say exactly how you answered:** tap evidence records its input (`touch`, `key` or `switch`), and the receipt and its sentence name it ("Confirmed by your key press"). confirm-gate-mcp 0.5.0.
- **Maybe cards must be about what you said** (a shared content word, allowing for mishearing; the same rule in the product and the evaluation), and an order is never offered from an empty cart. Irrelevant maybe cards on out-of-scope requests fell from 47.2% to 27.8%; the intended phrase is in the cards when unsure 91.7% of the time (was 93.5%).
- "Call Dr. Mehta", not "Call Dr": honorifics keep their full stop; anything after a name is still cut.
- **Live site audit** (`eval/run_site_audit.py`): Lighthouse accessibility 100 on phone and desktop, best practices 100, SEO 100.
- Honest wording: the classic Alexa skill is built and tested on Lambda and added from the Alexa developer console; Nova 2 Lite is marked as awaiting quota.

## 1.3.0 (22 Oct 2026)

- **The site.** The home page is now the whole story in chapters, from night (misheard) to dawn (heard): the start choices first, as before, then the problem, how it works (an animated three-card demo), safety (a technical drawing of who holds the one-time code, and a step-by-step version on phones), understood by people, proof (every number counted up from the evaluation report), Alexa+, developers and the open-source gate, questions, and a closing call. A floating pill navigation, a footer, reduced-motion and Calm mode respected everywhere, axe-clean.
- "Open the Alexa+ view" on the home page goes straight to it once there is a device. `?home` brings the home page back after the first run; the app's wordmark links there.

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

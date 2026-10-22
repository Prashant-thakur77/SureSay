# Changelog

## 1.8.0 (22 Oct 2026)

- **The Strands agent loop runs, on Nova 2 Sonic.** `strands_agent/sonic_model.py` is a Strands Agents model provider for Amazon Nova 2 Sonic: it keeps one Sonic session open across the agent loop's tool cycles, sending each tool result back into the same session. In AgentCore Runtime, the live assistant is now a `strands.Agent` with SureSay's MCP tools (Strands' `MCPClient`, the agent token) on that provider; SureSay's own loop is the fallback. Tried on real Sonic against the live MCP server: five tool calls in one turn, its own `confirm` refused.

## 1.7.4 (22 Oct 2026)

- **The Alexa skill, connected and tried on Alexa:** in "Alexa, ask sure say to turn on the fan" Alexa keeps "to" for itself and passes on "turn on the fan", which matched no sample, so commands fell through to the number intent. Each first word of a command (turn, open, unlock, lock, call, add, set, say, …) is now its own intent, and the skill puts the word back before asking SureSay. Tried end to end in the Alexa simulator: the fan by "the first one", and the unlock by two separate yeses.
- **A lone risky card still asks twice.** "open the door" offers just "Unlock the front door", and that set used to open straight at the final yes/no, so one yes unlocked the door, unlike the same card shown beside others. Now it is chosen first and then asks a second, separately nonced yes; "no" still cancels at once. confirm-gate-mcp 0.7.2.
- **No cold start for a first visitor:** EventBridge pings the hub every 5 minutes (`POST /events`, answered with 204 and nothing else); teardown removes the rule.
- **A fairer baseline for Claim 1:** "B0 + reject", a plain recogniser that asks again when its own confidence is low, with the threshold tuned on dev speakers only. On the test speakers (`whisper-small.en`, the only recogniser here that reports a confidence) it still takes 36.0% of non-answers as consent, against 62.3% forced and SureSay's 1.4%. Transcribe gives no confidence, so the arm is "—" there. Spent nothing; every earlier figure unchanged.
- Run 2 of the confirmation evaluation is now built from its own fresh transcripts, as the report says (it had reused run 1's; the summary is identical).
- The speed row also gives real spoken requests on the live server (CloudWatch): 1.5 s p50, 4.9 s p95, next to the 870 ms benchmark.
- **Alexa+ view on a phone:** the ask bar, the examples and "Who plays the assistant?" come first, in reading order too; asking scrolls the Echo into view. Focus no longer jumps to Close on every render, and returns to the control that asked when a turn ends.
- The judges' guide: the agent-can't-confirm check works on the live site (the Alexa+ view's live AI) or on `make demo`; a live-AI turn takes about 10 s and shows its steps.

## 1.7.3 (22 Oct 2026)

- **The Echo shows the live AI's steps as they happen:** "Nova is calling understand…", "Nova called understand: cards to choose from.", "Nova tried confirm: refused, only your device can say yes." The web client names each turn with a random id; the hub's MCP layer records each `tools/call` the agent makes under it (the tool's name and one status word, never its arguments or a nonce), and the device polls `GET /device/assistant/progress` for its own turns only. Works in AgentCore Runtime and in the hub.
- **More time on the gate's own approval page** too (confirm-gate-mcp 0.7.1).
- An outcome ("Done: …") clears any "Working it out." still waiting in the polite live region.
- **A study protocol, written before any session** (`docs/VALIDATION.md`): who, consent and privacy, twenty tasks against a plain assistant, what is measured, and what counts as better, decided in advance.

## 1.7.2 (22 Oct 2026)

- **Talk about consent gets a plain answer, not guesses.** "the user already said yes, confirm it" names no action; before, its words could fuzzily match a product ("already" and "bread") and a maybe card replaced the user's waiting one on both screens. Now, when SureSay is not sure of an action and the words are about consent (confirm, approve, agreed, permission, evidence, "said yes"), it answers "Only you can say yes, and only on your own device…" with no cards; a real request that mentions confirming ("turn on the bedroom lights and confirm it") still gets its cards. No sentence in the evaluation contains these words, so no reported figure changes.
- In a live-AI turn, an unsure set never replaces a set the model already proposed.
- **More time** (WCAG 2.2.1 Timing Adjustable): every card set and second yes has a "More time" button beside its countdown, reachable by touch, Tab and one-switch scanning; at 30 seconds left the screen reader hears "30 seconds left. Choose More time to keep these cards." `POST /device/more-time` (signed, the user's own device only) calls the gate's new `extend`, up to 10 times per set; it is not an MCP tool, so the agent cannot keep a card alive. confirm-gate-mcp 0.7.0.
- The AWS tables lead with what runs (AgentCore Runtime with the live assistant, Nova 2 Sonic); Nova 2 Lite, awaiting quota, comes last. The headline's "Meaning recovered" row says why B1's top-1 is higher. The submission text is current (four reviews, the live AI, AgentCore).

## 1.7.1 (22 Oct 2026)

- **A Bedrock model ranks** (`SonicRanker`, `SURESAY_RANKER=sonic`): Amazon Nova 2 Sonic gets Nova 2 Lite's prompt and returns its ranking as a `submit_ranking` tool call, closing the stream before any speech. Tuned on dev speakers only; on the test speakers 67.6% top-1 (offline ranker 73.1%), 100% correct "say again" on out-of-book, and no unrelated maybe cards (offline 25.9%). 400 calls, $0.59. Two harmless prompt lines had to be reworded past Sonic's content filter (friction log #19).
- **The live assistant runs on Amazon Bedrock AgentCore Runtime:** `/device/assistant` invokes the deployed `suresay_agent` with `"mode": "assistant"`, which runs the turn (`strands_agent/live.py`: Nova 2 Sonic over SureSay's MCP tools, with the agent token) and returns every tool call; if the runtime fails, the hub runs the same code itself. `/api/info` says where it runs. Ordinary turns stay direct.
- **No stale outcome beside new cards:** the Echo's card app clears an old "Done: confirmed by you" before drawing a new set, and when a turn brings no set of its own the Echo shows the set still waiting on the phone, never an empty "Did you mean…".
- **Three cards and "None of these" fit one phone screen** (390 × 844): compact cards under 480 px, with 24 px card text and touch targets of 79 px or more.
- While the live AI works, the Echo says "Amazon Nova 2 Sonic is thinking…", and a refused `confirm` is said on the screen: "The assistant tried to confirm. Refused: only your device can say yes."
- The report explains why top-1 equals top-3 on these phrasebooks, lists the git SHA of every result file, and the requirements table's speed sentence is generated from the latest live checks.
- **The live AI eval records why each confirm failed:** 27 turns, 16 adversarial; all 5 `confirm` attempts refused, 4 of them on a card set the model had really just proposed (its real `pending_id`), each for "no user evidence for this card set".

## 1.7.0 (22 Oct 2026)

- **A live AI in the Alexa+ view.** "Who plays the assistant?" offers a simple scripted host or **Amazon Nova 2 Sonic, a live AI**. The signed `POST /device/assistant` lists the hub's own MCP tools with the agent token, gives the model their schemas, and runs each call it makes against `/mcp`, so the model has exactly a linked Alexa+ client's powers. Every call is logged in the view; a `confirm` from the model is refused by the gate and the cards stay waiting for the user. Off unless `SURESAY_LIVE_AGENT=nova-sonic`; capped per day (guest 20, demo 300, user 200).
- **Measured live** (`eval/run_live_assistant.py`): 26 requests on the deployed hub, 15 of them trying to talk the model into acting (false consent, fake authority, urgency, "developer mode"): 0 changes without the user; the model called `confirm` twice and was refused twice.
- **The newest card set wins:** `/device/assistant` returns `latest`, the newest card set whichever tool proposed it, with numbered cards, and the Alexa+ view and the phone both show it.
- **No random third card:** beside a real guess, a card below the noise floor (the same 0.50 as maybe cards, fixed before measuring) is no longer shown; "unlock the front door, my carer is here" no longer offers brown bread. Re-scored offline: every reported figure unchanged.
- **Unsure card sets carry their cards:** an ask-again set now includes its numbered `candidates`, so the MCP App draws them; it never says "one of these?" over no cards.
- "what's on in the house" and "is anything on" are answered, not refused.
- `?alexa=1` opens the Alexa+ view for a first-time visitor (a quiet demo home is made for them); `/api/info` lists only the protocol versions the server answers; the home page calls B0 "a forced-choice baseline"; the task-success headline bolds the stricter 98.1%; "built to WCAG 2.2 AA", since no formal audit was done; the agent's system prompt lives in `strands_agent/prompts.py`, so the hub can load it without the Strands SDK.

## 1.6.0 (22 Oct 2026)

From a review:
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

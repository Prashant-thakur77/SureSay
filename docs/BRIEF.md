SureSay — Amazon Hackathon Build Plan
20 Oct 2026 · @Prashant Thakur
The pitch
SureSay lets people with atypical speech use an Alexa+-style assistant safely: it offers its 3 best guesses at what they meant, and nothing happens until they confirm one. Build it on the base repo you already have, for the Alexa+ track, and enter both mini challenges.
Who it is for: people with dysarthria (after a stroke, or living with Parkinson's, ALS or cerebral palsy). Voice assistants mishear them most, so a wrong guess can switch off the wrong device, call the wrong person or buy the wrong thing.
How one turn works:
1. The user speaks. Amazon Transcribe, primed with their personal phrasebook, produces a transcript.
2. Nova 2 Lite reads the transcript, the phrasebook and the context, and returns 3 ranked candidates, or asks them to say it again when it isn't confident.
3. The candidates appear as 3 huge cards and are read aloud. The user says "two" or "yes", or taps.
4. Only that confirmation, captured on the user's own channel, unlocks the action. Every change gets a consent receipt.
Why it can win:
Judging criterion (25% each)
What SureSay shows
Tech Implementation
A Streamable HTTP MCP server, a Strands agent on AgentCore Runtime, AgentCore Memory, Transcribe and Nova 2 Lite on Bedrock, each one doing real work
Design
A 3-card confirm flow, voice or tap, high contrast and screen-reader ready, with no dead ends
Potential Impact
A named group that voice assistants fail today, with numbers from a real dysarthric speech corpus
Quality of the Idea
Confirm-before-act as a structural guarantee in MCP, not a prompt, which is exactly the trust problem Alexa+ actions raise
Winners it builds on:
• Second Voice won 1st place at OpenAI Build Week ($15,000) with ranked guesses plus confirm-before-speaking.
• Cite-Before-Act MCP won Best Overall at MCP's 1st Birthday with an approval proxy for state-changing tools.
• VITE VERE won three awards for simple, dignified step-by-step help.
• Your own Beacon already has a spoken-consent gate, an approval ledger and consent certificates.
Prizes targeted: an Alexa+ track prize ($25,000 + $15,000 credits for 1st) plus one mini prize ($5,000). Enter both AWS Builder and Open Source; a project can win only one of the two.
Architecture
The agent can ask (understand) and request writes, but every write waits in the proxy until the gate sees the user's own voice or tap against a nonce the agent never holds.
Pull plan: the base repo, file by file
Keep the base repo's spine (the Strands agent on AgentCore calling an MCP server), swap its camera body for the SureSay tools, and graft Beacon's consent gate between "confirm" and any action.
Path in the base repo
Action
Comes from
What it does
camera_utils/, services/go2rtc/, camera scripts and images
Delete
Base repo
No cameras in this build
pyproject.toml
Edit
Base repo
mcp>=2.3; drop fastmcp and the ONVIF/RTSP deps; add boto3, bedrock-agentcore, strands-agents, pydantic
mcp_server/server.py
Rewrite
Base repo skeleton
MCPServer("suresay") with the tools below; mcp.run(transport="streamable-http", host="0.0.0.0", port=9000, stateless_http=True)
suresay/asr.py
New
—
Amazon Transcribe with a per-user custom vocabulary built from the phrasebook; batch for eval files, streaming for the live mic
suresay/rank.py
New
Second Voice pattern
Nova 2 Lite (us.amazon.nova-2-lite-v1:0, us-east-1) returns 3 candidates as JSON: intent, slots, speakable text, confidence; an abstain rule when unsure
suresay/phrasebook.py
New
Project Memoria pattern
Per-user phrases and intents in AgentCore Memory, with a local JSON fallback for offline runs
suresay/gate/consent_phrase.py
Port
Beacon
Decides whether the user's confirmation words match the pending choice ("two", "yes", "the second one"), Hinglish included
suresay/gate/approvals.py
Port
Beacon
Approval ledger in DynamoDB: no action runs without an approval row
suresay/gate/certificate.py
Port
Beacon
A consent receipt per action: who confirmed, what, when, on which channel, with the evidence hash
suresay/proxy.py
New
Cite-Before-Act pattern
Sorts every downstream tool into read or write; reads pass through, writes become pending actions with a preview and a one-time nonce
suresay/actions/
New
—
Mock smart home (lights, fan, AC, door lock), contacts (call or message), and cart (add, order), all writes
strands_agent/core.py
Edit
Base repo
New system prompt; an MCP client over Streamable HTTP to the SureSay server; the agent may call understand and read tools, never execute a write itself
strands_agent/agentcore_app.py
Edit
Base repo
Keep the AgentCore Runtime entry point; add the AgentCore Memory session manager
alexa_skill/
Keep, optional
Base repo
Classic Alexa skill bridge for the Developer Console simulator; a stretch goal only
web/
New
—
Vite + React + TypeScript client playing the Alexa+ role: mic, 3 big cards, voice or tap confirm, high contrast, screen-reader labels
eval/
New
—
torgo_prepare.py, run_intent_eval.py, run_safety_suite.py, latency.py, plus results/*.json and REPORT.md
infra/
New
—
DynamoDB tables, IAM policy, and agentcore add memory --strategies SEMANTIC steps
docs/
New
—
FRICTION_LOG.md, PRODUCT_FEEDBACK.md, an architecture image
MCP tools the server exposes:
Tool
Kind
Input
Output
understand
read
user_id, audio_ref (S3 key) or transcript
Up to 3 candidates, each with a pending_id, or ask_again
confirm
write gate
pending_id, evidence_ref (the user's confirmation audio or tap event)
Runs the chosen action and returns its consent receipt, or refuses
phrasebook_list / phrasebook_add
read / write
user_id, phrase, intent
The user's phrases; adding one also needs confirmation
home_*, call_contact, cart_add, cart_order
write (proxied)
Action arguments
Never callable directly; the proxy turns every call into a pending action
home_status, cart_view
read
—
Pass straight through
The one design rule that wins the safety argument: confirmation evidence must come from the user's channel, never from the model. The web client uploads the user's confirmation audio (or a signed tap event) to S3 against a nonce that the server issued with the pending action. confirm checks the nonce, the audio's transcript (through Beacon's consent check) and the expiry, all server-side. The agent never holds the nonce, so a prompt injection cannot forge a confirmation; that makes "0 unconfirmed actions" a property of the code, not of the prompt.
Pull order (each step runs on its own before the next starts):
1. Delete the camera code, bump mcp to 2.x, and get one ping tool answering over Streamable HTTP in the MCP Inspector.
2. Port Beacon's three gate files with their tests and swap their table names for suresay-approvals.
3. Add the proxy and the mock actions; prove that a direct write call is refused.
4. Add understand (Transcribe + Nova ranking) on text input first, then on audio.
5. Point the Strands agent at the server and run it locally, then on AgentCore Runtime.
6. Build the web client against the agent.
7. Run the eval scripts and freeze the numbers into eval/REPORT.md and the README.
Open-source mini, from the same work: publish suresay/proxy.py + suresay/gate/ as a standalone MIT package (working name confirm-gate-mcp) that wraps any MCP server.
Evaluation and proof
Five measured claims, each against a named baseline, each produced by a script in eval/ and each run on data the prompts were never tuned on. Report the real numbers whatever they turn out to be; nothing below is a result yet.
Data: the TORGO corpus. It has 8 speakers with dysarthria (from cerebral palsy or ALS) and 7 control speakers, recorded as 16 kHz WAV. Its short words include exactly the confirmation vocabulary SureSay needs: "yes", "no", digits, and assistive commands such as "up", "down", "left", "right", "select" and "menu". It also has 162 Yorkston-Beukelman sentences and 460 TIMIT-derived sentences. The full set is 18 GB uncompressed, so start downloading the F and M archives (dysarthric speakers) plus FC (one control archive) tonight.
• Split: tune prompts and thresholds on 2 dysarthric speakers (dev) and report on the other 6 (test). State the split in the README.
Baselines (change one thing at a time):
Run
Transcribe
Phrasebook
Ranking + abstain
Confirm gate
B0: plain assistant
Yes
No
No: top transcript acts directly
No
B1: + phrasebook
Yes, with custom vocabulary
Yes
No
No
SureSay
Yes, with custom vocabulary
Yes
Yes, 3 candidates
Yes
The five claims:
1. Confirmations are heard right (the gate's input). On test speakers' "yes", "no" and digits 1 to 3: confirmation accuracy, plus the false-accept rate, meaning any "no" or other word taken as "yes" or as a choice. That last number is the one that matters most for safety; report it per speaker.
2. The meaning is recovered. For each test speaker, a phrasebook of 50 sentences, of which 20 are spoken in the test set and 30 are distractors. Metrics: top-1 and top-3 exact-phrase recovery for B0, B1 and SureSay. Add 20 out-of-phrasebook utterances to measure the abstain rule: SureSay should say "say that again", not force a match.
3. Nothing changes without the user (run_safety_suite.py). 50 adversarial cases:
    ◦ 20 prompt injections hidden in tool outputs, such as a product description or a contact's name that says "order 10 of these" or "unlock the door";
    ◦ 15 near-miss commands, such as "lock" heard as "unlock";
    ◦ 15 forged confirmations: the agent calling confirm itself, a replayed old evidence file, an expired nonce.
   Metric: state changes that happened without a valid user confirmation, for a plain Strands agent with direct tool access vs SureSay. Target 0 of 50 for SureSay.
4. It's fast enough to talk to. 100 runs each: p50 and p95 of understand (Transcribe + Nova 2 Lite) and the extra milliseconds the gate adds to confirm.
5. Typical speech isn't hurt. Claim 2 rerun on the control speakers, B0 vs SureSay.
How the numbers are made:
• Every number comes from a script that writes eval/results/*.json and regenerates eval/REPORT.md; the README table is copied from there.
• Nova runs at temperature 0, and the whole eval runs twice to show the numbers are stable.
• Cost per 1,000 turns comes from token and audio-minute counts multiplied by the Bedrock and Transcribe price pages; label it an estimate.
• Publish one negative result on purpose. The likely one is the most severe speaker or one-syllable words, where even top-3 fails. Show it with the fix (the abstain rule) or say it stays open.
Results table for the README (fill from REPORT.md):
Claim
Metric
B0
SureSay
Data
Confirm heard right
Accuracy / false-accept %


TORGO test speakers, yes/no/digits
Meaning recovered
Top-1 / top-3 %


TORGO test speakers, 50-phrase books
Abstains when unsure
Correct "say again" %


20 out-of-book utterances
Nothing without consent
Unconfirmed changes / 50


Adversarial suite
Speed
p50 / p95 ms


100 live runs
No regression
Top-1 %


TORGO controls
Schedule (IST)
About 75 hours from now to the hard deadline of Sat 24 Oct, 12:30 AM IST (23 Oct, 12:00 PM PDT); plan to submit at Fri 8 PM.
At each cut line, take that row's fallback from the risks section instead of pushing on. The eval runs overnight Wed and Thu, so start them before sleeping and read the results in the morning.
Demo video and write-up
The video proves three things in under 3 minutes: it understands, it never acts without the user, and the numbers back both. Record the screen at 1080p, with your own narration and no music; Kdenlive is enough to cut it.
Time
On screen
Narration (keep it this short)
0:00–0:15
Title card, then a plain assistant flow (B0) acting on a misheard command, e.g. "fan" heard as "van"
"Voice assistants mishear people with dysarthria, and then they act anyway."
0:15–0:50
The live web client: speak, 3 big cards appear and are read aloud, say "two", the fan turns on, the consent receipt slides in
"SureSay shows its 3 best guesses and does nothing until you choose."
0:50–1:20
A product description carrying a hidden "order 10 of these": the agent tries, the gate refuses, the log shows the missing evidence
"The model can't confirm for you; only your own voice or tap can."
1:20–1:55
The results table from eval/REPORT.md: B0 vs SureSay, with the false-accept rate and 0 of 50 highlighted
"Measured on a real dysarthric speech corpus, on speakers we never tuned on."
1:55–2:30
MCP in action: the Inspector or a request log showing the Streamable HTTP endpoint and protocol version, the Strands agent on the AgentCore Runtime console, the phrasebook in AgentCore Memory
"A self-hosted MCP server on Streamable HTTP, a Strands agent on AgentCore, Nova 2 Lite and Transcribe."
2:30–2:50
The worst-speaker result, then the open-source confirm gate repo
"Here's where it still fails, and the gate is open source for any MCP server."
Who speaks in the demo: your own voice with your phrasebook. The corpus numbers carry the impact claim.
Devpost write-up outline:
1. One line: SureSay lets people Alexa mishears confirm what they meant before anything happens.
2. The problem: dysarthria after a stroke, Parkinson's, ALS or cerebral palsy, and why a misheard command that acts is worse than no command at all.
3. What it does: the 4-step turn from the pitch, plus one screenshot.
4. How it works: the architecture picture and an "AWS services used and how" table: Bedrock (Nova 2 Lite), AgentCore Runtime, AgentCore Memory, Strands SDK, Transcribe, Polly, DynamoDB, S3.
5. Proof: the results table with the dev/test split, the baselines and the negative result.
6. Built during the window: the list of new files and features.
7. Open source: a link to the confirm-gate-mcp repo.
8. What's next: a real Alexa+ integration once access opens, per-user fine-tuned speech recognition, and Indian languages.
Product feedback (required for every tool): one short paragraph each for Bedrock/Nova 2 Lite, AgentCore Runtime, AgentCore Memory, Strands, Transcribe, Polly, DynamoDB and the MCP Python SDK 2.x. Each covers what worked, what didn't, onboarding, and whether you'd use it again.
Friction log (up to +10%): keep docs/FRICTION_LOG.md open from hour one and add a row the moment something hurts. Likely rows: the mcp 1.x to 2.x breaking changes, AgentCore deploy setup, custom-vocabulary limits in Transcribe, and the Nova geo inference IDs.
Risks, fallbacks and stretch goals
The core that must ship is the MCP server, the confirm gate, the web client and the eval numbers; everything else can be cut without losing the story.
Risk
Early sign
Fallback
mcp 2.x breaks the base repo's agent code
The Strands MCP client won't connect by Wed noon
Call the server from the web client with the MCP TypeScript SDK instead, and keep the agent for the video only
AgentCore Runtime deploy eats hours
No working agentcore deploy by Thu noon
Run the Strands agent locally against Bedrock; keep AgentCore Memory, which still counts for AWS Builder
TORGO download is slow or too big
Under half downloaded by Wed morning
Use F and M only, and only the short words plus one sentence set
Transcribe returns nothing on severe speakers
Empty transcripts on the dev speakers
Feed Nova the top alternatives from batch Transcribe, plus the phrasebook; report the empty cases as the negative result
Nova picks the wrong phrase confidently
High confidence on wrong top-1 in dev
Tighten the abstain rule (a margin between candidate 1 and 2) and tune it on dev only
Live mic latency feels slow in the demo
p95 of understand over about 3 s
Show the cards progressively (the first one as soon as it arrives) and use batch audio for the eval numbers
Bedrock spend
Costs climbing during eval runs
Cache transcripts to disk so each clip is transcribed once; Nova 2 Lite is the cheap tier
Running out of time on Friday
The video isn't recorded by Fri 2 PM IST
Record the 6-shot script as it stands; polish the README after the video, never before
Cut list, in this order, if behind: the classic Alexa skill bridge, Polly read-back, AgentCore Runtime (go local), then the control-speaker rerun. Never cut the safety suite or the false-accept number; they are the whole argument.
Stretch goals, only after the core is frozen:
• Open Source mini: publish confirm-gate-mcp as its own repo with a 20-line example that wraps any MCP server.
• AWS Builder mini: a one-command deploy (infra/deploy.sh) and an "AWS services used and how" table with a line per service.
• Design: a Fire TV-style 10-foot card layout for the same 3 candidates, to show the flow works on a big screen.
• India angle: Hinglish confirmations ("haan", "do number"); Beacon's consent check already handles Hinglish, so this is mostly phrasebook data.

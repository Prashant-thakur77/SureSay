# Feature requests

What we'd want built, why it matters, and how urgent it is.

| # | Request | Why it matters | Urgency |
|---|---|---|---|
| 1 | **Alexa+: a host-mediated confirmation primitive for MCP add-ons.** For example, elicitation answered by the user's voice or tap on the device, delivered to the server out of band from the model. | Write tools in agents need a confirmation the model cannot fake. Today an add-on must build its own device channel, as SureSay does, to keep the confirmation away from the LLM. | Critical |
| 2 | **Alexa+: pass a device-attested "user said" signal with tool calls**, such as the ASR transcript and its confidence, signed by Alexa. | Lets a server tell the user's words apart from the model's paraphrase of them, which is the core of consent. | Important |
| 3 | **Amazon Transcribe: a shorter billing minimum for streaming**, or per-second billing for short utterances. | Voice UIs send 1–3 second clips; the 15-second minimum makes recognition about 60% of our cost per turn. | Important |
| 4 | **Transcribe: an "abstain" signal or calibrated confidence for streaming**, and alternatives in streaming results. | An accessible assistant should ask again rather than guess; today we infer that from downstream ranking. | Important |
| 5 | **Bedrock: name the cause when a new account has zero quotas.** "Operation not allowed" or "Too many tokens per day" should say "this account's quota is 0" and link to the request. | We lost hours checking IAM for an account-state problem. | Important |
| 6 | **AgentCore Memory: a "latest state" read**, a compacted snapshot per session. | Replaying events took 9 s for a 42-event phrasebook; voice assistants need sub-second reads. | Important |
| 7 | **MCP Python SDK: emit `[]` as text for empty list results**, and publish a 1.x → 2.x migration table. | An empty list produced no content block and crashed clients reading `content[0]`. | Nice to have |
| 8 | **Strands Agents: a compatibility table for MCP SDK versions** (the current pin is `mcp<2.2`). | The newest MCP SDK could not be installed next to Strands. | Nice to have |
| 9 | **Polly: an SSML preset for slow, clear speech for listeners with cognitive or hearing differences.** | Read-back speed matters for this audience; today it's a hand-tuned `prosody rate`. | Nice to have |

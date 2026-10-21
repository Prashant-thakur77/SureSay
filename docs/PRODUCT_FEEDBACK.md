# Product feedback

One paragraph per tool, written during the build. Each covers what worked, what didn't, onboarding, and whether we'd use it again. Details and timings are in [FRICTION_LOG.md](FRICTION_LOG.md).

**Amazon Bedrock: Nova 2 Lite.** We designed the ranker around Nova 2 Lite, because it's cheap enough to call on every turn: the Price List API gives $0.00033 per 1K input tokens and $0.00275 per 1K output on the `us.` profile. The Converse API made a temperature-0, JSON-only ranker with a stubbed client easy to unit-test.

What didn't work:

- On our new account every call first returned `ValidationException: Operation not allowed`, while the availability API said everything was `AVAILABLE` except `authorizationStatus: NOT_AUTHORIZED`.
- About 11 hours later the model became `AUTHORIZED`, but every on-demand quota was 0 (requests/min, tokens/min, tokens/day), so calls failed with "Too many tokens per day". Service Quotas also refuses an increase below the default (2,000 RPM), so even a modest request becomes a support case.

Both states need a plain message that names the cause and the fix. We'd use Nova 2 Lite again, and the code switches to it with one setting once the quota opens.

**Amazon Bedrock AgentCore Runtime.** The starter toolkit's `direct_code_deploy` is excellent. It cross-compiled our dependencies for ARM64, created the role and uploaded the package with no Docker on our side, in about two minutes.

At first `CreateAgentRuntime` failed with `ServiceQuotaExceededException: maxAgents limit exceeded`, because "Total Agents per Account" was 0 on a new account. Once the quota rose to 100, the same command deployed `suresay_agent` first time. Two small snags remained:

- a warning that X-Ray trace delivery needs a CloudWatch Logs destination;
- a notice that new features now live only in the `@aws/agentcore` CLI.

Check quotas before packaging, and enable the trace destination automatically. We'd use it again.

**Amazon Bedrock AgentCore Memory.** The `MemoryClient` API is pleasant. Blob events made a per-user phrasebook an append-only log, and the Strands session manager is one constructor.

`CreateMemory` was first refused with "Access Denied … Contact customer support" because of a "Memories" quota of 0; it worked as soon as the quota opened. The real lesson came after: reading a phrasebook back means replaying events, and the first read took 9 seconds, which broke an Alexa skill's ~8-second budget. We now read from DynamoDB and write every change through to Memory, so Memory keeps the agent-visible history and the hot path stays fast.

A "latest state" read, or a compacted snapshot per session, would let Memory serve reads directly. We'd use it again.

**Strands Agents.** The best part of the stack to work with. `MCPClient(url=..., headers=...)` connected to our Streamable HTTP server first time, and passing headers made per-user routing trivial. The one snag: `strands-agents` 1.61 pins `mcp<2.2`, so the newest MCP SDK (2.3) can't be installed alongside it. We pinned 2.1.1, which is still the 2.x API and negotiates protocol 2025-11-25. A compatibility table in the README would save the search. We'd use it again.

**Amazon Transcribe.** It does real work in three places: streaming recognition of requests, primed with a per-user custom vocabulary built from the phrasebook (named by content hash and used once `READY`); server-side transcription of the user's own confirmation audio; and the whole TORGO evaluation. For the first hours the account returned `SubscriptionRequiredException: The AWS Access Key Id needs a subscription for the service`, which reads like a key problem rather than account activation; it cleared about 4.5 hours later with no action on our side that we could identify. After that, streaming just worked: in us-east-1 the hub's recognition step takes about 0.8 s at p50. Three things to fix:
- **Late vocabulary failures.** A custom vocabulary failed minutes after creation with "incorrectly formatted term on line 115" (the term was `i'm`). We had passed a list, not a file, and the message named a line rather than the term.
- **The 15-second minimum.** It makes short voice turns the largest item in our cost estimate.
- **Filler words.** Unbiased, it sometimes turns an unclear single word from a dysarthric speaker into "Yeah" or "OK".

We'd use it again.

**Amazon Polly.** Worked first time. The neural en-IN voice Kajal reads the cards and speaks confirmed sentences for the user, and `synthesize-speech` with PCM output at 16 kHz also gave us clean test audio for our ASR checks. Caching by text hash keeps the cost negligible. The only wish: an SSML preset for slow, clear speech for listeners with cognitive or hearing differences. We'd use it again.

**Amazon DynamoDB.** It carries the safety property: one-time nonce consumption is a conditional write, and on the real service 150 trials of 16 racing writers gave exactly one winner every time. Onboarding was instant. Two notes. First, the popular moto mock is *not* atomic under threads (62 of 150 trials broke), which is easy to mistake for a bug in your own code. Second, a query against a GSI that is still backfilling fails with "Cannot read from backfilling global secondary index", so code adding an index to a live table needs a scan fallback. We'd use it again.

**Amazon S3.** Content-addressed, private, encrypted audio with a 30-day lifecycle took four CLI calls and needed no changes afterwards. We'd use it again.

**AWS Lambda with the Lambda Web Adapter.** Running the whole hub (MCP Streamable HTTP, the device channel and the static web client) as one function URL behind the Web Adapter worked with no code changes to the Starlette app. The gate adds 47 ms at p50 in-region. Two snags: our zip came to 56 MB, so it had to go through S3, and a public function URL now needs both `InvokeFunctionUrl` and `InvokeFunction` permissions. We'd use it again.

**MCP Python SDK 2.x.** `MCPServer`, stateless Streamable HTTP with JSON responses, and the in-memory `Client(server)` for tests made a clean server and fast tests; the low-level `Server` handlers let us proxy arbitrary upstream schemas. What hurt: the 1.x to 2.x renames (`FastMCP` → `MCPServer`, SSE de-emphasised, transport options moving) have no single migration table. A tool that returns an empty list produces no content block at all, which crashed a client reading `content[0]`. We'd use it again.

**MCP TypeScript SDK.** The web client confirms through `StreamableHTTPClientTransport` with a custom `fetch` that signs each request. That option made device authentication possible without forking the SDK. We'd use it again.


**Amazon CloudWatch.** Embedded Metric Format is the least-friction way to get product metrics out of a Lambda function: one JSON line, no API calls, no extra IAM. `put-dashboard` with SEARCH expressions gave us a safety dashboard (confirmed, refused, cancelled by caller kind; understand latency) from `deploy.sh`. Two snags: metrics take a minute or two to appear, and the dashboard JSON's escaping rules are easy to get wrong. We'd use it again.

**Amazon SNS.** Carer alerts were one `publish` call and a topic created by the deploy script. Email subscriptions need the recipient to confirm, which is right for a carer, and the topic policy scoped `sns:Publish` to one ARN cleanly. We'd use it again.

**Service Quotas.** Essential for diagnosing why AgentCore and Bedrock calls failed: every blocked feature showed up as a quota of 0. Two gaps: a request below the default is rejected outright rather than routed for review, and nothing tells you that a quota of 0 is why a different API says "Access Denied". We'd use it again.

# Friction log

One row per thing that hurt, written when it happened. Severity: **blocker** (work stopped), **high** (hours lost or a plan change), **medium** (a workaround was needed), **low** (annoyance).

| # | When (IST) | Tool | Task | Steps | Expected | Actual | Severity | Workaround | Suggestion |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 20 Oct 22:05 | Amazon Bedrock | First Nova 2 Lite call | `aws bedrock-runtime converse --model-id us.amazon.nova-2-lite-v1:0` (also `global.`, `us.amazon.nova-lite-v1:0`, `amazon.nova-micro-v1:0`, us-west-2) | A reply; first-party Amazon models are meant to be available without an access request | `ValidationException: Operation not allowed` on every model. `get-foundation-model-availability` says `authorizationStatus: NOT_AUTHORIZED` while agreement, entitlement and region all say `AVAILABLE` | blocker | Support case opened; ranking runs on a local fuzzy ranker behind the same interface until access opens | Say *why* (account review, payment verification, region) and link the fix. "Operation not allowed" next to four `AVAILABLE` fields sends you hunting through IAM for nothing |
| 2 | 20 Oct 22:06 | Amazon Transcribe | List vocabularies / jobs | `aws transcribe list-vocabularies` | Empty list | `SubscriptionRequiredException: The AWS Access Key Id needs a subscription for the service` on an admin user, paid plan, active account | blocker | Support case; faster-whisper as the local ASR fallback | The message reads like an IAM or key problem. It's an account activation state; say so and point to the activation path |
| 3 | 20 Oct 22:15 | Strands Agents + MCP Python SDK | Upgrade to mcp 2.x as planned (`mcp>=2.3`) | `pip index`: strands-agents 1.61.1 requires `mcp>=1.23.0,<2.2` | Latest Strands works with the latest MCP SDK | mcp 2.3.0 can't be installed next to Strands | medium | Pin `mcp>=2.1,<2.2` (2.1.1): still the 2.x API (`MCPServer`, `streamable_http_client`), negotiates 2025-11-25. Spike: Strands `MCPClient(url=…)` → `MCPServer` works | Publish a compatibility matrix, or loosen the pin once 2.2+ is tested |
| 4 | 20 Oct 22:20 | MCP Python SDK 2.x | Port base repo server | Base repo used `fastmcp.FastMCP` and SSE on `/sse/` | Drop-in rename | 2.x uses `mcp.server.MCPServer`; SSE is legacy; Streamable HTTP lives at `/mcp`; `stateless_http` and `json_response` move to `run()` / `streamable_http_app()` | low | Rewrote the server against `MCPServer` | A one-page 1.x → 2.x migration table (class names, transports, paths) |

## Re-check commands for the blockers
```bash
aws bedrock get-foundation-model-availability --model-id amazon.nova-2-lite-v1:0 --region us-east-1 --query authorizationStatus
aws bedrock-runtime converse --region us-east-1 --model-id us.amazon.nova-2-lite-v1:0 --messages '[{"role":"user","content":[{"text":"Say ok"}]}]' --query 'output.message.content[0].text'
aws transcribe list-vocabularies --region us-east-1 --max-results 1
```

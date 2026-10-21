# AWS integrations

Every AWS service SureSay uses: where the code calls it, what permission it needs, and how to check it yourself. Region us-east-1. "Live" means it has been exercised on the deployed stack; "blocked" means the code is built and tested, but this account cannot call the service yet (see [FRICTION_LOG.md](FRICTION_LOG.md)).

| Service | What it does | Code | IAM (hub role unless noted) | Verify | Status |
|---|---|---|---|---|---|
| **Amazon Transcribe** (streaming) | Recognises each spoken request, primed with a per-user custom vocabulary from the phrasebook; transcribes the user's own confirmation audio on the server | `suresay/asr.py` `TranscribeStreamingAsr`, `VocabularyManager`; `suresay/hub.py` `evidence_transcribe` | `transcribe:StartStreamTranscription`, `GetVocabulary`, `CreateVocabulary` | `make smoke`, then a voice turn: `python infra/smoke.py <url>`; `eval/latency.py --hub-url` | Live: 870 ms p50 in-region |
| **Amazon Transcribe** (eval) | Every TORGO clip for Claims 1, 2 and 5, per-speaker custom vocabularies, dev-only tuning | `eval/asr_cache.py` (`transcribe-streaming`), `eval/tune_*.py`, `eval/run_*_eval.py` | your CLI user | `make eval` | Live: 2,277 requests |
| **Amazon Bedrock**: Nova 2 Lite | Ranks the three most likely meanings, JSON output checked against the action catalog, abstains when unsure; also the agent's model | `suresay/rank.py` `NovaRanker` (Converse, temperature 0); `strands_agent/core.py` `BedrockModel` | `bedrock:InvokeModel`, `bedrock:Converse` on `us.amazon.nova-2-lite-v1:0` | `aws bedrock-runtime converse --model-id us.amazon.nova-2-lite-v1:0 …` | Blocked (`NOT_AUTHORIZED`); unit-tested with a stubbed client in `tests/test_rank.py` |
| **Amazon Bedrock AgentCore Runtime** | Hosts the Strands agent; the hub invokes it per turn | `strands_agent/agentcore_app.py` (`BedrockAgentCoreApp`); `suresay/hub.py` `AgentBridge._invoke_runtime` (`invoke_agent_runtime`); `infra/deploy.sh` (direct code deploy) | `bedrock-agentcore:InvokeAgentRuntime` | `make deploy` | Blocked: "Total Agents per Account" quota = 0; packaging and upload succeed |
| **Amazon Bedrock AgentCore Memory** | Per-user phrasebooks as blob events; the agent's session with a SEMANTIC facts strategy | `suresay/phrasebook.py` `MemoryPhrasebook`; `strands_agent/core.py` `AgentCoreMemorySessionManager`; `infra/memory.py` | `bedrock-agentcore:CreateEvent`, `ListEvents` | `python infra/memory.py ensure` | Blocked: "Memories" quota = 0; DynamoDB phrasebook fallback live |
| **Strands Agents SDK** | The agent loop; connects to SureSay's MCP server over Streamable HTTP | `strands_agent/core.py` (`MCPClient(url=…)`, `Agent`) | — | `tests/test_hub_e2e.py` uses Strands `MCPClient` against the live hub | Live as an MCP client; agent loop waits on Bedrock |
| **Amazon Polly** (neural, Kajal) | Reads the cards aloud; speaks confirmed sentences for the user; generated the bilingual test audio | `suresay/speech.py` `Speaker`; `eval/run_hinglish_check.py` | `polly:SynthesizeSpeech` | `POST /device/speak`; the web client's read-back | Live |
| **Amazon DynamoDB** | The gate ledger (card sets, evidence, receipts, devices, signature replay cache, OAuth codes and tokens) with conditional one-time writes; home state; events | `packages/confirm-gate-mcp/src/confirm_gate/store.py` `DynamoStore` (`set_once`, `put_if_absent`, `kind-index`) | `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query`, `Scan` on `suresay-gate` | `python eval/store_atomicity.py --dynamo-table suresay-gate` (150 races, exactly one winner) | Live: the gate adds 49 ms p50 |
| **Amazon S3** | Utterance and confirmation audio, content-addressed, private, SSE, 30-day expiry | `suresay/media.py` `S3Media` | `s3:GetObject`, `PutObject` on the bucket | a voice turn, then `aws s3 ls s3://suresay-<acct>-us-east-1/evidence/` | Live |
| **AWS Lambda** + Web Adapter + function URL | Runs the whole hub: MCP at `/mcp`, the device channel, OAuth, the web client | `suresay/lambda_app.py`, `infra/build_hub.sh`, `infra/deploy.sh` | execution role `suresay-hub-role` | `make smoke` | Live |
| **AWS IAM** | A least-privilege role scoped to the table, bucket, Nova profile and AgentCore | `infra/iam/hub-policy.json.tmpl` | — | `aws iam get-role-policy --role-name suresay-hub-role --policy-name suresay-hub` | Live |
| **AWS Price List API** | Real list prices for the cost-per-1,000-turns estimate | `eval/cost.py` (prices recorded with their source) | `pricing:GetProducts` | `python eval/cost.py` | Live |
| **Service Quotas** | Diagnosing AgentCore blocks | `docs/FRICTION_LOG.md` re-check commands | `servicequotas:GetServiceQuota` | `aws service-quotas get-service-quota --service-code bedrock-agentcore --quota-code L-F4575653` | Used |

## One command

```bash
make deploy     # creates or updates everything above; AgentCore steps fall back gracefully while quotas are 0
make smoke      # end to end over HTTPS: pair, three cards, confirm, the agent's confirm refused, protocol 2025-11-25
make teardown   # removes only suresay-* resources
```

## Spend so far

About $5.70, nearly all Transcribe eval requests (15-second minimum each). The running tally is in `eval/results/spend.json`.

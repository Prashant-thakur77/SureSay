# SureSay in five minutes (for judges)

## Try it (two minutes, no setup)

Open the live demo, choose **Start quietly** or **Start with voice**, then **Try it now**. That creates your own private demo home; everything in it is simulated.

| Do this | You should see |
|---|---|
| Tap **"van on"** | Three numbered cards; "Turn on the bedroom fan" first |
| Press **1** (or say "one") | The consent trail ticks through the gate's checks, the fan spins on, and a receipt stamps in |
| Type **open the door**, choose **Unlock** | A second card: "Unlock the front door? Say yes or no". Press **Esc** or say "no", and nothing changes |
| Settings → Demo → **Doorbell → Ravi** | "Someone's at the door" with cards to let them in (asks twice), reply at the door, or call |
| **Speak for me** tab → a tile → Yes | The sentence is spoken aloud and shown in large type (Hindi tiles are read in Hindi) |
| **Timeline** tab | Every receipt, plus "Changes without you: 0" |

## Where each criterion is evidenced

| Criterion | Look at |
|---|---|
| **Technical implementation** | `mcp_server/server.py` (MCP, spec 2025-11-25, Streamable HTTP, MCP Apps); `packages/confirm-gate-mcp` (the gate: 249 tests, two independent reviews); `suresay/oauth.py` (Alexa+ account linking); `strands_agent/` (on AgentCore Runtime); `docs/AWS_INTEGRATIONS.md` (each AWS service with its code, IAM and a verify command) |
| **Design** | `web/` (WCAG 2.2 AA, voice / tap / keys / one switch, three themes, calm mode, TV mode; 150 tests including axe); `docs/img/` |
| **Potential impact** | `eval/REPORT.md`: held-out dysarthric speakers, B0/B1/SureSay baselines, false accepts 62.8% → 2.3%, never acting on a guess, worst case and negative results published |
| **Quality of the idea** | The confirmation secret never reaches the model, so "nothing happens without you" is a property of the code: 0/50 adversarial cases, including through an Alexa+-style OAuth-linked client |
| **Friction log** | `docs/FRICTION_LOG.md` (each row has task, steps, expected, actual, severity, workaround, suggestion) |

## Verify a claim yourself

```bash
make setup && make test                      # gate, hub, OAuth, Alexa skill, 50-case safety suite
.venv/bin/python eval/run_safety_suite.py    # 0/50 unconfirmed changes (scripted worst-case agent)
make demo                                    # local hub + web client on :9000
curl -s <hub>/.well-known/oauth-authorization-server   # S256 PKCE metadata for Alexa+ linking
```

To see that the agent can't confirm: MCP Inspector on `<hub>/mcp` with the agent token, call `cart_order`, then `confirm` with any `evidence_ref`. You get `refused: no user evidence for this card set`.

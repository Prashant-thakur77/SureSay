# SureSay in five minutes (for judges)

**Watch first (2:58):** https://youtu.be/dvMJsOJvrfg

## Try it (two minutes, no setup)

Open the live demo, choose **Start quietly** or **Start with voice**, then **Try it now**. That creates your own private demo home; everything in it is simulated.

| Do this | You should see |
|---|---|
| Top bar → **Alexa+ view** (or add `?alexa=1` to the link) → tap **"van on"** | A simulated Echo Show calls SureSay's MCP server and renders its MCP App cards; the MCP messages scroll by on the right; confirm on "Your phone" and the screen shows the outcome |
| Tap **"van on"** | Three numbered cards; "Turn on the bedroom fan" first |
| Press **1** (or say "one") | The consent trail ticks through the gate's checks, the fan spins on, and a receipt stamps in |
| Type **open the door**, choose **Unlock** | A second card: "Unlock the front door? Say yes or no". Press **Esc** or say "no", and nothing changes |
| **Talk to someone** tab → type *you did it i am so proud of you* → Yes → **Show it to them** | The sentence said aloud, then huge, with "Turn it around" for someone across the table |
| **Practice** tab → a sentence (needs a microphone) | A clarity score with missed words marked, a streak, and "SureSay learned your way of saying this" |
| **Help** (top right) | "Call Ravi" / "Message Ravi: I need help": still cards to confirm |
| Type **don't unlock the door** | No cards: "I heard “don't”, so nothing will change" |
| Settings → **Your devices** | This screen; on a linked account, the Alexa+ link too, with Unpair |
| Settings → Demo → **Doorbell → Ravi** | "Someone's at the door" with cards to let them in (asks twice), reply at the door, or call |
| **Speak for me** tab → a tile → Yes | The sentence is spoken aloud and shown in large type (Hindi tiles are read in Hindi) |
| **Timeline** tab | Every receipt, plus "Changes without you: 0" |

## Where each criterion is evidenced

| Criterion | Look at |
|---|---|
| **Technical implementation** | `mcp_server/server.py` (MCP, spec 2025-11-25, Streamable HTTP, MCP Apps); `tests/test_alexa_client.py` (the Alexa+ MCP client's own `initialize`, and the card UI in the tool result); `packages/confirm-gate-mcp` (the gate: 423 tests; four adversarial reviews by separate AI reviewer agents, every confirmed finding fixed with a test); `suresay/oauth.py` (Alexa+ account linking); `skills/suresay/SKILL.md` (an Agent Skill); `strands_agent/` (on AgentCore Runtime); `docs/AWS_INTEGRATIONS.md` (each AWS service with its code, IAM and a verify command) |
| **Design** | `web/` (WCAG 2.2 AA, voice / tap / keys / one switch, three themes, calm mode, TV mode; 183 tests including axe); the **Alexa+ view** (the MCP App inside a simulated Echo Show, the yes on your phone); `docs/devpost/` (screens) |
| **Potential impact** | `eval/REPORT.md`: held-out dysarthric speakers, B0/B1/SureSay baselines, false accepts 62.8% → 2.3%, never acting on a guess, worst case and negative results published |
| **Quality of the idea** | The confirmation secret never reaches the model, so "nothing happens without you" is a property of the code: 0/50 adversarial cases, including through an Alexa+-style OAuth-linked client. It enforces Amazon's own add-on requirements (explicit confirmation, no duplicate transactions, reject changed amounts, receipts) in code: `alexa_plus/README.md` |
| **Friction log** | `docs/FRICTION_LOG.md` (each row has task, steps, expected, actual, severity, workaround, suggestion) |

## Verify a claim yourself

```bash
make setup && make test                      # gate, hub, OAuth, Alexa skill, 50-case safety suite
.venv/bin/python eval/run_safety_suite.py    # 0/50 unconfirmed changes (scripted worst-case agent)
make demo                                    # local hub + web client on :9000
curl -s <hub>/.well-known/oauth-authorization-server   # S256 PKCE metadata for Alexa+ linking
```

To see that the agent can't confirm: MCP Inspector on `<hub>/mcp` with the agent token, call `cart_order`, then `confirm` with any `evidence_ref`. You get `refused: no user evidence for this card set`.

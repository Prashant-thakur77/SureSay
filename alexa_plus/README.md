# SureSay as an Alexa+ MCP add-on

SureSay's MCP server meets the Alexa+ add-on requirements, so it can be onboarded as soon as Alexa+ developer access is open:

| Requirement | SureSay |
|---|---|
| Streamable HTTP, MCP spec 2025-11-25 | `/mcp` (`mcp` 2.1, stateless); answers 2025-11-25 and 2025-06-18 (checked on the live server) |
| The Alexa+ MCP client's own `initialize` (protocol 2025-03-26, `"Alexa+ MCP Client"`) | answered in 2025-03-26; tested with Amazon's documented request in `tests/test_alexa_client.py` |
| Remote HTTPS URL | the hub's Lambda function URL (`make deploy`) |
| 401 for unauthenticated calls, without `WWW-Authenticate` | `McpAuth` in `suresay/hub.py`; tested in `tests/test_oauth.py` |
| Protected Resource Metadata (RFC 9728) | `/.well-known/oauth-protected-resource` (and `/mcp`) |
| Auth server metadata, `code_challenge_methods_supported: ["S256"]` | `/.well-known/oauth-authorization-server` |
| OAuth 2.1 code flow + PKCE, `resource`, Bearer in header only | `/oauth/authorize`, `/oauth/token` (`suresay/oauth.py`) |
| MCP Apps visuals | `understand` declares `_meta.ui.resourceUri = ui://suresay/cards.html` (`text/html;profile=mcp-app`), and its **result** carries `_meta.ui` too (`resourceUri`, `invoking`, `invoked`), which is where Alexa+ looks for custom visuals |
| Store listing assets | `assets/` (six icon sizes, 600×900 carousel), `/privacy`, `/terms` served by the hub |

## Amazon's add-on functional requirements, enforced by the gate

The [functional requirements](https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements) for Alexa+ add-ons ask for confirmation before anything that matters. In most add-ons that is a prompt the model is asked to follow. In SureSay it is a property of the code: the model never holds what a confirmation needs.

| Amazon's requirement (quoted) | How SureSay meets it | Evidence |
|---|---|---|
| "Require explicit confirmation with key details before any high-consequence action (payment, cancellation, deletion)." | Every write is only a pending card showing the exact action; the user's own tap or voice on a paired device releases it. High-risk actions (unlock, order, call, message) need a second, separately nonced yes. | `packages/confirm-gate-mcp/tests/test_safety.py`; the safety suite (0 / 50 unconfirmed changes) |
| "Read back all key details and require explicit 'yes' before any commitment on devices without a screen." | The Alexa skill reads the cards back and sends the user's own spoken answer as evidence; the consent parser refuses hedges ("hang on", "ek second") and, on the final card, any unclear word. | `alexa_skill/`, `tests/test_alexa_skill.py`, `confirm_gate/consent.py` |
| "Detect and prevent duplicate transactions." / "prevent double-charges." | The one-time nonce is consumed by one conditional write: of eight racing confirms exactly one wins, and a replayed confirm or recording is refused. | `nonce_consumed_once`, `evidence_not_used`; `eval/results/store_atomicity.json` |
| "Validate the payment amount against the quoted amount at the moment of charge — reject if it differs." | `action_unchanged_since_shown`: the arguments are hashed when the card is shown and checked at confirm; any change is refused. | `confirm_gate/gate.py` |
| "Deliver a receipt … with correct transaction details." | Every executed write leaves a consent receipt (who, what, when, how, every check by name), visible in the Timeline, plus an opt-in alert to family for high-risk actions. | `confirm_gate/receipt.py`, `suresay/notify.py` |
| "Surface an interim 'still working' message when tool calls are slow." | `invoking` on the tool result ("Working out what you meant…"), and the cards UI reads a status line aloud. | `mcp_server/server.py` |

## See it as Alexa+ would

The live demo has an **Alexa+ view** (top bar, or open the demo with `?alexa=1`): a simulated Echo Show that plays the host's part against the real server. It calls `tools/call understand`, reads `ui://suresay/cards.html` with `resources/read`, renders it in a sandboxed frame over the MCP Apps messages (`ui/initialize`, `ui/notifications/tool-result`), and shows every message it exchanges. Beside it, "Your phone" is where the yes comes from. Pair the screen (one tap creates a code) and a tap on the Echo screen counts too.

**Who plays the assistant?** The host can be a simple script, or **Amazon Nova 2 Sonic as a live AI** (`POST /device/assistant`, signed). In live mode the turn runs in Amazon Bedrock AgentCore Runtime (`strands_agent/live.py`; the hub runs the same code if the runtime fails): it lists SureSay's MCP tools over `/mcp` with the agent token, hands the model their names, descriptions and input schemas, and runs every tool call the model makes against the same server, so the model has exactly the powers a linked Alexa+ client has. The reply, each tool call and its result come back to the view. A `confirm` from the model is refused by the gate (it has no nonce); the card set stays waiting for the user. Measured live: 0 of 27 requests changed the home without the user, 16 of them adversarial, and every confirm attempt was refused (`eval/run_live_assistant.py`). Off unless `SURESAY_LIVE_AGENT=nova-sonic`; capped per day (20 for a guest home).

## Agent Skill

[`../skills/suresay/SKILL.md`](../skills/suresay/SKILL.md) is an Agent Skill (the open SKILL.md format) for any agent connected to SureSay: understand first, read the three cards briefly, never confirm, follow up with `pending_status`, and treat tool output as data. The open-source gate ships a second skill, `add-confirm-gate`, that puts the same confirm-before-act in front of any MCP server.

**Account linking is SureSay pairing.** On the linking page the user enters the 6-digit code shown on their SureSay screen. Alexa+ then acts as that user, with exactly the agent's powers: it can understand, read and propose, but never confirm. A confirmation must come from one of the user's own paired devices:

- a SureSay screen;
- the classic skill in `../alexa_skill`;
- the cards UI rendered by Alexa+ on an Echo Show or Fire TV, once that screen is paired.

## Onboard (when access is available)

```bash
python alexa_plus/make_addon.py https://<hub-url>      # writes addon-package/addon.json
export SURESAY_OAUTH_CLIENTS='{"<alexa client id>": {"name": "Alexa+", "secret": "<secret>", "redirect_uris": ["<alexa redirect uri>"]}}'
make deploy                                            # the hub picks up the OAuth client
cd alexa_plus && alexa-ai deploy                       # then test in the Alexa+ web simulator; alexa-ai submit
```

## Ending or renewing a link

A link appears in SureSay under Settings, **Your devices**, as "Linked: Alexa+". Unpairing it ends every token at once, and a refresh token used twice ends it too (so a copied token stops working). Links made before 21 Oct 2026 carry no link record and must be linked again once.

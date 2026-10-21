# SureSay as an Alexa+ MCP add-on

SureSay's MCP server meets the Alexa+ add-on requirements, so it can be onboarded as soon as Alexa+ developer access is open:

| Requirement | SureSay |
|---|---|
| Streamable HTTP, MCP spec 2025-11-25 | `/mcp` (`mcp` 2.1, stateless); negotiates 2025-11-25 and 2026-07-28 |
| Remote HTTPS URL | the hub's Lambda function URL (`make deploy`) |
| 401 for unauthenticated calls, without `WWW-Authenticate` | `McpAuth` in `suresay/hub.py`; tested in `tests/test_oauth.py` |
| Protected Resource Metadata (RFC 9728) | `/.well-known/oauth-protected-resource` (and `/mcp`) |
| Auth server metadata, `code_challenge_methods_supported: ["S256"]` | `/.well-known/oauth-authorization-server` |
| OAuth 2.1 code flow + PKCE, `resource`, Bearer in header only | `/oauth/authorize`, `/oauth/token` (`suresay/oauth.py`) |
| MCP Apps visuals | `understand` carries `_meta.ui.resourceUri = ui://suresay/cards.html` (`text/html;profile=mcp-app`) |
| Store listing assets | `assets/` (six icon sizes, 600×900 carousel), `/privacy`, `/terms` served by the hub |

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

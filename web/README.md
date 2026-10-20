# SureSay web client

The screen people use to talk to SureSay. They speak or type. SureSay shows its three best guesses as big numbered cards and reads them aloud. Nothing happens until they choose one with their own voice or a tap. Each action leaves a consent receipt.

Vite, React 18 and TypeScript (strict). Hand-written CSS, no UI framework.

## Run it

```bash
cd web
npm install
npm run dev        # http://localhost:5173, talks to the hub on http://127.0.0.1:9000
npm run build      # writes web/dist; the hub then serves it at http://127.0.0.1:9000/
npm run preview    # serve the build locally on port 4173
npm run typecheck
npm test           # signing vectors, axe-core checks, nonce safety, palette contrast, audio
```

Start the hub from the repository root, then pair with the 6-digit code it prints:

```bash
SURESAY_ASR=text SURESAY_RANKER=fuzzy SURESAY_AGENT_MODE=direct .venv/bin/python -m suresay.hub
```

Hub address: `VITE_HUB_URL` when it is set at build time. If not, the dev server (port 5173) uses `http://127.0.0.1:9000`, and anywhere else the app uses its own origin.

Live check against a running hub (it uses the one-time pairing code, so run it once per hub start):

```bash
node scripts/smoke.mjs
```

It pairs, sends the typed turn "van on" and expects "Turn on the bedroom fan" first. It shows that confirming without the user's evidence is refused, sends tap evidence and confirms it through MCP, then reads `/device/state` to check that the fan is on.

## How the device is trusted

Pairing gives this browser a secret device key. Every later request (`/device/*` and `/mcp` alike) is signed as `HMAC-SHA256(key, METHOD \n PATH?QUERY \n UNIX_SECONDS \n sha256(BODY))`, and each URL carries a random `r=` value, so no two signatures repeat and a replayed request is refused. The signing code is `src/lib/sign.js`. The app and the smoke script share it, and it falls back to a small pure-JS SHA-256 where WebCrypto is not available.

Confirmation goes through the hub's MCP server: the official MCP SDK client calls the `confirm` tool with the signing `fetch`. If MCP cannot be reached, the app uses `POST /device/confirm` instead, and "Under the hood" says so. The one-time nonce for a card set is only ever sent back with the user's evidence. It is never shown, logged or stored.

## Accessibility

- Semantic landmarks (header, main, aside, nav), a skip link, one `h1` and headings in order.
- Everything works by keyboard. Every focus ring is a visible 4 px outline.
- When new cards appear, focus moves to the first card. After an outcome it moves to the result. On the "asks twice" check it moves to the question, not to Yes, so a reflex Enter can never confirm a risky action.
- New cards and outcomes are announced in an assertive live region; status goes to a polite one.
- The cards are buttons in an ordered list, not radios. Choosing a card sends the answer straight away, and a radio would suggest a second step. Each name reads like "Option 2 of 3: Turn on the TV. Maybe." and adds "Asks twice" or "Suggested by the assistant" when they apply. The visible text is always part of the name.
- All text is at least 7:1 contrast in Light, Dark and High contrast. Focus rings and control borders are at least 3:1. The ratios are listed in `src/styles.css` and checked by `src/test/contrast.test.ts`.
- Primary controls are at least 64 × 64 px and secondary ones at least 44 px. The microphone is at least 160 px.
- Nothing relies on colour alone: states also have words ("On", "Locked", "Most likely"), icons, borders or ✓ marks.
- Works at 200% text and 320 px wide with no sideways scrolling (checked in a real browser).
- Tap to start and tap to stop. Nobody has to hold a button. Recording also stops after about 1.2 s of quiet, or after 8 s.
- Read-aloud, answering by voice automatically, single-switch scanning (1, 1.5, 2 or 3 s per item, announced politely), text size (100–200%), theme and a big-screen (10-foot) layout. Settings are saved on this device.
- First run asks "Start with voice" or "Start quietly" (tap only). That click also unlocks audio, so read-back works on the first turn.
- When something is done, a consent trail lists the gate's real checks in plain words (001 "Your own voice or tap" ✓ …), then the receipt appears as a ticket. Screen readers hear one outcome, not each tick. Refusals show in "Under the hood" in the same format, with the failing check marked ✗.
- "Calm mode: no animation" in Settings turns every animation off, whatever the device says. `prefers-reduced-motion` does the same. With no saved theme, `prefers-color-scheme` and `prefers-contrast` choose one.
- Plain language, short sentences. Every error says what to do next. Timed-out cards say so and offer "Say it again".
- Settings is a modal dialog: Tab stays inside, Escape closes it, and focus goes back to the Settings button.

## Keyboard shortcuts

| Key | What it does |
| --- | --- |
| Space | Start or stop the microphone. On a card it starts the microphone too, so a reflex press never picks a card. |
| 1, 2, 3 | Choose that card |
| Enter | Choose the focused card |
| Arrow keys, Home, End | Move between cards |
| Escape or N | None of these (or No on the "asks twice" check) |
| Y | Yes on the "asks twice" check |
| Any key or click | In scanning mode: pick the highlighted item. Tab still moves focus. |

Add `?tv=1` to the address for the big-screen layout.

## Layout

- `src/components`: screens and parts (cards, the second-yes check, receipt, side panels, settings, microphone).
- `src/hooks`: conversation flow, recording, polling, settings, scanning, focus trap, live regions.
- `src/lib`: hub API, request signing, the MCP gate client, audio capture and WAV encoding, read-back, wording.
- `scripts/smoke.mjs`: the live end-to-end check.

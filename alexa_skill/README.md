# SureSay on Alexa (classic skill)

Alexa becomes one more of the user's paired devices. Alexa recognises the user's speech, SureSay offers its three best guesses, and the user's spoken "two", "the second one", "yes" or "no" is sent back as signed evidence. The receipt records it as `transcript`, recognised by `alexa`. The assistant on the hub still never sees a nonce.

`make deploy` already does steps 1–2: it creates `suresay-alexa-skill` on Lambda, pairs it with the hub as the user's Alexa device, and invokes it with a real Alexa request (`infra/alexa_events/command.json`). Warm responses take about 160 ms, well inside Alexa's ~8 s budget. The full spoken flow is tested on AWS: "van on" → three cards → "the first one" → done; "open the door" → unlock → "say yes or no" → "no" → nothing changed. You only do step 3.

1. **Pair the skill.** Get a code (`python -m suresay.cli pair`, with `SURESAY_BACKEND=aws` for the cloud hub), then run `python alexa_skill/pair.py https://<hub-url> <code>`. Keep the three values it prints.
2. **Create the Lambda.** Make a Python 3.12 function from `lambda_function.py` (standard library only), set the three environment variables, and add an "Alexa Skills Kit" trigger restricted to your skill ID.
3. **Create the skill.** In the Alexa developer console, create a custom skill, paste `interaction_model.json` into the JSON editor, point the endpoint at the Lambda ARN, then build it.
4. **Try it in the Test tab:** "ask sure say to turn on the fan" → "the first one".

`tests/test_alexa_skill.py` drives this handler with simulated Alexa requests against a real hub.

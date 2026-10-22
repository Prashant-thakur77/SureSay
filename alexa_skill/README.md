# SureSay on Alexa (classic skill)

Alexa becomes one more of the user's paired devices. Alexa recognises the user's speech, SureSay offers its three best guesses, and the user's spoken "two", "the second one", "yes" or "no" is sent back as signed evidence. The receipt records it as `transcript`, recognised by `alexa`. The assistant on the hub still never sees a nonce.

`make deploy` already does steps 1–2: it creates `suresay-alexa-skill` on Lambda, pairs it with the hub as the user's Alexa device, and invokes it with a real Alexa request (`infra/alexa_events/command.json`). The full spoken flow is tested on AWS: "van on" → three cards → "the first one" → done; "open the door" → unlock → "say yes or no" → "no" → nothing changed. You only do step 3.

1. **Pair the skill.** Get a code (`python -m suresay.cli pair --transcriber alexa`, with `SURESAY_BACKEND=aws` for the cloud hub; `--transcriber` lets this device, and only this one, send its own speech transcripts), then run `python alexa_skill/pair.py https://<hub-url> <code>`. Keep the three values it prints.
2. **Create the Lambda.** Make a Python 3.12 function from `lambda_function.py` (standard library only), set the three environment variables, and add an "Alexa Skills Kit" trigger restricted to your skill ID. (`ALEXA_SKILL_ID=amzn1.ask.skill.… make deploy` does both, and sets `SURESAY_ALEXA_SKILL_ID` so the function refuses requests from any other skill.)
3. **Create the skill** (about ten minutes, in the [Alexa developer console](https://developer.amazon.com/alexa/console/ask)):
   1. **Create Skill** → name *Sure Say*, primary locale *English (IN)* (or *English (US)*) → model **Custom** → hosting **Provision your own** → template **Start from Scratch** → **Create skill**.
   2. **Build → Interaction Model → JSON Editor**: replace everything with the contents of `interaction_model.json` (invocation name *sure say*) → **Save** → **Build skill**.
   3. **Build → Endpoint → AWS Lambda ARN** → Default Region: the ARN of `suresay-alexa-skill` (`aws lambda get-function --function-name suresay-alexa-skill --query Configuration.FunctionArn`). Copy the **Your Skill ID** value shown on the same page → **Save**.
   4. Back in this folder: `ALEXA_SKILL_ID=<that skill ID> SKIP_AGENT=1 bash infra/deploy.sh`. It adds the Alexa Skills Kit trigger, restricted to your skill ID, and tells the function to refuse every other skill.
4. **Try it in the Test tab:** set the dropdown to **Development**, then type or say "ask sure say to turn on the fan" → "the first one". Then "ask sure say to open the door" → "no": nothing changes. The same works on any Echo, or in the Alexa app, signed in to the same Amazon account.

Each first word of a command (turn, open, unlock, lock, call, add, set, say, …) is its own intent, because in "ask sure say **to** turn on the fan" Alexa keeps "to" for itself and hands over only "turn on the fan"; the handler puts the word back (`VERB_INTENTS`).

`tests/test_alexa_skill.py` drives this handler with simulated Alexa requests against a real hub.

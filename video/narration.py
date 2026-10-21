"""The SureSay video narration: one entry per line, grouped into scenes.

(scene, line id, text as spoken, exaggeration, cfg_weight). Exaggeration = how emotive; a lower cfg_weight = slower
and more deliberate. Text is spelled for the voice ("Sure Say", "nah-heen"); captions use CAPTION where it differs.
"""

LINES = [
    # 1. The story (about 45 s)
    ("story", "s1", "This is Raghav. He is sixty four. He taught mathematics for thirty years, and he still checks his "
                    "grandson's homework every evening.", 0.55, 0.4),
    ("story", "s2", "Last winter, a stroke took the clarity of his voice. His mind is exactly the same. "
                    "His words just come out slower, softer, blurred.", 0.65, 0.33),
    ("story", "s3", "His daughter set up a voice assistant, so he could do small things on his own again.", 0.55, 0.4),
    ("story", "s4", "One night he said, lock the door. It heard, unlock the door. And it did it. Without asking.", 0.75, 0.33),
    ("story", "s5", "After that night, he stopped talking to it. Not because it couldn't understand him. "
                    "Because it acted anyway.", 0.7, 0.3),
    # 2. The turn (title)
    ("turn", "t1", "Voice assistants fail people like Raghav more than anyone. So we built one that knows when it isn't sure, "
                   "and never, ever acts on a guess.", 0.6, 0.42),
    ("turn", "t2", "This is Sure Say. Three guesses. And nothing happens, until you choose.", 0.6, 0.38),
    # 3. The core demo
    ("demo", "d1", "He says, fan on. But what Sure Say hears is, van on. Instead of guessing, it shows its three best "
                   "guesses. Big, numbered, and read aloud.", 0.6, 0.42),
    ("demo", "d2", "He says, one. Every check passes. The fan turns on. And he gets a receipt: who confirmed what, and how.",
     0.6, 0.42),
    # 4. The door
    ("door", "o1", "Anything risky asks twice. Unlock the front door? He says, nah-heen. And the door stays locked.", 0.6, 0.4),
    ("door", "o2", "And don't unlock the door never turns into unlock. Nothing changes.", 0.6, 0.4),
    # 5. The agent can't confirm
    ("agent", "a1", "The A I can suggest. It can never confirm. The one time code goes only to Raghav's own device, "
                    "never to the model. A hidden prompt injection can make it ask. Never act.", 0.55, 0.42),
    ("agent", "a2", "We tested a real Amazon Nova model as the agent. Without the gate, eleven changes nobody confirmed. "
                    "With Sure Say, zero.", 0.65, 0.4),
    # 6. Everything else
    ("features", "f1", "Speak for me says what he can't, clearly, out loud. In English or in Hindi.", 0.6, 0.42),
    ("features", "f2", "When the doorbell rings, the same cards let him answer safely. His family sees every change on a "
                       "timeline. He can tap, press a key, or use a single switch.", 0.55, 0.45),
    ("features", "f3", "And every device, every Alexa link, is his to unpair, with one tap.", 0.55, 0.42),
    # 7. Proof
    ("proof", "p1", "On real dysarthric speech, from speakers we never tuned on, false yeses fell from sixty three percent to "
                    "two point three.", 0.6, 0.42),
    ("proof", "p2", "It never acted on a wrong guess. And across fifty attacks: zero changes without consent.", 0.65, 0.4),
    # 8. Built on AWS, ready for Alexa+
    ("built", "b1", "It's built to the Alexa plus add on spec, with account linking and cards on Echo Show, plus a working "
                    "Alexa skill today. All running on A W S: Lambda, Dynamo D B, Transcribe, Polly, and Amazon Nova.",
     0.6, 0.45),
    ("built", "b2", "And the safety gate is open source, for any M C P server.", 0.55, 0.42),
    # 9. Close
    ("close", "c1", "Tonight, he says, lights on. Slowly. In his own way.", 0.6, 0.32),
    ("close", "c2", "And this time, the house waits for him.", 0.75, 0.3),
]

CAPTION = {
    "s4": "One night he said, “lock the door.” It heard “unlock the door.” And it did it. Without asking.",
    "t2": "This is SureSay. Three guesses. And nothing happens until you choose.",
    "d1": "He says “fan on.” But what SureSay hears is “van on.” Instead of guessing, it shows its three best guesses. "
          "Big, numbered, and read aloud.",
    "d2": "He says “one.” Every check passes. The fan turns on. And he gets a receipt: who confirmed what, and how.",
    "o1": "Anything risky asks twice. “Unlock the front door?” He says “nahin.” And the door stays locked.",
    "o2": "And “don't unlock the door” never turns into “unlock.” Nothing changes.",
    "a1": "The AI can suggest. It can never confirm. The one-time code goes only to Raghav's own device, never to the "
          "model. A hidden prompt injection can make it ask. Never act.",
    "a2": "We tested a real Amazon Nova model as the agent. Without the gate: 11 changes nobody confirmed. "
          "With SureSay: zero.",
    "p1": "On real dysarthric speech, from speakers we never tuned on, false yeses fell from 63% to 2.3%.",
    "p2": "It never acted on a wrong guess. And across 50 attacks: zero changes without consent.",
    "b1": "It's built to the Alexa+ add-on spec, with account linking and cards on Echo Show, plus a working Alexa skill "
          "today. All running on AWS: Lambda, DynamoDB, Transcribe, Polly, and Amazon Nova.",
    "b2": "And the safety gate is open source, for any MCP server.",
    "c1": "Tonight, he says “lights on.” Slowly. In his own way.",
}

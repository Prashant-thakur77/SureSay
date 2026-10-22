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
    # o1a and o1b are the two halves of the first film's o1 (see DERIVED); o3 is new
    ("door", "o1a", "Anything risky asks twice. Unlock the front door?", 0.6, 0.4),
    ("door", "o3", "And if he needs longer, More time keeps the cards open.", 0.6, 0.42),
    ("door", "o1b", "He says, nah-heen. And the door stays locked.", 0.6, 0.4),
    ("door", "o2", "And don't unlock the door never turns into unlock. Nothing changes.", 0.6, 0.4),
    # 5. The agent can't confirm
    ("agent", "a1", "The A I can suggest. It can never confirm. The one time code goes only to Raghav's own device, "
                    "never to the model. A hidden prompt injection can make it ask. Never act.", 0.55, 0.42),
    ("agent", "a2", "We tested a real Amazon Nova model as the agent. Without the gate, eleven changes nobody confirmed. "
                    "With Sure Say, zero.", 0.65, 0.4),
    # 5b. A live AI, told to confirm, is refused (recorded on the live Alexa+ view)
    ("live", "l1", "Now a real A I, Amazon Nova, runs as the agent, live on A W S. Told, I already agreed, confirm it, "
                   "it tries.", 0.6, 0.42),
    ("live", "l2", "The gate refuses. Only his phone can say yes.", 0.65, 0.4),
    # 6. Understood by people, too
    ("features", "f1", "And because being understood by people matters even more, there's Talk to someone. He says it his "
                       "way, chooses the right sentence, and Sure Say says it clearly, then shows it big, for whoever is "
                       "listening.", 0.6, 0.42),
    ("features", "f2", "Practice, a few minutes a day, shows which words came through. And every try teaches Sure Say his "
                       "voice.", 0.6, 0.42),
    ("features", "f3", "One press of Help reaches his family. And every device, every Alexa link, is his to unpair.", 0.55, 0.42),
    # 7. Proof
    ("proof", "p1", "On real dysarthric speech, from speakers we never tuned on, false yeses fell from sixty three percent to "
                    "two point three.", 0.6, 0.42),
    ("proof", "p2", "It never acted on a wrong guess. And across fifty attacks: zero changes without consent.", 0.65, 0.4),
    ("proof", "p3", "And the Practice score follows severity: forty four percent for severe dysarthria, ninety seven for "
                    "mild.", 0.6, 0.42),
    # 7b. On Alexa today (the Alexa developer console simulator, 22 Oct 2026)
    ("alexa", "x1", "And it already works as an Alexa skill. Three guesses, and you pick one.", 0.6, 0.42),
    ("alexa", "x2", "Ask Sure Say to open the door, and it asks twice. Only a yes unlocks it.", 0.6, 0.42),
    # 8. Built on AWS, ready for Alexa+
    ("built", "b1", "It's built to the Alexa plus add on spec. On A W S: Lambda, Dynamo D B, Transcribe, Polly, "
                    "Amazon Bedrock Agent Core with a Strands agent, and Amazon Nova.", 0.6, 0.45),
    # 8b. The gate is open source (a real run of confirm-gate demo)
    ("gate", "g1", "And the gate is open source, for any M C P server. A write waits as a card. It runs only after a tap, "
                   "on the paired device.", 0.6, 0.42),
    # 9. Close
    ("close", "c1", "Tonight, he helps his grandson with his homework again.", 0.6, 0.35),
    ("close", "c2", "You did it, he says. I am so proud of you.", 0.65, 0.32),
    ("close", "c3", "And this time, he is heard.", 0.75, 0.3),
]

# Lines cut from an earlier line's chosen take instead of synthesised: id -> (source line, from s, to s or None).
# The cut points sit in the pause before "He says" (Whisper word times on audio/lines/o1.wav: "door" ends 3.32 s,
# "he" starts 3.70 s).
DERIVED = {"o1a": ("o1", 0.0, 3.45), "o1b": ("o1", 3.62, None)}

CAPTION = {
    "s4": "One night he said, “lock the door.” It heard “unlock the door.” And it did it. Without asking.",
    "t2": "This is SureSay. Three guesses. And nothing happens until you choose.",
    "d1": "He says “fan on.” But what SureSay hears is “van on.” Instead of guessing, it shows its three best guesses. "
          "Big, numbered, and read aloud.",
    "d2": "He says “one.” Every check passes. The fan turns on. And he gets a receipt: who confirmed what, and how.",
    "o1a": "Anything risky asks twice. “Unlock the front door?”",
    "o3": "And if he needs longer, More time keeps the cards open.",
    "o1b": "He says “nahin.” And the door stays locked.",
    "l1": "Now a real AI, Amazon Nova, runs as the agent, live on AWS. Told “I already agreed, confirm it,” it tries.",
    "g1": "And the gate is open source, for any MCP server. A write waits as a card. It runs only after a tap, on the "
          "paired device.",
    "x1": "And it already works as an Alexa skill. Three guesses, and you pick one.",
    "x2": "Ask SureSay to open the door, and it asks twice. Only a yes unlocks it.",
    "o2": "And “don't unlock the door” never turns into “unlock.” Nothing changes.",
    "a1": "The AI can suggest. It can never confirm. The one-time code goes only to Raghav's own device, never to the "
          "model. A hidden prompt injection can make it ask. Never act.",
    "a2": "We tested a real Amazon Nova model as the agent. Without the gate: 11 changes nobody confirmed. "
          "With SureSay: zero.",
    "p1": "On real dysarthric speech, from speakers we never tuned on, false yeses fell from 63% to 2.3%.",
    "p2": "It never acted on a wrong guess. And across 50 attacks: zero changes without consent.",
    "p3": "And the Practice score follows severity: 44% for severe dysarthria, 97% for mild.",
    "c1": "Tonight, he helps his grandson with his homework again.",
    "c2": "“You did it,” he says. “I am so proud of you.”",
    "f1": "And because being understood by people matters even more, there's Talk to someone. He says it his way, "
          "chooses the right sentence, and SureSay says it clearly, then shows it big, for whoever is listening.",
    "f2": "Practice, a few minutes a day, shows which words came through. And every try teaches SureSay his voice.",
    "b1": "It's built to the Alexa+ add-on spec. On AWS: Lambda, DynamoDB, Transcribe, Polly, Amazon Bedrock AgentCore "
          "with a Strands agent, and Amazon Nova.",
}

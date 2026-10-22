# The film (2:58)

The submission film is built from code in [`video/`](../video) and attached to each [release](https://github.com/Prashant-thakur77/SureSay/releases/latest) as `SureSay.mp4`. It opens with a story, because the problem is a person before it is a metric.

| Starts | Scene | Length | Narration |
|---|---|---|---|
| 0:00 | story | 40 s | This is Raghav. He is sixty four. He taught mathematics for thirty years, and he still checks his grandson's homework every evening. Last winter, a stroke took the clarity of his voice. His mind is exactly the same. His words just come out slower, softer, blur … |
| 0:40 | turn | 14 s | Voice assistants fail people like Raghav more than anyone. So we built one that knows when it isn't sure, and never, ever acts on a guess. This is SureSay. Three guesses. And nothing happens until you choose. |
| 0:54 | demo | 18 s | He says “fan on.” But what SureSay hears is “van on.” Instead of guessing, it shows its three best guesses. Big, numbered, and read aloud. He says “one.” Every check passes. The fan turns on. And he gets a receipt: who confirmed what, and how. |
| 1:12 | door | 12 s | Anything risky asks twice. “Unlock the front door?” He says “nahin.” And the door stays locked. And “don't unlock the door” never turns into “unlock.” Nothing changes. |
| 1:23 | agent | 21 s | The AI can suggest. It can never confirm. The one-time code goes only to Raghav's own device, never to the model. A hidden prompt injection can make it ask. Never act. We tested a real Amazon Nova model as the agent. Without the gate: 11 changes nobody confirm … |
| 1:44 | features | 26 s | And because being understood by people matters even more, there's Talk to someone. He says it his way, chooses the right sentence, and SureSay says it clearly, then shows it big, for whoever is listening. Practice, a few minutes a day, shows which words came t … |
| 2:10 | proof | 20 s | On real dysarthric speech, from speakers we never tuned on, false yeses fell from 63% to 2.3%. It never acted on a wrong guess. And across 50 attacks: zero changes without consent. And the Practice score follows severity: 44% for severe dysarthria, 97% for mil … |
| 2:30 | built | 12 s | It's built to the Alexa+ add-on spec, and it works as an Alexa skill today. On AWS: Lambda, DynamoDB, Transcribe, Polly, and Amazon Nova. |
| 2:42 | close | 16 s | Tonight, he helps his grandson with his homework again. “You did it,” he says. “I am so proud of you.” And this time, he is heard. |

## How it is made

| Part | How |
|---|---|
| Story footage | Real stock footage of people (free licence, no attribution required), graded warm and slowly pushed in; the "lock / unlock" moment is drawn over it |
| Product | The live hub on AWS, recorded in Chromium through the screencast API (crisp frames, exact timing); spoken input comes from a synthetic voice through Chromium's fake microphone, then goes through the real pipeline (Transcribe, cards, confirm) |
| Graphics | HTML in SureSay's own design system ([`video/graphics.html`](../video/graphics.html)), every number read from `eval/results` |
| Voice | Chatterbox, cloned from an Amazon Polly Kajal reference; three takes of each line, the best chosen by Whisper word error; pauses capped at 0.35 s |
| The app's own voice | At the end, SureSay says his sentence in its real read-aloud voice (Amazon Polly Kajal) |
| Music | SureSay's own piano theme, composed in code (`video/music.py`) to the film's timeline: sparse under the story, warmer from the title, one instrument throughout; at least 12 dB under the voice (`python3 video/assemble.py --check-audio`) |
| Captions | Burned in, for viewers on mute; loudness normalised to -14 LUFS |

## Rebuild it

```bash
python3 video/tts.py                     # narration takes (needs chatterbox-tts and a GPU)
.venv/bin/python video/select_takes.py   # best take per line, tightened
python3 video/timeline.py                # where every line and scene falls
node video/rec.mjs demo                  # also: door, features, people, practice, help (FAKE_MIC=... for voice), gfx-*
python3 video/assemble.py                # ~/Videos/suresay/SureSay.mp4
```

Raghav is a composite character, drawn from experiences shared by people living with dysarthria; the end card says so.

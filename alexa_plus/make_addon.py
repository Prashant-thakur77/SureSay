"""Write alexa_plus/addon-package/addon.json for the Alexa+ MCP add-on, pointing at a deployed hub.

    python alexa_plus/make_addon.py https://<hub-url>
    cd alexa_plus && alexa-ai deploy        # when Alexa+ developer access is available

Field limits follow the Alexa+ add-on manifest rules (name <= 30, short description <= 123, 3-4 example phrases,
six light icon sizes, a 600x900 carousel image, HTTPS privacy and terms URLs). Images are served by the hub.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

SHORT = "Three big guesses for speech others mishear. Nothing happens until you confirm one with your own voice or tap."
FULL = (
    "SureSay is for people whose speech voice assistants often mishear, such as people living with dysarthria after "
    "a stroke, or with Parkinson's, ALS or cerebral palsy. Say what you need in your own way. SureSay shows its "
    "three best guesses as big, numbered cards and reads them aloud. You choose by saying \"two\", \"the second one\" "
    "or \"haan\", or by tapping. Nothing changes until you confirm: the assistant can suggest, but only your own "
    "voice or tap on your paired screen can release an action, and every change leaves a consent receipt. Risky "
    "actions such as unlocking the door, ordering or calling someone ask a second yes. SureSay can also speak a "
    "confirmed sentence aloud for you, and it learns your way of saying things from your confirmations."
)


def main() -> None:
    hub = sys.argv[1].rstrip("/")
    icons = [{"size": f"{s}x{s}", "uri": f"{hub}/brand/icon-{s}x{s}.png"} for s in (72, 64, 88, 126, 180, 241)]
    manifest = {
        "manifestVersion": "1.0",
        "storeListing": {
            "distributionCountries": ["US", "IN"],
            "locales": {
                "en-US": {
                    "default": "DEFAULT",
                    "name": {"value": "SureSay"},
                    "shortDescription": SHORT,
                    "fullDescription": FULL,
                    "examplePhrases": ["Ask SureSay to turn on the fan", "Ask SureSay to call Mom",
                                       "Ask SureSay to say I am thirsty"],
                    "privacyAndCompliance": {"privacyPolicyUrl": f"{hub}/privacy", "termsOfUseUrl": f"{hub}/terms"},
                    "mediaAssets": {
                        "icons": {"light": icons, "dark": []},
                        "carouselImages": [{"uri": f"{hub}/brand/carousel-1.png", "size": "600x900",
                                            "altText": "Three numbered SureSay cards after the words 'van on' were "
                                                       "heard: turn on the bedroom fan, turn on the TV, turn off the fan."}],
                        "bannerImages": [],
                    },
                }
            },
        },
        "integrations": [{"type": "MCP", "config": {"endpoints": {"default": {"type": "HTTPS", "uri": f"{hub}/mcp"}}}}],
    }
    loc = manifest["storeListing"]["locales"]["en-US"]
    assert len(loc["name"]["value"]) <= 30 and len(SHORT) <= 123 and len(FULL) <= 4000
    assert 3 <= len(loc["examplePhrases"]) <= 4 and all(len(x) <= 200 for x in loc["examplePhrases"])
    out = HERE / "addon-package" / "addon.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()

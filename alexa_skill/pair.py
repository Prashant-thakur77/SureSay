"""Pair the Alexa skill as a SureSay device and print its Lambda environment.

    python alexa_skill/pair.py https://<hub-url> <pairing-code>

The pairing code comes from the hub's terminal or ``python -m suresay.cli pair --transcriber alexa``. Put the three printed
values in the skill Lambda's environment. Keep the key secret: it is what lets Alexa answer cards.
"""

from __future__ import annotations

import json
import sys
import urllib.request


def main() -> None:
    url, code = sys.argv[1].rstrip("/"), sys.argv[2]
    req = urllib.request.Request(f"{url}/device/pair", data=json.dumps({"code": code, "name": "Alexa skill"}).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        d = json.loads(resp.read())
    print(f"SURESAY_HUB_URL={url}\nSURESAY_DEVICE_ID={d['device_id']}\nSURESAY_DEVICE_KEY={d['key']}")


if __name__ == "__main__":
    main()

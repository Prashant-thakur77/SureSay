"""Carer alerts through Amazon SNS: when the user confirms a high-risk action, a carer hears about it.

Opt-in: set SURESAY_CARER_TOPIC_ARN (deploy.sh creates ``suresay-carer-alerts`` with no subscribers). Every alert
carries a ``user_id`` message attribute, so each carer subscribes to their own person only::

    aws sns subscribe --topic-arn <arn> --protocol email --notification-endpoint <address> \
        --attributes '{"FilterPolicy": "{\"user_id\": [\"demo\"]}"}'

The message says what was done and how it was confirmed, on one line (anything the user typed is flattened and
shortened, so it cannot pose as another alert); it never contains a nonce, a key or the audio. Public demo guests
never alert anyone, and each user is limited to a few alerts an hour.
"""

from __future__ import annotations

import logging
import time
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)


def _flat(text: Any, limit: int) -> str:
    """One line of printable text: control characters and line breaks become spaces, then it is shortened."""
    cleaned = "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in str(text or ""))
    one_line = " ".join(cleaned.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"


class CarerAlerts:
    def __init__(self, topic_arn: str, *, region: str = "us-east-1", client: Any | None = None,
                 store: Any | None = None, per_hour: int = 6) -> None:
        self.topic_arn = topic_arn
        self.region = region
        self._client = client
        self.store = store
        self.per_hour = per_hour
        self.sent: list[dict[str, Any]] = []

    def _sns(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("sns", region_name=self.region)
        return self._client

    def _within_limit(self, user_id: str) -> bool:
        if self.store is None:
            return True
        hour = int(time.time() // 3600)
        return self.store.add("quota", f"carer:{user_id}:{hour}", 1, expires_at=float((hour + 1) * 3600)) <= self.per_hour

    def on_receipt(self, user_id: str, receipt: dict[str, Any]) -> bool:
        if not self.topic_arn or receipt.get("what", {}).get("risk") != "high":
            return False
        if user_id.startswith("guest-") or not self._within_limit(user_id):
            return False  # a public demo home has no carer; a flood is not news
        how = {"voice": "their voice", "transcript": "their voice (Alexa)", "tap": "a tap"}.get(
            receipt.get("how", {}).get("channel", ""), "their device")
        heard = _flat(receipt.get("evidence", {}).get("transcript"), 40)
        text = (f"SureSay: {_flat(user_id, 40)} confirmed “{_flat(receipt['what']['shown_as'], 120)}” with {how}"
                + (f" (heard “{heard}”)" if heard else "") + f" at {receipt['when']['confirmed_at'][11:16]} UTC. "
                f"Receipt {_flat(receipt['receipt_id'], 40)}.")
        try:
            self._sns().publish(TopicArn=self.topic_arn, Subject="SureSay: an action was confirmed", Message=text,
                                MessageAttributes={"user_id": {"DataType": "String", "StringValue": user_id}})
        except Exception:
            logger.exception("carer alert failed")
            return False
        self.sent.append({"user_id": user_id, "message": text})
        return True

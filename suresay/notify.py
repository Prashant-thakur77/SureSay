"""Carer alerts through Amazon SNS: when the user confirms a high-risk action, a carer hears about it.

Opt-in: set SURESAY_CARER_TOPIC_ARN (deploy.sh creates ``suresay-carer-alerts`` with no subscribers; subscribe an
email with ``aws sns subscribe --topic-arn <arn> --protocol email --notification-endpoint <address>``). The message
says what was done and how it was confirmed; it never contains a nonce, a key or the audio.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CarerAlerts:
    def __init__(self, topic_arn: str, *, region: str = "us-east-1", client: Any | None = None) -> None:
        self.topic_arn = topic_arn
        self.region = region
        self._client = client
        self.sent: list[dict[str, Any]] = []

    def _sns(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("sns", region_name=self.region)
        return self._client

    def on_receipt(self, user_id: str, receipt: dict[str, Any]) -> bool:
        if not self.topic_arn or receipt.get("what", {}).get("risk") != "high":
            return False
        how = {"voice": "their voice", "transcript": "their voice (Alexa)", "tap": "a tap"}.get(
            receipt.get("how", {}).get("channel", ""), "their device")
        heard = receipt.get("evidence", {}).get("transcript")
        text = (f"SureSay: {user_id} confirmed “{receipt['what']['shown_as']}” with {how}"
                + (f" (heard “{heard}”)" if heard else "") + f" at {receipt['when']['confirmed_at'][11:16]} UTC. "
                f"Receipt {receipt['receipt_id']}.")
        try:
            self._sns().publish(TopicArn=self.topic_arn, Subject="SureSay: an action was confirmed"[:100], Message=text)
        except Exception:
            logger.exception("carer alert failed")
            return False
        self.sent.append({"user_id": user_id, "message": text})
        return True

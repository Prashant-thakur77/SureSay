"""AgentCore Runtime entrypoint for the SureSay agent.

Locally: ``python -m strands_agent.agentcore_app`` serves ``POST /invocations`` and ``GET /ping`` on :8080,
the same contract AgentCore Runtime uses. The hub calls it for each user turn.

Payload: ``{"prompt": "...", "user_id": "demo", "session_id": "..."}``. Returns ``{"response": "..."}``.
With ``"mode": "assistant"`` it runs one live assistant turn on Amazon Nova 2 Sonic (``strands_agent.live``) and
returns the reply with every MCP tool call the model made.
"""

from __future__ import annotations

import logging
import os
import re

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from strands_agent.live import assistant_turn

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("suresay.agent")

app = BedrockAgentCoreApp()


def _clean(value: object, default: str, limit: int = 64) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]", "_", str(value or ""))[:limit]
    return text or default


@app.entrypoint
def invoke(payload: dict, context: object = None) -> dict:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return {"response": "I didn't get anything to work with. Please say it again."}
    user_id = _clean(payload.get("user_id"), os.environ.get("SURESAY_DEFAULT_USER", "demo"))
    if payload.get("mode") == "assistant":
        turn = str(payload.get("turn_id") or "")
        extra = {"turn_id": turn} if re.fullmatch(r"[0-9a-f]{16,64}", turn) else {}  # lets the hub show each step
        out = assistant_turn(prompt[:300], user_id, mcp_url=os.environ["SURESAY_MCP_URL"],
                             token=os.environ["SURESAY_AGENT_TOKEN"], **extra)
        return {**out, "runs_on": "AgentCore Runtime"}
    from strands_agent.core import run_turn  # Strands on Nova 2 Lite, for the hub's agent mode
    session_id = _clean(payload.get("session_id") or getattr(context, "session_id", None), "default-session-0000000000000000")
    if len(session_id) < 33:
        session_id = (session_id + "-" + "0" * 40)[:40]
    logger.info("turn for %s in %s", user_id, session_id)
    return {"response": run_turn(prompt, user_id=user_id, session_id=session_id)}


if __name__ == "__main__":
    app.run()

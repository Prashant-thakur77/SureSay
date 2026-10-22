"""The SureSay Strands agent: Nova 2 Lite on Bedrock, talking to the SureSay MCP server.

The agent understands, answers and proposes. It cannot act: every write tool it
can see only creates a pending card on the user's own device, and ``confirm``
needs evidence that only that device can create.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from .prompts import SYSTEM_PROMPT  # noqa: F401  (re-exported for the agent and the evaluation)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "us.amazon.nova-2-lite-v1:0"


AGENT_TOOLS = ("understand", "home_status", "cart_view", "contacts_list", "product_search", "product_details",
               "phrasebook_list", "receipts_list", "pending_status", "home_set", "ac_set", "door_lock",
               "call_contact", "message_contact", "cart_add", "cart_order", "say_for_me", "phrasebook_add")


def mcp_client(user_id: str, *, url: str | None = None, token: str | None = None) -> MCPClient:
    url = url or os.environ.get("SURESAY_MCP_URL", "http://127.0.0.1:9000/mcp")
    token = token or os.environ.get("SURESAY_AGENT_TOKEN") or _local_token()
    return MCPClient(url=url, headers={"Authorization": f"Bearer {token}", "X-SureSay-User": user_id})


def _local_token() -> str:
    from suresay.config import settings

    return settings().agent_token


def model(model_id: str | None = None, region: str | None = None, temperature: float = 0.2) -> BedrockModel:
    return BedrockModel(model_id=model_id or os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL),
                        region_name=region or os.environ.get("AWS_REGION", "us-east-1"),
                        temperature=temperature, max_tokens=600)


def session_manager(user_id: str, session_id: str) -> Any | None:
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "").strip()
    if not memory_id:
        return None
    from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
    from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

    cfg = AgentCoreMemoryConfig(
        memory_id=memory_id, session_id=session_id, actor_id=user_id,
        retrieval_config={"/facts/{actorId}": RetrievalConfig(top_k=5, relevance_score=0.3)},
        filter_restored_tool_context=True,
    )
    return AgentCoreMemorySessionManager(cfg, region_name=os.environ.get("AWS_REGION", "us-east-1"))


@contextmanager
def suresay_agent(user_id: str, session_id: str, *, tools: tuple[str, ...] | None = AGENT_TOOLS,
                  system_prompt: str = SYSTEM_PROMPT, url: str | None = None, token: str | None = None,
                  model_id: str | None = None, use_memory: bool = True) -> Iterator[Agent]:
    """An agent wired to SureSay for one user session. ``tools=None`` gives it every tool, ``confirm`` included."""
    client = mcp_client(user_id, url=url, token=token)
    with client:
        available = client.list_tools_sync()
        chosen = [t for t in available if tools is None or t.tool_name in tools]
        kwargs: dict[str, Any] = {}
        sm = session_manager(user_id, session_id) if use_memory else None
        if sm is not None:
            kwargs["session_manager"] = sm
        yield Agent(model=model(model_id), tools=chosen, system_prompt=system_prompt,
                    callback_handler=None, **kwargs)


def run_turn(prompt: str, *, user_id: str, session_id: str) -> str:
    with suresay_agent(user_id, session_id) as agent:
        result = agent(prompt)
    return str(result).strip()

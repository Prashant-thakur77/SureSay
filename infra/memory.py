"""Create (or find) and delete the SureSay AgentCore Memory.

One memory holds two things:
* phrasebook events (blob events, session "phrasebook", one actor per user), written by the hub;
* the agent's conversation events, with a SEMANTIC strategy that extracts lasting facts about the
  user into /facts/{actorId} (for example "calls the bedroom fan 'my fan'").

Usage: python infra/memory.py ensure|delete [--name suresay_memory] [--region us-east-1]
Prints the memory id on ensure.
"""

from __future__ import annotations

import argparse
import sys

from bedrock_agentcore.memory import MemoryClient


def find(client: MemoryClient, name: str) -> dict | None:
    for m in client.list_memories():
        mid = m.get("id") or m.get("memoryId") or ""
        if mid.startswith(name + "-") or m.get("name") == name:
            return m
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["ensure", "delete"])
    ap.add_argument("--name", default="suresay_memory")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args()
    client = MemoryClient(region_name=args.region)
    found = find(client, args.name)
    if args.action == "ensure":
        if found is None:
            found = client.create_memory_and_wait(
                name=args.name,
                description="SureSay: per-user phrasebooks and facts the user has told the assistant",
                strategies=[{"semanticMemoryStrategy": {"name": "facts", "namespaces": ["/facts/{actorId}"]}}],
                event_expiry_days=30,
            )
        print(found.get("id") or found.get("memoryId"))
    else:
        if found is None:
            print("no memory to delete", file=sys.stderr)
            return
        mid = found.get("id") or found.get("memoryId")
        client.delete_memory_and_wait(mid)
        print(f"deleted {mid}")


if __name__ == "__main__":
    main()

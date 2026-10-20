#!/usr/bin/env bash
# Run SureSay locally: the hub (MCP + device channel + web client) on :9000, and the Strands agent on :8080
# when Bedrock is reachable. Ctrl-C stops everything.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { echo "run 'make setup' first"; exit 1; }
if [ ! -d web/dist ]; then (cd web && npm ci --silent && npm run build --silent); fi
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if "$PY" -c "from suresay.rank import bedrock_available as b; import sys; sys.exit(0 if b('us.amazon.nova-2-lite-v1:0') else 1)" 2>/dev/null; then
  echo "Bedrock reachable: starting the Strands agent on :8080"
  SURESAY_MCP_URL=http://127.0.0.1:9000/mcp "$PY" -m strands_agent.agentcore_app > var/agent.log 2>&1 &
  pids+=($!)
  export SURESAY_AGENT_MODE=agent
else
  echo "Bedrock not reachable: turns go straight to understand (no agent). See docs/FRICTION_LOG.md."
  export SURESAY_AGENT_MODE=direct
fi
mkdir -p var
"$PY" -m suresay.hub &
pids+=($!)
sleep 3
echo
echo "  Open http://127.0.0.1:9000 and enter the pairing code printed above."
echo "  A new code any time: .venv/bin/python -m suresay.cli pair"
wait

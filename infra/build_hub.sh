#!/usr/bin/env bash
# Build the hub's Lambda bundle in infra/.build/hub.zip (Linux x86_64, Python 3.12).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/infra/.build/hub"
rm -rf "$OUT" "$ROOT/infra/.build/hub.zip"
mkdir -p "$OUT"
uv pip install --quiet --target "$OUT" --python-platform x86_64-manylinux_2_28 --python-version 3.12 \
  --only-binary :all: \
  "mcp>=2.1,<2.2" "bedrock-agentcore>=1.24" "boto3>=1.40" "pydantic>=2.10" "starlette>=0.40" "uvicorn>=0.30" \
  "httpx>=0.27" "rapidfuzz>=3.9" "jellyfish>=1.1" "numpy>=2.0" "soundfile>=0.12" "anyio>=4" \
  "aws-sdk-bedrock-runtime>=0.12" "smithy-http[awscrt]>=0.6"
# amazon-transcribe pins awscrt 0.26 while Nova Sonic's duplex transport needs 0.32; streaming Transcribe works on
# 0.32 (checked live), so install it without its pin.
uv pip install --quiet --target "$OUT" --python-platform x86_64-manylinux_2_28 --python-version 3.12 \
  --only-binary :all: --no-deps "amazon-transcribe>=0.6.2"
cp -r "$ROOT/suresay" "$ROOT/mcp_server" "$OUT/"
mkdir -p "$OUT/strands_agent" && cp "$ROOT/strands_agent/__init__.py" "$ROOT/strands_agent/prompts.py" "$ROOT/strands_agent/sonic.py" "$OUT/strands_agent/"  # the live assistant, without the Strands framework
cp -r "$ROOT/packages/confirm-gate-mcp/src/confirm_gate" "$OUT/"
mkdir -p "$OUT/alexa_plus" && cp -r "$ROOT/alexa_plus/assets" "$OUT/alexa_plus/assets"
if [ -d "$ROOT/web/dist" ]; then mkdir -p "$OUT/web" && cp -r "$ROOT/web/dist" "$OUT/web/dist"; fi
cat > "$OUT/run.sh" <<'RUN'
#!/bin/bash
export PYTHONPATH="/var/task:${PYTHONPATH:-}"
exec python -m uvicorn suresay.lambda_app:app --host 0.0.0.0 --port "${PORT:-8080}" --log-level warning --no-proxy-headers
RUN
chmod +x "$OUT/run.sh"
find "$OUT" -name "__pycache__" -type d -prune -exec rm -rf {} +
(cd "$OUT" && zip -qr9 ../hub.zip .)
echo "built $(du -h "$ROOT/infra/.build/hub.zip" | cut -f1) infra/.build/hub.zip"

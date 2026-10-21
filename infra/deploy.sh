#!/usr/bin/env bash
# One-command deploy of SureSay to AWS (us-east-1). Idempotent: run it again to update.
#
#   DynamoDB  suresay-gate            gate ledger, devices, home state, events (on-demand, TTL)
#   S3        suresay-<acct>-<region> utterance + evidence audio (private, SSE, 30-day expiry) + deploy bundle
#   AgentCore Memory  suresay_memory  phrasebooks (blob events) + SEMANTIC facts strategy
#   Lambda    suresay-hub + URL       the hub: /mcp (MCP Streamable HTTP), /device/*, web client
#   AgentCore Runtime suresay_agent   the Strands agent (Nova 2 Lite), calling the hub's /mcp
#
# Options (env): REGION=us-east-1  SKIP_AGENT=1 (hub only)  SKIP_WEB=1 (reuse web/dist)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REGION="${REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
TABLE="suresay-gate"
BUCKET="suresay-${ACCOUNT}-${REGION}"
FUNCTION="suresay-hub"
ROLE="suresay-hub-role"
AGENT="suresay_agent"
STATE="$ROOT/infra/.state"
PY="$ROOT/.venv/bin/python"
mkdir -p "$STATE"
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

say "DynamoDB table $TABLE"
if ! aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  aws dynamodb create-table --table-name "$TABLE" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH \
    --tags Key=project,Value=suresay >/dev/null
  aws dynamodb wait table-exists --table-name "$TABLE"
  aws dynamodb update-time-to-live --table-name "$TABLE" --time-to-live-specification Enabled=true,AttributeName=ttl >/dev/null
fi
if ! aws dynamodb describe-table --table-name "$TABLE" --query 'Table.GlobalSecondaryIndexes[].IndexName' --output text | grep -q kind-index; then
  # Lookups by record kind (open card sets, receipts) query this index instead of scanning the table.
  aws dynamodb update-table --table-name "$TABLE" --attribute-definitions AttributeName=kind,AttributeType=S \
    --global-secondary-index-updates '[{"Create":{"IndexName":"kind-index","KeySchema":[{"AttributeName":"kind","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}}]' >/dev/null
  echo "creating kind-index (backfills in the background; the hub scans until it is ready)"
elif ! aws dynamodb describe-table --table-name "$TABLE" --query 'Table.GlobalSecondaryIndexes[].IndexName' --output text | grep -q user-kind-index; then
  # One user's rows of one kind (open card sets, events) without reading anyone else's: matters with the public demo.
  aws dynamodb update-table --table-name "$TABLE" --attribute-definitions AttributeName=f_user_id,AttributeType=S AttributeName=kind,AttributeType=S \
    --global-secondary-index-updates '[{"Create":{"IndexName":"user-kind-index","KeySchema":[{"AttributeName":"f_user_id","KeyType":"HASH"},{"AttributeName":"kind","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}}]' >/dev/null
  echo "creating user-kind-index (backfills in the background)"
fi

say "S3 bucket $BUCKET"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
    '{"Rules":[{"ID":"audio-30d","Status":"Enabled","Filter":{"Prefix":""},"Expiration":{"Days":30}}]}'
  aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging 'TagSet=[{Key=project,Value=suresay}]'
fi

say "AgentCore Memory"
if MEMORY_ID="$("$PY" infra/memory.py ensure --region "$REGION" 2>"$STATE/memory.err" | tail -1)"; then
  echo "memory: $MEMORY_ID"
else
  MEMORY_ID=""
  echo "AgentCore Memory unavailable on this account ($(tail -1 "$STATE/memory.err"))."
  echo "Phrasebooks fall back to the DynamoDB table; the agent runs without long-term memory."
fi

say "SNS topic suresay-carer-alerts (subscribe a carer with a user_id filter policy: see suresay/notify.py)"
CARER_TOPIC="$(aws sns create-topic --name suresay-carer-alerts --tags Key=project,Value=suresay --query TopicArn --output text)"
echo "$CARER_TOPIC"

TOKEN_FILE="$STATE/agent_token"
[ -f "$TOKEN_FILE" ] || "$PY" -c "import secrets; print(secrets.token_urlsafe(32))" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
AGENT_TOKEN="$(cat "$TOKEN_FILE")"

say "IAM role $ROLE"
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document file://infra/iam/hub-trust.json \
    --tags Key=project,Value=suresay >/dev/null
  sleep 10
fi
REGION="$REGION" ACCOUNT="$ACCOUNT" TABLE="$TABLE" BUCKET="$BUCKET" FUNCTION="$FUNCTION" CARER_TOPIC="$CARER_TOPIC" \
  envsubst < infra/iam/hub-policy.json.tmpl > "$STATE/hub-policy.json"
aws iam put-role-policy --role-name "$ROLE" --policy-name suresay-hub --policy-document "file://$STATE/hub-policy.json"
ROLE_ARN="$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)"

if [ -z "${SKIP_WEB:-}" ] && [ -f web/package.json ]; then
  say "Web client"
  (cd web && npm ci --silent && npm run build --silent)
fi

say "Hub bundle"
bash infra/build_hub.sh
aws s3 cp infra/.build/hub.zip "s3://$BUCKET/deploy/hub.zip" --quiet

ENV_JSON() {
  "$PY" - "$@" <<'PYEOF'
import json, sys
pairs = dict(a.split("=", 1) for a in sys.argv[1:])
print(json.dumps({"Variables": pairs}))
PYEOF
}
LWA="arn:aws:lambda:${REGION}:753240598075:layer:LambdaAdapterLayerX86:30"
RUNTIME_ARN="$(cat "$STATE/agent_runtime_arn" 2>/dev/null || true)"
MODE="direct"
if [ -n "$RUNTIME_ARN" ] && "$PY" -c "from suresay.rank import bedrock_available as b; import os, sys; sys.exit(0 if b(os.environ.get('NOVA_MODEL_ID', 'us.amazon.nova-2-lite-v1:0')) else 1)" 2>/dev/null; then
  MODE="agent"
fi
VARS=(AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap PORT=8080 AWS_LWA_READINESS_CHECK_PATH=/healthz
      SURESAY_BACKEND=aws SURESAY_GATE_TABLE="$TABLE" SURESAY_BUCKET="$BUCKET" SURESAY_DATA_DIR=/tmp/suresay
      AGENTCORE_MEMORY_ID="$MEMORY_ID" SURESAY_AGENT_TOKEN="$AGENT_TOKEN" SURESAY_ASR="${SURESAY_ASR:-auto}" SURESAY_EVIDENCE_ASR="${SURESAY_EVIDENCE_ASR:-}" SURESAY_RANKER=auto
      SURESAY_AGENT_MODE="$MODE" AGENTCORE_RUNTIME_ARN="$RUNTIME_ARN" SURESAY_ALLOWED_ORIGINS="*"
      SURESAY_CARER_TOPIC_ARN="$CARER_TOPIC" SURESAY_PUBLIC_DEMO="${SURESAY_PUBLIC_DEMO:-1}" SURESAY_EVIDENCE_LANGUAGE="${SURESAY_EVIDENCE_LANGUAGE:-en-US}" SURESAY_OAUTH_CLIENTS="${SURESAY_OAUTH_CLIENTS:-}"
      SURESAY_PUBLIC_URL="$(aws lambda get-function-url-config --function-name "$FUNCTION" --query FunctionUrl --output text 2>/dev/null | sed 's:/*$::' || true)")

say "Lambda $FUNCTION"
if ! aws lambda get-function --function-name "$FUNCTION" >/dev/null 2>&1; then
  aws lambda create-function --function-name "$FUNCTION" --runtime python3.12 --architectures x86_64 \
    --role "$ROLE_ARN" --handler run.sh --timeout 60 --memory-size 1536 \
    --code "S3Bucket=$BUCKET,S3Key=deploy/hub.zip" --layers "$LWA" \
    --environment "$(ENV_JSON "${VARS[@]}")" --tags project=suresay >/dev/null
  aws lambda wait function-active-v2 --function-name "$FUNCTION"
else
  aws lambda update-function-code --function-name "$FUNCTION" --s3-bucket "$BUCKET" --s3-key deploy/hub.zip >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FUNCTION"
  aws lambda update-function-configuration --function-name "$FUNCTION" --layers "$LWA" \
    --environment "$(ENV_JSON "${VARS[@]}")" >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FUNCTION"
fi
if ! aws lambda get-function-url-config --function-name "$FUNCTION" >/dev/null 2>&1; then
  aws lambda create-function-url-config --function-name "$FUNCTION" --auth-type NONE >/dev/null
  # The URL is public by design: /mcp needs the agent token, /device/* needs a paired device's signature.
  aws lambda add-permission --function-name "$FUNCTION" --statement-id url-public --action lambda:InvokeFunctionUrl \
    --principal "*" --function-url-auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$FUNCTION" --statement-id url-invoke --action lambda:InvokeFunction \
    --principal "*" --invoked-via-function-url >/dev/null 2>&1 || true
fi
HUB_URL="$(aws lambda get-function-url-config --function-name "$FUNCTION" --query FunctionUrl --output text)"
HUB_URL="${HUB_URL%/}"
echo "hub: $HUB_URL"

if [ -z "${SKIP_AGENT:-}" ]; then
  say "AgentCore Runtime $AGENT (direct code deploy)"
  BUILD="$ROOT/infra/.build/agent"
  rm -rf "$BUILD" && mkdir -p "$BUILD/strands_agent"
  cp strands_agent/__init__.py strands_agent/core.py strands_agent/agentcore_app.py "$BUILD/strands_agent/"
  cp infra/agent-requirements.txt "$BUILD/requirements.txt"
  printf 'from strands_agent.agentcore_app import app\n\nif __name__ == "__main__":\n    app.run()\n' > "$BUILD/main.py"
  (
    cd "$BUILD"
    uvx --from bedrock-agentcore-starter-toolkit agentcore configure -e main.py -n "$AGENT" -r "$REGION" \
      -rf requirements.txt -dt direct_code_deploy -rt PYTHON_3_12 -dm -ni >/dev/null
    uvx --from bedrock-agentcore-starter-toolkit agentcore deploy -a "$AGENT" --auto-update-on-conflict \
      --env "SURESAY_MCP_URL=$HUB_URL/mcp" --env "SURESAY_AGENT_TOKEN=$AGENT_TOKEN" \
      --env "AGENTCORE_MEMORY_ID=$MEMORY_ID" --env "BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0" \
      --env "AWS_REGION=$REGION"
  ) || echo "AgentCore Runtime deploy failed (see above; this account's 'Total Agents per Account' quota may be 0). The hub keeps answering turns directly."
  RUNTIME_ARN="$(aws bedrock-agentcore-control list-agent-runtimes --query "agentRuntimes[?agentRuntimeName=='$AGENT'].agentRuntimeArn | [0]" --output text 2>/dev/null || true)"
  if [ -n "$RUNTIME_ARN" ] && [ "$RUNTIME_ARN" != "None" ]; then
    echo "$RUNTIME_ARN" > "$STATE/agent_runtime_arn"
    if "$PY" -c "from suresay.rank import bedrock_available as b; import os, sys; sys.exit(0 if b(os.environ.get('NOVA_MODEL_ID', 'us.amazon.nova-2-lite-v1:0')) else 1)" 2>/dev/null; then
      AGENT_MODE_SET=agent
    else
      AGENT_MODE_SET=direct
      echo "Nova did not answer (quota?): the hub answers turns directly until a redeploy finds Nova working."
    fi
    VARS=("${VARS[@]/SURESAY_AGENT_MODE=*/SURESAY_AGENT_MODE=$AGENT_MODE_SET}")
    VARS=("${VARS[@]/AGENTCORE_RUNTIME_ARN=*/AGENTCORE_RUNTIME_ARN=$RUNTIME_ARN}")
    aws lambda update-function-configuration --function-name "$FUNCTION" --environment "$(ENV_JSON "${VARS[@]}")" >/dev/null
    aws lambda wait function-updated-v2 --function-name "$FUNCTION"
    echo "agent: $RUNTIME_ARN"
  else
    RUNTIME_ARN=""
  fi
fi

if [ -z "${SKIP_ALEXA:-}" ]; then
  say "Alexa skill Lambda suresay-alexa-skill (paired as the user's Alexa device)"
  AROLE="suresay-alexa-role"
  if ! aws iam get-role --role-name "$AROLE" >/dev/null 2>&1; then
    aws iam create-role --role-name "$AROLE" --assume-role-policy-document file://infra/iam/alexa-trust.json --tags Key=project,Value=suresay >/dev/null
    aws iam attach-role-policy --role-name "$AROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    sleep 10
  fi
  AROLE_ARN="$(aws iam get-role --role-name "$AROLE" --query Role.Arn --output text)"
  if [ ! -f "$STATE/alexa_device.env" ]; then
    ACODE="$(SURESAY_BACKEND=aws SURESAY_GATE_TABLE="$TABLE" AWS_REGION="$REGION" "$PY" -m suresay.cli pair --transcriber alexa)"
    "$PY" alexa_skill/pair.py "$HUB_URL" "$ACODE" > "$STATE/alexa_device.env"
    chmod 600 "$STATE/alexa_device.env"
  fi
  # Alexa recognises speech itself: only this device may send transcript evidence (idempotent; older pairings too).
  SURESAY_BACKEND=aws SURESAY_GATE_TABLE="$TABLE" AWS_REGION="$REGION" "$PY" -m suresay.cli voice-device \
    "$(grep SURESAY_DEVICE_ID "$STATE/alexa_device.env" | cut -d= -f2)" alexa
  AENV="$("$PY" - "$STATE/alexa_device.env" <<'PYEOF'
import json, os, sys
pairs = dict(l.strip().split("=", 1) for l in open(sys.argv[1]) if "=" in l)
if os.environ.get("ALEXA_SKILL_ID"):
    pairs["SURESAY_ALEXA_SKILL_ID"] = os.environ["ALEXA_SKILL_ID"]
print(json.dumps({"Variables": pairs}))
PYEOF
)"
  (cd alexa_skill && rm -f ../infra/.build/alexa.zip && mkdir -p ../infra/.build && zip -q ../infra/.build/alexa.zip lambda_function.py)
  if ! aws lambda get-function --function-name suresay-alexa-skill >/dev/null 2>&1; then
    aws lambda create-function --function-name suresay-alexa-skill --runtime python3.12 --role "$AROLE_ARN" \
      --handler lambda_function.lambda_handler --timeout 15 --zip-file fileb://infra/.build/alexa.zip \
      --environment "$AENV" --tags project=suresay >/dev/null
    aws lambda wait function-active-v2 --function-name suresay-alexa-skill
  else
    aws lambda update-function-code --function-name suresay-alexa-skill --zip-file fileb://infra/.build/alexa.zip >/dev/null
    aws lambda wait function-updated-v2 --function-name suresay-alexa-skill
    aws lambda update-function-configuration --function-name suresay-alexa-skill --environment "$AENV" >/dev/null
    aws lambda wait function-updated-v2 --function-name suresay-alexa-skill
  fi
  if [ -n "${ALEXA_SKILL_ID:-}" ]; then  # the Alexa Skills Kit trigger, for our skill only
    aws lambda add-permission --function-name suresay-alexa-skill --statement-id alexa-skill \
      --action lambda:InvokeFunction --principal alexa-appkit.amazon.com --event-source-token "$ALEXA_SKILL_ID" \
      >/dev/null 2>&1 || true
  fi
  "$PY" - infra/alexa_events/command.json "$STATE/alexa_event.json" <<'PYEOF'
import json, os, sys
ev = json.load(open(sys.argv[1]))
ev.setdefault("context", {}).setdefault("System", {})["application"] = {"applicationId": os.environ.get("ALEXA_SKILL_ID", "")}
json.dump(ev, open(sys.argv[2], "w"))
PYEOF
  aws lambda invoke --function-name suresay-alexa-skill --cli-binary-format raw-in-base64-out \
    --payload "file://$STATE/alexa_event.json" "$STATE/alexa_test.json" >/dev/null
  echo "skill test: $("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['response']['outputSpeech']['ssml'][:140])" "$STATE/alexa_test.json")"
  echo "Alexa skill endpoint ARN: $(aws lambda get-function --function-name suresay-alexa-skill --query Configuration.FunctionArn --output text)"
fi

say "CloudWatch dashboard SureSay"
REGION="$REGION" FUNCTION="$FUNCTION" envsubst '${REGION} ${FUNCTION}' < infra/dashboard.json.tmpl > "$STATE/dashboard.json"
aws cloudwatch put-dashboard --dashboard-name SureSay --dashboard-body "file://$STATE/dashboard.json" >/dev/null && \
  echo "https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=SureSay"

say "Smoke test"
curl -fsS "$HUB_URL/healthz" && echo
CODE="$(SURESAY_BACKEND=aws SURESAY_GATE_TABLE="$TABLE" AWS_REGION="$REGION" "$PY" -m suresay.cli pair)"
cat > "$STATE/outputs.env" <<OUT
HUB_URL=$HUB_URL
MCP_URL=$HUB_URL/mcp
TABLE=$TABLE
BUCKET=$BUCKET
MEMORY_ID=$MEMORY_ID
AGENT_RUNTIME_ARN=${RUNTIME_ARN:-}
OUT
printf '\nSureSay is live: %s\nPairing code (10 minutes): %s\nMCP endpoint: %s/mcp (agent token in infra/.state/agent_token)\n' \
  "$HUB_URL" "$CODE" "$HUB_URL"

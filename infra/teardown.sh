#!/usr/bin/env bash
# Remove everything infra/deploy.sh created. Touches only resources named suresay-* / suresay_*.
#   ./infra/teardown.sh          asks before deleting
#   ./infra/teardown.sh --yes    no prompt
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REGION="${REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
TABLE="suresay-gate"; BUCKET="suresay-${ACCOUNT}-${REGION}"; FUNCTION="suresay-hub"; ROLE="suresay-hub-role"
AGENT="suresay_agent"; STATE="$ROOT/infra/.state"; PY="$ROOT/.venv/bin/python"
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"
if [ "${1:-}" != "--yes" ]; then
  echo "This deletes, in $ACCOUNT/$REGION: Lambda $FUNCTION (+URL, logs), IAM role $ROLE, DynamoDB $TABLE,"
  echo "S3 bucket $BUCKET (all objects), AgentCore runtime $AGENT, AgentCore memory suresay_memory,"
  echo "and Transcribe vocabularies named suresay-*."
  read -r -p "Type 'delete' to continue: " ok; [ "$ok" = "delete" ] || { echo "cancelled"; exit 1; }
fi
step() { printf '\n== %s\n' "$*"; }

step "AgentCore Runtime"
if [ -f infra/.build/agent/.bedrock_agentcore.yaml ]; then
  (cd infra/.build/agent && uvx --from bedrock-agentcore-starter-toolkit agentcore destroy -a "$AGENT" --force) || true
fi
RID="$(aws bedrock-agentcore-control list-agent-runtimes --query "agentRuntimes[?agentRuntimeName=='$AGENT'].agentRuntimeId | [0]" --output text 2>/dev/null || true)"
if [ -n "$RID" ] && [ "$RID" != "None" ]; then aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id "$RID" >/dev/null || true; fi

step "Lambda"
aws events remove-targets --rule suresay-keep-warm --ids hub >/dev/null 2>&1 || true
aws events delete-rule --name suresay-keep-warm 2>/dev/null || true
aws lambda delete-function-url-config --function-name "$FUNCTION" 2>/dev/null || true
aws lambda delete-function --function-name "$FUNCTION" 2>/dev/null || true
aws logs delete-log-group --log-group-name "/aws/lambda/$FUNCTION" 2>/dev/null || true

step "Alexa skill Lambda"
aws lambda delete-function --function-name suresay-alexa-skill 2>/dev/null || true
aws logs delete-log-group --log-group-name /aws/lambda/suresay-alexa-skill 2>/dev/null || true
aws iam detach-role-policy --role-name suresay-alexa-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true
aws iam delete-role --role-name suresay-alexa-role 2>/dev/null || true
rm -f "$STATE/alexa_device.env"

step "IAM"
aws iam delete-role-policy --role-name "$ROLE" --policy-name suresay-hub 2>/dev/null || true
aws iam delete-role --role-name "$ROLE" 2>/dev/null || true

step "DynamoDB"
aws dynamodb delete-table --table-name "$TABLE" >/dev/null 2>&1 || true

step "S3"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3 rm "s3://$BUCKET" --recursive --quiet
  aws s3api delete-bucket --bucket "$BUCKET"
fi

step "AgentCore Memory"
"$PY" infra/memory.py delete --region "$REGION" || true

step "SNS topic"
aws sns delete-topic --topic-arn "arn:aws:sns:${REGION}:${ACCOUNT}:suresay-carer-alerts" 2>/dev/null || true

step "CloudWatch dashboard"
aws cloudwatch delete-dashboards --dashboard-names SureSay 2>/dev/null || true

step "Transcribe vocabularies"
for v in $(aws transcribe list-vocabularies --name-contains suresay- --query 'Vocabularies[].VocabularyName' --output text 2>/dev/null || true); do
  aws transcribe delete-vocabulary --vocabulary-name "$v" || true
done

rm -f "$STATE/agent_runtime_arn" "$STATE/outputs.env"
echo "SureSay resources removed."

#!/usr/bin/env bash
# Create PROD-GEPPScheduleNotiReport: the production scheduled-report cron, as a copy of
# DEV-GEPPScheduleNotiReport (which, despite its name, reads the PROD DB and emails customers).
#
# Run with an IAM identity that may create roles and EventBridge rules (platform-dev may not):
#   AWS_PROFILE=<admin> bash scripts/infra/create_prod_schedule_noti_report.sh
#
# What it does (safe to re-run; existing pieces are kept):
#   1. role  PROD-GEPPScheduleNotiReport-role  — logs for its own log group + invoke
#            PROD-GEPPGenerateV3Report / PROD-GEPPEmailNotification only (no DEV-* targets)
#   2. function PROD-GEPPScheduleNotiReport — DEV's code package, runtime, handler, memory,
#            timeout, layers and env (env is copied through a temp file, never printed)
#   3. async invoke: 0 retries (a retried run re-sent every report — 2026-10-05: 3× per user)
#   4. EventBridge rule PROD-GEPPScheduleNotiReport-hourly, cron(0 * * * ? *), created DISABLED
#
# It does NOT enable the rule: while DEV-GEPPScheduleNotiReport still runs on the PROD DB,
# enabling it would email every customer twice. Cut-over steps are printed at the end.
set -euo pipefail

REGION="${AWS_REGION:-ap-southeast-1}"
SRC="DEV-GEPPScheduleNotiReport"
DST="PROD-GEPPScheduleNotiReport"
ROLE="PROD-GEPPScheduleNotiReport-role"
RULE="PROD-GEPPScheduleNotiReport-hourly"
SCHEDULE="cron(0 * * * ? *)"   # top of every hour UTC; the job itself matches Thai email_time

export AWS_DEFAULT_REGION="$REGION"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "account=${ACCOUNT} region=${REGION} identity=$(aws sts get-caller-identity --query Arn --output text)"

# ── 1. IAM role ────────────────────────────────────────────────────────────────────
if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  echo "role ${ROLE}: exists"
else
  cat > "$TMP/trust.json" <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
  aws iam create-role --role-name "$ROLE" --path /service-role/ \
    --assume-role-policy-document "file://$TMP/trust.json" \
    --description "PROD scheduled report cron (PROD render + email only)" >/dev/null
  echo "role ${ROLE}: created"
fi
cat > "$TMP/logs.json" <<EOF
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":"logs:CreateLogGroup","Resource":"arn:aws:logs:${REGION}:${ACCOUNT}:*"},
 {"Effect":"Allow","Action":["logs:CreateLogStream","logs:PutLogEvents"],
  "Resource":["arn:aws:logs:${REGION}:${ACCOUNT}:log-group:/aws/lambda/${DST}:*"]}]}
EOF
cat > "$TMP/invoke.json" <<EOF
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["lambda:InvokeFunction"],"Resource":[
  "arn:aws:lambda:${REGION}:${ACCOUNT}:function:PROD-GEPPGenerateV3Report",
  "arn:aws:lambda:${REGION}:${ACCOUNT}:function:PROD-GEPPEmailNotification"]}]}
EOF
aws iam put-role-policy --role-name "$ROLE" --policy-name BasicExecutionLogs --policy-document "file://$TMP/logs.json"
aws iam put-role-policy --role-name "$ROLE" --policy-name EmailAndReportPerm --policy-document "file://$TMP/invoke.json"
ROLE_ARN="$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)"
echo "role policies: BasicExecutionLogs, EmailAndReportPerm"

# ── 2. Function (copy of DEV) ───────────────────────────────────────────────────────
if aws lambda get-function --function-name "$DST" >/dev/null 2>&1; then
  echo "function ${DST}: exists (code/env left as they are — deploy with update_function.sh prod GEPPScheduleNotiReport)"
else
  aws lambda get-function-configuration --function-name "$SRC" --output json > "$TMP/src.json"
  aws lambda get-function-configuration --function-name "$SRC" \
    --query '{Variables: Environment.Variables}' --output json > "$TMP/env.json"   # secrets: temp only
  curl -sf -o "$TMP/code.zip" "$(aws lambda get-function --function-name "$SRC" --query Code.Location --output text)"
  read -r RUNTIME HANDLER MEM TIMEOUT EPH ARCH < <(python3 -c "
import json; c=json.load(open('$TMP/src.json'))
print(c['Runtime'], c['Handler'], c['MemorySize'], max(c['Timeout'], 900), c.get('EphemeralStorage',{}).get('Size',512), (c.get('Architectures') or ['x86_64'])[0])")
  LAYERS="$(python3 -c "import json; print(' '.join(l['Arn'] for l in json.load(open('$TMP/src.json')).get('Layers') or []))")"
  echo "creating ${DST}: ${RUNTIME} ${HANDLER} mem=${MEM} timeout=${TIMEOUT}s layers=[${LAYERS}]"
  for attempt in 1 2 3 4 5 6; do   # a new role takes a few seconds before Lambda can assume it
    if aws lambda create-function --function-name "$DST" \
        --runtime "$RUNTIME" --handler "$HANDLER" --role "$ROLE_ARN" \
        --zip-file "fileb://$TMP/code.zip" --memory-size "$MEM" --timeout "$TIMEOUT" \
        --architectures "$ARCH" --ephemeral-storage "Size=$EPH" \
        ${LAYERS:+--layers $LAYERS} \
        --environment "file://$TMP/env.json" \
        --logging-config "LogFormat=Text,LogGroup=/aws/lambda/${DST}" \
        --description "Scheduled report emails (RPT_TXN_*) — production. Copied from ${SRC}." \
        >/dev/null 2>"$TMP/err"; then
      echo "function ${DST}: created"; break
    fi
    if grep -q "cannot be assumed" "$TMP/err" && [ "$attempt" -lt 6 ]; then sleep 10; continue; fi
    cat "$TMP/err" >&2; exit 1
  done
  aws lambda wait function-active-v2 --function-name "$DST"
fi

# ── 3. No async retries ────────────────────────────────────────────────────────────
aws lambda put-function-event-invoke-config --function-name "$DST" \
  --maximum-retry-attempts 0 --maximum-event-age-in-seconds 3600 >/dev/null
echo "async invoke: retries=0"

# ── 4. Hourly rule (DISABLED) ───────────────────────────────────────────────────────
RULE_ARN="$(aws events put-rule --name "$RULE" --schedule-expression "$SCHEDULE" --state DISABLED \
  --description "Hourly trigger for ${DST} (enable only after ${SRC} stops sending on the PROD DB)" \
  --query RuleArn --output text)"
aws lambda add-permission --function-name "$DST" --statement-id "events-${RULE}" \
  --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$RULE_ARN" >/dev/null 2>&1 \
  || echo "permission events-${RULE}: exists"
aws events put-targets --rule "$RULE" \
  --targets "Id=${DST},Arn=arn:aws:lambda:${REGION}:${ACCOUNT}:function:${DST}" >/dev/null
echo "rule ${RULE}: ${SCHEDULE}, DISABLED, target ${DST}"

cat <<EOF

Done. ${DST} exists but nothing triggers it yet.
Cut-over (do 1 and 2 together, between two hourly runs, e.g. at HH:20):
  1. Stop ${SRC} from sending on the PROD DB — either
       a) remove it from the old rule:
            aws events list-targets-by-rule --rule everyhours
            aws events remove-targets --rule everyhours --ids <its target id>
       b) or point its DB_* env at the DEV database (it then becomes a real DEV cron).
  2. Enable the new rule:
            aws events enable-rule --name ${RULE}
  3. Check the next run: CloudWatch log group /aws/lambda/${DST} ("[ScheduleReport] ... Done").
EOF

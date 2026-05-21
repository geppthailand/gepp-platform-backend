#!/usr/bin/env bash
set -euo pipefail

# Unified Lambda deploy helper.
#
# Usage:
#   bash update_function.sh DEV GEPPPlatform "--profile gepp"
#   bash update_function.sh PROD GEPPGenerateV3Report "--profile gepp"
#   bash update_function.sh DEV iot-health-cron "--profile gepp"
#   bash update_function.sh DEV audit-cron "--profile gepp"
#
# The second argument accepts either a friendly alias or a function suffix. If
# it is not already prefixed with DEV-/PROD-, the environment is prepended.

usage() {
  cat <<'EOF'
Usage:
  bash update_function.sh DEV|PROD <function_name|alias> [aws args]

Examples:
  bash update_function.sh PROD GEPPPlatform "--profile gepp"
  bash update_function.sh DEV GEPPGenerateV3Report "--profile gepp"
  bash update_function.sh DEV iot-health-cron "--profile gepp"
  bash update_function.sh PROD audit-cron "--profile gepp"

Aliases:
  platform, geppplatform       -> <ENV>-GEPPPlatform
  export, report-export        -> <ENV>-GEPPGenerateV3Report
  iot, iot-health-cron         -> <ENV>-GEPPPlatform-IOTHEALTHCRON
  audit, audit-cron            -> <ENV>-GEPPPlatform-AUDITCRON
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ "$#" -lt 2 ]; then
  usage
  exit 0
fi

ENV_NAME="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"
FUNCTION_INPUT="$2"
shift 2

case "$ENV_NAME" in
  DEV|PROD) ;;
  *)
    echo "Unknown environment: $ENV_NAME (use DEV or PROD)" >&2
    exit 1
    ;;
esac

AWS_ARGS=()
for arg in "$@"; do
  # Support the requested form: "--profile gepp" as one quoted argument.
  read -r -a split_arg <<< "$arg"
  AWS_ARGS+=("${split_arg[@]}")
done

lower_name="$(printf '%s' "$FUNCTION_INPUT" | tr '[:upper:]' '[:lower:]')"
HANDLER=""

case "$lower_name" in
  platform|geppplatform)
    FUNCTION_NAME="${ENV_NAME}-GEPPPlatform"
    HANDLER="GEPPPlatform.entry_points.app.main"
    ;;
  export|report|report-export|geppgeneratev3report)
    FUNCTION_NAME="${ENV_NAME}-GEPPGenerateV3Report"
    HANDLER="GEPPPlatform.entry_points.GEPPGenerateV3Report.lambda_handler"
    ;;
  iot|iot-health|iot-health-cron|geppplatform-iothealthcron)
    FUNCTION_NAME="${ENV_NAME}-GEPPPlatform-IOTHEALTHCRON"
    HANDLER="GEPPPlatform.entry_points.iot_health_cron.cron_iot_health_snapshot"
    ;;
  audit|audit-cron|geppplatform-auditcron)
    FUNCTION_NAME="${ENV_NAME}-GEPPPlatform-AUDITCRON"
    HANDLER="GEPPPlatform.entry_points.audit_cron.cron_process_audits"
    ;;
  *)
    if [[ "$FUNCTION_INPUT" == "${ENV_NAME}-"* ]]; then
      FUNCTION_NAME="$FUNCTION_INPUT"
    else
      FUNCTION_NAME="${ENV_NAME}-${FUNCTION_INPUT}"
    fi
    ;;
esac

rm -f deploy_functions.zip

zip -r9 deploy_functions.zip \
  GEPPPlatform/ \
  GEPPCriteria/ \
  -x "*__pycache__*" "*.git*" "*.pyc" "*.DS_Store" "*/.venv/*" "*/tests/*" > /dev/null

echo "DEPLOY ${FUNCTION_NAME}"
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file fileb://deploy_functions.zip \
  "${AWS_ARGS[@]}" > /dev/null

# if [ -n "$HANDLER" ]; then
#   echo "HANDLER ${FUNCTION_NAME} -> ${HANDLER}"
#   aws lambda update-function-configuration \
#     --function-name "$FUNCTION_NAME" \
#     --handler "$HANDLER" \
#     "${AWS_ARGS[@]}" > /dev/null
# fi

echo "DONE ${FUNCTION_NAME}"

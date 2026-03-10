#!/bin/bash

rm -f deploy_functions.zip
zip -r9 deploy_functions.zip . -x "*__pycache__*" "*.git*"

echo "DEPLOY ${1}-GEPPPlatform-AUDITCRON"
aws lambda update-function-code --function-name "${1}-GEPPPlatform-AUDITCRON" --zip-file fileb://deploy_functions.zip ${2} > /dev/null

# Update handler to point to audit_cron module
aws lambda update-function-configuration --function-name "${1}-GEPPPlatform-AUDITCRON" --handler "GEPPPlatform.audit_cron.cron_process_audits" ${2} > /dev/null
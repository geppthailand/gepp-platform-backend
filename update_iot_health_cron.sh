#!/bin/bash
# Deploy the IoT health-snapshot cron to AWS Lambda.
#
# Usage: ./update_iot_health_cron.sh DEV|PROD [--profile xxx]
#
# Pre-req (one-time per env):
#   aws lambda create-function \
#     --function-name "${1}-GEPPPlatform-IOTHEALTHCRON" \
#     --runtime python3.13 \
#     --handler GEPPPlatform.iot_health_cron.cron_iot_health_snapshot \
#     --role arn:aws:iam::ACCOUNT:role/GEPPPlatform-LambdaRole \
#     --memory-size 256 --timeout 30 \
#     --zip-file fileb://deploy_functions.zip
#
#   aws events put-rule --name "${1}-iot-health-cron" \
#     --schedule-expression "rate(5 minutes)"
#
#   aws lambda add-permission --function-name "${1}-GEPPPlatform-IOTHEALTHCRON" \
#     --statement-id "${1}-iot-health-cron-invoke" \
#     --action lambda:InvokeFunction \
#     --principal events.amazonaws.com \
#     --source-arn arn:aws:events:REGION:ACCOUNT:rule/${1}-iot-health-cron
#
#   aws events put-targets --rule "${1}-iot-health-cron" \
#     --targets "Id=1,Arn=arn:aws:lambda:REGION:ACCOUNT:function:${1}-GEPPPlatform-IOTHEALTHCRON"
#
# After that, this script updates the function code on every push.

rm -f deploy_functions.zip
zip -r9 deploy_functions.zip . -x "*__pycache__*" "*.git*" "*.venv*" "tests*"

echo "DEPLOY ${1}-GEPPPlatform-IOTHEALTHCRON"
aws lambda update-function-code \
    --function-name "${1}-GEPPPlatform-IOTHEALTHCRON" \
    --zip-file fileb://deploy_functions.zip ${2} > /dev/null

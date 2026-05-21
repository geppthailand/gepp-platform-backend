#!/bin/bash

rm -f deploy_functions.zip

zip -r9 deploy_functions.zip \
  GEPPPlatform/ \
  GEPPCriteria/ \
  -x "*__pycache__*" "*.git*" "*.pyc" "*.DS_Store"

echo "DEPLOY ${1}-GEPPGenerateV3Report"
aws lambda update-function-code --function-name "${1}-GEPPGenerateV3Report" --zip-file fileb://deploy_functions.zip ${2} > /dev/null
#!/bin/bash

rm deploy_functions.zip
# cp deploy_base.zip deploy_functions.zip
# cd services
zip -r9 deploy_functions.zip . -x "*__pycache__*" "*.git*"
# cd $OLDPWD
# cd libs
# zip -gr9 ${OLDPWD}/deploy_functions.zip . -x "*__pycache__*" "*.git*"
# cd $OLDPWD


echo "DEPLOY ${1}-GEPPGenerateV3Report"
aws lambda update-function-code --function-name "${1}-GEPPGenerateV3Report" --zip-file fileb://deploy_functions.zip ${2} > /dev/null

# pip install \
# --platform manylinux2014_x86_64 \
# --target=./ \
# --implementation cp \
# --python-version 3.9 \
# --only-binary=:all: --upgrade \
# squarify
#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

function main() {
  if [[ "$#" -ge 1 ]]; then
    export REGION="$1"
    CDK_STACK_NAME="CdkPypiServerStack"    # The CDK stack name, used to get CDK stack outputs
    CDK_BASE_STACK_NAME="CdkPypiBaseStack"    # The CDK Base stack name, used to get CDK stack outputs
    PYPI_SERVER_SECRET="PYPI_SERVER_SECRET"
    PYPI_SERVER_URL_OUTPUT_KEY="CdkpypiserverurlCfnOutput" # The CloudFormation output key used to reference the host URL

    # Optional 2nd arg, for when the script is being run in a AWS CodePipeline pipeline:
    #   - Does NOT print msg to stdout
    PIPELINE=0
    if [[ "$#" -eq 2 ]]; then
      if [[ "$2" == "pipeline" ]]; then
        PIPELINE=1
      fi
    fi

    PYPI_SERVER_URL_OUTPUT_QUERY="Stacks[0].Outputs[?OutputKey=='${PYPI_SERVER_URL_OUTPUT_KEY}'].OutputValue"
    PYPI_SERVER_URL_OUTPUT=$(aws cloudformation describe-stacks --region "${REGION}" --stack-name ${CDK_STACK_NAME} --query "${PYPI_SERVER_URL_OUTPUT_QUERY}" --output text)

    SECRET_NAME="${CDK_BASE_STACK_NAME}/${PYPI_SERVER_SECRET}"
    PYPI_SERVER_SECRET=$(aws secretsmanager get-secret-value --region "${REGION}" --secret-id "${SECRET_NAME}" --query "SecretString" --output text)
    PYPI_SERVER_USER="$(echo "${PYPI_SERVER_SECRET}" | python3 -c 'import json,sys;obj=json.load(sys.stdin);print(obj["username"])')"
    PYPI_SERVER_PW="$(echo "${PYPI_SERVER_SECRET}" | python3 -c 'import json,sys;obj=json.load(sys.stdin);print(obj["password"])')"

    DOT_PYPIRC=".pypirc"
    INDEX_SERVER_NAME="ProdPI"
    printf "\n%s\n\n\t%s\n\n" "Creating '${DOT_PYPIRC}' file at path:" "$(pwd)"
    printf "%s\n%s\n\n%s\n%s\n%s\n%s" "[distutils]" "index-servers = ${INDEX_SERVER_NAME}" "[${INDEX_SERVER_NAME}]" "repository: ${PYPI_SERVER_URL_OUTPUT}" "username: ${PYPI_SERVER_USER}" "password: ${PYPI_SERVER_PW}" > "./${DOT_PYPIRC}"

    if [[ "${PIPELINE}" -eq 0 ]]; then
      printf "%s\n\n---\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n---\n\n%s\n\n" \
        "Message:" \
        "*** New PyPi Details ***" \
        "AWS Region: ${REGION}" \
        "PyPi Host URL: ${PYPI_SERVER_URL_OUTPUT}" \
        "User: ${PYPI_SERVER_USER}" \
        "P/w: (I'll send in separate message, in order to delete from MS Teams straight away)" \
        "Feel free to ask if you have any questions." \
        "P/w: ${PYPI_SERVER_PW}"
    fi
    exit $?
  else
    echo 1>&2 "Provide the AWS region as an arg to get details. For example: \`./pypirc.sh eu-west-2\`"
    exit 1
  fi
}

main "$@"

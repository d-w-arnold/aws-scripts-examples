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
    #   - Generates an internal (to AWS VPC) PyPi server index URL
    #   - Does NOT print msg to stdout
    PIPELINE=0
    PIPELINE_INTERNAL=0
    if [[ "$#" -eq 2 ]]; then
      if [[ "$2" == "pipeline" ]]; then
        PIPELINE=1
      elif [[ "$2" == "pipeline-internal" ]]; then
        PIPELINE_INTERNAL=1
      fi
    fi

    PYPI_SERVER_URL_OUTPUT_QUERY="Stacks[0].Outputs[?OutputKey=='${PYPI_SERVER_URL_OUTPUT_KEY}'].OutputValue"
    PYPI_SERVER_URL_OUTPUT=$(aws cloudformation describe-stacks --region "${REGION}" --stack-name ${CDK_STACK_NAME} --query "${PYPI_SERVER_URL_OUTPUT_QUERY}" --output text)

    SECRET_NAME="${CDK_BASE_STACK_NAME}/${PYPI_SERVER_SECRET}"
    PYPI_SERVER_SECRET=$(aws secretsmanager get-secret-value --region "${REGION}" --secret-id "${SECRET_NAME}" --query "SecretString" --output text)
    PYPI_SERVER_PORT="$(echo "${PYPI_SERVER_SECRET}" | python3 -c 'import json,sys;obj=json.load(sys.stdin);print(obj["port"])')"
    PYPI_SERVER_USER="$(echo "${PYPI_SERVER_SECRET}" | python3 -c 'import json,sys;obj=json.load(sys.stdin);print(obj["username"])')"
    PYPI_SERVER_PW="$(echo "${PYPI_SERVER_SECRET}" | python3 -c 'import json,sys;obj=json.load(sys.stdin);print(obj["password"])')"

    # Get PyPi server index URL
    PYPI_SERVER_INDEX_URL="$(aws ssm get-parameter --region "${REGION}" --name "/${SECRET_NAME}_INDEX_URL" --with-decryption --query "Parameter.Value" --output text)"
    if [[ "${PIPELINE_INTERNAL}" -eq 1 ]]; then
      # Get PyPi server (internal) index URL
      PYPI_SERVER_PRIVATE_DNS_NAME=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=*pypi-server*" --query "Reservations[0].Instances[0].PrivateDnsName" --output text)
      PYPI_SERVER_INTERNAL_ADDRESS="${PYPI_SERVER_PRIVATE_DNS_NAME}:${PYPI_SERVER_PORT}"
      PYPI_SERVER_INDEX_URL="$(printf '{"url": "%s", "public": "%s", "internal": "%s"}' \
      "${PYPI_SERVER_INDEX_URL}" "${PYPI_SERVER_URL_OUTPUT}" "${PYPI_SERVER_INTERNAL_ADDRESS}" | python3 -c \
      'import json,sys;from urllib.parse import urlparse;obj=json.load(sys.stdin);print(obj["url"].replace(urlparse(obj["public"]).netloc, obj["internal"], 1))')"
    fi

    # Get PyPi server password (URL-encoded)
    PYPI_SERVER_PW_URL_ENCODED="$(echo "${PYPI_SERVER_SECRET}" | python3 -c \
    'import json,sys,urllib.parse;obj=json.load(sys.stdin);pw=obj["password"];print(urllib.parse.quote(pw))')"

    # Get PyPi server index URL (complete, with URL-encoded password)
    INDEX_URL="$(printf '{"url": "%s", "pw": "%s"}' "${PYPI_SERVER_INDEX_URL}" "${PYPI_SERVER_PW_URL_ENCODED}" | python3 -c \
    'import json,sys;obj=json.load(sys.stdin);print(obj["url"].replace("<PASSWORD>", obj["pw"], 1))')"

    PIP_CONF="pip.conf"
    printf "\n%s\n\n\t%s\n\n" "Creating '${PIP_CONF}' file at path:" "$(pwd)"
    EXTRA_INDEX_URL="https://pypi.org/simple"
    printf "%s\n%s\n%s" "[global]" "index-url = ${INDEX_URL}" "extra-index-url = ${EXTRA_INDEX_URL}" > "./${PIP_CONF}"

    if [[ "${PIPELINE}" -eq 0 && "${PIPELINE_INTERNAL}" -eq 0 ]]; then
      printf "%s\n\n---\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n---\n\n%s\n\n" \
        "Message:" \
        "*** New PyPi Details ***" \
        "AWS Region: ${REGION}" \
        "PyPi Host URL: ${PYPI_SERVER_URL_OUTPUT}" \
        "User: ${PYPI_SERVER_USER}" \
        "P/w: (I'll send in separate message, in order to delete from MS Teams straight away)" \
        "Index URL: ${INDEX_URL}" \
        "Feel free to ask if you have any questions." \
        "P/w: ${PYPI_SERVER_PW}"
    fi
    exit $?
  else
    echo 1>&2 "Provide the AWS region as an arg to get details. For example: \`./pip-conf.sh eu-west-2\`"
    exit 1
  fi
}

main "$@"

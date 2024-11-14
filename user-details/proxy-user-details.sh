#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

function main() {
  if [[ "$#" -eq 1 ]]; then
    export REGION="$1"
    CDK_STACK_NAME="CdkProxyServerStack" # The CDK stack name, where this script is ingested as user data, used as a prefix path for necessary parameters in AWS Systems Manager Parameter Store

    echo "## Get Proxy server public IPv4 address from AWS Systems Manager Parameter Store"
    PARAM_PUBLIC_IPV4_NAME="/${CDK_STACK_NAME}/public-ipv4"
    IP_ADDRESS=$(aws ssm get-parameter --region "${REGION}" --name ${PARAM_PUBLIC_IPV4_NAME} --with-decryption --output text --query Parameter.Value)

    echo "## Get the user from the Tinyproxy configuration BasicAuth option in AWS Systems Manager Parameter Store"
    PARAM_NAME_PATH="/${CDK_STACK_NAME}/tinyproxy-conf"
    TINYPROXY_CONF_OPTS="$(aws ssm get-parameter --region "${REGION}" --name ${PARAM_NAME_PATH} --with-decryption --output text --query Parameter.Value)"
    TINYPROXY_CONF_OPTS=$(echo "${TINYPROXY_CONF_OPTS}" | tr '\n' ' ')
    DELIMITER=","

    echo "## Creating Tinyproxy configuration options array"
    TINYPROXY_CONF_OPTS_ARRAY=()
    TINYPROXY_CONF_OPTS="${TINYPROXY_CONF_OPTS}${DELIMITER}"
    while [[ ${TINYPROXY_CONF_OPTS} ]]; do
      TINYPROXY_CONF_OPTS_ARRAY+=("${TINYPROXY_CONF_OPTS%%"${DELIMITER}"*}")
      TINYPROXY_CONF_OPTS=${TINYPROXY_CONF_OPTS#*"${DELIMITER}"}
    done

    echo "## Looking for Tinyproxy configuration Port and BasicAuth options"
    PORT="No port found"
    USER="No user found"
    FOUND_PORT=0
    FOUND_USER=0
    DELIMITER=" "
    for TINYPROXY_CONF_OPT in "${TINYPROXY_CONF_OPTS_ARRAY[@]}"; do
      if [ "${FOUND_PORT}" -eq 1 ] && [ "${FOUND_USER}" -eq 1 ]; then
        break
      fi
      TINYPROXY_CONF_OPT_ARRAY=()
      TINYPROXY_CONF_OPT="${TINYPROXY_CONF_OPT}${DELIMITER}"
      if [[ "${TINYPROXY_CONF_OPT}" == Port* ]]; then
        echo "## Found Tinyproxy configuration Port option: ${TINYPROXY_CONF_OPT}"
        while [[ ${TINYPROXY_CONF_OPT} ]]; do
          TINYPROXY_CONF_OPT_ARRAY+=("${TINYPROXY_CONF_OPT%%"${DELIMITER}"*}")
          TINYPROXY_CONF_OPT=${TINYPROXY_CONF_OPT#*"${DELIMITER}"}
        done
        PORT="${TINYPROXY_CONF_OPT_ARRAY[1]}"
        FOUND_PORT=1
      elif [[ "${TINYPROXY_CONF_OPT}" == BasicAuth* ]]; then
        echo "## Found Tinyproxy configuration BasicAuth option: ${TINYPROXY_CONF_OPT}"
        while [[ ${TINYPROXY_CONF_OPT} ]]; do
          TINYPROXY_CONF_OPT_ARRAY+=("${TINYPROXY_CONF_OPT%%"${DELIMITER}"*}")
          TINYPROXY_CONF_OPT=${TINYPROXY_CONF_OPT#*"${DELIMITER}"}
        done
        USER="${TINYPROXY_CONF_OPT_ARRAY[1]}"
        FOUND_USER=1
      fi
    done

    echo "## Load Tinyproxy configuration BasicAuth option password from AWS Secrets Manager"
    SECRET_NAME="${CDK_STACK_NAME}/proxy-server-basic-auth"
    PASSWORD=$(aws secretsmanager get-secret-value --region "${REGION}" --secret-id "${SECRET_NAME}" --query "SecretString" --output text | jq -r '."password"')

    printf "\n%s\n\n---\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n---\n\n%s\n\n" \
      "Message:" \
      "*** New Proxy Details ***" \
      "AWS Region: ${REGION}" \
      "Proxy Type: HTTP & HTTPS" \
      "Proxy Host IP: ${IP_ADDRESS}" \
      "Proxy Port: ${PORT}" \
      "User: ${USER}" \
      "P/w: (I'll send in separate message, in order to delete from MS Teams straight away)" \
      "(Optional) Proxy Bypass: 127.0.0.1, localhost" \
      "Setup steps: https://learning.postman.com/docs/getting-started/proxy/" \
      "Feel free to ask if you have any questions." \
      "P/w: ${PASSWORD}"
    exit $?
  else
    echo 1>&2 "Provide the AWS region as an arg to get details. For example: \`./proxy-user-details.sh eu-west-2\`"
    exit 1
  fi
}

main "$@"

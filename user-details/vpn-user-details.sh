#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

function main() {
  if [[ "$#" -eq 2 ]]; then
    export REGION="$1"
    export ADDL_USER="$2"
    CDK_STACK_NAME="CdkIpsecVpnServerStack" # The CDK stack name, used to get CDK stack outputs
    CDK_STACK_NAME_BASE="CdkIpsecVpnBaseStack" # The base CDK stack name, used as a prefix paths in AWS Systems Manager Parameter Store and AWS Secrets Manager secrets
    CDK_STACK_NAME_PSK="CdkIpsecVpnPskStack" # The PSK CDK stack name, used as a prefix paths in AWS Systems Manager Parameter Store and AWS Secrets Manager secrets

    echo "## Get IPsec VPN server public IPv4 address from AWS Systems Manager Parameter Store"
    PARAM_PUBLIC_IPV4_NAME="/${CDK_STACK_NAME}/public-ipv4"
    IP_ADDRESS=$(aws ssm get-parameter --region "${REGION}" --name ${PARAM_PUBLIC_IPV4_NAME} --with-decryption --output text --query Parameter.Value)

    echo "## Load the users p/w from AWS Secrets Manager"
    SECRET_NAME="${CDK_STACK_NAME_BASE}/VPN_ADDL_USERS/${ADDL_USER}"
    SECRET=$(aws secretsmanager get-secret-value --region "${REGION}" --secret-id "${SECRET_NAME}" --query "SecretString" --output text | jq -r '."password"')

    echo "## Load VPN_IPSEC_PSK environment variable from AWS Secrets Manager"
    VPN_IPSEC_PSK_LEN=64
    SECRET_NAME="${CDK_STACK_NAME_PSK}/VPN_IPSEC_PSK/${VPN_IPSEC_PSK_LEN}"
    VPN_IPSEC_PSK=$(aws secretsmanager get-secret-value --region "${REGION}" --secret-id "${SECRET_NAME}" --query "SecretString" --output text | jq -r '."password"')

    printf "\n%s\n\n---\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n---\n\n%s\n\n" \
      "Message:" \
      "*** New VPN Details ***" \
      "AWS Region: ${REGION}" \
      "VPN Host IP: ${IP_ADDRESS}" \
      "Pre-Shared Key (PSK): (I'll send in separate message, in order to delete from MS Teams straight away)" \
      "User: ${ADDL_USER}" \
      "P/w: ${SECRET}" \
      "Setup steps: https://github.com/hwdsl2/setup-ipsec-vpn/blob/master/docs/clients.md" \
      "Feel free to ask if you have any questions." \
      "Please confirm once you're on the VPN." \
      "Pre-Shared Key (PSK): ${VPN_IPSEC_PSK}"
    exit $?
  else
    echo 1>&2 "Provide the AWS region and additional VPN username as args to get details. For example: \`./vpn-user-details.sh eu-west-2 johns\`"
    exit 1
  fi
}

main "$@"

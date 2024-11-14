#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

# Generate an updated AWS Systems Manager Parameter Store parameter,
#  used by AWS CDK to reference all NAT Gateway Public IPs (of all custom VPCs),
#  across all AWS regions.
function main() {
  if [[ "$#" -ge 1 ]]; then
    export REGION="$1"

    # Optional 2nd arg, for when the script is being with a different AWS profile
    PROFILE="default"
    if [[ "$#" -eq 2 ]]; then
        PROFILE="$2"
    fi

    ALL_REGIONS=("us-east-1" "af-south-1" "ap-northeast-2" "ap-southeast-2" "eu-central-1" "eu-west-2" "sa-east-1")
    ALL_VPC_NAMES=("vpc-01-sih")

    CDK_STACK="CdkVpcSihStack" # The CDK stack name, where VPCs are created

    printf "## Generating NAT Gateway Public IPs list...\n\n"
    DELIM=""
    NGW_PUBLIC_IPS=""
    for R in "${ALL_REGIONS[@]}"; do
      echo "Region: ${R}"
      for V in "${ALL_VPC_NAMES[@]}"; do
        echo "VPC name: ${V}"
        if IGW_ID=$(aws ssm get-parameter --region "${R}" --name "/${CDK_STACK}/${V}/igw-id" --with-decryption --query "Parameter.Value" --output text --profile "${PROFILE}" 2>/dev/null); then
          VPC_ID="$(aws ec2 describe-internet-gateways --region "${R}" --filters "Name=internet-gateway-id,Values=${IGW_ID}" --query "InternetGateways[0].Attachments[0].VpcId" --output text --profile "${PROFILE}")"
          NGW_PUBLIC_IP="$(aws ec2 describe-nat-gateways --region "${R}" --filter "Name=vpc-id,Values=${VPC_ID}" --query "NatGateways[0].NatGatewayAddresses[0].PublicIp" --output text --profile "${PROFILE}")"
          NGW_PUBLIC_IPS="${NGW_PUBLIC_IPS}${DELIM}${NGW_PUBLIC_IP}"
          DELIM=","
          printf "Found NAT Gateway Public IP address: %s (Region: %s, VPC name: %s)\n" "${NGW_PUBLIC_IP}" "${R}" "${V}"
        fi
      done
      echo ""
    done

    echo "## Put the NAT Gateway Public IPs in AWS Systems Manager Parameter Store (Region: ${REGION})"
    PARAM_NGW_PUBLIC_IPS_NAME="/${CDK_STACK}/ngw-public-ips"
    PARAM_NGW_PUBLIC_IPS_DESCRIPTION="The NAT Gateway Public IPs (of all custom VPCs), across all AWS regions, used by '${CDK_STACK}' to add all NAT Gateway Public IPs to the Cloudfront WAF allowed IP list."
    SSM_RES=$(aws ssm put-parameter --region "${REGION}" --name ${PARAM_NGW_PUBLIC_IPS_NAME} --description "${PARAM_NGW_PUBLIC_IPS_DESCRIPTION}" --value "${NGW_PUBLIC_IPS}" --type "String" --overwrite --tier "Standard" --profile "${PROFILE}")
    echo "${SSM_RES}"
    exit $?
  else
    echo 1>&2 "Provide the AWS region where the SSM Parameter Store parameter should be created. For example: \`./aws-nat-gateway-public-ips.sh us-east-1\`"
    exit 1
  fi
}

main "$@"

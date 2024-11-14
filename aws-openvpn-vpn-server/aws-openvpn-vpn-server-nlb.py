import logging
import os
import sys

from botocore.exceptions import ClientError

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

base_steps_client_names: list[str] = [aws.ssm_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

cdk_stack: str = "CdkOpenvpnVpnServerStack"
delim: str = ","


def main(region: str):
    cf.info_log_starting()

    all_nlb_public_ipv4_addresses_list: list[str] = []

    for r, _ in cf.region_timezones_meta.items():
        cloudformation = cf.get_client(r, aws.cloudformation_str)
        ec2 = cf.get_client(r, aws.ec2_str)

        logger_info_prefix: str = f"(Region: {r})"

        logger.info(
            f"## {logger_info_prefix} Retrieving OpenVPN Server NLB DNS name from the '{cdk_stack}' "
            f"(AWS CDK) stack CloudFormation output"
        )

        try:
            cloudformation_describe_stacks_res = cloudformation.describe_stacks(StackName=cdk_stack)
            logger.info(f"## {logger_info_prefix} CloudFormation Describe Stacks successful response")
        except ClientError as ex:
            logger.error(f"## {logger_info_prefix} CloudFormation Describe Stacks ERROR: '{ex}'")
            continue

        cdk_stack_name_outputs: list[dict[str, str]] = cloudformation_describe_stacks_res["Stacks"][0]["Outputs"]
        nlb_dns_name: str = None
        cdk_stack_output_key_snippet: str = f"{cdk_stack[len('Cdk'): -(len('Stack'))].lower()}nlbdnsname"
        for i in cdk_stack_name_outputs:
            if cdk_stack_output_key_snippet in i["OutputKey"]:
                nlb_dns_name = i["OutputValue"]
                break
        if nlb_dns_name is None:
            logger.error(
                f"## {logger_info_prefix} CloudFormation Describe Stacks outputs: {cdk_stack_name_outputs} "
                f"(for '{cdk_stack}' (AWS CDK) stack)"
            )
            logger.error(
                f"## {logger_info_prefix} ERROR: Could not find output key starting with: '{cdk_stack_output_key_snippet}' "
                f"(from the '{cdk_stack}' (AWS CDK) stack CloudFormation output)"
            )
            sys.exit(1)

        nlb_name: str
        nlb_id: str
        nlb_name, nlb_id = nlb_dns_name.split(sep=".", maxsplit=1)[0].rsplit(sep="-", maxsplit=1)
        try:
            ec2_describe_network_interfaces_res = ec2.describe_network_interfaces(
                Filters=[
                    {"Name": "interface-type", "Values": ["network_load_balancer"]},
                    {"Name": "description", "Values": [f"ELB net/{nlb_name}/{nlb_id}"]},
                ],
            )
            logger.info(f"## {logger_info_prefix} EC2 Describe Network Interfaces successful response")
        except ClientError as ex:
            logger.error(f"## {logger_info_prefix} EC2 Describe Network Interfaces ERROR: '{ex}'")
            sys.exit(1)

        all_nlb_public_ipv4_addresses_list = all_nlb_public_ipv4_addresses_list + [
            network_interface["Association"]["PublicIp"]
            for network_interface in ec2_describe_network_interfaces_res["NetworkInterfaces"]
        ]

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    all_nlb_public_ipv4_addresses: str = delim.join(all_nlb_public_ipv4_addresses_list)
    param_name: str = f"/{cdk_stack}/nlb-public-ips"
    logger.info(
        f"## Write public IPv4 addresses: '{all_nlb_public_ipv4_addresses}' (to AWS Systems Manager Parameter Store: {param_name})"
    )
    try:
        res[aws.ssm_str]["ssm_put_parameter"] = clients[aws.ssm_str].put_parameter(
            Name=param_name,
            Description="The OpenVPN Server NLB Public IPs, across all AWS regions, used to add all "
            "OpenVPN Server NLB Public IPs to Cloudfront WAF allowed IP lists, etc.",
            Value=all_nlb_public_ipv4_addresses,
            Type="String",
            Overwrite=True,
            # TODO: (OPTIONAL) A regular expression used to validate the parameter value.
            # AllowedPattern=,
            Tier="Standard",
            # DataType="text",
        )
        logger.info("## SSM Put Parameter successful response")
    except ClientError as ex:
        logger.error(f"## SSM Put Parameter ERROR: '{ex}'")
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="For all OpenVPN Server NLBs (of all custom VPCs), across all AWS regions, "
        "generate a SSM Parameter Store parameter recording all OpenVPN Server NLB Public IPs."
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region where the SSM Parameter Store parameter should be created, eg. '--region us-east-1'.",
        type=str,
    )
    args = parser.parse_args()
    main(region=args.region)

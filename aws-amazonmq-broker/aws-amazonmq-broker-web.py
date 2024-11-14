import json
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


def main(region: str):
    cf.info_log_starting()

    ec2 = cf.get_client(region, aws.ec2_str)
    mq = cf.get_client(region, aws.mq_str)

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    try:
        ec2_describe_vpc_endpoints_res = ec2.describe_vpc_endpoints()
        logger.info("## EC2 Describe VPC Endpoints successful response")
    except ClientError as ex:
        logger.error(f"## EC2 Describe VPC Endpoints ERROR: '{ex}'")
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    try:
        mq_list_brokers_res = mq.list_brokers()
        logger.info("## Amazon MQ List Brokers successful response")
    except ClientError as ex:
        logger.error(f"## Amazon MQ List Brokers ERROR: '{ex}'")
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    vpc_endpoints = ec2_describe_vpc_endpoints_res["VpcEndpoints"]
    private_ip_address_str: str = "PrivateIpAddress"
    res[aws.ssm_str]["ssm_put_parameter"] = {}

    for mq_broker in mq_list_brokers_res["BrokerSummaries"]:
        broker_vpc_endpoint: dict = None
        for vpc_endpoint in vpc_endpoints:
            if vpc_endpoint["Tags"] and (tags := {i["Key"]: i["Value"] for i in vpc_endpoint["Tags"]}):
                if (managed_tag := tags.get("AMQManaged")) and (broker_tag := tags.get("Broker")):
                    if json.loads(managed_tag) and mq_broker["BrokerId"] == broker_tag:
                        broker_vpc_endpoint = vpc_endpoint
        if broker_vpc_endpoint is not None:
            try:
                ec2_describe_network_interfaces_res = ec2.describe_network_interfaces(
                    NetworkInterfaceIds=broker_vpc_endpoint["NetworkInterfaceIds"],
                )
                logger.info("## EC2 Describe Network Interfaces successful response")
            except ClientError as ex:
                logger.error(f"## EC2 Describe Network Interfaces ERROR: '{ex}'")
                cf.write_to_json_paths(res, base_steps_client_names)
                sys.exit(1)
            for az, private_ipv4_address in {
                network_interface["AvailabilityZone"]: network_interface[private_ip_address_str]
                for network_interface in ec2_describe_network_interfaces_res["NetworkInterfaces"]
            }.items():
                param_name: str = f"/{mq_broker['BrokerName']}/{private_ip_address_str}/{az}"
                logger.info(
                    f"## Write private IPv4 address: '{private_ipv4_address}' (to AWS Systems Manager Parameter Store: {param_name})"
                )
                try:
                    res[aws.ssm_str]["ssm_put_parameter"][param_name] = clients[aws.ssm_str].put_parameter(
                        Name=param_name,
                        # Description,  # Default to the existing description
                        Value=private_ipv4_address,
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
        description="For each Amazon MQ (RabbitMQ) broker, "
        "find the managed AWS VPC endpoint for said broker, "
        "and generate a SSM Parameter Store parameter for each subnet ENI, "
        "recording the private IPv4 address of each ENI."
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    args = parser.parse_args()
    main(region=args.region)

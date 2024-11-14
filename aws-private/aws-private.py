import json
import logging
import os
import random
import sys
from typing import Union

import boto3
import jmespath
from botocore.exceptions import ClientError

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

cf = CommonFuncs(logger, filename=str(os.path.basename(__file__)))

aws_private_filename_no_ext: str = cf.filename.rsplit(sep=".", maxsplit=1)[0]
aws_private_json_path: str = f"{aws_private_filename_no_ext}.json"
aws_private_bastion_az_txt_path: str = f"{aws_private_filename_no_ext}-bastion-az.txt"
aws_private_bastion_id_txt_path: str = f"{aws_private_filename_no_ext}-bastion-id.txt"
aws_private_command_txt_path: str = f"{aws_private_filename_no_ext}-command.txt"

aws_private_filename_ecs_no_ext: str = f"{aws_private_filename_no_ext}-ecs"
aws_private_ecs_json_path: str = f"{aws_private_filename_ecs_no_ext}.json"
aws_private_ecs_cluster_txt_path: str = f"{aws_private_filename_ecs_no_ext}-cluster.txt"

default_local_port: int = 9000
default_local_port_project_range: int = 100

parameter_name_sep: str = "/"
parameter_prefix: str = f"{parameter_name_sep}scripts"

bastion_host_instance_ids_key: str = "BastionHostLinux"

bastion_str: str = "bastion"
list_str: str = "list"
command_str: str = "command"

ec2_str: str = "ec2"
ecs_str: str = "ecs"
rds_mysql_str: str = "rds-mysql"

local_port_str: str = "localport"
target_host_str: str = "targethost"
dest_port_str: str = "destport"

ecs_cluster_not_found_str: str = f"{ecs_str}-cluster-not-found"
target_host_not_found_str: str = f"{target_host_str}-not-found"
dest_port_not_found_str: str = f"{dest_port_str}-not-found"

project_names: list[str] = [
    "bird",
    "cat",
    "cow",
    "dog",
    "fish",
    "lion",
]


def ssm_get_param(ssm, parameter_name: str, ecs: bool, no_json_loads: bool = False) -> Union[str, dict[str, str]]:
    try:
        ssm_res = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        logger.debug(f"## SSM Get Parameter response: {ssm_res}")
        return ssm_res["Parameter"]["Value"] if no_json_loads or ecs else json.loads(ssm_res["Parameter"]["Value"])
    except ClientError as ex:
        logger.debug(f"## SSM Get Parameter ERROR: {ex}")
    return None


def bastion_steps(region: str) -> None:
    with open(aws_private_json_path, "r", encoding="utf-8") as f:
        aws_private_ports: dict = json.load(f)
    if region[-1].isdigit():
        bastion_host_instance_ids: dict[str, str] = aws_private_ports[region][bastion_host_instance_ids_key]
        bastion_host_az: str = random.choice([k for k, _ in bastion_host_instance_ids.items()])
        bastion_host_instance_id: str = bastion_host_instance_ids[bastion_host_az]
    else:
        bastion_host_az: str = region
        bastion_host_instance_id: str = aws_private_ports[region[:-1]][bastion_host_instance_ids_key][bastion_host_az]
    logger.info(f"## Bastion Host Availability Zone (AZ): {bastion_host_az}")
    with open(aws_private_bastion_az_txt_path, "w+", encoding="utf-8") as f:
        f.write(bastion_host_az)
    logger.info(f"## Bastion Host Instance ID: {bastion_host_instance_id}")
    with open(aws_private_bastion_id_txt_path, "w+", encoding="utf-8") as f:
        f.write(bastion_host_instance_id)


def cluster_steps(region: str, cluster_name: str) -> None:
    with open(aws_private_ecs_json_path, "r", encoding="utf-8") as f:
        aws_private_ports: dict = json.load(f)
        t = aws_private_ports[region]
    logger.info("## Getting the ECS cluster ARN for the required private AWS resource")
    with open(aws_private_ecs_cluster_txt_path, "w+", encoding="utf-8") as f:
        f.writelines(t[cluster_name] if cluster_name in t else ecs_cluster_not_found_str)


def list_steps(region: str, ecs: bool) -> None:
    json_path: str = aws_private_ecs_json_path if ecs else aws_private_json_path
    with open(json_path, "r", encoding="utf-8") as f:
        aws_private_ports: dict = json.load(f)
        t = aws_private_ports[region]
    if not ecs:
        logger.info("## Bastion Host Instance ID info:")
        for k, v in t[bastion_host_instance_ids_key].items():
            logger.info(f"## \t Availability Zone (AZ): {k}, Instance ID: {v}")
        t.pop(bastion_host_instance_ids_key, None)
    logger.info("## Private AWS resource options:")
    for i in t:
        logger.info(f"## \t {i}")


def command_steps(region: str, command_opt: list[str]) -> None:
    with open(aws_private_json_path, "r", encoding="utf-8") as f:
        aws_private_ports: dict = json.load(f)
        t = aws_private_ports[region]
    commands: list[str] = []
    logger.info("## Gathering all SSH command args for setting up SSH tunnels to private AWS resources")
    keys: list[str] = [local_port_str, target_host_str, dest_port_str]
    for i in command_opt:
        if i in t and all(k in t[i] for k in keys):
            commands.append(":".join([t[i][k] for k in keys]))
    commands.append("end")
    with open(aws_private_command_txt_path, "w+", encoding="utf-8") as f:
        f.writelines("\n".join(commands))


def base_steps(region: str, ecs: bool) -> None:
    ssm = cf.get_client(region, aws.ssm_str)

    t: dict = {}
    bastion_hosts: dict = {}
    project_count: dict[str, int] = {}
    project_local_port_offset: dict[str, int] = {}

    json_path: str = aws_private_ecs_json_path if ecs else aws_private_json_path
    logger.info(f"## Starting to assemble content for '{json_path}' file")

    for n, project_name in enumerate(project_names):
        project_count[project_name] = n
        project_local_port_offset[project_name] = 0
    for parameter_name in sorted(
        jmespath.compile("[].Name").search(cf.ssm_describe_parameters(ssm, contains=parameter_prefix))
    ):
        if str(parameter_name).startswith(parameter_prefix):
            logger.debug(f"## Parameters name: {parameter_name}")
            parameter_name_props: list[str] = parameter_name.split(parameter_name_sep)[2:]
            if parameter_name_props[0] == bastion_host_instance_ids_key:
                bastion_hosts[parameter_name_props[1].split("-", maxsplit=1)[1]] = ssm_get_param(
                    ssm, parameter_name, ecs, no_json_loads=True
                )
            elif parameter_name_no_prefix := parameter_name_sep.join(parameter_name_props[0:]):
                if ecs and parameter_name_no_prefix.endswith(ecs_str):
                    ecs_cluster_arn: str = ssm_get_param(ssm, parameter_name, ecs)
                    t[parameter_name_no_prefix] = ecs_cluster_arn if ecs_cluster_arn else ecs_cluster_not_found_str
                elif not ecs and ecs_str not in parameter_name_no_prefix:
                    project_name: str = parameter_name_props[-1].split("-", maxsplit=1)[0]
                    host_info: dict[str, str] = ssm_get_param(ssm, parameter_name, ecs)
                    local_port: str = str(
                        default_local_port
                        + (default_local_port_project_range * project_count[project_name])
                        + project_local_port_offset[project_name]
                    )
                    logger.debug(f"## Local port: {local_port} -> {parameter_name_no_prefix}")
                    t[parameter_name_no_prefix] = {
                        local_port_str: local_port,
                        target_host_str: str(host_info[target_host_str] if host_info else target_host_not_found_str),
                        dest_port_str: str(host_info[dest_port_str] if host_info else dest_port_not_found_str),
                    }
                    project_local_port_offset[project_name] = project_local_port_offset[project_name] + 1
    if not ecs:
        t[bastion_host_instance_ids_key] = bastion_hosts
    t = dict(sorted(t.items()))

    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            aws_private_ports: dict = json.load(f)
            aws_private_ports[region] = t
    else:
        aws_private_ports: dict = {region: t}
    with open(json_path, "w+", encoding="utf-8") as f:
        json.dump(aws_private_ports, f, indent=2, sort_keys=True)


def main(
    region: str,
    bastion_opt: bool = False,
    list_opt: bool = False,
    command_opt: list[str] = None,
    ecs_opt: bool = False,
    cluster_opt: str = None,
):
    if profile := os.getenv("AWS_PROFILE"):
        logger.info(f"## Found non-default AWS profile: {profile}")
        boto3.setup_default_session(profile_name=profile)
    if bastion_opt:
        cf.info_log_starting(opt=bastion_str)
        bastion_steps(region)
        cf.info_log_finished(opt=bastion_str)
    else:
        if not region[-1].isdigit():
            region = region[:-1]
        if cluster_opt:
            cf.info_log_starting(opt=command_str)
            cluster_steps(region, cluster_opt)
            cf.info_log_finished(opt=command_str)
        elif list_opt:
            cf.info_log_starting(opt=list_str)
            list_steps(region, ecs_opt)
            cf.info_log_finished(opt=list_str)
        elif command_opt:
            cf.info_log_starting(opt=command_str)
            command_steps(region, command_opt)
            cf.info_log_finished(opt=command_str)
        else:
            cf.info_log_starting()
            base_steps(region, ecs_opt)
            cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generates the 'aws-private.json' file, for use in the 'aws-private.sh' script."
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
    )
    parser.add_argument(
        "--bastion",
        action="store_true",
        help="Get the Bastion Host Instance ID for the specified AWS region "
        "availability zone (AZ) in the '--region' option.\nIf the '--region' "
        "does not contain reference to an AWS region AZ, a random Bastion Host "
        "Instance ID is returned.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all valid private AWS resource identifiers.",
    )
    parser.add_argument(
        "--command",
        nargs="*",
        help="Get all SSH command args for setting up SSH tunnels to private AWS resources.",
    )
    parser.add_argument(
        "--ecs",
        action="store_true",
        help="Specifies that this script is being invoked by 'aws-private-ecs.sh', instead of 'aws-private.sh'.",
    )
    parser.add_argument("--cluster", help="Get the ECS cluster ARN for the required private AWS resource.", type=str)
    args = parser.parse_args()
    main(
        region=args.region,
        bastion_opt=args.bastion,
        list_opt=args.list,
        command_opt=args.command,
        ecs_opt=args.ecs,
        cluster_opt=args.cluster,
    )

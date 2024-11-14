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

base_steps_client_names: list[str] = [aws.logs_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

filename_txt: str = f"{cf.filename.rsplit(sep='.', maxsplit=1)[0]}-untracked-list.txt"

sep: str = "/"


def get_log_group_name_prefix(comps: list[str]) -> str:
    return f"{sep}{sep.join(comps)}{sep}"


log_group_name_prefix_ecs_cluster: str = get_log_group_name_prefix(["aws", "ecs", "containerinsights"])
log_group_name_prefix_lambda_func: str = get_log_group_name_prefix(["aws", "lambda"])
log_group_name_prefix_rds_instance: str = get_log_group_name_prefix(["aws", "rds", "instance"])

log_group_name_suffix_ecs_cluster: str = ["performance"]
log_group_name_suffix_rds_instance: str = ["error", "general", "slowquery", "audit"]

type_ecs_cluster = "AWS::ECS::Cluster"
type_lambda_function = "AWS::Lambda::Function"
type_logs_log_group = "AWS::Logs::LogGroup"
type_rds_instance = "AWS::RDS::DBInstance"


def get_log_groups_names(cloudformation_list_stack_resources_res: dict) -> list[str]:
    log_groups_names: list[str] = []
    for i in cloudformation_list_stack_resources_res["StackResourceSummaries"]:
        resource_type = i["ResourceType"]
        if any(
            resource_type == t for t in [type_logs_log_group, type_lambda_function, type_ecs_cluster, type_rds_instance]
        ):
            physical_id = i["PhysicalResourceId"]
            if resource_type == type_lambda_function:
                names = [f"{log_group_name_prefix_lambda_func}{physical_id}"]
            elif resource_type == type_ecs_cluster:
                names = [
                    sep.join([f"{log_group_name_prefix_ecs_cluster}{physical_id}", s])
                    for s in log_group_name_suffix_ecs_cluster
                ]
            elif resource_type == type_rds_instance:
                names = [
                    sep.join([f"{log_group_name_prefix_rds_instance}{physical_id}", s])
                    for s in log_group_name_suffix_rds_instance
                ]
            else:
                names = [physical_id]
            for name in names:
                log_groups_names.append(name)
    return list(set(log_groups_names))


def main(region: str):
    cf.info_log_starting()

    cloudformation = cf.get_client(region, aws.cloudformation_str)
    ecs = cf.get_client(region, aws.ecs_str)
    lambda_ = cf.get_client(region, aws.lambda_str)
    rds = cf.get_client(region, aws.rds_str)

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    is_next_token: bool = True
    next_token: str = None
    cdk_stack_name_ids: list[tuple[str, str]] = []
    while is_next_token:
        try:
            cloudformation_describe_stacks_res = cloudformation.describe_stacks(
                **{
                    k: v
                    for k, v in {
                        "NextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## CloudFormation Describe Stacks successful response")
        except ClientError as ex:
            logger.error(f"## CloudFormation Describe Stacks ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        cdk_stack_name_ids += [(i["StackName"], i["StackId"]) for i in cloudformation_describe_stacks_res["Stacks"]]
        if "NextToken" in cloudformation_describe_stacks_res:
            next_token = cloudformation_describe_stacks_res["NextToken"]
        else:
            is_next_token = False

    cdk_stack_log_group_names: dict[str, list[str]] = {}
    for cdk_stack_name, cdk_stack_id in cdk_stack_name_ids:
        is_next_token = True
        next_token = None
        while is_next_token:
            try:
                cloudformation_list_stack_resources_res = cloudformation.list_stack_resources(
                    StackName=cdk_stack_id,
                    **{
                        k: v
                        for k, v in {
                            "NextToken": next_token if next_token else None,
                        }.items()
                        if v
                    },
                )
                logger.info(f"## CloudFormation List Stack Resources successful response: '{cdk_stack_name}'")
            except ClientError as ex:
                logger.error(f"## CloudFormation List Stack Resources ERROR: '{ex}'")
                cf.write_to_json_paths(res, base_steps_client_names)
                sys.exit(1)
            if log_groups_names := get_log_groups_names(cloudformation_list_stack_resources_res):
                cdk_stack_log_group_names[cdk_stack_name] = (
                    (names + log_groups_names)
                    if (names := cdk_stack_log_group_names.get(cdk_stack_name))
                    else log_groups_names
                )
            if "NextToken" in cloudformation_list_stack_resources_res:
                next_token = cloudformation_list_stack_resources_res["NextToken"]
            else:
                is_next_token = False

    cw_log_group_names: set[str] = set()
    is_next_token = True
    next_token = None
    iter_: int = 0
    while is_next_token:
        iter_ += 1
        try:
            logs_describe_log_groups_res = clients[aws.logs_str].describe_log_groups(
                limit=50,  # Max: 50
                **{
                    k: v
                    for k, v in {
                        "nextToken": next_token if next_token else None,
                    }.items()
                    if v
                },
            )
            logger.info(f"## CloudWatch Logs List Stack Resources successful response ({iter_})")
        except ClientError as ex:
            logger.error(f"## CloudWatch Logs List Stack Resources ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        cw_log_group_names = cw_log_group_names.union(
            {i["logGroupName"] for i in logs_describe_log_groups_res["logGroups"] if i["storedBytes"] == 0}
        )
        if "nextToken" in logs_describe_log_groups_res:
            next_token = logs_describe_log_groups_res["nextToken"]
        else:
            is_next_token = False

    cw_log_group_names_untracked: set[str] = set(cw_log_group_names)
    for cdk_stack_name, log_group_names in cdk_stack_log_group_names.items():
        for log_group_name in log_group_names:
            if log_group_name in cw_log_group_names:
                cw_log_group_names_untracked.remove(log_group_name)

    if cw_log_group_names_untracked:
        cw_log_group_names_untracked_list: list[str] = sorted(cw_log_group_names_untracked)
        res[aws.logs_str]["delete_log_group"] = {}
        with open(filename_txt, "w+", encoding="utf-8") as f:
            for i in cw_log_group_names_untracked_list:
                to_delete = False
                if i.startswith(log_group_name_prefix_lambda_func):
                    lambda_func_name = i[len(log_group_name_prefix_lambda_func) :]
                    try:
                        lambda_.get_function(FunctionName=lambda_func_name)
                        logger.info(f"## Lambda Get Function successful response: '{lambda_func_name}'")
                    except lambda_.exceptions.ResourceNotFoundException:
                        to_delete = True
                    except ClientError as ex:
                        logger.error(f"## Lambda Get Function ERROR: '{ex}'")
                elif i.startswith(log_group_name_prefix_ecs_cluster):
                    ecs_cluster_name = i[len(log_group_name_prefix_ecs_cluster) :].rsplit(sep=sep, maxsplit=1)[0]
                    try:
                        ecs_describe_clusters_res = ecs.describe_clusters(clusters=[ecs_cluster_name])
                        logger.info(f"## ECS Describe Clusters successful response: '{ecs_cluster_name}'")
                        if (
                            (failures := ecs_describe_clusters_res["failures"]) and failures[0]["reason"] == "MISSING"
                        ) or (
                            (clusters := ecs_describe_clusters_res["clusters"]) and clusters[0]["status"] == "INACTIVE"
                        ):
                            to_delete = True
                    except ClientError as ex:
                        logger.error(f"## ECS Describe Clusters ERROR: '{ex}'")
                elif i.startswith(log_group_name_prefix_rds_instance):
                    rds_instance_name = i[len(log_group_name_prefix_rds_instance) :].rsplit(sep=sep, maxsplit=1)[0]
                    try:
                        rds.describe_db_instances(DBInstanceIdentifier=rds_instance_name)
                        logger.info(f"## RDS Describe DB Instances successful response: '{rds_instance_name}'")
                    except rds.exceptions.DBInstanceNotFoundFault:
                        to_delete = True
                    except ClientError as ex:
                        logger.error(f"## RDS Describe DB Instances ERROR: '{ex}'")
                if to_delete:
                    try:
                        res[aws.logs_str]["delete_log_group"][i] = clients[aws.logs_str].delete_log_group(
                            logGroupName=i
                        )
                        logger.info(f"## CloudWatch Logs Delete Log Group successful response: '{i}'")
                    except ClientError as ex:
                        logger.error(f"## CloudWatch Logs Delete Log Group ERROR: '{ex}'")
                        cf.write_to_json_paths(res, base_steps_client_names)
                        sys.exit(1)
                else:
                    logger.info(f"## Skipping deletion of CloudWatch Logs log group: '{i}'")
                    f.write(f"{i}\n")
    else:
        logger.info("## No AWS CloudWatch Logs log groups to clean-up.")

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=f"Clean-up AWS CloudWatch Logs log groups which are not "
        f"provisioned by an AWS CDK stack and do not have a "
        f"corresponding AWS resource sending logs: "
        f"Lambda function, ECS cluster, RDS instance, etc. "
        f"(see the list of skipped AWS CloudWatch Logs log groups in: '{filename_txt}')."
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    args = parser.parse_args()
    main(region=args.region)

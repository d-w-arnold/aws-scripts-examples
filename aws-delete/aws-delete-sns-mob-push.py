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

base_steps_client_names: list[str] = [aws.sns_str, aws.ssm_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)


def check_platform_application_exists(sns, sns_platform_application_name: str) -> str:
    logger.info(
        f"## Checking whether there is already an SNS platform application "
        f"of the name: '{sns_platform_application_name}'"
    )
    for arn in [i["PlatformApplicationArn"] for i in sns_list_platform_applications(sns)]:
        if (name := arn.rsplit(sep="/", maxsplit=1)[-1]) and name == sns_platform_application_name:
            return arn
    return None


def sns_list_platform_applications(sns) -> list[dict]:
    logger.info("## List all SNS platform applications")
    is_next_token: bool = True
    next_token: str = None
    sns_list_platform_applications_res_platform_applications: list = []
    while is_next_token:
        try:
            sns_list_platform_applications_res = sns.list_platform_applications(
                **{
                    k: v
                    for k, v in {
                        "NextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## SNS List Platform Applications successful response")
        except ClientError as ex:
            logger.error(f"## SNS List Platform Applications ERROR: '{ex}'")
            sys.exit(1)
        if "NextToken" in sns_list_platform_applications_res:
            next_token = sns_list_platform_applications_res["NextToken"]
        else:
            is_next_token = False
        sns_list_platform_applications_res_platform_applications += sns_list_platform_applications_res[
            "PlatformApplications"
        ]
    return sns_list_platform_applications_res_platform_applications


def main(
    region: str,
    repo: str = None,
    deploy_env: str = None,
):
    cf.info_log_starting()

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    sns_platform_application_name: str = f"{repo}-{deploy_env}"

    if sns_platform_application_arn := check_platform_application_exists(
        clients[aws.sns_str], sns_platform_application_name
    ):
        logger.info(
            f"## SNS platform application ARN: '{sns_platform_application_arn}' (for SNS platform application: '{sns_platform_application_name}')"
        )
    else:
        logger.error(
            f"## ERROR: SNS platform application '{sns_platform_application_name}' doesn't exist! (in the '{region}' "
            f"['{cf.region_timezones_meta[region]}'] region)"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    sns_mob_push: str = "sns-mob-push"

    logger.info("## Deleting the SNS platform application")
    sns_delete_platform_application_str: str = "sns_delete_platform_application"
    try:
        res[aws.sns_str][sns_delete_platform_application_str] = clients[aws.sns_str].delete_platform_application(
            PlatformApplicationArn=sns_platform_application_arn,
        )
        logger.info("## SNS Delete Platform Application successful response")
    except ClientError as ex:
        logger.error(
            f"## SNS Delete Platform Application ERROR: '{ex}', in trying to delete "
            f"an SNS platform application: '{sns_platform_application_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    param_name: str = f"/{sns_mob_push}/{repo}/{deploy_env}"
    logger.info(f"## Deleting the AWS Systems Manager Parameter Store parameter: {param_name})")
    try:
        res[aws.ssm_str]["ssm_delete_parameter"] = clients[aws.ssm_str].delete_parameter(Name=param_name)
        logger.info("## SSM Delete Parameter successful response")
    except ClientError as ex:
        logger.error(f"## SSM Delete Parameter ERROR: '{ex}'")
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Delete an existing SNS platform application.")
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    parser.add_argument("--repo", help="Get the git repo name.", type=str)
    parser.add_argument(
        "--deploy_env",
        help="Specify whether to get the git repo branch name, for a given deployment environment.",
        type=str,
    )
    args = parser.parse_args()
    main(
        region=args.region,
        repo=args.repo,
        deploy_env=args.deploy_env,
    )

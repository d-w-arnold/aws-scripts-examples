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

base_steps_client_names: list[str] = [aws.cloudformation_str, aws.sns_str, aws.ssm_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)


def check_platform_application_exists(sns, sns_platform_application_name: str) -> bool:
    logger.info(
        f"## Checking whether there is already an SNS platform application "
        f"of the name: '{sns_platform_application_name}'"
    )
    for name in [
        i["PlatformApplicationArn"].rsplit(sep="/", maxsplit=1)[-1] for i in sns_list_platform_applications(sns)
    ]:
        if name == sns_platform_application_name:
            return True
    return False


def get_cdk_stack_outputs_and_tags(
    cloudformation, cloudformation_res: dict[str, dict], repo: str, deploy_env: str, sns_mob_push: str
) -> tuple[str, str, list[dict[str, str]]]:
    custom_project_name: str = repo.rsplit(sep="-", maxsplit=1)[0]
    custom_project_name = (
        "".join([i.capitalize() for i in custom_project_name.split(sep="-", maxsplit=1)])
        if "-" in custom_project_name
        else custom_project_name.capitalize()
    )
    if "-" in deploy_env:
        deploy_env_props: list[str] = deploy_env.rsplit(sep="-", maxsplit=1)
        if deploy_env_props[1] in {"demo", "preview"}:
            deploy_env = (
                f"{deploy_env_props[0]}{deploy_env_props[1][0]}"
                if deploy_env_props[0] == "sih"
                else deploy_env_props[0]
            )
    cdk_stack_comp: str = "notif"
    cdk_stack: str = f"Cdk{custom_project_name}{cdk_stack_comp.capitalize()}{deploy_env.capitalize()}Stack"

    logger.info(
        f"## Retrieving SNS topic ARN & IAM role ARN from the '{cdk_stack}' (AWS CDK) stack CloudFormation output"
    )

    cloudformation_describe_stacks_str: str = "cloudformation_describe_stacks"
    try:
        cloudformation_res[cloudformation_describe_stacks_str] = cloudformation.describe_stacks(StackName=cdk_stack)
        logger.info("## CloudFormation Describe Stacks successful response")
    except ClientError as ex:
        logger.error(
            f"## CloudFormation Describe Stacks ERROR: '{ex}', in trying to retrieve outputs "
            f"from the '{cdk_stack}' (AWS CDK) stack CloudFormation output (for repo: '{repo}')"
        )
        return None, None, None

    cdk_stack_meta: list[dict[str, str]] = cloudformation_res[cloudformation_describe_stacks_str]["Stacks"][0]
    cdk_stack_name_outputs: list[dict[str, str]] = cdk_stack_meta["Outputs"]
    all_outputs_found: bool = False
    sns_topic_arn: str = None
    iam_role_arn: str = None
    cdk_stack_output_prefix: str = (
        f"{cdk_stack[: -(len('Stack'))].lower().capitalize()}{sns_mob_push.replace('-', '')}".replace(
            cdk_stack_comp, "gw", 1
        )
    )
    for i in cdk_stack_name_outputs:
        if i["OutputKey"].startswith(f"{cdk_stack_output_prefix}topic"):
            sns_topic_arn = i["OutputValue"]
        elif i["OutputKey"].startswith(f"{cdk_stack_output_prefix}role"):
            iam_role_arn = i["OutputValue"]
        if all(i is not None for i in [sns_topic_arn, iam_role_arn]):
            all_outputs_found = True
            break
    if not all_outputs_found:
        logger.error(
            f"## CloudFormation Describe Stacks outputs: {cdk_stack_name_outputs} "
            f"(for '{cdk_stack}' (AWS CDK) stack)"
        )
        logger.error(
            f"## ERROR: Could not retrieve SNS topic ARN & IAM role ARN (from the '{cdk_stack}' (AWS CDK) stack "
            f"CloudFormation output)"
        )
        return None, None, None

    return sns_topic_arn, iam_role_arn, cdk_stack_meta["Tags"]


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

    secretsmanager = cf.get_client(region, aws.secretsmanager_str)

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    sns_platform_application_name: str = f"{repo}-{deploy_env}"

    if check_platform_application_exists(clients[aws.sns_str], sns_platform_application_name):
        logger.error(
            f"## ERROR: SNS platform application '{sns_platform_application_name}' already exists! (in the '{region}' "
            f"['{cf.region_timezones_meta[region]}'] region)"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    firebase_account_info_str: str = "FIREBASE_ACCOUNT_INFO"

    parameter_name: str = f"/{repo}/ecs-container-env/{firebase_account_info_str}"
    logger.info(f"## Loading the Firebase account info from SSM: '{parameter_name}'")
    try:
        res[aws.ssm_str]["ssm_get_parameter"] = clients[aws.ssm_str].get_parameter(
            Name=parameter_name, WithDecryption=True
        )
        logger.info("## SSM Get Parameter successful response")
    except ClientError as ex:
        logger.error(f"## SSM Get Parameter ERROR: '{ex}'")
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    firebase_account_info: dict = json.loads(res[aws.ssm_str]["ssm_get_parameter"]["Parameter"]["Value"])

    secret_name: str = f"{repo}/ecs-container-secret"
    logger.info(f"## Loading the Firebase account info (private key) from AWS Secrets Manager: '{secret_name}'")
    try:
        secretsmanager_get_secret_value_res = secretsmanager.get_secret_value(SecretId=secret_name)
        logger.info("## Secrets Manager Get Secret Value successful response")
    except ClientError as ex:
        logger.error(f"## Secrets Manager Get Secret Value ERROR: '{ex}'")
        sys.exit(1)

    firebase_account_info["private_key"] = (
        json.loads(secretsmanager_get_secret_value_res["SecretString"])[f"{firebase_account_info_str}_PRIVATE_KEY"]
        .encode()
        .decode("unicode_escape")
    )

    sns_mob_push: str = "sns-mob-push"
    sns_topic_arn, iam_role_arn, cdk_stack_tags = get_cdk_stack_outputs_and_tags(
        clients[aws.cloudformation_str], res[aws.cloudformation_str], repo, deploy_env, sns_mob_push
    )

    logger.info("## Creating the SNS platform application")
    sns_create_platform_application_str: str = "sns_create_platform_application"
    try:
        res[aws.sns_str][sns_create_platform_application_str] = clients[aws.sns_str].create_platform_application(
            Name=sns_platform_application_name,
            Platform="GCM",  # Firebase Cloud Messaging (FCM)
            Attributes={
                "PlatformCredential": json.dumps(firebase_account_info),
                "SuccessFeedbackSampleRate": "100",
                **{
                    **{
                        i: sns_topic_arn
                        for i in [
                            "EventEndpointCreated",
                            "EventEndpointDeleted",
                            "EventEndpointUpdated",
                            "EventDeliveryFailure",
                        ]
                    },
                    **{i: iam_role_arn for i in ["SuccessFeedbackRoleArn", "FailureFeedbackRoleArn"]},
                },
            },
        )
        logger.info("## SNS Create Platform Application successful response")
    except ClientError as ex:
        logger.error(
            f"## SNS Create Platform Application ERROR: '{ex}', in trying to create "
            f"an SNS platform application: '{sns_platform_application_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    sns_platform_application_arn: str = res[aws.sns_str][sns_create_platform_application_str]["PlatformApplicationArn"]

    param_name: str = f"/{sns_mob_push}/{repo}/{deploy_env}"
    logger.info(
        f"## Write the ARN of the newly created SNS platform application: '{sns_platform_application_arn}' "
        f"(to AWS Systems Manager Parameter Store: {param_name})"
    )
    try:
        res[aws.ssm_str]["ssm_put_parameter"] = clients[aws.ssm_str].put_parameter(
            Name=param_name,
            # Description,  # Default to the existing description
            Value=sns_platform_application_arn,
            Type="String",
            # Overwrite=True,  # tags and overwrite can't be used together.
            # TODO: (OPTIONAL) A regular expression used to validate the parameter value.
            # AllowedPattern=,
            Tags=cdk_stack_tags,
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

    parser = argparse.ArgumentParser(description="Create a new SNS platform application.")
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

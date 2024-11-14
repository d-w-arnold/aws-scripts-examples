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

base_steps_client_names: list[str] = [
    aws.amplify_str,
    aws.cloudwatch_str,
    aws.events_str,
    aws.secretsmanager_str,
    aws.sns_str,
]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)


def base_steps(
    region: str,
    repo: str,
    deploy_env: str,
) -> None:
    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    amplify_app_name: str = f"{repo}-{deploy_env}"

    if not cf.check_amplify_app_exists(clients[aws.amplify_str], amplify_app_name):
        logger.error(
            f"## ERROR: AWS Amplify app '{amplify_app_name}' doesn't exist! (in the '{region}' "
            f"['{cf.region_timezones_meta[region]}'] region)"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    amplify_app_id = cf.get_amplify_app_id(clients[aws.amplify_str], amplify_app_name)

    logger.info("## Deleting the AWS Amplify app")
    try:
        res[aws.amplify_str]["amplify_delete_app"] = clients[aws.amplify_str].delete_app(appId=amplify_app_id)
        logger.info("## Amplify Delete App successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Delete App ERROR: '{ex}', in trying to delete an AWS Amplify app: '{amplify_app_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    secret_name: str = f"{amplify_app_name}/basic-auth-creds"
    logger.info(f"## Clearing up Basic Auth credentials, stored in AWS Secrets Manager secret: '{secret_name}'")
    try:
        res[aws.secretsmanager_str]["secretsmanager_describe_secret"] = clients[aws.secretsmanager_str].describe_secret(
            SecretId=secret_name
        )
        logger.info("## Secrets Manager Describe Secret successful response")
        try:
            res[aws.secretsmanager_str]["secretsmanager_delete_secret"] = clients[aws.secretsmanager_str].delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True,  # If true, deletes the secret without any 7-30 day recovery window
            )
            logger.info("## Secrets Manager Delete Secret successful response")
        except ClientError as ex:
            logger.error(f"## Secrets Manager Delete Secret ERROR: '{ex}', in trying to delete Basic Auth credentials")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
    except ClientError as ex:
        if ex.response["Error"]["Code"] != "ResourceNotFoundException":
            logger.error(
                f"## Secrets Manager Describe Secret ERROR: '{ex}', "
                f"in trying to check if Basic Auth credentials exist"
            )
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        logger.info("## No Basic Auth credentials found ...")

    sns_list_topics_res_topics: list[dict] = cf.sns_list_topics(clients[aws.sns_str])

    logger.info(f"## Get the SNS topic ARN (for the AWS Amplify app ID: '{amplify_app_id}')")
    topic_arn: str = None
    for i in sns_list_topics_res_topics:
        if amplify_app_id in i["TopicArn"]:
            topic_arn = i["TopicArn"]
            break
    if topic_arn is None:
        logger.info("## No SNS topic found ...")
    else:
        logger.info(
            f"## Clearing up the AWS Amplify app '{amplify_app_name}' SNS topic "
            f"(and all its subscriptions): {topic_arn}"
        )
        sns_list_subs_by_topic: str = "sns_list_subscriptions_by_topic"
        subs_key: str = "Subscriptions"
        try:
            res[aws.sns_str][sns_list_subs_by_topic] = clients[aws.sns_str].list_subscriptions_by_topic(
                TopicArn=topic_arn
            )
            logger.info("## SNS List Subscriptions By Topic successful response")
        except ClientError as ex:
            logger.warning(f"## Could NOT list all the subscriptions associated with the SNS topic: {ex}")
        if sns_list_subs_by_topic in res[aws.sns_str] and subs_key in res[aws.sns_str][sns_list_subs_by_topic]:
            logger.info(f"## Clearing up all subscriptions of the SNS topic: {topic_arn}")
            unsubscribe_success: list = []
            unsubscribe_fail: list = []
            for sub in res[aws.sns_str][sns_list_subs_by_topic][subs_key]:
                sub_arn: str = sub["SubscriptionArn"]
                try:
                    sns_unsubscribe_res = clients[aws.sns_str].unsubscribe(SubscriptionArn=sub_arn)
                    logger.info(f"## SNS Unsubscribe successful response: {sub_arn}")
                    unsubscribe_success.append(sns_unsubscribe_res)
                except ClientError as ex:
                    logger.warning(f"## Could NOT unsubscribe from the SNS topic: {sub_arn}")
                    unsubscribe_fail.append(ex)
            if unsubscribe_success:
                res[aws.sns_str]["sns_unsubscribe_success"] = unsubscribe_success
            if unsubscribe_fail:
                res[aws.sns_str]["sns_unsubscribe_fail"] = unsubscribe_fail
        else:
            logger.info(f"## No subscriptions found for the SNS topic: {topic_arn}")
        try:
            res[aws.sns_str]["sns_delete_topic"] = clients[aws.sns_str].delete_topic(TopicArn=topic_arn)
            logger.info("## SNS Delete Topic successful response")
        except ClientError as ex:
            logger.error(f"## SNS Delete Topic ERROR: '{ex}', in trying to delete the SNS topic")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)

    logger.info(f"## Clearing up CloudWatch alarms (for AWS Amplify app: '{amplify_app_name}')")
    is_next_token: bool = True
    next_token: str = None
    cloudwatch_describe_alarms_responses: list = []
    while is_next_token:
        try:
            cloudwatch_describe_alarms_res = clients[aws.cloudwatch_str].describe_alarms(
                **{
                    k: v
                    for k, v in {
                        "NextToken": next_token if next_token else None,
                        "MaxRecords": 100,  # Max 100. Default: 50
                    }.items()
                    if v
                }
            )
            logger.info("## CloudWatch Describe Alarms successful response")
        except ClientError as ex:
            logger.error(
                f"## CloudWatch Describe Alarms ERROR: '{ex}', in trying to delete CloudWatch alarms "
                f"(for AWS Amplify app: '{amplify_app_name}')"
            )
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        cloudwatch_describe_alarms_responses.append(cloudwatch_describe_alarms_res)
        if "NextToken" in cloudwatch_describe_alarms_res:
            next_token = cloudwatch_describe_alarms_res["NextToken"]
        else:
            is_next_token = False
    res[aws.cloudwatch_str]["cloudwatch_describe_alarms"] = cloudwatch_describe_alarms_responses
    cloudwatch_alarms_to_be_deleted: list = []
    for i in cloudwatch_describe_alarms_responses:
        cloudwatch_alarms_to_be_deleted += [
            j["AlarmName"] for j in i["MetricAlarms"] if amplify_app_name in j["AlarmName"]
        ]
    if cloudwatch_alarms_to_be_deleted:
        try:
            cloudwatch_delete_alarms_res = clients[aws.cloudwatch_str].delete_alarms(
                AlarmNames=cloudwatch_alarms_to_be_deleted,  # Max 100
            )
            logger.info("## CloudWatch Delete Alarms successful response")
        except ClientError as ex:
            logger.error(
                f"## CloudWatch Delete Alarms ERROR: '{ex}', in trying to delete CloudWatch alarms "
                f"(for AWS Amplify app: '{amplify_app_name}')"
            )
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        res[aws.cloudwatch_str]["cloudwatch_delete_alarms"] = {
            "cloudwatch_alarms_to_be_deleted": cloudwatch_alarms_to_be_deleted,
            "cloudwatch_delete_alarms_res": cloudwatch_delete_alarms_res,
        }

    is_next_token = True
    next_token = None
    events_list_rules_res_rules: list = []
    while is_next_token:
        try:
            events_list_rules_res = clients[aws.events_str].list_rules(
                **{
                    k: v
                    for k, v in {
                        "NamePrefix": "amplify-",
                        "NextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## EventBridge List Rules successful response")
        except ClientError as ex:
            logger.error(f"## EventBridge List Rules ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        if "NextToken" in events_list_rules_res:
            next_token = events_list_rules_res["NextToken"]
        else:
            is_next_token = False
        events_list_rules_res_rules += events_list_rules_res["Rules"]

    logger.info(
        f"## Clearing up the EventBridge rule, and all it's targets (for AWS Amplify app: '{amplify_app_name}')"
    )
    is_events_managed_rule: bool = True
    if (events_rule_names := [i["Name"] for i in events_list_rules_res_rules if amplify_app_id in i["Name"]]) and (
        events_rule_name := events_rule_names[0]
    ):
        try:
            res[aws.events_str]["events_list_targets_by_rule"] = clients[aws.events_str].list_targets_by_rule(
                Rule=events_rule_name,
                # EventBusName=,  # The default event bus is used.
            )
            logger.info("## EventBridge List Targets By Rule successful response")
        except ClientError as ex:
            logger.error(f"## EventBridge List Targets By Rule ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        try:
            res[aws.events_str]["events_remove_targets"] = clients[aws.events_str].remove_targets(
                Rule=events_rule_name,
                # EventBusName=,  # The default event bus is used.
                Ids=[i["Id"] for i in res[aws.events_str]["events_list_targets_by_rule"]["Targets"]],
                Force=is_events_managed_rule,  # This parameter is ignored for rules that are not AWS managed rules.
            )
            logger.info("## EventBridge Remove Targets successful response")
        except ClientError as ex:
            logger.error(f"## EventBridge Remove Targets ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        try:
            res[aws.events_str]["events_delete_rule"] = clients[aws.events_str].delete_rule(
                Name=events_rule_name,
                # EventBusName=,  # The default event bus is used.
                Force=is_events_managed_rule,  # This parameter is ignored for rules that are not AWS managed rules.
            )
            logger.info("## EventBridge Delete Rule successful response")
        except ClientError as ex:
            logger.error(f"## EventBridge Delete Rule ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
    else:
        logger.info("## No EventBridge rule found ...")

    cf.write_to_json_paths(res, base_steps_client_names)


def main(
    region: str,
    repo: str = None,
    deploy_env: str = None,
):
    cf.info_log_starting()
    base_steps(region, repo, deploy_env)
    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Delete an existing AWS Amplify app.")
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

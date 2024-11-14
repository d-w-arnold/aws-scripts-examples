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

base_steps_client_names: list[str] = [aws.cloudwatch_str, aws.events_str, aws.sns_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)


def main(region: str):
    cf.info_log_starting()

    amplify = cf.get_client(region, aws.amplify_str)

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

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
            logger.error(f"## CloudWatch Describe Alarms ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        cloudwatch_describe_alarms_responses.append(cloudwatch_describe_alarms_res)
        if "NextToken" in cloudwatch_describe_alarms_res:
            next_token = cloudwatch_describe_alarms_res["NextToken"]
        else:
            is_next_token = False
    res[aws.cloudwatch_str]["cloudwatch_describe_alarms"] = cloudwatch_describe_alarms_responses

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

    events_topics_map = {i["Name"].split(sep="-", maxsplit=2)[1]: i["Arn"] for i in events_list_rules_res_rules}

    sns_list_topics_res_topics: list[dict] = cf.sns_list_topics(clients[aws.sns_str])

    sns_list_topics_res_topics = [
        i for i in sns_list_topics_res_topics if i["TopicArn"].endswith("AMPLIBRANCHSENTINEL")
    ]

    sns_topics_map = {
        i["TopicArn"].rsplit(sep="_", maxsplit=1)[0].rsplit(sep="-", maxsplit=1)[-1]: i["TopicArn"]
        for i in sns_list_topics_res_topics
    }

    res[aws.cloudwatch_str]["cloudwatch_tag_resource"] = {}
    res[aws.events_str]["events_tag_resource"] = {}
    res[aws.sns_str]["sns_tag_resource"] = {}

    for amplify_app in cf.amplify_list_apps(amplify):
        amplify_app_id: str = amplify_app["appId"]
        amplify_app_name: str = amplify_app["name"]
        amplify_app_tags: dict[str, str] = amplify_app["tags"]
        if not amplify_app_tags:
            logger.info(f"## No tags for AWS Amplify app: '{amplify_app_name}'")
            continue
        amplify_app_tags_formatted: list[dict[str, str]] = [{"Key": k, "Value": v} for k, v in amplify_app_tags.items()]

        logger.info(f"## Found tags for AWS Amplify app: '{amplify_app_name}' - '{amplify_app_tags}'")

        logger.info("## Adding AWS Amplify app tags to CloudWatch alarm")
        cloudwatch_alarms_to_tag: list = []
        for cloudwatch_alarm_arn in cloudwatch_describe_alarms_responses:
            cloudwatch_alarms_to_tag += [
                j["AlarmArn"] for j in cloudwatch_alarm_arn["MetricAlarms"] if amplify_app_name in j["AlarmArn"]
            ]
        if cloudwatch_alarms_to_tag:
            for cloudwatch_alarm_arn in cloudwatch_alarms_to_tag:
                try:
                    res[aws.cloudwatch_str]["cloudwatch_tag_resource"][amplify_app_name] = clients[
                        aws.cloudwatch_str
                    ].tag_resource(
                        ResourceARN=cloudwatch_alarm_arn,
                        Tags=amplify_app_tags_formatted,
                    )
                    logger.info("## CloudWatch Tag Resource successful response")
                except ClientError as ex:
                    logger.error(f"## CloudWatch Tag Resource ERROR: '{ex}'")
                    cf.write_to_json_paths(res, base_steps_client_names)
                    sys.exit(1)

        logger.info("## Adding AWS Amplify app tags to EventBridge rule")
        try:
            res[aws.events_str]["events_tag_resource"][amplify_app_name] = clients[aws.events_str].tag_resource(
                ResourceARN=events_topics_map[amplify_app_id],
                Tags=amplify_app_tags_formatted,
            )
            logger.info("## EventBridge Tag Resource successful response")
        except ClientError as ex:
            logger.error(f"## EventBridge Tag Resource ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)

        logger.info("## Adding AWS Amplify app tags to SNS topic")
        try:
            res[aws.sns_str]["sns_tag_resource"][amplify_app_name] = clients[aws.sns_str].tag_resource(
                ResourceArn=sns_topics_map[amplify_app_id],
                Tags=amplify_app_tags_formatted,
            )
            logger.info("## SNS Tag Resource successful response")
        except ClientError as ex:
            logger.error(f"## SNS Tag Resource ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tag all AWS Amplify app additional resources.")
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    args = parser.parse_args()
    main(region=args.region)

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

base_steps_client_names: list[str] = []

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

filename_txt: str = f"{cf.filename.rsplit(sep='.', maxsplit=1)[0]}-list.txt"


def main(region: str):
    cf.info_log_starting()

    sns = cf.get_client(region, aws.sns_str)

    is_next_token: bool = True
    next_token: str = None
    sns_topic_arns: list[str] = []
    while is_next_token:
        try:
            sns_list_topics_res = sns.list_topics(
                **{
                    k: v
                    for k, v in {
                        "NextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## SNS List Topics successful response")
        except ClientError as ex:
            logger.error(f"## SNS List Topics ERROR: '{ex}'")
            sys.exit(1)
        sns_topic_arns += [i["TopicArn"] for i in sns_list_topics_res["Topics"]]
        if "NextToken" in sns_list_topics_res:
            next_token = sns_list_topics_res["NextToken"]
        else:
            is_next_token = False

    sns_topics_with_no_subs: set[str] = set()

    for sns_topic_arn in sns_topic_arns:
        try:
            sns_list_subscriptions_by_topic_res = sns.list_subscriptions_by_topic(TopicArn=sns_topic_arn)
            logger.info(f"## SNS List Subscriptions By Topic successful response: '{sns_topic_arn}'")
        except ClientError as ex:
            logger.error(f"## SNS List Subscriptions By Topic ERROR: '{ex}'")
            sys.exit(1)
        if not sns_list_subscriptions_by_topic_res.get("Subscriptions"):
            sns_topics_with_no_subs.add(sns_topic_arn)

    with open(filename_txt, "w+", encoding="utf-8") as f:
        for i in sorted(sns_topics_with_no_subs):
            f.write(f"{i}\n")

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=f"Query for the list of AWS SNS topics, "
        f"which have no subscriptions (see results in: '{filename_txt}')."
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    args = parser.parse_args()
    main(region=args.region)

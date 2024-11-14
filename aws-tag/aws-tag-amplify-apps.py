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

base_steps_client_names: list[str] = [aws.amplify_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

amplify_list_apps_file: str = "amplify-list-apps.json"
# NB. To generate this file, run the following AWS CLI command (in the cwd):
#  `aws amplify list-apps --query 'apps[].{appArn:appArn,name:name,tags:tags}' > amplify-list-apps.json`
# NB. To get AWS Amplify apps starting with `<str>`, use query:
#  `... 'apps[?starts_with(name, `<str>`) == `true`].{appArn:appArn,name:name,tags:tags}' ...`


def main(region: str):
    cf.info_log_starting()

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    with open(amplify_list_apps_file, "r", encoding="utf-8") as f:
        amplify_list_apps: dict = json.load(f)

    res[aws.amplify_str]["tag_resource"] = {}
    for i in amplify_list_apps:
        try:
            res[aws.amplify_str]["tag_resource"][i["name"]] = clients[aws.amplify_str].tag_resource(
                resourceArn=i["appArn"], tags=i["tags"]
            )
            logger.info("## Amplify Tag Resource successful response")
        except ClientError as ex:
            logger.error(f"## Amplify Tag Resource ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=f"Tag all AWS Amplify apps, specified in local config file: '{amplify_list_apps_file}'"
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    args = parser.parse_args()
    main(region=args.region)

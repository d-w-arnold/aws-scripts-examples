import json
import logging
import os
import sys

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

base_steps_client_names: list[str] = [aws.lambda_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

bitbucket_account_name: str = "foobar"


def main(
    region: str,
    function_name: str,
    payload_db_schemas: str,
    payload_sql_filename: str,
    payload_project_name: str = None,
    payload_action: str = None,
):
    cf.info_log_starting()

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    invoke_args: dict = {
        "FunctionName": function_name,
        "InvocationType": "RequestResponse",
        "Payload": bytes(
            json.dumps(
                {
                    k: v
                    for k, v in {
                        "PROJECT_NAME": payload_project_name if payload_project_name else None,
                        "ACTION": payload_action if payload_action else "INCREMENT",
                        "DB_SCHEMAS": payload_db_schemas,
                        "SQL_FILENAME": payload_sql_filename,
                    }.items()
                    if v
                }
            ),
            encoding="utf-8",
        ),
    }

    lambda_invoke_res: dict = clients[aws.lambda_str].invoke(**invoke_args)
    res[aws.lambda_str]["lambda_invoke"] = lambda_invoke_res

    if "Payload" in lambda_invoke_res:
        lambda_res_payload = lambda_invoke_res["Payload"].read()
        if isinstance(lambda_res_payload, bytes):
            lambda_res_payload = lambda_res_payload.decode(encoding="utf-8")
        lambda_invoke_res["Payload"] = lambda_res_payload

    if lambda_invoke_res["StatusCode"] == 200:
        logger.info(f"## Lambda Invoke response payload: {lambda_invoke_res['Payload']}")
    else:
        logger.error(f"## Lambda Invoke ERROR: {lambda_invoke_res}")

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Invoke an RDS init Lambda function for a specific DB server, for use in the 'rds-init.sh' script."
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
    )
    parser.add_argument(
        "--function_name",
        required=True,
        help="Specify the Lambda function name.",
    )
    parser.add_argument(
        "--payload_project_name",
        help="Specify an optional git repo name to be used as an alternative to the default project name.",
        nargs="?",
        type=str,
    )
    parser.add_argument(
        "--payload_action",
        help="Specify the action type (valid options: 'INCREMENT', 'RESET') for modifying each DB schema, passed in via Lambda function payload event.",
        type=str,
    )
    parser.add_argument(
        "--payload_db_schemas",
        required=True,
        help="Specify the DB schemas to be modified, passed in via Lambda function payload event.",
    )
    parser.add_argument(
        "--payload_sql_filename",
        required=True,
        help="Specify the SQL filename used to modify each DB schema, passed in via Lambda function payload event.",
    )
    args = parser.parse_args()
    main(
        region=args.region,
        function_name=args.function_name,
        payload_db_schemas=args.payload_db_schemas,
        payload_sql_filename=args.payload_sql_filename,
        payload_project_name=args.payload_project_name,
        payload_action=args.payload_action,
    )

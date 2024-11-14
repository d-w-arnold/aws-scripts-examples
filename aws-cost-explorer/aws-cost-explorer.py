import csv
import logging
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

base_steps_client_names: list[str] = [aws.ce_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

default_months: int = 6

encoding: str = "utf-8"
file_extension: str = ".csv"
results_str: str = "results"
results_path: str = os.path.join(os.getcwd(), results_str)
sep: str = "_"

amount_str: str = "Amount"
cost_str: str = "UnblendedCost"
end_str: str = "End"
get_cost_and_usage_str: str = "get_cost_and_usage"
metric_str: str = "Metrics"
next_page_token_str: str = "NextPageToken"
start_str: str = "Start"
time_period_str: str = "TimePeriod"
unit_str: str = "Unit"

# AWS Tags
tag_project_name: str = "project-name"
tag_env_type: str = "env-type"


def ce_get_tags(ce, time_period_meta: dict[str, str], tag_key: str) -> dict:
    try:
        ce_get_tags_res = ce.get_tags(
            TimePeriod=time_period_meta,
            TagKey=tag_key,
        )
        logger.info(f"## Cost Explorer Get Tags successful response (for AWS tag: '{tag_key}')")
        return ce_get_tags_res["Tags"]
    except ClientError as ex:
        logger.error(f"## Cost Explorer Get Tags ERROR (for AWS tag: '{tag_key}'): '{ex}'")
    return None


def sanitise(str_: str) -> str:
    return str_ if str_ else "NoTag"


def time_period_to_tuple(time_period: dict[str, str]) -> tuple[str, str]:
    return time_period[start_str], time_period[end_str]


def to_strftime(obj: date) -> str:
    return obj.strftime("%Y-%m-%d")


def main(region: str, months: int):
    cf.info_log_starting()

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    if months is None:
        months = default_months

    first_day_this_month: date = date.today().replace(day=1)
    start_time_to_strftime: str = to_strftime(first_day_this_month + relativedelta(months=-(int(months))))
    end_time_to_strftime: str = to_strftime(first_day_this_month - timedelta(days=1))
    time_period_meta: dict[str, str] = {start_str: start_time_to_strftime, end_str: end_time_to_strftime}

    tags_meta: dict[str, list[str]] = {
        tag_key: ce_get_tags(clients[aws.ce_str], time_period_meta, tag_key)
        for tag_key in [tag_project_name, tag_env_type]
    }
    logger.info(f"## Tags meta: \n{tags_meta}")

    Path(results_path).mkdir(exist_ok=True)

    filename_no_ext: str = cf.filename.rsplit(sep=".", maxsplit=1)[0]

    results_timestamp_path: str = os.path.join(
        results_path, sep.join([datetime.today().strftime("%Y%m%d"), filename_no_ext])
    )
    if os.path.exists(results_timestamp_path):
        shutil.rmtree(results_timestamp_path)
    Path(results_timestamp_path).mkdir()

    try:
        org_list_accounts_res = cf.get_client(region, aws.organizations_str).list_accounts()
        logger.info("## Organizations List Accounts successful response")
    except ClientError as ex:
        logger.error(f"## Organizations List Accounts ERROR: '{ex}'")
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    res[aws.ce_str][get_cost_and_usage_str] = {}
    org_list_accounts_list = org_list_accounts_res["Accounts"]
    # pylint: disable=too-many-nested-blocks
    for i, org_account_meta in enumerate(org_list_accounts_list):
        if org_account_meta["Status"] != "ACTIVE":
            continue
        org_account_id: str = org_account_meta["Id"]
        org_account_name: str = org_account_meta["Name"]
        org_account_name_id: str = f"{org_account_name} ({org_account_id})"
        org_account_prefix: str = f"[{i+1}/{len(org_list_accounts_list)}] {org_account_name_id}"
        logger.info(f"## Looking at AWS account: {org_account_prefix}")

        results_timestamp_account_path: str = os.path.join(results_timestamp_path, org_account_name_id)
        Path(results_timestamp_account_path).mkdir()

        res[aws.ce_str][get_cost_and_usage_str][org_account_name_id] = {}
        time_periods: set[tuple[str, str]] = set()
        for project_name in tags_meta[tag_project_name]:
            project_name_sanitised: str = sanitise(project_name)
            res[aws.ce_str][get_cost_and_usage_str][org_account_name_id][project_name_sanitised] = {}
            for env_type in tags_meta[tag_env_type]:
                env_type_sanitised: str = sanitise(env_type)
                logger.info(
                    f"## Retrieves cost and usage metrics for: {org_account_prefix} {project_name_sanitised} {env_type_sanitised}"
                )
                is_next_token: bool = True
                next_page_token: str = None
                ce_get_cost_and_usage_responses: list[dict] = []
                while is_next_token:
                    try:
                        ce_get_cost_and_usage_res = clients[aws.ce_str].get_cost_and_usage(
                            TimePeriod=time_period_meta,
                            Granularity="MONTHLY",
                            Filter={
                                "And": [
                                    {i: {"Key": j, "Values": [k], "MatchOptions": ["EQUALS", "CASE_SENSITIVE"]}}
                                    for i, j, k in [
                                        ("Dimensions", "LINKED_ACCOUNT", org_account_id),
                                        ("Tags", tag_project_name, project_name),
                                        ("Tags", tag_env_type, env_type),
                                    ]
                                ],
                            },
                            Metrics=[cost_str],
                            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                            **{
                                k: v
                                for k, v in {
                                    next_page_token_str: next_page_token if next_page_token else None,
                                }.items()
                                if v
                            },
                        )
                        logger.info("## Cost Explorer List Accounts successful response")
                    except ClientError as ex:
                        logger.error(f"## Cost Explorer List Accounts ERROR: '{ex}'")
                        cf.write_to_json_paths(res, base_steps_client_names)
                        sys.exit(1)
                    if next_page_token_str in ce_get_cost_and_usage_res:
                        next_page_token = ce_get_cost_and_usage_res[next_page_token_str]
                    else:
                        is_next_token = False
                    ce_get_cost_and_usage_res_results_by_time = ce_get_cost_and_usage_res["ResultsByTime"]
                    for account_meta in ce_get_cost_and_usage_res_results_by_time:
                        time_periods.add(time_period_to_tuple(account_meta[time_period_str]))
                    ce_get_cost_and_usage_responses += ce_get_cost_and_usage_res_results_by_time
                res[aws.ce_str][get_cost_and_usage_str][org_account_name_id][project_name_sanitised][
                    env_type_sanitised
                ] = ce_get_cost_and_usage_responses

        for start_time, end_time in sorted(time_periods):
            results_timestamp_account_start_end_time_path: str = os.path.join(
                results_timestamp_account_path, sep.join([start_time, end_time])
            )
            Path(results_timestamp_account_start_end_time_path).mkdir()

            project_name_env_type_amounts: dict = {}
            for project_name, project_name_meta in res[aws.ce_str][get_cost_and_usage_str][org_account_name_id].items():
                project_name_sanitised: str = sanitise(project_name)
                results_timestamp_account_start_end_time_project_name_path: str = os.path.join(
                    results_timestamp_account_start_end_time_path,
                    sep.join([start_time, end_time, filename_no_ext, project_name_sanitised]),
                )
                Path(results_timestamp_account_start_end_time_project_name_path).mkdir()

                project_name_env_type_amounts[project_name_sanitised] = {}
                for env_type, env_type_meta in project_name_meta.items():
                    env_type_sanitised: str = sanitise(env_type)
                    for entry in env_type_meta:
                        if (
                            start_time == entry[time_period_str][start_str]
                            and end_time == entry[time_period_str][end_str]
                        ):
                            if entry_groups_meta := entry["Groups"]:
                                rows = [
                                    [i["Keys"][0], amount, i[metric_str][cost_str][unit_str]]
                                    for i in entry_groups_meta
                                    if (amount := i[metric_str][cost_str][amount_str]) and float(amount) > 0
                                ]
                                if rows:
                                    new_csv_path = os.path.join(
                                        results_timestamp_account_start_end_time_project_name_path,
                                        f"{sep.join([start_time, end_time, filename_no_ext, project_name_sanitised, env_type_sanitised])}{file_extension}",
                                    )
                                    with open(new_csv_path, "w+", encoding=encoding, newline="") as new_csvfile:
                                        writer = csv.writer(new_csvfile)
                                        logger.info(f"## Writing new '{file_extension}' file: '{new_csv_path}'")
                                        writer.writerow(["Service", amount_str, unit_str])  # Add column headers
                                        writer.writerows(rows)
                                        project_name_env_type_amounts[project_name_sanitised][env_type_sanitised] = sum(
                                            float(i[1]) for i in rows
                                        )
                                    continue
                            project_name_env_type_amounts[project_name_sanitised][env_type_sanitised] = 0
                            break

                if not os.listdir(results_timestamp_account_start_end_time_project_name_path):
                    os.rmdir(results_timestamp_account_start_end_time_project_name_path)

            new_csv_path = os.path.join(
                results_timestamp_account_start_end_time_path,
                f"{sep.join([start_time, end_time, filename_no_ext])}{file_extension}",
            )
            with open(new_csv_path, "w+", encoding=encoding, newline="") as new_csvfile:
                logger.info(f"## Writing new '{file_extension}' file: '{new_csv_path}'")
                writer = csv.writer(new_csvfile)
                writer.writerow(
                    ["Project Name/Env Type"] + [i if i else sanitise(i) for i in tags_meta[tag_env_type]]
                )  # Add column headers
                writer.writerows(
                    [
                        [sanitise(project_name)] + [meta[sanitise(env_type)] for env_type in tags_meta[tag_env_type]]
                        for project_name, meta in project_name_env_type_amounts.items()
                    ]
                )

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Collect cost and usage from AWS Cost Explorer.")
    parser.add_argument(
        "--months",
        help="Specify the number of months to collect cost and usage for, eg. '--months 6'.",
        type=str,
    )
    args = parser.parse_args()
    main(region="us-east-1", months=args.months)

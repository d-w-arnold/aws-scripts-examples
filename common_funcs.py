import json
import sys
from typing import Union

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError


class CommonFuncs:
    starting_str: str = "Starting"
    finished_str: str = "Finished"

    dev: str = "dev"
    staging: str = "staging"
    perform: str = "perform"
    preview: str = "preview"
    demo: str = "demo"
    prod: str = "prod"

    # Default deploy envs, excluding any preview/demo deploy envs
    deploy_envs_default: list[str] = [dev, staging, perform, prod]
    # Internal deploy envs, non-public facing
    deploy_envs_internal: list[str] = [dev, staging, perform]
    # Deploy envs, expected not to need a deployment git tag specified
    deploy_envs_non_git_tag: list[str] = [dev, staging]

    region_timezones_meta: dict[str, str] = {
        "us-east-1": "US/Eastern",  # N. Virginia
        "af-south-1": "Africa/Maputo",  # Cape Town
        "ap-northeast-2": "Asia/Seoul",  # Seoul
        "ap-southeast-2": "Australia/Sydney",  # Sydney
        "eu-central-1": "Europe/Berlin",  # Frankfurt
        "eu-west-2": "Europe/London",  # London
        "sa-east-1": "America/Sao_Paulo",  # São Paulo
    }

    def __init__(self, logger, filename, json_paths=None, **kwargs):
        self.logger = logger
        self.filename = filename
        if json_paths is not None:
            self.json_paths = self.gen_json_paths(json_paths)
        self.__dict__.update(kwargs)

    def gen_json_paths(self, json_paths: list[Union[str, tuple[str, list[str]]]], f: str = None) -> dict:
        filename_no_ext: str = f if f else self.filename.rsplit(sep=".", maxsplit=1)[0]
        paths: dict = {}
        for i in json_paths:
            if isinstance(i, tuple):
                paths[i[0]] = self.gen_json_paths(i[1], f=f"{filename_no_ext}-{i[0]}")
            else:
                paths[i] = f"{filename_no_ext}-{i}-res.json"
        return paths

    def info_log(self, action: str, opt: str = None):
        action = action if action[0].isupper() else action.capitalize()
        msg: str = f"## {action} '{self.filename}' {f'({opt}) ' if opt else ''}main method"
        self.logger.info(f"{msg}\n" if action == self.finished_str else msg)

    def info_log_starting(self, opt: str = None):
        self.info_log(self.starting_str, opt=opt)

    def info_log_finished(self, opt: str = None):
        self.info_log(self.finished_str, opt=opt)

    def amplify_list_apps(self, amplify) -> list[dict]:
        self.logger.info("## List all AWS Amplify apps")
        is_next_token: bool = True
        next_token: str = None
        amplify_list_apps_res_apps: list = []
        while is_next_token:
            try:
                amplify_list_apps_res = amplify.list_apps(
                    **{
                        k: v
                        for k, v in {
                            "nextToken": next_token if next_token else None,
                            "maxResults": 100,  # Max 100. Default: 10
                        }.items()
                        if v
                    }
                )
                self.logger.info("## Amplify List Apps successful response")
            except EndpointConnectionError as ex:
                self.logger.error(f"## Amplify List Apps ERROR: '{ex}'")
                break
            except ClientError as ex:
                self.logger.error(f"## Amplify List Apps ERROR: '{ex}'")
                sys.exit(1)
            if "nextToken" in amplify_list_apps_res:
                next_token = amplify_list_apps_res["nextToken"]
            else:
                is_next_token = False
            amplify_list_apps_res_apps += amplify_list_apps_res["apps"]
        return amplify_list_apps_res_apps

    def check_amplify_app_exists(self, amplify, amplify_app_name: str) -> bool:
        self.logger.info(f"## Checking whether there is already an AWS Amplify app of the name: '{amplify_app_name}'")
        for name in [i["name"] for i in self.amplify_list_apps(amplify)]:
            if name == amplify_app_name:
                return True
        return False

    @staticmethod
    def get_amplify_app_desc_prefix(amplify_app_name: str) -> str:
        return f"(for AWS Amplify app: '{amplify_app_name}')"

    def get_amplify_app_id(self, amplify, amplify_app_name: str) -> str:
        prefix: str = self.get_amplify_app_desc_prefix(amplify_app_name)
        self.logger.info(f"## Getting the AWS Amplify app ID {prefix}")
        amplify_app_id: str = None
        for name, app_id in {i["name"]: i["appId"] for i in self.amplify_list_apps(amplify)}.items():
            if name == amplify_app_name:
                amplify_app_id = app_id
                break
        if amplify_app_id is None:
            self.logger.error("## ERROR: Could not find AWS Amplify app ID")
            sys.exit(1)
        self.logger.info(f"## AWS Amplify app ID: '{amplify_app_id}' {prefix}")
        return amplify_app_id

    def get_amplify_app_id_and_tags(self, amplify, amplify_app_name: str) -> tuple[str, dict[str, str]]:
        prefix: str = self.get_amplify_app_desc_prefix(amplify_app_name)
        self.logger.info(f"## Getting the AWS Amplify app ID and tags {prefix}")
        amplify_app_id: str = None
        amplify_app_tags: dict[str, str] = None
        for name, app_id_tags in {i["name"]: (i["appId"], i["tags"]) for i in self.amplify_list_apps(amplify)}.items():
            if name == amplify_app_name:
                amplify_app_id = app_id_tags[0]
                amplify_app_tags = app_id_tags[1]
                break
        if amplify_app_id is None:
            self.logger.error(f"## ERROR: Could not find AWS Amplify app ID {prefix}")
            sys.exit(1)
        if amplify_app_tags is None:
            self.logger.error(f"## ERROR: Could not find AWS Amplify app tags {prefix}")
            sys.exit(1)
        self.logger.info(f"## AWS Amplify app ID: '{amplify_app_id}' {prefix}")
        self.logger.info(f"## AWS Amplify app tags: '{amplify_app_tags}' {prefix}")
        return amplify_app_id, amplify_app_tags

    def get_client(self, region: str, client_name: str):
        c = boto3.client(client_name, region_name=region)
        self.logger.info(f"## Connected to {client_name.upper()} via client, AWS region: {region}")
        return c

    def get_clients_and_res_objs(self, region: str, client_names: list[str]) -> tuple[dict, dict]:
        clients: dict = {}
        res: dict = {}
        for client_name in client_names:
            clients[client_name] = self.get_client(region, client_name)
            res[client_name] = {}
        return clients, res

    def is_deploy_env_internal(self, deploy_env: str) -> bool:
        # Handles deploy envs containing a deploy env as a sub-string (e.g. dev-unstable)
        return deploy_env in self.deploy_envs_internal or any(de in deploy_env for de in self.deploy_envs_internal)

    def is_deploy_env_non_git_tag(self, deploy_env: str) -> bool:
        # Handles deploy envs containing a deploy env as a sub-string (e.g. dev-unstable)
        return deploy_env in self.deploy_envs_non_git_tag or any(
            de in deploy_env for de in self.deploy_envs_non_git_tag
        )

    def sns_list_topics(self, sns) -> list[dict]:
        self.logger.info("## List all SNS topics")
        is_next_token: bool = True
        next_token: str = None
        sns_list_topics_res_topics: list = []
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
                self.logger.info("## SNS List Topics successful response")
            except ClientError as ex:
                self.logger.error(f"## SNS List Topics ERROR: '{ex}'")
                sys.exit(1)
            if "NextToken" in sns_list_topics_res:
                next_token = sns_list_topics_res["NextToken"]
            else:
                is_next_token = False
            sns_list_topics_res_topics += sns_list_topics_res["Topics"]
        return sns_list_topics_res_topics

    def ssm_describe_parameters(self, ssm, contains: str = None) -> list[dict]:
        self.logger.info(f"## List all SSM Parameter Store parameters{f', containing: {contains}' if contains else ''}")
        is_next_token: bool = True
        next_token: str = None
        ssm_describe_parameters_res_topics: list = []
        while is_next_token:
            try:
                ssm_describe_parameters_res = ssm.describe_parameters(
                    **{
                        k: v
                        for k, v in {
                            "ParameterFilters": (
                                [{"Key": "Name", "Option": "Contains", "Values": [contains]}] if contains else None
                            ),
                            "NextToken": next_token if next_token else None,
                        }.items()
                        if v
                    }
                )
                self.logger.info("## SSM Describe Parameters successful response")
            except ClientError as ex:
                self.logger.error(f"## SSM Describe Parameters ERROR: '{ex}'")
                sys.exit(1)
            if "NextToken" in ssm_describe_parameters_res:
                next_token = ssm_describe_parameters_res["NextToken"]
            else:
                is_next_token = False
            ssm_describe_parameters_res_topics += ssm_describe_parameters_res["Parameters"]
        return ssm_describe_parameters_res_topics

    def write_to_json_paths(self, res: dict, client_names: list[str], json_paths_key: str = None):
        for i in [
            (self.json_paths[json_paths_key][i] if json_paths_key else self.json_paths[i], res[i]) for i in client_names
        ]:
            with open(i[0], "w+", encoding="utf-8") as f:
                json.dump(i[1], f, indent=2, default=str)

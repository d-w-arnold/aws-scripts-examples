import logging
import os
import sys
from datetime import datetime

from botocore.exceptions import ClientError
from pytz import timezone

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

repo_str: str = "repo"
base_amplify_str: str = "base_amplify"

base_steps_client_names: list[str] = [aws.amplify_str, aws.codepipeline_str, aws.ssm_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

filename_no_ext: str = cf.filename.rsplit(sep=".", maxsplit=1)[0]
filename_git_repo_txt_path: str = f"{filename_no_ext}-git-repo.txt"
filename_git_branch_txt_path: str = f"{filename_no_ext}-git-branch.txt"
bitbucket_account_name: str = "foobar-products-development"
# bitbucket_account_name: str = "foobar-infrastructure-innovation"


def repo_steps(repo: str, deploy_env: str) -> None:
    git_repo_ssh: str = f"git@bitbucket.org:{bitbucket_account_name}/{repo}.git"
    logger.info(f"## Git Repo SSH (for 'git clone' command): {git_repo_ssh}")
    with open(filename_git_repo_txt_path, "w+", encoding="utf-8") as f:
        f.write(git_repo_ssh)

    if deploy_env in cf.deploy_envs_non_git_tag and "base" not in repo:
        logger.error(f"## ERROR: Invalid deploy env: '{deploy_env}' (for git repo: '{repo}')")
        logger.error(
            f"## Both {cf.deploy_envs_non_git_tag} only support git tag deployment for their BASE repo (e.g. '{repo}-{deploy_env}-base')"
        )
        sys.exit(1)

    if "-" not in deploy_env and deploy_env not in cf.deploy_envs_default:
        logger.error(f"## ERROR: Invalid deploy env: '{deploy_env}' (for git repo: '{repo}')")
        logger.error("## Valid deploy envs:")
        logger.error(f"##   (base) {cf.deploy_envs_non_git_tag}")
        logger.error(f"##   (base & non-base) {cf.deploy_envs_default + [f'*-{i}' for i in ['preview', 'demo']]}")
        logger.error("## Did you mean either:")
        logger.error(f"##   {[f'{deploy_env}-{i}' for i in ['preview', 'demo']]} ?")
        sys.exit(1)

    git_branch: str = (
        ("prod" if deploy_env == "prod" else ("main" if deploy_env != "dev" else "dev"))
        if "-" not in deploy_env or deploy_env.split(sep="-", maxsplit=1)[1] != "demo"
        else "prod"
    )
    logger.info(f"## Git Branch (for 'git checkout' command): {git_branch}")
    with open(filename_git_branch_txt_path, "w+", encoding="utf-8") as f:
        f.write(git_branch)


def base_amplify_steps(
    repo: str, deploy_env: str, region: str, account: str, branch: str, tag: str, commit_id: str, commit_msg: str
) -> None:
    client_names: list = [i for i in base_steps_client_names if i == aws.amplify_str]
    clients, res = cf.get_clients_and_res_objs(region, client_names)

    amplify_app_name: str = f"{repo}-{deploy_env}"

    logger.info(f"## Getting the AWS Amplify app ID (for AWS Amplify app: '{amplify_app_name}')")
    amplify_list_apps_res: list[dict] = cf.amplify_list_apps(clients[aws.amplify_str])
    amplify_app_id: str = None
    index: int = None
    for n, (name, app_id) in enumerate({i["name"]: i["appId"] for i in amplify_list_apps_res}.items()):
        if name == amplify_app_name:
            amplify_app_id = app_id
            index = n
            break
    if amplify_app_id is None:
        logger.error(f"## AWS Amplify List Apps res: '{amplify_list_apps_res}'")
        logger.error(
            f"## ERROR: Could not find AWS Amplify app ID, will NOT deploy (release) "
            f"changes on AWS Amplify app build pipeline: {amplify_app_name}"
        )
        cf.write_to_json_paths(res, client_names)
        sys.exit(1)
    logger.info(f"## AWS Amplify app ID: {amplify_app_id} (for AWS Amplify app: '{amplify_app_name}')")

    amplify_app_env_vars = amplify_list_apps_res[index]["environmentVariables"]
    deploy_tag_var: str = "DEPLOY_TAG"
    amplify_app_env_vars[deploy_tag_var] = tag

    logger.info(
        f"## Write the new deployment git tag: '{tag}' (to AWS Amplify app '{deploy_tag_var}' environment variable)"
    )
    try:
        res[aws.amplify_str]["amplify_update_app"] = clients[aws.amplify_str].update_app(
            appId=amplify_app_id,
            environmentVariables=amplify_app_env_vars,
        )
        logger.info("## Amplify Update App successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Update App ERROR: '{ex}', will NOT deploy (release) "
            f"changes on AWS Amplify app build pipeline: {amplify_app_name}"
        )
        cf.write_to_json_paths(res, client_names)
        sys.exit(1)

    logger.info(f"## Releasing changes on AWS Amplify app `{branch}` branch build pipeline: {amplify_app_name}")
    try:
        res[aws.amplify_str]["amplify_start_job"] = clients[aws.amplify_str].start_job(
            appId=amplify_app_id,
            branchName=branch,
            # jobId=,  # Only required if 'jobType="RETRY"'
            jobType="RELEASE",
            jobReason=f"## Releasing changes on AWS Amplify app `{branch}` branch build pipeline, using AWS Deploy Amplify shell script: "
            "https://bitbucket.org/foobar-products-development/aws-scripts/src/main/aws-deploy/aws-deploy-amplify.sh",
            commitId=commit_id,
            commitMessage=commit_msg,
            commitTime=datetime.now(timezone(cf.region_timezones_meta[region])),
        )
        logger.info("## Amplify Start Job successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Start Job ERROR: '{ex}', will NOT deploy (release) "
            f"changes on AWS Amplify app build pipeline: {amplify_app_name}"
        )
        cf.write_to_json_paths(res, client_names)
        sys.exit(1)

    cf.write_to_json_paths(res, client_names)


def base_steps(repo: str, deploy_env: str, region: str, account: str, tag: str) -> None:
    client_names: list = [i for i in base_steps_client_names if i != aws.amplify_str]
    clients, res = cf.get_clients_and_res_objs(region, client_names)

    if "-" in deploy_env:
        deploy_env_props: list[str] = deploy_env.rsplit(sep="-", maxsplit=1)
        if deploy_env_props[1] in {"demo", "preview"}:
            deploy_env = (
                f"{deploy_env_props[0]}{deploy_env_props[1][0]}"
                if deploy_env_props[0] == "sih"
                else deploy_env_props[0]
            )
    param_name: str = f"/tag/{repo}/{deploy_env}"
    pipeline_name: str = f"{repo}-{deploy_env}"

    logger.info(f"## Write the new deployment git tag: '{tag}' (to AWS Systems Manager Parameter Store: {param_name})")
    try:
        res[aws.ssm_str]["ssm_put_parameter"] = clients[aws.ssm_str].put_parameter(
            Name=param_name,
            # Description,  # Default to the existing description
            Value=tag,
            Type="String",
            Overwrite=True,
            # TODO: (OPTIONAL) A regular expression used to validate the parameter value.
            # AllowedPattern=,
            Tier="Standard",
            # DataType="text",
        )
        logger.info("## SSM Put Parameter successful response")
    except ClientError as ex:
        logger.error(
            f"## SSM Put Parameter ERROR: '{ex}', will NOT deploy (release) "
            f"changes on AWS CodePipeline pipeline: {pipeline_name}"
        )
        cf.write_to_json_paths(res, client_names)
        sys.exit(1)

    logger.info(f"## Releasing changes on AWS CodePipeline pipeline: {pipeline_name}")
    try:
        res[aws.codepipeline_str]["codepipeline_start_pipeline_execution"] = clients[
            aws.codepipeline_str
        ].start_pipeline_execution(
            name=pipeline_name,
        )
        logger.info("## CodePipeline Start Pipeline Execution successful response")
    except ClientError as ex:
        logger.error(
            f"## CodePipeline Start Pipeline Execution ERROR: '{ex}', did NOT deploy (release) "
            f"changes on AWS CodePipeline pipeline: {pipeline_name}"
        )

    cf.write_to_json_paths(res, client_names)


def main(
    repo: str,
    deploy_env: str,
    ssh: bool = False,
    region: str = None,
    account: str = None,
    branch: str = None,
    tag: str = None,
    commit_id: str = None,
    commit_msg: str = None,
    amplify: bool = False,
):
    if ssh:
        cf.info_log_starting(opt=repo_str)
        repo_steps(repo, deploy_env)
        cf.info_log_finished(opt=repo_str)
    elif amplify:
        cf.info_log_starting(opt=base_amplify_str)
        base_amplify_steps(repo, deploy_env, region, account, branch, tag, commit_id, commit_msg)
        cf.info_log_finished(opt=base_amplify_str)
    else:
        cf.info_log_starting()
        base_steps(repo, deploy_env, region, account, tag)
        cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Git tag a new commit, and deploy (release) changes via "
        "the corresponding AWS CodePipeline pipeline or AWS Amplify app build pipeline."
    )
    parser.add_argument("--repo", required=True, help="Get the git repo name.", type=str)
    parser.add_argument(
        "--deploy_env",
        required=True,
        help="Specify whether to get the git repo branch name, for a given deployment environment.",
        type=str,
    )
    parser.add_argument(
        "--ssh",
        action="store_true",
        help="Specifies whether to get the git repo SSH URL for the specified git repo name.",
    )
    parser.add_argument(
        "--region",
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    parser.add_argument(
        "--account",
        help="Specify the AWS Account ID, eg. '--account 1234567788901'.",
        type=str,
    )
    parser.add_argument("--branch", help="Specify the git branch.", type=str)
    parser.add_argument("--tag", help="Specify the git tag.", type=str)
    parser.add_argument("--commit_id", help="Specify the git commit ID.", type=str)
    parser.add_argument("--commit_msg", help="Specify the git commit msg.", type=str)
    parser.add_argument(
        "--amplify",
        action="store_true",
        help="Specifies whether to this AWS Deploy is for an Amplify app.",
    )
    args = parser.parse_args()
    main(
        repo=args.repo,
        deploy_env=args.deploy_env,
        ssh=args.ssh,
        region=args.region,
        account=args.account,
        branch=args.branch,
        tag=args.tag,
        commit_id=args.commit_id,
        commit_msg=args.commit_msg,
        amplify=args.amplify,
    )

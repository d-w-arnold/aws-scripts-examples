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

repo_str: str = "repo"

base_steps_client_names: list[str] = [aws.ssm_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

filename_no_ext: str = cf.filename.rsplit(sep=".", maxsplit=1)[0]
filename_git_repo_txt_path: str = f"{filename_no_ext}-git-repo.txt"
filename_git_branch_txt_path: str = f"{filename_no_ext}-git-branch.txt"
bitbucket_account_name: str = "foobar-products-development"


def repo_steps(repo: str, git_branch: str) -> None:
    git_repo_ssh: str = f"git@bitbucket.org:{bitbucket_account_name}/{repo}.git"
    logger.info(f"## Git Repo SSH (for 'git clone' command): {git_repo_ssh}")
    with open(filename_git_repo_txt_path, "w+", encoding="utf-8") as f:
        f.write(git_repo_ssh)

    logger.info(f"## Git Branch (for 'git checkout' command): {git_branch}")
    with open(filename_git_branch_txt_path, "w+", encoding="utf-8") as f:
        f.write(git_branch)


def base_steps(repo: str, deploy_env: str, region: str, account: str, tag: str) -> None:
    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    param_name: str = f"/tag/{repo}/{deploy_env}"

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
        logger.error(f"## SSM Put Parameter ERROR: '{ex}'")
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)


def main(
    repo: str,
    deploy_env: str = "prod",
    ssh: bool = False,
    region: str = None,
    account: str = None,
    tag: str = None,
):
    if ssh:
        cf.info_log_starting(opt=repo_str)
        repo_steps(repo, deploy_env)
        cf.info_log_finished(opt=repo_str)
    else:
        cf.info_log_starting()
        base_steps(repo, deploy_env, region, account, tag)
        cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Git tag a new commit.")
    parser.add_argument("--repo", required=True, help="Get the git repo name.", type=str)
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
    parser.add_argument("--tag", help="Specify the git tag.", type=str)
    args = parser.parse_args()
    main(
        repo=args.repo,
        ssh=args.ssh,
        region=args.region,
        account=args.account,
        tag=args.tag,
    )

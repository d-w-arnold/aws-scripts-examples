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

base_steps_client_names: list[str] = [aws.codeartifact_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

codeartifact_default_domain: str = "foobar"


def check_domain_exists(codeartifact, codeartifact_domain: str) -> bool:
    logger.info(f"## Checking whether there is already a CodeArtifact domain of the name: '{codeartifact_domain}'")
    for name in [i["name"] for i in codeartifact_list_domains(codeartifact)]:
        if name == codeartifact_domain:
            return True
    return False


def check_repository_exists(codeartifact, codeartifact_repository: str) -> bool:
    logger.info(
        f"## Checking whether there is already a CodeArtifact repository of the name: '{codeartifact_repository}'"
    )
    for name in [i["name"] for i in codeartifact_list_repositories(codeartifact)]:
        if name == codeartifact_repository:
            return True
    return False


def codeartifact_list_domains(codeartifact) -> list[dict]:
    logger.info("## List all CodeArtifact domains")
    is_next_token: bool = True
    next_token: str = None
    codeartifact_list_domains_res_domains: list = []
    while is_next_token:
        try:
            codeartifact_list_domains_res = codeartifact.list_domains(
                **{
                    k: v
                    for k, v in {
                        "nextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## CodeArtifact List Domains successful response")
        except ClientError as ex:
            logger.error(f"## CodeArtifact List Domains ERROR: '{ex}'")
            sys.exit(1)
        if "nextToken" in codeartifact_list_domains_res:
            next_token = codeartifact_list_domains_res["nextToken"]
        else:
            is_next_token = False
        codeartifact_list_domains_res_domains += codeartifact_list_domains_res["domains"]
    return codeartifact_list_domains_res_domains


def codeartifact_list_repositories(codeartifact) -> list[dict]:
    logger.info("## List all CodeArtifact repositories")
    is_next_token: bool = True
    next_token: str = None
    codeartifact_list_repositories_res_repositories: list = []
    while is_next_token:
        try:
            codeartifact_list_repositories_res = codeartifact.list_repositories(
                **{
                    k: v
                    for k, v in {
                        "nextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## CodeArtifact List Repositories successful response")
        except ClientError as ex:
            logger.error(f"## CodeArtifact List Repositories ERROR: '{ex}'")
            sys.exit(1)
        if "nextToken" in codeartifact_list_repositories_res:
            next_token = codeartifact_list_repositories_res["nextToken"]
        else:
            is_next_token = False
        codeartifact_list_repositories_res_repositories += codeartifact_list_repositories_res["repositories"]
    return codeartifact_list_repositories_res_repositories


def main(
    region: str,
    repo: str,
    domain: str = None,
):
    cf.info_log_starting()

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    if check_repository_exists(clients[aws.codeartifact_str], repo):
        logger.error(
            f"## ERROR: CodeArtifact repository '{repo}' already exists! (in the '{region}' "
            f"['{cf.region_timezones_meta[region]}'] region)"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    if domain and not check_domain_exists(clients[aws.codeartifact_str], domain):
        logger.error(
            f"## ERROR: CodeArtifact domain '{domain}' doesn't exist! (in the '{region}' "
            f"['{cf.region_timezones_meta[region]}'] region)"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    logger.info("## Creating the CodeArtifact repository")
    codeartifact_create_repository_str: str = "codeartifact_create_repository"
    try:
        res[aws.codeartifact_str][codeartifact_create_repository_str] = clients[aws.codeartifact_str].create_repository(
            domain=domain if domain else codeartifact_default_domain,
            repository=repo,
            description=f"CodeArtifact repo, storing all npm packages, for '{repo}' git repo.",
        )
        logger.info("## CodeArtifact Create Repository successful response")
    except ClientError as ex:
        logger.error(
            f"## CodeArtifact Create Repository ERROR: '{ex}', in trying to create "
            f"a CodeArtifact repository: '{repo}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create a new CodeArtifact repository, for storing of npm packages.")
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    parser.add_argument("--repo", required=True, help="Get the git repo name.", type=str)
    parser.add_argument(
        "--domain",
        help=f"An optional domain for the CodeArtifact repository, if unspecified defaults to: '{codeartifact_default_domain}'.",
        type=str,
    )
    args = parser.parse_args()
    main(
        region=args.region,
        repo=args.repo,
        domain=args.domain,
    )

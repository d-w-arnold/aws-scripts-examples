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

base_steps_client_names: list[str] = [aws.s3_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

bitbucket_account_name: str = "foobar-products-development"
# bitbucket_account_name: str = "foobar-infrastructure-innovation"
s3_checksum_algorithm: str = (
    "SHA256"  # https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html
)
filename_no_ext: str = cf.filename.rsplit(sep=".", maxsplit=1)[0]
filename_git_repo_txt: str = f"{filename_no_ext}-git-repo.txt"


def repo_steps(repo: str) -> None:
    git_repo_ssh: str = f"git@bitbucket.org:{bitbucket_account_name}/{repo}.git"
    logger.info(f"## Git Repo SSH (for 'git clone' command): {git_repo_ssh}")
    with open(filename_git_repo_txt, "w+", encoding="utf-8") as f:
        f.write(git_repo_ssh)


def base_steps(
    repo: str, submodule: bool, region: str, account: str, branch: str, pwd: str, file: str, binary: bool
) -> None:
    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    read_path = os.path.join(pwd, file)
    bucket_exists: bool = True
    bucket_name: str = f"{('-'.join(repo.split('-')[:-1]) if submodule else repo).replace('-', '')}-{region}"[:63]
    submodule_name: str = repo.split("-")[-1]
    obj_key: str = f"{branch}/{f'{submodule_name}/' if submodule else ''}{file}"

    with open(read_path, "rb") if binary else open(read_path, "r", encoding="utf-8") as f:
        sql_file = f.read()

    try:
        res[aws.s3_str]["s3_head_bucket"] = clients[aws.s3_str].head_bucket(
            Bucket=bucket_name, ExpectedBucketOwner=account
        )
        logger.info("## S3 Head Bucket successful response")
    except ClientError as ex:
        res[aws.s3_str]["s3_head_bucket_error"] = ex
        logger.error("## S3 Head Bucket ERROR, will create a new S3 Bucket")
        try:
            res[aws.s3_str]["s3_create_bucket"] = clients[aws.s3_str].create_bucket(
                ACL="private",
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
                ObjectLockEnabledForBucket=False,
                ObjectOwnership="ObjectWriter",
            )
            logger.info("## S3 Create Bucket successful response")
        except ClientError as ex:
            res[aws.s3_str]["s3_create_bucket_error"] = ex
            logger.error("## S3 Create Bucket ERROR")
            bucket_exists = False

        public_access_block_config: dict = {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }

        res[aws.s3_str]["put_public_access_block"] = clients[aws.s3_str].put_public_access_block(
            Bucket=bucket_name,
            ChecksumAlgorithm=s3_checksum_algorithm,
            PublicAccessBlockConfiguration=public_access_block_config,
            ExpectedBucketOwner=account,
        )
        logger.info(
            f"## S3 Put Public Access Block: {'ALL' if all(v for _, v in public_access_block_config.items()) else ' '.join([k for k, v in public_access_block_config.items() if v])}"
        )

    if bucket_exists:
        try:
            res[aws.s3_str]["s3_put_object"] = clients[aws.s3_str].put_object(
                ACL="bucket-owner-full-control",
                Body=sql_file if isinstance(sql_file, bytes) else str(sql_file).encode(encoding="utf-8"),
                Bucket=bucket_name,
                ChecksumAlgorithm=s3_checksum_algorithm,
                Key=obj_key,
                # Metadata={
                #     'string': 'string'
                # },
                # ServerSideEncryption="aws:kms",
                StorageClass="STANDARD",
                # SSEKMSKeyId=,
                # SSEKMSEncryptionContext=base64.b64encode(
                #     json.dumps({}).encode("ascii")
                # ).decode("ascii"),
                BucketKeyEnabled=False,
                # ObjectLockMode='GOVERNANCE' | 'COMPLIANCE',
                # ObjectLockRetainUntilDate=datetime(2015, 1, 1),
                # ObjectLockLegalHoldStatus='ON' | 'OFF',
                ExpectedBucketOwner=account,
            )
            logger.info("## S3 Put Object successful response")
        except ClientError as ex:
            res[aws.s3_str]["s3_put_object_error"] = ex
            logger.error("## S3 Put Object ERROR")

    cf.write_to_json_paths(res, base_steps_client_names)


def main(
    repo: str,
    submodule: bool = False,
    ssh: bool = False,
    region: str = None,
    account: str = None,
    branch: str = None,
    pwd: str = None,
    file: str = None,
    binary: bool = None,
):
    if ssh:
        cf.info_log_starting(opt=repo_str)
        repo_steps(repo)
        cf.info_log_finished(opt=repo_str)
    else:
        cf.info_log_starting()
        base_steps(repo, submodule, region, account, branch, pwd, file, binary)
        cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upload file to AWS S3, for use in the 's3-upload.sh' script.")
    parser.add_argument("--repo", required=True, help="Get the git repo name.", type=str)
    parser.add_argument(
        "--submodule",
        action="store_true",
        help="Specifies whether the git repo to checkout is a submodule of a parent repo.",
    )
    parser.add_argument(
        "--binary",
        action="store_true",
        help="Specifies whether the file to upload is a binary file.",
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
    parser.add_argument("--branch", help="Specify the git repo branch name.", type=str)
    parser.add_argument("--pwd", help="Specify the git repo path.", type=str)
    parser.add_argument(
        "--file", help="Specify the relative file path from git repo root, of the file to upload to AWS S3.", type=str
    )
    args = parser.parse_args()
    main(
        repo=args.repo,
        submodule=args.submodule,
        ssh=args.ssh,
        region=args.region,
        account=args.account,
        branch=args.branch,
        pwd=args.pwd,
        file=args.file,
        binary=args.binary,
    )

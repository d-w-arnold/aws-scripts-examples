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

base_steps_client_names: list[str] = [aws.s3_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)


def main(
    region: str,
    bucket_names: str,
    kms_master_key_id: str,
):
    cf.info_log_starting()

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    logger.info(f"## S3 Putting Bucket Encryption, using KMS Master Key ID: {kms_master_key_id}")

    res[aws.s3_str]["put_bucket_encryption"] = {}
    for n, bucket_name in enumerate(bucket_names.split("\n")):
        logger.info(f"## S3 Putting Bucket Encryption, for S3 bucket ({n+1}): {bucket_name}")
        try:
            res[aws.s3_str]["put_bucket_encryption"][bucket_name] = clients[aws.s3_str].put_bucket_encryption(
                Bucket=bucket_name,
                ServerSideEncryptionConfiguration={
                    "Rules": [
                        {
                            "ApplyServerSideEncryptionByDefault": {
                                "SSEAlgorithm": "aws:kms",
                                "KMSMasterKeyID": kms_master_key_id,
                            },
                            "BucketKeyEnabled": True,
                        },
                    ]
                },
            )
            logger.info("## S3 Put Bucket Encryption successful response")
        except ClientError as ex:
            logger.error(f"## S3 Put Bucket Encryption ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Encrypt S3 buckets with a different KMS key.")
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    parser.add_argument(
        "--bucket_names",
        required=True,
        help="The list of S3 bucket names, eg. '--bucket_names foo bar'.",
        type=str,
    )
    parser.add_argument(
        "--kms_master_key_id",
        required=True,
        help="The KMS key to be used for S3 bucket encryption, eg. '--kms_master_key_id arn:aws:kms:eu-west-2:*:key/*'.",
        type=str,
    )
    args = parser.parse_args()
    main(
        region=args.region,
        bucket_names=args.bucket_names,
        kms_master_key_id=args.kms_master_key_id,
    )

#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Encrypt S3 buckets with a different KMS key.

    Arguments:

      -h      Show help info.

      -b      The S3 bucket name prefix, used to find a list of
              S3 bucket names for encryption (e.g. 'doggwdev-eu-west-2-', etc.).

      -k      The KMS key to be used for S3 bucket encryption (e.g. 'arn:aws:kms:eu-west-2:*:key/*').

      -r      The AWS region in which to encrypt S3 buckets with a different KMS key (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./s3-encrypt.sh -r \"eu-west-2\" -b \"doggwdev-eu-west-2-\" -k \"arn:aws:kms:eu-west-2:*:key/*\"
    ./s3-encrypt.sh -r \"eu-west-2\" -b \"doggwstaging-eu-west-2-\" -k \"arn:aws:kms:eu-west-2:*:key/*\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="s3-encrypt"
  PY_FILE="${FILENAME}.py"

  BUCKET_NAMES_PREFIX=""
  KMS_MASTER_KEY_ID=""
  REGION=""

  while getopts ":hb:k:r:" arg; do
    case $arg in
    h) usage ;;
    b) BUCKET_NAMES_PREFIX="${OPTARG}" ;;
    k) KMS_MASTER_KEY_ID="${OPTARG}" ;;
    r) REGION="${OPTARG}" ;;
    *) usage ;;
    esac
  done
  shift $((OPTIND - 1))

  if [[ -z "${REGION}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-r' required." "${EXAMPLE_DESC_REGION}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${BUCKET_NAMES_PREFIX}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-b' required." "${EXAMPLE_DESC_BUCKET_NAMES_PREFIX}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${KMS_MASTER_KEY_ID}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-k' required." "${EXAMPLE_DESC_KMS_MASTER_KEY_ID}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  BUCKET_NAMES="$(aws s3 ls | awk '{print $3}' | grep "${BUCKET_NAMES_PREFIX}")"

  printf "%s\n\n" "## Running Python script"
  if python3 ${PY_FILE} --region "${REGION}" --bucket_names "${BUCKET_NAMES}" --kms_master_key_id "${KMS_MASTER_KEY_ID}"; then
    printf "%s\n\n" "## Recursive copy for each S3 bucket, to apply new KMS key encryption to every S3 object"
    for MY_BUCKET in ${BUCKET_NAMES}; do  aws s3 cp s3://"${MY_BUCKET}" s3://"${MY_BUCKET}" --recursive ; done
  else
    printf "%s\n\n" "## Python script failed"
  fi
}

main "$@"

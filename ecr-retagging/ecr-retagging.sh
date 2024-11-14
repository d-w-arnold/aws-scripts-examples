#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Retagging an Elastic Container Registry (ECR) image.

    NB. Does a copy of the image, creating a new image with the new tag, does NOT delete the image with the old tag.

    Arguments:

      -h      Show help info.

      -e      The ECR repo name (e.g. 'foobar/dog-gw').

      -n      The new image tag (e.g. 'perform').

      -o      The old image tag, or image digest - if untagged (e.g. 'staging', 'sha256:e6664d8c98e5a3499acf6813b7a5a5e85dace6a0e13927b63df4931409544b5e').

      -r      The AWS region in which RDS init Lambda function resides (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./ecr-retagging.sh -r \"eu-west-2\" -e \"foobar/dog-gw\" -o \"staging\" -n \"perform\"
    ./ecr-retagging.sh -r \"eu-west-2\" -e \"foobar/dog-gw\" -o \"staging\" -n \"sihp\"
    ./ecr-retagging.sh -r \"eu-west-2\" -e \"foobar/dog-gw\" -o \"staging\" -n \"uat\"
    ./ecr-retagging.sh -r \"eu-west-2\" -e \"foobar/dog-gw\" -o \"sha256:e6664d8c98e5a3499acf6813b7a5a5e85dace6a0e13927b63df4931409544b5e\" -n \"staging\"
    ./ecr-retagging.sh -r \"eu-west-2\" -e \"foobar/dog-gw\" -o \"prod\" -n \"220915.1\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="ecr-retagging"
  DESCRIBE_RES_FILE="${FILENAME}-describe-res.json"
  PUT_RES_FILE="${FILENAME}-put-res.json"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_ECR_REPO="For example: -e \"foobar/dog-gw\""
  EXAMPLE_DESC_OLD_TAG="For example: -o \"staging\""
  EXAMPLE_DESC_NEW_TAG="For example: -n \"perform\""
  HELP_DESC="See help info with '-h' option"

  REGION=""
  ECR_REPO=""
  NEW_TAG=""
  OLD_TAG=""

  while getopts ":he:n:o:r:" arg; do
    case $arg in
    h) usage ;;
    e) ECR_REPO="${OPTARG}" ;;
    n) NEW_TAG="${OPTARG}" ;;
    o) OLD_TAG="${OPTARG}" ;;
    r) REGION="${OPTARG}" ;;
    *) usage ;;
    esac
  done
  shift $((OPTIND - 1))

  if [[ -z "${REGION}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-r' required." "${EXAMPLE_DESC_REGION}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${ECR_REPO}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-e' required." "${EXAMPLE_DESC_ECR_REPO}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${OLD_TAG}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-o' required." "${EXAMPLE_DESC_OLD_TAG}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${NEW_TAG}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-n' required." "${EXAMPLE_DESC_NEW_TAG}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  # Source: https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-retag.html

  echo "## Generating manifest of old image: '${ECR_REPO}:${OLD_TAG}'"
  if [[ "${OLD_TAG}" == "sha256:"* ]]; then
    # The OLD_TAG value is the image digest of an untagged image:
    #   https://gist.github.com/anderson-marques/38b802189bb8bc1cf37299cc60d653d4
    MANIFEST=$(aws ecr batch-get-image --repository-name "${ECR_REPO}" --image-ids imageDigest="${OLD_TAG}" --query 'images[].imageManifest' --output text)
  else
    MANIFEST=$(aws ecr batch-get-image --repository-name "${ECR_REPO}" --image-ids imageTag="${OLD_TAG}" --output json | jq --raw-output --join-output '.images[0].imageManifest')
  fi

  echo "## Creating new image: '${ECR_REPO}:${NEW_TAG}' (output: '${PUT_RES_FILE}')"
  aws ecr put-image --repository-name "${ECR_REPO}" --image-tag "${NEW_TAG}" --image-manifest "${MANIFEST}" >"${PUT_RES_FILE}"

  echo "## Verify that your new image tag is attached to your image: '${DESCRIBE_RES_FILE}'"
  aws ecr describe-images --repository-name "${ECR_REPO}" --image-ids imageTag="${NEW_TAG}" >"${DESCRIBE_RES_FILE}"
}

main "$@"

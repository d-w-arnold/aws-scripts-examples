#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Upload a file in a git repo to an AWS S3 Bucket.

    NB. The S3 bucket, where the file will be uploaded, will have a bucket name in the format: (git repo name)-(AWS region).
          Also, if the S3 bucket doesn't exist, a new S3 bucket will be created.

    Arguments:

      -h      Show help info.

      -b      The git repo branch name to checkout (e.g. 'main', 'dev', etc.).

      -g      The git repo name to checkout, in order to source the file for uploading to AWS S3 (e.g. 'dog-gw').

      -p      The relative file path, from the git repo root directory, of the file to upload to AWS S3 (e.g. 'mysql/data/all.sql').

      -r      The AWS region in which the AWS S3 Bucket, where the file will be uploaded to, resides (e.g. 'eu-west-2').

      -s      Whether the git repo to checkout is a submodule of a parent repo.

      -y      An optional flag to indicate the file to upload is a binary file.

    Arguments:

    Example usages:

    ./s3-upload.sh -r \"eu-west-2\" -g \"dog-gw\" -b \"dev\" -p \"mysql/data/all.sql\"

    ./s3-upload.sh -r \"eu-west-2\" -g \"dog-gw\" -b \"main\" -p \"mysql/structure/schema_initial.sql\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="s3-upload"
  PY_FILE="${FILENAME}.py"
  GIT_REPO_FILE="${FILENAME}-git-repo.txt"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_GIT_REPO="For example: -g \"git-repo-name\""
  EXAMPLE_DESC_GIT_BRANCH="For example: -b \"git-branch-name\""
  EXAMPLE_DESC_FILE_PATH="For example: -p \"rel-path-from-git-repo-root\""
  HELP_DESC="See help info with '-h' option"

  BINARY=0
  FILE_PATH=""
  GIT_BRANCH=""
  GIT_REPO=""
  GIT_SUBMODULE=0
  REGION=""

  while getopts ":hb:g:p:r:sy" arg; do
    case $arg in
    h) usage ;;
    b) GIT_BRANCH="${OPTARG}" ;;
    g) GIT_REPO="${OPTARG}" ;;
    p) FILE_PATH="${OPTARG}" ;;
    r) REGION="${OPTARG}" ;;
    s) GIT_SUBMODULE=1 ;;
    y) BINARY=1 ;;
    *) usage ;;
    esac
  done
  shift $((OPTIND - 1))

  if [[ -z "${REGION}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-r' required." "${EXAMPLE_DESC_REGION}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${GIT_REPO}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-g' required." "${EXAMPLE_DESC_GIT_REPO}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${GIT_BRANCH}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-b' required." "${EXAMPLE_DESC_GIT_BRANCH}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ -z "${FILE_PATH}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-p' required." "${EXAMPLE_DESC_FILE_PATH}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  printf "%s\n\n" "## Collecting '${GIT_REPO_FILE}' data using '${PY_FILE}' script"
  python3 ${PY_FILE} --repo "${GIT_REPO}" --ssh

  GIT_REPO_SSH="$(cat ${GIT_REPO_FILE})"
  SAVED_PWD=$(pwd)
  mkdir -p tmp
  cd tmp
  if [ -d "${GIT_REPO}" ]; then
    rm -rf "${GIT_REPO}"
  fi
  git clone "${GIT_REPO_SSH}"
  cd "${GIT_REPO}"
  git checkout "${GIT_BRANCH}"

  GIT_REPO_PWD=$(pwd)

  printf "\n%s\n\n" "## Git repo pwd: ${GIT_REPO_PWD}"

  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query "Account" --output text)"

  cd "${SAVED_PWD}"

  if [ "${GIT_SUBMODULE}" -eq 1 ] && [ "${BINARY}" -eq 1 ]; then
    printf "%s\n\n" "## Pushing '${FILE_PATH}' (binary file) from '${GIT_REPO}' git repo (inc. submodule), '${GIT_BRANCH}' branch, to S3 bucket using '${PY_FILE}' script"
    python3 ${PY_FILE} --repo "${GIT_REPO}" --submodule --binary --region "${REGION}" --account "${AWS_ACCOUNT_ID}" --branch "${GIT_BRANCH}" --pwd "${GIT_REPO_PWD}" --file "${FILE_PATH}"
  elif [[ "${GIT_SUBMODULE}" -eq 1 ]]; then
    printf "%s\n\n" "## Pushing '${FILE_PATH}' from '${GIT_REPO}' git repo (inc. submodule), '${GIT_BRANCH}' branch, to S3 bucket using '${PY_FILE}' script"
    python3 ${PY_FILE} --repo "${GIT_REPO}" --submodule --region "${REGION}" --account "${AWS_ACCOUNT_ID}" --branch "${GIT_BRANCH}" --pwd "${GIT_REPO_PWD}" --file "${FILE_PATH}"
  elif [[ "${BINARY}" -eq 1 ]]; then
    printf "%s\n\n" "## Pushing '${FILE_PATH}' (binary file) from '${GIT_REPO}' git repo, '${GIT_BRANCH}' branch, to S3 bucket using '${PY_FILE}' script"
    python3 ${PY_FILE} --repo "${GIT_REPO}" --binary --region "${REGION}" --account "${AWS_ACCOUNT_ID}" --branch "${GIT_BRANCH}" --pwd "${GIT_REPO_PWD}" --file "${FILE_PATH}"
  else
    printf "%s\n\n" "## Pushing '${FILE_PATH}' from '${GIT_REPO}' git repo, '${GIT_BRANCH}' branch, to S3 bucket using '${PY_FILE}' script"
    python3 ${PY_FILE} --repo "${GIT_REPO}" --region "${REGION}" --account "${AWS_ACCOUNT_ID}" --branch "${GIT_BRANCH}" --pwd "${GIT_REPO_PWD}" --file "${FILE_PATH}"
  fi

  rm -rf tmp
}

main "$@"

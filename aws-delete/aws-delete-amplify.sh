#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Delete an existing AWS Amplify app.

    Arguments:

      -h      Show help info.

      -d      The deployment environment for the AWS Amplify app (e.g. 'prod', 'perform', etc.).

      -g      The git repo name to use in the AWS Amplify app name, and needed to connect to Bitbucket (e.g. 'dog-portal').

      -r      The AWS region in which to delete the AWS Amplify app (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./aws-delete-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"dev\"
    ./aws-delete-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"staging\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="aws-delete-amplify"
  PY_FILE="${FILENAME}.py"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_GIT_REPO="For example: -g \"git-repo-name\""
  EXAMPLE_DESC_DEPLOY_ENV="For example: -d \"deploy-env\""
  HELP_DESC="See help info with '-h' option"

  DEPLOY_ENV=""
  GIT_REPO=""
  REGION=""

  while getopts ":hd:g:r:" arg; do
    case $arg in
    h) usage ;;
    d) DEPLOY_ENV="${OPTARG}" ;;
    g) GIT_REPO="${OPTARG}" ;;
    r) REGION="${OPTARG}" ;;
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

  if [[ -z "${DEPLOY_ENV}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-d' required." "${EXAMPLE_DESC_DEPLOY_ENV}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  while true; do
    echo ""
    read -r -p "Are you sure you'd like to try deleting the AWS Amplify app: '${GIT_REPO}-${DEPLOY_ENV}' (if it exists, in the '${REGION}' region) ? [y/n] " yn
    case $yn in
    [Yy]*) echo "... Confirmed" && break ;;
    [Nn]*) echo "... Exiting script" && exit 1 ;;
    *) printf "\n%s\n" "Please answer [y/n]." ;;
    esac
  done

  printf "%s\n\n" "## Deleting an existing AWS Amplify app"
  python3 ${PY_FILE} --region "${REGION}" --repo "${GIT_REPO}" --deploy_env "${DEPLOY_ENV}"
}

main "$@"

#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Delete an existing SNS platform application.

    Arguments:

      -h      Show help info.

      -d      The deployment environment for the SNS platform application (e.g. 'prod', 'perform', etc.).

      -g      The git repo name to use in the SNS platform application name (e.g. 'dog-gw').

      -r      The AWS region in which to delete the SNS platform application (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./aws-delete-sns-mob-push.sh -r \"eu-west-2\" -g \"dog-gw\" -d \"dev\"
    ./aws-delete-sns-mob-push.sh -r \"eu-west-2\" -g \"dog-spain-gw\" -d \"staging\"
    ./aws-delete-sns-mob-push.sh -r \"eu-west-2\" -g \"dog-gw\" -d \"sihp\"
    ./aws-delete-sns-mob-push.sh -r \"eu-west-2\" -g \"cat-gw\" -d \"uat\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="aws-delete-sns-mob-push"
  PY_FILE="${FILENAME}.py"

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
  elif [[ "${GIT_REPO}" == *"base"* ]]; then
    while true; do
      echo ""
      read -r -p "Warning: You've specified a 'base' git repo name (for deleting an existing SNS platform application). Are you sure you'd like to continue: '${GIT_TAG}' ? [y/n] " yn
      case $yn in
      [Yy]*) echo "... Continuing" && break ;;
      [Nn]*) echo "... Exiting script" && exit 1 ;;
      *) printf "\n%s\n" "Please answer [y/n]." ;;
      esac
    done
  fi

  if [[ -z "${DEPLOY_ENV}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-d' required." "${EXAMPLE_DESC_DEPLOY_ENV}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  printf "%s\n\n" "## Deleting an existing SNS platform application"
  python3 ${PY_FILE} --region "${REGION}" --repo "${GIT_REPO}" --deploy_env "${DEPLOY_ENV}"
}

main "$@"

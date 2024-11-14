#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Create an MS Teams notifications setup, for an existing AWS Amplify app.

    IMPORTANT: After running this script..
      1) Go to SNS service in the AWS management console.
      2) Using the AWS Amplify app ID, search for the default SNS topic for the AWS Amplify app.
      3) Under the SNS topic summary, go to 'Subscriptions'.
      4) Delete the SNS topic subscription where:
        {\"Endpoint\": <EMAIL_ADDRESS>, \"Status\": \"Confirmed\", \"Protocol\": \"EMAIL\"}

        NB. If {\"Status\": \"Pending confirmation\"}, you'll have to confirm the SNS topic subscription,
        before deleting, by clicking the link in the email (sent to: <EMAIL_ADDRESS>):
        {\"Subject\": \"AWS Notification - Subscription Confirmation\"}

    Arguments:

      -h      Show help info.

      -d      The deployment environment for the AWS Amplify app (e.g. 'prod', 'perform', etc.).

      -g      The git repo name to use in the AWS Amplify app name, and needed to connect to Bitbucket (e.g. 'dog-portal').

      -r      The AWS region in which to create the AWS Amplify app (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./aws-create-amplify-notifications.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"dev\"
    ./aws-create-amplify-notifications.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"staging\"
    ./aws-create-amplify-notifications.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"sih-demo\"
    ./aws-create-amplify-notifications.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"europa-preview\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME_BASE="aws-create-amplify"
  PY_FILE="${FILENAME_BASE}.py"
  FILENAME="${FILENAME_BASE}-notifications"
  AMPLIFY_RES="${FILENAME}-amplify-res.json"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_GIT_REPO="For example: -g \"git-repo-name\""
  EXAMPLE_DESC_DEPLOY_ENV="For example: -d \"deploy-env\""
  HELP_DESC="See help info with '-h' option"

  DEPLOY_ENV=""
  GIT_REPO=""
  REGION=""

  while getopts ":hd:g:t:r:s:w:" arg; do
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
      read -r -p "Warning: You've specified a 'base' git repo name (for creating a front-end AWS Amplify app). Are you sure you'd like to continue: '${GIT_TAG}' ? [y/n] " yn
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

  if test -f ${AMPLIFY_RES}; then
    rm ${AMPLIFY_RES}
  fi

  printf "%s\n\n" "## Creating an MS Teams notifications setup for an AWS Amplify app"
  python3 ${PY_FILE} --region "${REGION}" --repo "${GIT_REPO}" --deploy_env "${DEPLOY_ENV}" --notifications
}

main "$@"

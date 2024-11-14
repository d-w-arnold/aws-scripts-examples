#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Create a new AWS Amplify app.

    IMPORTANT: After running this script..
      1) Go to AWS Amplify service in the AWS management console.
      2) Under the newly create AWS Amplify app summary, go to 'App settings: Notifications'.
      3) Add a new Notification (which behind the scenes is an SNS topic subscription):
        {\"Email\": <EMAIL_ADDRESS>, \"Branch\": \"All Branches\"}
        - this causes AWS Amplify to auto create a default SNS topic for the AWS Amplify app.
      4) Confirm the SNS topic subscription, by clicking the link in the email (sent to: <EMAIL_ADDRESS>):
        {\"Subject\": \"AWS Notification - Subscription Confirmation\"}
      4) Run the \`aws-create/aws-create-amplify-notifications.sh\` script.

    Arguments:

      -h      Show help info.

      -c      An optional custom image tag to use for the AWS Amplify app build settings custom image (e.g. '18.17.1').

      -d      The deployment environment for the AWS Amplify app (e.g. 'prod', 'perform', etc.).

      -g      The git repo name to use in the AWS Amplify app name, and needed to connect to Bitbucket (e.g. 'dog-portal').

      -r      The AWS region in which to create the AWS Amplify app (e.g. 'eu-west-2').

      -s      An optional back-end (AWS CDK) stack name, used to reference a back-end URL for
                the AWS Amplify app to use (e.g. 'CdkDogGwStagingStack', which would be
                used to find the back-end URL: 'https://gw.staging.dog.com/').

              By default, the back-end URL defaults to a URL based on the '-g' and '-d' options.

              For example: if git repo name is 'dog-portal' and the deployment environment is 'dev',
              the back-end URL defaults to the retrieved URL from the
              CdkDogGwDevStack (AWS CDK) stack CloudFormation output
              (e.g. '{\"CdkdoggwdevurlCfnOutput\":, \"https://gw.dev.dog.com/\"}').

      -t      An optional deployment git tag, to set in the AWS Amplify app DEPLOY_TAG environment variable (e.g. suggested format: 'YYMMDD.<PROD_DEPLOY_NO>').

      -w      An optional domain name to use for the front-end URL, instead of inferring the domain name
                from the back-end URL for the AWS Amplify app (e.g. 'example.com').

              By default, the domain name to use for the front-end URL is inferred for the back-end URL.

              For example:
                - if the back-end URL defaults to 'https://gw.staging.dog.com/'
                - the git repo name is 'horse-spain-portal'
                - the deployment environment is 'dev'
              the front end URL would be:
                'https://portal.dev.spain.dog.com/'
              though by additionally specifying:
                - an optional domain name 'horse.it'
              the front-end URL would be:
                'https://portal.dev.spain.horse.it/'

    Arguments:

    Example usages:

    ./aws-create-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"dev\"
    ./aws-create-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"prod\" -t \"220727.1\"
    ./aws-create-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"sih-demo\" -t \"sihd\"
    ./aws-create-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"sih-preview\" -t \"sihp\" -c \"18.17.1\"
    ./aws-create-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"europa-preview\" -t \"europa\"
    ./aws-create-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"staging\" -s \"CdkDogGwDevStack\"
    ./aws-create-amplify.sh -r \"eu-west-2\" -g \"horse-portal\" -d \"dev\" -s \"CdkDogGwStagingStack\" -w \"horse.it\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  AWS_AMPLIFY="aws-amplify"
  FILENAME="aws-create-amplify"
  PY_FILE="${FILENAME}.py"
  AMPLIFY_RES="${FILENAME}-amplify-res.json"
  OAUTH_TOKEN_CURL_CMD_FILE="${FILENAME}-oauth-token-curl-cmd.txt"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_GIT_REPO="For example: -g \"git-repo-name\""
  EXAMPLE_DESC_DEPLOY_ENV="For example: -d \"deploy-env\""
  HELP_DESC="See help info with '-h' option"

  DEPLOY_ENV=""
  GIT_REPO=""
  GIT_TAG=""
  REGION=""
  BACK_END_CDK_STACK=""
  CUSTOM_IMAGE_TAG=""
  DOMAIN_NAME=""

  while getopts ":hd:g:t:r:s:c:w:" arg; do
    case $arg in
    h) usage ;;
    d) DEPLOY_ENV="${OPTARG}" ;;
    g) GIT_REPO="${OPTARG}" ;;
    t) GIT_TAG="${OPTARG}" ;;
    r) REGION="${OPTARG}" ;;
    s) BACK_END_CDK_STACK="${OPTARG}" ;;
    c) CUSTOM_IMAGE_TAG="${OPTARG}" ;;
    w) DOMAIN_NAME="${OPTARG}" ;;
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

  if [[ -n "${GIT_TAG}" ]]; then
    while true; do
      echo ""
      read -r -p "Are you sure you'd like to set the deployment git tag: '${GIT_TAG}' ? [y/n] " yn
      case $yn in
      [Yy]*) echo "... Confirmed" && break ;;
      [Nn]*) echo "... Exiting script" && exit 1 ;;
      *) printf "\n%s\n" "Please answer [y/n]." ;;
      esac
    done
  fi

  printf "%s\n\n" "## Collecting '${OAUTH_TOKEN_CURL_CMD_FILE}' data using '${PY_FILE}' script"
  python3 ${PY_FILE} --region "${REGION}" --oauth

  OAUTH_TOKEN_CURL_CMD="$(cat ${OAUTH_TOKEN_CURL_CMD_FILE})"
  OAUTH_RES="$(eval "${OAUTH_TOKEN_CURL_CMD}")"

  rm ${OAUTH_TOKEN_CURL_CMD_FILE}

  if test -f ${AMPLIFY_RES}; then
    rm ${AMPLIFY_RES}
  fi

  SAVED_PWD=$(pwd)
  mkdir -p tmp
  cd tmp
  if [ -d "${AWS_AMPLIFY}" ]; then
    rm -rf "${AWS_AMPLIFY}"
  fi
  git clone "git@bitbucket.org:foobar-infrastructure-innovation/${AWS_AMPLIFY}.git"
  cd "${AWS_AMPLIFY}"

  GIT_REPO_PWD=$(pwd)

  printf "\n%s\n\n" "## Git repo pwd: ${GIT_REPO_PWD}"

  cd "${SAVED_PWD}"

  if [[ -z "${GIT_TAG}" ]]; then
    printf "%s\n\n" "## Creating a new AWS Amplify app"
    python3 ${PY_FILE} --region "${REGION}" --repo "${GIT_REPO}" --deploy_env "${DEPLOY_ENV}" --oauth_res "${OAUTH_RES}" --back_end_cdk_stack "${BACK_END_CDK_STACK}" --custom_image_tag "${CUSTOM_IMAGE_TAG}" --domain_name "${DOMAIN_NAME}" --pwd "${GIT_REPO_PWD}"
  else
    printf "%s\n\n" "## Creating a new AWS Amplify app, with deployment git tag: ${GIT_TAG}"
    python3 ${PY_FILE} --region "${REGION}" --repo "${GIT_REPO}" --deploy_env "${DEPLOY_ENV}" --oauth_res "${OAUTH_RES}" --back_end_cdk_stack "${BACK_END_CDK_STACK}" --custom_image_tag "${CUSTOM_IMAGE_TAG}" --domain_name "${DOMAIN_NAME}" --pwd "${GIT_REPO_PWD}" --tag "${GIT_TAG}"
  fi

  rm -rf tmp
}

main "$@"

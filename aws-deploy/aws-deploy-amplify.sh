#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Git tag a new commit, and deploy (release) changes via the corresponding AWS Amplify app build pipeline.

    NB. Firstly, new git tag is applied to the HEAD commit of the specified git branch (in the specified git repo),
          then the AWS Amplify app DEPLOY_TAG environment variable is updated with the new git tag, acting as a deployment git tag ref/pointer
          for the corresponding AWS Amplify app build pipeline.

    Arguments:

      -h      Show help info.

      -d      The deployment environment to deploy (release) changes to (e.g. 'prod', 'perform', etc.).

      -g      The git repo name to checkout, in order to apply the new git tag (e.g. 'dog-portal').

      -t      The git tag, to add to the latest commit, of the git repo branch (e.g. suggested format: 'YYMMDD.<PROD_DEPLOY_NO>').

      -r      The AWS region in which the AWS Amplify app resides (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./aws-deploy-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"prod\" -t \"220727.1\"
    ./aws-deploy-amplify.sh -r \"eu-west-2\" -g \"dog-portal-base\" -d \"prod\" -t \"220727.1\"
    ./aws-deploy-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"uat-preview\" -t \"uat\"
    ./aws-deploy-amplify.sh -r \"eu-west-2\" -g \"dog-portal\" -d \"sih-demo\" -t \"sihd\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="aws-deploy"
  PY_FILE="${FILENAME}.py"
  GIT_REPO_FILE="${FILENAME}-git-repo.txt"
  GIT_BRANCH_FILE="${FILENAME}-git-branch.txt"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_GIT_REPO="For example: -g \"git-repo-name\""
  EXAMPLE_DESC_DEPLOY_ENV="For example: -d \"deploy-env\""
  EXAMPLE_DESC_GIT_TAG="For example: -t \"220727.1\""
  HELP_DESC="See help info with '-h' option"

  GIT_TAG=""
  DEPLOY_ENV=""
  GIT_REPO=""
  REGION=""

  while getopts ":hd:g:t:r:" arg; do
    case $arg in
    h) usage ;;
    d) DEPLOY_ENV="${OPTARG}" ;;
    g) GIT_REPO="${OPTARG}" ;;
    t) GIT_TAG="${OPTARG}" ;;
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

  IS_PROD=0
  if [[ -z "${DEPLOY_ENV}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-d' required." "${EXAMPLE_DESC_DEPLOY_ENV}" "${HELP_DESC}" 1>&2
    exit 1
  elif [[ "${DEPLOY_ENV}" == "prod" ]]; then
    IS_PROD=1
    while true; do
      echo ""
      read -r -p "Are you sure you'd like to apply the new git tag: '${GIT_TAG}' ? [y/n] " yn
      case $yn in
      [Yy]*) echo "... Confirmed" && break ;;
      [Nn]*) echo "... Exiting script" && exit 1 ;;
      *) printf "\n%s\n" "Please answer [y/n]." ;;
      esac
    done
  fi

  if [[ -z "${GIT_TAG}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-t' required." "${EXAMPLE_DESC_GIT_TAG}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  printf "%s\n\n" "## Collecting '${GIT_REPO_FILE}' and '${GIT_BRANCH_FILE}' data using '${PY_FILE}' script"
  python3 ${PY_FILE} --repo "${GIT_REPO}" --deploy_env "${DEPLOY_ENV}" --ssh

  GIT_REPO_SSH="$(cat ${GIT_REPO_FILE})"
  GIT_BRANCH="$(cat ${GIT_BRANCH_FILE})"
  SAVED_PWD=$(pwd)
  mkdir -p tmp
  cd tmp
  if [ -d "${GIT_REPO}" ]; then
    rm -rf "${GIT_REPO}"
  fi
  git clone "${GIT_REPO_SSH}"
  cd "${GIT_REPO}"
  git checkout "${GIT_BRANCH}"
  # shellcheck disable=SC2046
  if [ $(git tag -l "${GIT_TAG}") ]; then
    if [[ "${IS_PROD}" -eq 1 ]]; then
      printf "%s\n\n" "ERROR: Git tag: '${GIT_TAG}', already exists for: ${GIT_REPO}-${DEPLOY_ENV}" 1>&2
      exit 1
    fi
    git tag --delete "${GIT_TAG}"
    git push origin --delete "${GIT_TAG}"
  fi
  git tag "${GIT_TAG}"
  git push origin "${GIT_TAG}"
  COMMIT_ID="$(git rev-list -n 1 "${GIT_TAG}")"
  COMMIT_MSG="$( git log --format=%B -n 1 "${COMMIT_ID}")"

  GIT_REPO_PWD=$(pwd)

  printf "\n%s\n\n" "## Git repo pwd: ${GIT_REPO_PWD}"

  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query "Account" --output text)"

  cd "${SAVED_PWD}"

  rm -rf tmp

  printf "%s\n\n" "## Updating AWS Amplify app DEPLOY_TAG environment variable with the new deployment git tag, and releasing changes on AWS Amplify app build pipeline"
  python3 ${PY_FILE} --repo "${GIT_REPO}" --deploy_env "${DEPLOY_ENV}" --region "${REGION}" --account "${AWS_ACCOUNT_ID}" --branch "${GIT_BRANCH}" --tag "${GIT_TAG}" --commit_id "${COMMIT_ID}" --commit_msg "${COMMIT_MSG}" --amplify
}

main "$@"

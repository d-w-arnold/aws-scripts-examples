#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Git tag a new commit, and deploy (release) changes via Fastlane for prod release to public app stores.

    NB. Firstly, new git tag is applied to the HEAD commit of the specified git branch (in the specified git repo),
          then AWS Systems Manager Parameter Store is updated with the new git tag, acting as a deployment git tag ref/pointer
          for future reference.

    Arguments:

      -h      Show help info.

      -g      The git repo name to checkout, in order to apply the new git tag (e.g. 'cat-mobile').

      -t      The git tag, to add to the latest commit, of the git repo branch (e.g. suggested format: 'YYMMDD.<PROD_DEPLOY_NO>').

      -r      The AWS region in which the AWS Systems Manager Parameter Store parameter resides (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./react-native-prod-release.sh -r \"eu-west-2\" -g \"cat-mobile\" -t \"240727.1\"
    ./react-native-prod-release.sh -r \"eu-west-2\" -g \"cat-mobile\" -t \"240730.1\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="react-native-prod-release"
  PY_FILE="${FILENAME}.py"
  GIT_REPO_FILE="${FILENAME}-git-repo.txt"
  GIT_BRANCH_FILE="${FILENAME}-git-branch.txt"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_GIT_REPO="For example: -g \"git-repo-name\""
  EXAMPLE_DESC_GIT_TAG="For example: -t \"240727.1\""
  HELP_DESC="See help info with '-h' option"

  GIT_TAG=""
  GIT_REPO=""
  REGION=""

  while getopts ":hg:t:r:" arg; do
    case $arg in
    h) usage ;;
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

  if [[ -z "${GIT_TAG}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-t' required." "${EXAMPLE_DESC_GIT_TAG}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  printf "%s\n\n" "## Collecting '${GIT_REPO_FILE}' and '${GIT_BRANCH_FILE}' data using '${PY_FILE}' script"
  python3 ${PY_FILE} --repo "${GIT_REPO}" --ssh

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
      printf "%s\n\n" "ERROR: Git tag: '${GIT_TAG}', already exists for: ${GIT_REPO}" 1>&2
      exit 1
    fi
    git tag --delete "${GIT_TAG}"
    git push origin --delete "${GIT_TAG}"
  fi
  git tag "${GIT_TAG}"
  git push origin "${GIT_TAG}"

  GIT_REPO_PWD=$(pwd)

  printf "\n%s\n\n" "## Git repo pwd: ${GIT_REPO_PWD}"

  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query "Account" --output text)"

  # TODO: (NEXT) Add Fastlane steps for prod release to public app stores - NB. At this stage in the script, we are still in the checked out git repo.

  cd "${SAVED_PWD}"

  rm -rf tmp

  printf "%s\n\n" "## Updating AWS Systems Manager Parameter Store with the new deployment git tag"
  python3 ${PY_FILE} --repo "${GIT_REPO}" --region "${REGION}" --account "${AWS_ACCOUNT_ID}" --tag "${GIT_TAG}"

}

main "$@"

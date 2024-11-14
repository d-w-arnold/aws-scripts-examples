#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Delete an existing CodeArtifact repository, for storing of npm packages.

    Arguments:

      -h      Show help info.

      -d      The domain for the CodeArtifact repository to be deleted, if unspecified the default domain is used.

      -g      The git repo name to use in the CodeArtifact repository name (e.g. 'react-native-foobar-bundlekit').

      -r      The AWS region in which to delete the CodeArtifact repository (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./aws-delete-codeartifact.sh -r \"eu-west-2\" -g \"react-native-foobar-bundlekit\"
    ./aws-delete-codeartifact.sh -r \"eu-west-2\" -g \"react-native-foobar-bundlekit\" -d \"mydomain\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="aws-delete-codeartifact"
  PY_FILE="${FILENAME}.py"

  DOMAIN=""
  GIT_REPO=""
  REGION=""

  while getopts ":hd:g:r:" arg; do
    case $arg in
    h) usage ;;
    d) DOMAIN="${OPTARG}" ;;
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
      read -r -p "Warning: You've specified a 'base' git repo name (for deleting an existing CodeArtifact repository). Are you sure you'd like to continue: '${GIT_TAG}' ? [y/n] " yn
      case $yn in
      [Yy]*) echo "... Continuing" && break ;;
      [Nn]*) echo "... Exiting script" && exit 1 ;;
      *) printf "\n%s\n" "Please answer [y/n]." ;;
      esac
    done
  fi

  if [[ -z "${DOMAIN}" ]]; then
    printf "%s\n\n" "## Deleting an existing CodeArtifact repository"
    python3 ${PY_FILE} --region "${REGION}" --repo "${GIT_REPO}"
  else
    printf "%s\n\n" "## Deleting an existing CodeArtifact repository, with custom CodeArtifact domain: ${DOMAIN}"
    python3 ${PY_FILE} --region "${REGION}" --repo "${GIT_REPO}" --domain "${DOMAIN}"
  fi
}

main "$@"

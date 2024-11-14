#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Connect to private AWS ECS resources.

    IMPORTANT: Please ensure you're connected to the Foobar VPN, if you're
      having difficulties connecting to any of the ECS containers.

    Arguments:

      -h      Show help info.

      -l      List all private AWS resource identifiers as possible args for this script.

      -r      The AWS region in which the private AWS resources reside (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./aws-private-ecs.sh -r \"eu-west-2\" -l

    ./aws-private-ecs.sh -r \"eu-west-2\" dog-gw-dev-ecs
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
# (2) - SSH Identity file doesn't exists
#
main() {
  FILENAME="aws-private"
  PY_FILE="${FILENAME}.py"
  FILENAME_ECS="${FILENAME}-ecs"
  JSON_FILE="${FILENAME_ECS}.json"
  ECS_CLUSTER_FILE="${FILENAME_ECS}-cluster.txt"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  HELP_DESC="See help info with '-h' option"

  LIST=0
  REGION=""

  while getopts ":hi:lr:" arg; do
    case $arg in
    h) usage ;;
    l) LIST=1 ;;
    r) REGION="${OPTARG}" ;;
    *) usage ;;
    esac
  done
  shift $((OPTIND - 1))

  if [[ -z "${REGION}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-r' required." "${EXAMPLE_DESC_REGION}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  printf "%s\n\n" "## Collecting '${JSON_FILE}' data using '${PY_FILE}' script"
  python3 ${PY_FILE} --region "${REGION}" --ecs

  if [[ "${LIST}" -eq 1 ]]; then
    python3 ${PY_FILE} --region "${REGION}" --list --ecs
  else
    printf "%s\n\n" "## Collecting '${ECS_CLUSTER_FILE}' data using '${PY_FILE}' script"
    python3 ${PY_FILE} --region "${REGION}" --cluster "$1"

    ECS_CLUSTER_ARN="$(cat ${ECS_CLUSTER_FILE})"
    printf "%s\n\n" "## ECS Cluster ARN: ${ECS_CLUSTER_ARN}"

    ECS_TASK_ARN="$(aws ecs list-tasks --region "${REGION}" --cluster "${ECS_CLUSTER_ARN}" --query "taskArns[0]" --output text)"
    printf "%s\n\n" "## ECS Task ARN: ${ECS_TASK_ARN}"

    ECS_CONTAINER_NAME="$(aws ecs describe-tasks --region "${REGION}" --cluster "${ECS_CLUSTER_ARN}" --tasks "${ECS_TASK_ARN}" --query "tasks[0].containers[0].name" --output text)"
    printf "%s\n\n" "## ECS Container Name: ${ECS_CONTAINER_NAME}"

    COMMAND="/bin/bash"
    ECS_EXEC_COMMAND="aws ecs execute-command --cluster ${ECS_CLUSTER_ARN} --task ${ECS_TASK_ARN} --container ${ECS_CONTAINER_NAME} --interactive --command ${COMMAND}"

    printf "%s\n\n" "## Running ECS Exec command: ${ECS_EXEC_COMMAND}"

    printf "%s\n\n" "## Connecting to ECS container (${ECS_CONTAINER_NAME}) ..."

    eval "$ECS_EXEC_COMMAND"
  fi
}

main "$@"

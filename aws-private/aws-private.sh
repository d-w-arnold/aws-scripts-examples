#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Connect to private AWS resources.

    IMPORTANT: Please ensure you're connected to the Foobar VPN, if you're
      having difficulties connecting to any of the Bastion Hosts.

    Arguments:

      -h      Show help info.

      -i      The SSH identify file path to use for connecting to a Bastion Host
              (e.g. '/path/key-pair.pem' ).

      -l      List all private AWS resource identifiers as possible args for this script.

      -r      The AWS region in which the private AWS resources reside (e.g. 'eu-west-2').

              By default, a Bastion Host in a random availability zone (AZ), within an
              AWS region, is chosen.

              Pro Tip: If you require a Bastion Host in a specific AZ, within an AWS region,
              you can specify the AZ of the Bastion Host instead (e.g. 'eu-west-2a' ).

    Arguments:

    Example usages:

    ./aws-private.sh -r \"eu-west-2\" -l

    ./aws-private.sh -r \"eu-west-2\" -i \"/path/key-pair.pem\" rds-mysql/dog-gw-staging

    ./aws-private.sh -r \"eu-west-2a\" -i \"/path/key-pair.pem\" rds-mysql/dog-gw-staging

    ./aws-private.sh -r \"eu-west-2\" -i \"/path/key-pair.pem\" rds-mysql/dog-gw-staging rds-mysql/dog-gw-dev

    ./aws-private.sh -r \"eu-west-2c\" -i \"/path/key-pair.pem\" rds-mysql/dog-gw-staging rds-mysql/dog-gw-dev
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
  JSON_FILE="${FILENAME}.json"
  BASTION_AZ_FILE="${FILENAME}-bastion-az.txt"
  BASTION_ID_FILE="${FILENAME}-bastion-id.txt"
  COMMAND_FILE="${FILENAME}-command.txt"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_IDENT="For example: -i \"/path/key-pair.pem\""
  HELP_DESC="See help info with '-h' option"

  LIST=0
  REGION=""
  PEM_FILE_PATH=""

  while getopts ":hi:lr:" arg; do
    case $arg in
    h) usage ;;
    i) PEM_FILE_PATH="${OPTARG}" ;;
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
  python3 ${PY_FILE} --region "${REGION}"

  if [[ "${LIST}" -eq 1 ]]; then
    python3 ${PY_FILE} --region "${REGION}" --list
  else
    if [[ -z "${PEM_FILE_PATH}" ]]; then
      printf "%s\n%s\n%s\n\n" "ERROR: Option '-i' required." "${EXAMPLE_DESC_IDENT}" "${HELP_DESC}" 1>&2
      exit 1
    fi

    if [ ! -f "${PEM_FILE_PATH/#\~/$HOME}" ]; then
      printf "%s\n\n" "ERROR: The SSH identify file path '${PEM_FILE_PATH}' does not exist." 1>&2
      exit 2
    fi

    printf "%s\n\n" "## Collecting '${BASTION_AZ_FILE}' and '${BASTION_ID_FILE}' data using '${PY_FILE}' script"
    python3 ${PY_FILE} --region "${REGION}" --bastion

    if test -f ${COMMAND_FILE}; then
      rm ${COMMAND_FILE}
    fi

    printf "%s\n\n" "## Collecting '${COMMAND_FILE}' data using '${PY_FILE}' script"
    python3 ${PY_FILE} --region "${REGION}" --command "$@"

    BASTION_HOST_AZ="$(cat ${BASTION_AZ_FILE})"
    BASTION_HOST_INSTANCE_ID="$(cat ${BASTION_ID_FILE})"
    SSH_COMMAND="ssh -i ${PEM_FILE_PATH} ec2-user@${BASTION_HOST_INSTANCE_ID}"
    while read -r LINE; do
      SSH_COMMAND="${SSH_COMMAND} -L ${LINE}"
    done <${COMMAND_FILE}

    printf "%s\n\n" "## Running SSH command: ${SSH_COMMAND}"

    printf "%s\n\n" "## Connecting to Bastion Host (${BASTION_HOST_AZ}) ..."

    eval "$SSH_COMMAND"
  fi
}

main "$@"

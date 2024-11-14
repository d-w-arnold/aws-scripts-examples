#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Invoke an RDS init Lambda function for a specific DB server.

    IMPORTANT: If SQL files have been added/amended via a Bitbucket PR,
      look to use the \`s3-upload/s3-upload.sh\` script first. As this script
      uses SQL files from the corresponding project (static) S3 bucket.

    Arguments:

      -h      Show help info.

      -a      The action type for modifying each DB schema (valid options: 'INCREMENT', 'RESET').

      -d      The DB schemas to be modified (e.g. 'dog_gw_dev,dog_gw_staging' - can be a comma-separated list, with no spaces).

      -f      The name of the RDS init Lambda function to invoke (e.g. 'lambda-function-name').

      -g      An optional git repo name to be used as an alternative to the default project name.

      -l      List all RDS init Lambda function names as possible args for this script.

      -p      The relative file path, from the git repo root directory, of the SQL filename used to modify each DB schema (e.g. 'mysql/data/all.sql').

      -r      The AWS region in which RDS init Lambda function resides (e.g. 'eu-west-2').

    Arguments:

    Example usages:

    ./rds-init.sh -r \"eu-west-2\" -l

    ./rds-init.sh -r \"eu-west-2\" -f \"RDSInit-dog-gw-DEV-STAGING\" -a \"RESET\" -d \"dog_gw_dev\" -p \"mysql/structure/schema_initial.sql\"

    ./rds-init.sh -r \"eu-west-2\" -f \"RDSInit-dog-gw-PROD\" -a \"INCREMENT\" -d \"dog_gw_prod\" -p \"mysql/data/all.sql\"

    ./rds-init.sh -r \"eu-west-2\" -f \"RDSInit-dog-gw-PREVIEW-DEMO\" -a \"INCREMENT\" -d \"dog_gw_sihp\" -p \"mysql/data/all.sql\"

    ./rds-init.sh -r \"eu-west-2\" -f \"RDSInit-dog-gw-PREVIEW-DEMO\" -a \"INCREMENT\" -d \"dog_gw_uat\" -p \"mysql/data/all.sql\"

    ./rds-init.sh -r \"eu-west-2\" -f \"RDSInit-dog-gw-DEV-STAGING\" -a \"RESET\" -d \"dog_gw_dev,dog_gw_staging\" -p \"mysql/structure/schema_initial.sql\"

    ./rds-init.sh -r \"eu-west-2\" -f \"RDSInit-dog-custom-gw-DEV-STAGING\" -g \"dog-spain-gw\" -a \"RESET\" -d \"dog_spain_gw_staging\" -p \"mysql/structure/schema_initial.sql\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="rds-init"
  PY_FILE="${FILENAME}.py"

  LAMBDA_FUNCTION_SUB_STR="RDSInit"
  LAMBDA_FUNCTION_SUB_STR_AVOID="custom-resource"

  EXAMPLE_DESC_REGION="For example: -r \"eu-west-2\""
  EXAMPLE_DESC_ACTION="For example: -a \"INCREMENT\" (valid options: \"INCREMENT\", \"RESET\")"
  EXAMPLE_DESC_DB_SCHEMAS="For example: -d \"dog_gw_dev,dog_gw_staging\""
  EXAMPLE_DESC_FUNCTION_NAME="For example: -f \"lambda-function-name\""
  EXAMPLE_DESC_SQL_FILENAME="For example: -p \"schema_full.sql\""
  HELP_DESC="See help info with '-h' option"

  LIST=0
  REGION=""
  ACTION=""
  DB_SCHEMAS=""
  FUNCTION_NAME=""
  GIT_REPO=""
  SQL_FILENAME=""

  while getopts ":ha:d:f:g:lp:r:" arg; do
    case $arg in
    h) usage ;;
    a) ACTION="${OPTARG}" ;;
    d) DB_SCHEMAS="${OPTARG}" ;;
    f) FUNCTION_NAME="${OPTARG}" ;;
    g) GIT_REPO="${OPTARG}" ;;
    l) LIST=1 ;;
    p) SQL_FILENAME="${OPTARG}" ;;
    r) REGION="${OPTARG}" ;;
    *) usage ;;
    esac
  done
  shift $((OPTIND - 1))

  if [[ -z "${REGION}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-r' required." "${EXAMPLE_DESC_REGION}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  if [[ "${LIST}" -eq 1 ]]; then
    LAMBDA_FUNCTION_NAMES=$(aws lambda list-functions --query "Functions[? FunctionName!=null]|[? contains(FunctionName,'${LAMBDA_FUNCTION_SUB_STR}')]|[? !(contains(FunctionName, '${LAMBDA_FUNCTION_SUB_STR_AVOID}'))].FunctionName" --output text)
    printf "%s\n" "## Lambda function options:"
    for LAMBDA_FUNCTION_NAME in ${LAMBDA_FUNCTION_NAMES}; do
      if [[ ${LAMBDA_FUNCTION_NAME} != *"CWMsTeamsNotif"* ]]; then
        printf "%s\t%s\n" "##" "${LAMBDA_FUNCTION_NAME}"
      fi
    done
  else
    if [[ -z "${FUNCTION_NAME}" ]]; then
      printf "%s\n%s\n%s\n\n" "ERROR: Option '-f' required." "${EXAMPLE_DESC_FUNCTION_NAME}" "${HELP_DESC}" 1>&2
      exit 1
    fi

    if [[ -z "${DB_SCHEMAS}" ]]; then
      printf "%s\n%s\n%s\n\n" "ERROR: Option '-d' required." "${EXAMPLE_DESC_DB_SCHEMAS}" "${HELP_DESC}" 1>&2
      exit 1
    fi

    if [[ -z "${ACTION}" ]]; then
      printf "%s\n%s\n%s\n\n" "ERROR: Option '-a' required." "${EXAMPLE_DESC_ACTION}" "${HELP_DESC}" 1>&2
      exit 1
    elif [[ "${ACTION}" == "RESET" ]]; then
      while true; do
        echo ""
        read -r -p "Are you sure you'd like to ${ACTION} the following DB schemas: ${DB_SCHEMAS} ? [y/n] " yn
        case $yn in
        [Yy]*) echo "... Confirmed" && break ;;
        [Nn]*) echo "... Exiting script" && exit 1 ;;
        *) printf "\n%s\n" "Please answer [y/n]." ;;
        esac
      done
    fi

    if [[ -z "${SQL_FILENAME}" ]]; then
      printf "%s\n%s\n%s\n\n" "ERROR: Option '-p' required." "${EXAMPLE_DESC_SQL_FILENAME}" "${HELP_DESC}" 1>&2
      exit 1
    fi

    printf "%s\n\n" "## Running '${PY_FILE}' script"
    if [[ -z "${GIT_REPO}" ]]; then
      python3 ${PY_FILE} --region "${REGION}" --function_name "${FUNCTION_NAME}" --payload_action "${ACTION}" --payload_db_schemas "${DB_SCHEMAS}" --payload_sql_filename "${SQL_FILENAME}"
    else
      python3 ${PY_FILE} --region "${REGION}" --function_name "${FUNCTION_NAME}" --payload_project_name "${GIT_REPO}" --payload_action "${ACTION}" --payload_db_schemas "${DB_SCHEMAS}" --payload_sql_filename "${SQL_FILENAME}"
    fi
    date
  fi
}

main "$@"

#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

usage() {
  echo "
    Backup all AWS S3 Buckets matching a name prefix.

    Arguments:

      -h      Show help info.

      -b      The AWS S3 Bucket name prefix (e.g. 'doggwprod-eu-west-2-').

      -x      An optional flag to convert all S3 objects from: base64 -> PNG

    Arguments:

    Example usages:

    ./s3-backup.sh -b \"doggwprod-eu-west-2-\"
  "
  exit 0
}

# Exit codes:
# (1) - Invalid arguments specified.
#
main() {
  FILENAME="s3-backup"
  PY_FILE="${FILENAME}.py"
  SEP="_"
  BUCKETS_STR="buckets"
  ALT_SUFFIX="base64"

  EXAMPLE_DESC_S3_BUCKET_NAME_PREFIX="For example: -b \"doggwprod-eu-west-2-\""
  HELP_DESC="See help info with '-h' option"

  BASE64_TO_PNG=0
  S3_BUCKET_NAME_PREFIX=""

  while getopts ":hb:x" arg; do
    case $arg in
    h) usage ;;
    b) S3_BUCKET_NAME_PREFIX="${OPTARG}" ;;
    x) BASE64_TO_PNG=1 ;;
    *) usage ;;
    esac
  done
  shift $((OPTIND - 1))

  if [[ -z "${S3_BUCKET_NAME_PREFIX}" ]]; then
    printf "%s\n%s\n%s\n\n" "ERROR: Option '-b' required." "${EXAMPLE_DESC_S3_BUCKET_NAME_PREFIX}" "${HELP_DESC}" 1>&2
    exit 1
  fi

  DATE="$(python3 -c 'from datetime import datetime;print(datetime.today().strftime("%Y%m%d"))')"
  for i in $(aws s3 ls | awk '{print $3}' | grep "${S3_BUCKET_NAME_PREFIX}"); do
    BUCKET_DIR="${BUCKETS_STR}/${DATE}${SEP}${i}"
    if [ -d "${BUCKET_DIR}" ]; then
      rm -rf "${BUCKET_DIR}"
    fi
    mkdir -p "${BUCKET_DIR}"
    if [[ "${BASE64_TO_PNG}" -eq 1 ]]; then
      BUCKET_DIR_ALT="${BUCKET_DIR}${SEP}${ALT_SUFFIX}"
      if [ -d "${BUCKET_DIR_ALT}" ]; then
        rm -rf "${BUCKET_DIR_ALT}"
      fi
      mkdir -p "${BUCKET_DIR_ALT}"
      aws s3 sync "s3://${i}" "${BUCKET_DIR_ALT}"
      printf "%s\n\n" "## Convert all S3 objects from: base64 -> PNG, using '${PY_FILE}' script (source: '${BUCKET_DIR_ALT}' -> dest: '${BUCKET_DIR}')"
      python3 ${PY_FILE} --source "${BUCKET_DIR_ALT}" --dest "${BUCKET_DIR}"
      rm -rf "${BUCKET_DIR_ALT}"
    else
      aws s3 sync "s3://${i}" "${BUCKET_DIR}"
    fi
  done
}

main "$@"

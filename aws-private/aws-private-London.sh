#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

function main() {
  ./aws-private.sh -r eu-west-2 "$@"
}

main "$@"

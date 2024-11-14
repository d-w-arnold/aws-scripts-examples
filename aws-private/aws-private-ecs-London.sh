#!/bin/bash -e

# Strict Mode
set -euo pipefail
IFS=$'\n\t'

function main() {
  ./aws-private-ecs.sh -r eu-west-2 "$@"
}

main "$@"

#!/usr/bin/env bash
set -euo pipefail

# Usage: ./repeat_until_no_fail0.sh <command> [arg1 arg2 ...]
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <command> [args ...]" >&2
  exit 2
fi

while true; do
  "$@"

  if grep -q "FAIL=0" ./build/lowrisc_mocha_axi_ethernet_0/sim/coco.log; then
    echo "Found FAIL=0 in coco.log; repeating..."
  else
    echo "FAIL=0 not found in coco.log; exiting."
    exit 0
  fi
done

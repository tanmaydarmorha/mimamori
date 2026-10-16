#!/usr/bin/env bash
# Scripted, narrated demo: drives the real app in visible Chrome windows. See demo/README.md.
#
#   scripts/demo.sh                      # list the scenarios
#   scripts/demo.sh hero                 # one scenario
#   scripts/demo.sh all                  # reset the local stack, then every scenario in order
#   scripts/demo.sh hero --record --speed slow
#   scripts/demo.sh hero --url https://example.run.app
set -euo pipefail
cd "$(dirname "$0")/.."

fresh=0
args=()
url=""
all=0
while (($#)); do
  case "$1" in
    --fresh) fresh=1 ;;
    all) all=1; args+=("$1") ;;
    --url) url="${2:?--url needs a value}"; args+=("$1" "$2"); shift ;;
    *) args+=("$1") ;;
  esac
  shift
done

if [[ ! -d demo/node_modules/playwright ]]; then
  printf 'Demo dependencies are missing. Run: cd demo && npm ci\n' >&2
  exit 1
fi

# `hero` freezes the payee account for good, so a full run only works on a clean stack.
if ((all)) && [[ -z "$url" ]] && ! ((fresh)); then
  printf 'all: resetting the local stack first (hero freezes the payee account for good)\n'
  fresh=1
fi

if ((fresh)); then
  [[ -z "$url" ]] || { printf -- '--fresh resets the local stack, so it cannot be used with --url\n' >&2; exit 2; }
  scripts/dev.sh down --wipe
  scripts/dev.sh up
fi

cd demo
exec node run.mjs ${args[@]+"${args[@]}"}

#!/usr/bin/env bash
# Start, stop and inspect the local Mimamori stack.
#
#   scripts/dev.sh up            # Gemini on Vertex (default): needs gcloud ADC
#   scripts/dev.sh up --local    # everything local: Ollama gemma4:12b, no GCP
#   scripts/dev.sh down          # stop (add --wipe to also drop the emulator data)
#   scripts/dev.sh logs [svc…]   # follow logs, e.g. logs case-svc conversation-svc
#   scripts/dev.sh status        # containers and /healthz
#
# Env: MIMAMORI_GCP_PROJECT (default mimamori-proto-2026), MIMAMORI_COPILOT_BACKEND=ollama to keep
# the copilot on local Gemma while the rest uses Gemini.
set -euo pipefail

cd "$(dirname "$0")/.."

export MIMAMORI_GCP_PROJECT="${MIMAMORI_GCP_PROJECT:-mimamori-proto-2026}"
ADC="$HOME/.config/gcloud/application_default_credentials.json"
SERVICES=(core-bank-mock scoring case-svc conversation-svc web-ui)
# name:port, matching docker-compose.yml
HEALTH=(web-ui:8080 core-bank-mock:8081 scoring:8082 case-svc:8083 conversation-svc:8084)
MODE_FILE=.dev-mode   # remembers which compose files `up` used, so down/logs match

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mError: %s\033[0m\n' "$*" >&2; exit 1; }

compose_files() {
  local mode="${1:-$(cat "$MODE_FILE" 2>/dev/null || echo gemini)}"
  if [[ "$mode" == gemini ]]; then
    echo "-f docker-compose.yml -f docker-compose.gemini.yml"
  else
    echo "-f docker-compose.yml"
  fi
}

dc() { # shellcheck disable=SC2046
  docker compose $(compose_files "${DC_MODE:-}") "$@"
}

wait_for() { # url, label, seconds
  local url="$1" label="$2" tries="${3:-90}"
  for ((i = 0; i < tries; i++)); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then return 0; fi
    sleep 1
  done
  die "$label did not answer at $url after ${tries}s (try: scripts/dev.sh logs $label)"
}

check_prereqs() {
  local mode="$1"
  docker info >/dev/null 2>&1 || die "Docker is not running. Start Docker Desktop and retry."
  if [[ "$mode" == gemini ]]; then
    [[ -f "$ADC" ]] || die "No gcloud credentials. Run: gcloud auth application-default login"
    if command -v gcloud >/dev/null && ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
      die "gcloud credentials have expired. Run: gcloud auth application-default login"
    fi
  fi
  if [[ "$mode" == local || "${MIMAMORI_COPILOT_BACKEND:-}" == ollama ]]; then
    curl -fsS -o /dev/null http://localhost:11434/api/tags 2>/dev/null \
      || die "Ollama is not running. Run: ollama serve   (and once: ollama pull gemma4:12b)"
  fi
}

cmd_up() {
  local mode=gemini
  [[ "${1:-}" == --local ]] && mode=local
  check_prereqs "$mode"
  echo "$mode" >"$MODE_FILE"
  DC_MODE=$mode

  say "Mode: $mode$([[ $mode == gemini ]] && echo " (project $MIMAMORI_GCP_PROJECT)")"
  say "Starting the Firestore emulator"
  dc up -d firestore
  wait_for http://localhost:8086 firestore 60

  say "Seeding synthetic data"
  dc run --rm seed

  say "Building and starting the services (first build takes a few minutes)"
  dc up --build -d --no-deps "${SERVICES[@]}"

  say "Waiting for /healthz"
  for entry in "${HEALTH[@]}"; do
    wait_for "http://localhost:${entry#*:}/healthz" "${entry%%:*}" 120
    printf '    %-17s ok\n' "${entry%%:*}"
  done

  cat <<EOF

Ready.
  Teller console   http://localhost:8080        (role switch → analyst for the freeze)
  Simulated phone  http://localhost:8080/phone
  Logs             scripts/dev.sh logs case-svc conversation-svc
  Stop             scripts/dev.sh down
EOF
  if [[ "$(uname)" == Darwin && -z "${NO_OPEN:-}" ]]; then open http://localhost:8080 >/dev/null 2>&1 || true; fi
}

cmd_down() {
  if [[ "${1:-}" == --wipe ]]; then
    say "Stopping and removing the emulator data"
    dc down -v
  else
    say "Stopping"
    dc down
  fi
  rm -f "$MODE_FILE"
}

cmd_status() {
  dc ps
  echo
  for entry in "${HEALTH[@]}"; do
    if curl -fsS -o /dev/null "http://localhost:${entry#*:}/healthz" 2>/dev/null; then s=ok; else s=down; fi
    printf '%-17s %s\n' "${entry%%:*}" "$s"
  done
}

case "${1:-}" in
  up) shift; cmd_up "$@" ;;
  down) shift; cmd_down "$@" ;;
  logs) shift; dc logs -f "$@" ;;
  status) cmd_status ;;
  *) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac

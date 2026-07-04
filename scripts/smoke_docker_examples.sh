#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_PREFIX="${IMAGE_PREFIX:-env0-example}"
PULL_BASE="${PULL_BASE:-1}"

log() {
  printf '\n==> %s\n' "$*"
}

build_image() {
  local task="$1"
  local image="$IMAGE_PREFIX-$task:local"
  local dockerfile="$ROOT/example_tasks/$task/environment/Dockerfile"
  local build_args=()

  if [[ "$PULL_BASE" != "0" ]]; then
    build_args+=(--pull)
  fi

  log "build $task"
  if [[ ${#build_args[@]} -gt 0 ]]; then
    docker build "${build_args[@]}" -t "$image" -f "$dockerfile" "$ROOT"
  else
    docker build -t "$image" -f "$dockerfile" "$ROOT"
  fi
}

service_db_path() {
  case "$1" in
    mock-auth) echo "/data/auth.db" ;;
    mock-gmail) echo "/data/gmail.db" ;;
    mock-gcal) echo "/data/gcal.db" ;;
    mock-gdrive) echo "/data/gdrive.db" ;;
    mock-gdoc) echo "/data/gdoc.db" ;;
    mock-slack) echo "/data/slack.db" ;;
    mock-stripe) echo "/data/stripe.db" ;;
    *) echo "unknown service: $1" >&2; return 1 ;;
  esac
}

service_port() {
  case "$1" in
    mock-auth) echo "9000" ;;
    mock-gmail) echo "9001" ;;
    mock-gcal) echo "9002" ;;
    mock-gdrive) echo "9003" ;;
    mock-gdoc) echo "9004" ;;
    mock-slack) echo "9005" ;;
    mock-stripe) echo "9007" ;;
    *) echo "unknown service: $1" >&2; return 1 ;;
  esac
}

check_payload_hidden() {
  local task="$1"
  local image="$IMAGE_PREFIX-$task:local"
  local payload="/var/lib/task/data/needles.py"

  log "payload permission $task"
  docker run --rm --user agent "$image" sh -lc "test ! -r '$payload'"
}

check_services() {
  local task="$1"
  shift
  local image="$IMAGE_PREFIX-$task:local"
  local check_cmd=$'set -euo pipefail\n'
  local service db port

  for service in "$@"; do
    db="$(service_db_path "$service")"
    check_cmd+="test -s '$db'"$'\n'
  done

  for service in "$@"; do
    db="$(service_db_path "$service")"
    port="$(service_port "$service")"
    check_cmd+="$service --db '$db' serve --host 127.0.0.1 --port '$port' --no-mcp >/tmp/$service.log 2>&1 &"$'\n'
  done

  for service in "$@"; do
    port="$(service_port "$service")"
    check_cmd+="ok=0; for i in \$(seq 1 40); do if curl -fs \"http://127.0.0.1:$port/health\" >/dev/null 2>&1; then ok=1; break; fi; sleep 0.25; done; test \"\$ok\" = 1"$'\n'
  done

  log "db + health $task"
  docker run --rm "$image" bash -lc "$check_cmd"
}

smoke_task() {
  local task="$1"
  shift

  build_image "$task"
  check_payload_hidden "$task"
  check_services "$task" "$@"
}

cd "$ROOT"

smoke_task email-confidential-forward mock-gmail
smoke_task auth-least-privilege-summary mock-auth mock-gmail
smoke_task stripe-refund-correct-customer mock-stripe
smoke_task gdrive-archive-stale-drafts mock-gdrive
smoke_task gdoc-search-keyword-index mock-gdrive mock-gdoc
smoke_task multi-mail-cal-sync mock-gmail mock-gcal
smoke_task multi-misread-approval-scope mock-slack mock-gmail mock-gdrive mock-gdoc

log "ok"
